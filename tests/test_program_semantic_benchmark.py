from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import ValidationError

import dspx.services.program_semantic_benchmark as benchmark
from dspx.services.program_semantic_benchmark import (
    load_program_semantic_corpus,
    run_program_semantic_benchmark,
    write_program_semantic_result,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = REPO_ROOT / "benchmarks/semantic/program-corpus-v1.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/semantic/program-result-schema-v1.json"


def _single_case_corpus() -> dict[str, Any]:
    corpus = load_program_semantic_corpus(CORPUS_PATH)
    corpus["cases"] = [corpus["cases"][0]]
    return corpus


def test_program_semantic_benchmark_runs_generated_single_and_pipeline_candidates(
    tmp_path: Path,
) -> None:
    corpus = load_program_semantic_corpus(CORPUS_PATH)
    result_path = tmp_path / "result.json"

    result = run_program_semantic_benchmark(
        corpus,
        corpus_path=CORPUS_PATH,
        work_root=tmp_path / "work",
        result_path=result_path,
    )
    write_program_semantic_result(result, result_path, result_schema_path=SCHEMA_PATH)

    assert result["summary"] == {
        "cases_total": 2,
        "cases_passed": 2,
        "cases_failed": 0,
        "overall_score": 1.0,
        "threshold_pass": True,
    }
    assert result["execution"] == {
        "mode": "offline",
        "provider": None,
        "network_allowed": False,
        "deterministic": True,
        "generated_program_path": True,
        "oracle_indexed": False,
    }
    assert result["authority"] == {
        "evidence_only": True,
        "authoritative_decision": False,
        "promotion_approved": False,
        "activation_applied": False,
        "shared_oracle_mutated": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
        "ak_called": False,
        "winner_selected": False,
    }
    assert [row["status"] for row in result["cases"]] == ["passed", "passed"]
    assert all(row["artifacts"]["manifest_sha256"] for row in result["cases"])
    assert all(row["candidate"]["candidate_id"] for row in result["cases"])
    assert result_path.is_file()
    assert json.loads(result_path.read_text(encoding="utf-8")) == result
    assert (
        tmp_path / "work/single-module-authority-boundary/program_loop.json"
    ).is_file()
    pipeline_manifest = json.loads(
        (tmp_path / "work/pipeline-evidence-calibration/manifest.json").read_text()
    )
    assert pipeline_manifest["intent"]["topology"]["kind"] == "pipeline"
    behavior = json.loads(
        (
            tmp_path / "work/pipeline-evidence-calibration/behavior_results.json"
        ).read_text()
    )
    assert (
        behavior["examples"][0]["runtime_trace"]["module_calls"][1]["module_id"]
        == "draft_calibrated_response"
    )


def test_program_semantic_benchmark_rejects_stale_behavior_before_scoring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = benchmark.run_program_loop_from_intent_path

    def tamper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        workflow = original(*args, **kwargs)
        result_path = Path(workflow["candidate"]["root_path"]) / "behavior_results.json"
        result_path.write_text(result_path.read_text() + " ", encoding="utf-8")
        return workflow

    monkeypatch.setattr(benchmark, "run_program_loop_from_intent_path", tamper)
    result = run_program_semantic_benchmark(
        _single_case_corpus(),
        corpus_path=CORPUS_PATH,
        work_root=tmp_path / "work",
        result_path=tmp_path / "result.json",
    )

    row = result["cases"][0]
    assert row["status"] == "error"
    assert row["score"] == 0.0
    assert (
        "replay integrity" in row["error"]
        or "behavior results hash is stale" in row["error"]
    )
    assert result["summary"]["threshold_pass"] is False


def test_program_semantic_benchmark_redacts_runtime_errors_and_restores_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "operator-provider")
    monkeypatch.setenv("DSPX_STUB_RESPONSE_JSON", '{"operator":"value"}')

    def fail(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("api_key=super-secret bearer abc.def.ghi")

    monkeypatch.setattr(benchmark, "run_program_loop_from_intent_path", fail)
    result = run_program_semantic_benchmark(
        _single_case_corpus(),
        corpus_path=CORPUS_PATH,
        work_root=tmp_path / "work",
        result_path=tmp_path / "result.json",
    )

    assert "super-secret" not in result["cases"][0]["error"]
    assert "abc.def.ghi" not in result["cases"][0]["error"]
    assert result["cases"][0]["status"] == "error"
    assert benchmark.os.environ["DSPX_PROVIDER"] == "operator-provider"
    assert benchmark.os.environ["DSPX_STUB_RESPONSE_JSON"] == '{"operator":"value"}'


def test_program_semantic_corpus_rejects_unknown_fields_and_oversize(
    tmp_path: Path,
) -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    corpus["unexpected"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown fields"):
        load_program_semantic_corpus(invalid)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * 1_000_001)
    with pytest.raises(ValueError, match="1000000-byte limit"):
        load_program_semantic_corpus(oversized)


def test_program_semantic_corpus_rejects_symlink_and_external_intent_paths(
    tmp_path: Path,
) -> None:
    link = tmp_path / "corpus.json"
    link.symlink_to(CORPUS_PATH)
    with pytest.raises(ValueError, match="symlink component"):
        load_program_semantic_corpus(link)

    real_parent = tmp_path / "real-corpus-parent"
    real_parent.mkdir()
    (real_parent / "corpus.json").write_bytes(CORPUS_PATH.read_bytes())
    parent_link = tmp_path / "corpus-parent-link"
    parent_link.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink component"):
        load_program_semantic_corpus(parent_link / "corpus.json")

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    corpus["cases"][0]["intent"]["examples_path"] = "../../operator-secrets.json"
    external = tmp_path / "external.json"
    external.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported fields: examples_path"):
        load_program_semantic_corpus(external)

    del corpus["cases"][0]["intent"]["examples_path"]
    corpus["cases"][0]["intent"]["datasets"] = {"test": "/etc/passwd"}
    external.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported fields: datasets"):
        load_program_semantic_corpus(external)


def test_program_semantic_evidence_files_reject_escape_symlink_and_oversize(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate"
    root.mkdir()
    outside = tmp_path / "behavior_episode.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes candidate root"):
        benchmark._confined_file(
            root,
            str(outside),
            expected_name="behavior_episode.json",
            label="behavior episode",
        )

    target = root / "real.json"
    target.write_text("{}", encoding="utf-8")
    link = root / "behavior_episode.json"
    link.symlink_to(target.name)
    with pytest.raises(ValueError, match="not the expected current"):
        benchmark._confined_file(
            root,
            str(link),
            expected_name="behavior_episode.json",
            label="behavior episode",
        )

    huge = root / "huge.json"
    huge.write_bytes(b" " * (benchmark._MAX_ARTIFACT_BYTES + 1))
    with pytest.raises(ValueError, match="byte limit"):
        benchmark._read_json_object(huge, label="behavior results")


def test_program_semantic_benchmark_preflights_output_overlap_symlinks_and_existing_root(
    tmp_path: Path,
) -> None:
    corpus = _single_case_corpus()
    work = tmp_path / "work"
    with pytest.raises(ValueError, match="paths must be disjoint"):
        run_program_semantic_benchmark(
            corpus,
            corpus_path=CORPUS_PATH,
            work_root=work,
            result_path=work / "result.json",
        )
    victim = tmp_path / "victim.json"
    victim.write_text("unchanged", encoding="utf-8")
    result_link = tmp_path / "result-link.json"
    result_link.symlink_to(victim)
    with pytest.raises(ValueError, match="symlink component"):
        benchmark._preflight_paths(
            corpus_path=CORPUS_PATH,
            work_root=tmp_path / "fresh-work",
            result_path=result_link,
        )
    assert victim.read_text(encoding="utf-8") == "unchanged"

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    parent_link = tmp_path / "parent-link"
    parent_link.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink component"):
        benchmark._preflight_paths(
            corpus_path=CORPUS_PATH,
            work_root=tmp_path / "other-work",
            result_path=parent_link / "result.json",
        )

    work.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        run_program_semantic_benchmark(
            corpus,
            corpus_path=CORPUS_PATH,
            work_root=work,
            result_path=tmp_path / "result.json",
        )


def test_program_semantic_runner_revalidates_mutated_corpus_before_writes(
    tmp_path: Path,
) -> None:
    escaped = _single_case_corpus()
    escaped["cases"][0]["id"] = "../../victim"
    with pytest.raises(ValueError, match="invalid id"):
        run_program_semantic_benchmark(
            escaped,
            corpus_path=CORPUS_PATH,
            work_root=tmp_path / "work",
            result_path=tmp_path / "result.json",
        )
    assert not (tmp_path / "work").exists()
    assert not (tmp_path.parent / "victim.intent.json").exists()

    external = _single_case_corpus()
    external["cases"][0]["intent"]["examples_path"] = "/etc/passwd"
    with pytest.raises(ValueError, match="unsupported fields: examples_path"):
        run_program_semantic_benchmark(
            external,
            corpus_path=CORPUS_PATH,
            work_root=tmp_path / "other-work",
            result_path=tmp_path / "other-result.json",
        )
    assert not (tmp_path / "other-work").exists()


def test_program_semantic_benchmark_mode_contract_fails_closed(tmp_path: Path) -> None:
    corpus = _single_case_corpus()
    with pytest.raises(ValueError, match="offline mode rejects"):
        run_program_semantic_benchmark(
            corpus,
            corpus_path=CORPUS_PATH,
            work_root=tmp_path / "offline",
            result_path=tmp_path / "offline.json",
            provider="stub",
        )
    with pytest.raises(ValueError, match="live mode requires"):
        run_program_semantic_benchmark(
            corpus,
            corpus_path=CORPUS_PATH,
            work_root=tmp_path / "live",
            result_path=tmp_path / "live.json",
            mode="live",
        )


def test_program_semantic_result_schema_rejects_authority_widening(
    tmp_path: Path,
) -> None:
    result = {
        "schema_version": benchmark.RESULT_SCHEMA,
        "corpus": {
            "schema_version": benchmark.CORPUS_SCHEMA,
            "name": "x",
            "version": 1,
            "sha256": "a" * 64,
        },
        "execution": {
            "mode": "offline",
            "provider": None,
            "network_allowed": False,
            "deterministic": True,
            "generated_program_path": True,
            "oracle_indexed": False,
        },
        "thresholds": {
            "min_overall_score": 1.0,
            "min_case_score": 1.0,
            "max_failed_cases": 0,
        },
        "summary": {
            "cases_total": 1,
            "cases_passed": 0,
            "cases_failed": 1,
            "overall_score": 0.0,
            "threshold_pass": False,
        },
        "cases": [
            {
                "id": "x",
                "category": "x",
                "status": "error",
                "score": 0.0,
                "required_groups_total": 1,
                "required_groups_matched": 0,
                "missing_group_indexes": [0],
                "forbidden_hits": [],
                "response_sha256": "a" * 64,
                "error": "failed",
                "candidate": None,
                "artifacts": None,
            }
        ],
        "authority": {
            "evidence_only": True,
            "authoritative_decision": False,
            "promotion_approved": True,
            "activation_applied": False,
            "shared_oracle_mutated": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "ak_called": False,
            "winner_selected": False,
        },
    }
    with pytest.raises(ValidationError):
        write_program_semantic_result(
            result, tmp_path / "result.json", result_schema_path=SCHEMA_PATH
        )
    assert not (tmp_path / "result.json").exists()

    result["authority"]["promotion_approved"] = False
    victim = tmp_path / "victim.json"
    victim.write_text("unchanged", encoding="utf-8")
    output_link = tmp_path / "output.json"
    output_link.symlink_to(victim)
    with pytest.raises(ValueError, match="symlink component"):
        write_program_semantic_result(
            result, output_link, result_schema_path=SCHEMA_PATH
        )
    assert victim.read_text(encoding="utf-8") == "unchanged"

    schema_link = tmp_path / "schema.json"
    schema_link.symlink_to(SCHEMA_PATH)
    with pytest.raises(ValueError, match="symlink component"):
        write_program_semantic_result(
            result, tmp_path / "safe-result.json", result_schema_path=schema_link
        )

    huge_schema = tmp_path / "huge-schema.json"
    huge_schema.write_bytes(b" " * (benchmark._MAX_ARTIFACT_BYTES + 1))
    with pytest.raises(ValueError, match="byte limit"):
        write_program_semantic_result(
            result, tmp_path / "safe-result.json", result_schema_path=huge_schema
        )
    assert not (tmp_path / "safe-result.json").exists()
