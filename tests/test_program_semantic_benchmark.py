# summary: "Tests offline semantic benchmarks for generated candidates and review replay evidence."
# read_when:
#   - "Changing semantic benchmark corpora, execution, scoring, schemas, or artifact safety."

from __future__ import annotations

import json
import stat
import subprocess
import sys
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
CORPUS_PATH = REPO_ROOT / "benchmarks/semantic/program-corpus-v2.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/semantic/program-result-schema-v2.json"
V1_CORPUS_PATH = REPO_ROOT / "benchmarks/semantic/program-corpus-v1.json"
V1_SCHEMA_PATH = REPO_ROOT / "benchmarks/semantic/program-result-schema-v1.json"


def _single_case_corpus() -> dict[str, Any]:
    corpus = load_program_semantic_corpus(CORPUS_PATH)
    corpus["cases"] = [corpus["cases"][0]]
    return corpus


def _review_case_corpus() -> dict[str, Any]:
    corpus = load_program_semantic_corpus(CORPUS_PATH)
    corpus["cases"] = [corpus["cases"][-1]]
    return corpus


def test_program_semantic_benchmark_runs_generated_candidates_and_review_replay(
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
        "cases_total": 3,
        "cases_passed": 3,
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
    assert [row["status"] for row in result["cases"]] == [
        "passed",
        "passed",
        "passed",
    ]
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
    assert behavior["quality_evaluation"]["status"] == "passed"
    assert behavior["quality_evaluation"]["quality_approved"] is False
    episode = json.loads(
        (
            tmp_path / "work/pipeline-evidence-calibration/behavior_episode.json"
        ).read_text()
    )
    assert episode["sources"][0]["quality_evaluation"] == behavior["quality_evaluation"]
    assert episode["quality_evaluation"] == behavior["quality_evaluation"]
    review_row = result["cases"][2]
    assert review_row["runtime_replay_status"] == "passed"
    assert review_row["runtime_replay"]["contract_mode"] == "pdf_transition_review"
    assert (
        review_row["runtime_replay"]["execution_status"] == "executed_valid_review_only"
    )
    assert review_row["runtime_replay"]["quality_status"] == "passed"
    assert review_row["runtime_replay"]["replay_status"] == "execution_reproduced"
    runtime_root = tmp_path / "work/pdf-transition-review-runtime-replay.runtime"
    assert (runtime_root / "benchmark-replay-evidence.json").is_file()
    assert stat.S_IMODE((runtime_root / "runtime_inputs.json").stat().st_mode) == 0o600
    assert (
        stat.S_IMODE(
            (tmp_path / "work/pdf-transition-review-runtime-replay.runtime-inputs.json")
            .stat()
            .st_mode
        )
        == 0o600
    )


def test_program_semantic_benchmark_review_case_rejects_boundary_failure(
    tmp_path: Path,
) -> None:
    corpus = _review_case_corpus()
    case = corpus["cases"][0]
    unsafe = json.loads(case["offline_stub_response"]["review_packet_json"])
    unsafe["canonical_mutation_performed"] = True
    unsafe_text = json.dumps(unsafe, separators=(",", ":"), sort_keys=True)
    case["offline_stub_response"]["review_packet_json"] = unsafe_text
    case["intent"]["examples"][0]["outputs"]["review_packet_json"] = unsafe_text

    result = run_program_semantic_benchmark(
        corpus,
        corpus_path=CORPUS_PATH,
        work_root=tmp_path / "work",
        result_path=tmp_path / "result.json",
    )

    row = result["cases"][0]
    assert row["status"] == "error"
    assert "runtime status is 'degraded'" in row["error"]
    assert row["runtime_replay"] is None
    assert row["runtime_replay_status"] == "failed"
    assert result["summary"]["threshold_pass"] is False


def test_program_semantic_benchmark_rejects_tampered_replay_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = benchmark.execute_run_receipt

    def tamper(receipt: Path, output: Path) -> dict[str, Any]:
        report = original(receipt, output)
        replay_path = receipt.parent / output
        payload = json.loads(replay_path.read_text(encoding="utf-8"))
        payload["contract_mode"] = "none"
        replay_path.write_text(json.dumps(payload), encoding="utf-8")
        return report

    monkeypatch.setattr(benchmark, "execute_run_receipt", tamper)
    result = run_program_semantic_benchmark(
        _review_case_corpus(),
        corpus_path=CORPUS_PATH,
        work_root=tmp_path / "work",
        result_path=tmp_path / "result.json",
    )

    row = result["cases"][0]
    assert row["status"] == "error"
    assert "replay evidence" in row["error"]
    assert row["runtime_replay"] is None
    assert row["runtime_replay_status"] == "failed"


def test_program_semantic_benchmark_rejects_candidate_mutation_during_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = benchmark.run_program_runtime_episode

    def mutate(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original(*args, **kwargs)
        manifest = Path(kwargs["manifest_path"])
        manifest.write_text(manifest.read_text() + " ", encoding="utf-8")
        return result

    monkeypatch.setattr(benchmark, "run_program_runtime_episode", mutate)
    result = run_program_semantic_benchmark(
        _review_case_corpus(),
        corpus_path=CORPUS_PATH,
        work_root=tmp_path / "work",
        result_path=tmp_path / "result.json",
    )
    assert result["cases"][0]["status"] == "error"
    assert any(
        marker in result["cases"][0]["error"]
        for marker in ("candidate evidence changed", "execution replay failed")
    )


def test_program_semantic_benchmark_v1_cli_derives_result_schema(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_program_semantic_benchmarks.py",
            "--corpus",
            str(V1_CORPUS_PATH),
            "--work-root",
            str(tmp_path / "v1-work"),
            "--out",
            str(tmp_path / "v1-result.json"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads((tmp_path / "v1-result.json").read_text())
    assert result["schema_version"] == benchmark.RESULT_SCHEMA_V1


def test_program_semantic_benchmark_v1_preserves_legacy_no_quality_intent(
    tmp_path: Path,
) -> None:
    corpus = load_program_semantic_corpus(V1_CORPUS_PATH)
    corpus["cases"] = [corpus["cases"][0]]
    corpus["cases"][0]["intent"].pop("quality_criteria")

    result = run_program_semantic_benchmark(
        corpus,
        corpus_path=V1_CORPUS_PATH,
        work_root=tmp_path / "work",
        result_path=tmp_path / "result.json",
    )

    assert result["schema_version"] == benchmark.RESULT_SCHEMA_V1
    assert result["summary"]["threshold_pass"] is True
    write_program_semantic_result(
        result, tmp_path / "v1-result.json", result_schema_path=V1_SCHEMA_PATH
    )
    behavior = json.loads(
        (
            tmp_path / "work/single-module-authority-boundary/behavior_results.json"
        ).read_text()
    )
    assert behavior["quality_evaluation"]["status"] == "not_declared"


def test_legacy_benchmark_forbidden_hit_fails_at_zero_threshold(
    tmp_path: Path,
) -> None:
    corpus = _single_case_corpus()
    case = corpus["cases"][0]
    case["intent"].pop("quality_criteria")
    forbidden_response = "This benchmark automatically activates the program."
    case["intent"]["examples"][0]["outputs"]["answer"] = forbidden_response
    case["offline_stub_response"]["answer"] = forbidden_response
    corpus["thresholds"]["min_overall_score"] = 0.0
    corpus["thresholds"]["min_case_score"] = 0.0
    corpus["thresholds"]["max_failed_cases"] = 0

    result = run_program_semantic_benchmark(
        corpus,
        corpus_path=CORPUS_PATH,
        work_root=tmp_path / "work",
        result_path=tmp_path / "result.json",
    )

    assert result["cases"][0]["forbidden_hits"] == ["automatically activates"]
    assert result["cases"][0]["status"] == "failed"
    assert result["summary"]["threshold_pass"] is False


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
    monkeypatch.setenv("DSPX_REPLAY_FIXTURE_JSON", '{"operator":"value"}')

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
    assert benchmark.os.environ["DSPX_REPLAY_FIXTURE_JSON"] == '{"operator":"value"}'


def test_program_semantic_corpus_rejects_unknown_fields_and_oversize(
    tmp_path: Path,
) -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    corpus["unexpected"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown fields"):
        load_program_semantic_corpus(invalid)

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    corpus["cases"][0]["intent"]["quality_criteria"][0]["forbidden_concepts"] = []
    invalid.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="outer semantic contract drifts"):
        load_program_semantic_corpus(invalid)

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    corpus["cases"][0]["intent"]["quality_criteria"][0]["min_score"] = 0.5
    invalid.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="outer semantic contract drifts"):
        load_program_semantic_corpus(invalid)

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    case = corpus["cases"][0]
    case["intent"]["outputs"].append("other")
    case["intent"]["quality_criteria"][0]["output_field"] = "other"
    invalid.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="outer semantic contract drifts"):
        load_program_semantic_corpus(invalid)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * 1_000_001)
    with pytest.raises(ValueError, match="1000000-byte limit"):
        load_program_semantic_corpus(oversized)


def test_program_semantic_corpus_v2_rejects_runtime_contract_drift(
    tmp_path: Path,
) -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    review = corpus["cases"][-1]
    review["runtime_contract"]["contract_mode"] = "none"
    invalid = tmp_path / "invalid-runtime.json"
    invalid.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="runtime_contract is invalid"):
        load_program_semantic_corpus(invalid)

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    review = corpus["cases"][-1]
    review["intent"]["outputs"].remove("evidence_cards_json")
    invalid.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="outputs must match the PDF review contract"):
        load_program_semantic_corpus(invalid)

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    review = corpus["cases"][-1]
    del review["offline_stub_response"]["artifact_contract_manifest_json"]
    invalid.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="stub must contain every PDF review output"):
        load_program_semantic_corpus(invalid)


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


def test_program_semantic_private_json_writer_handles_short_and_zero_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_write = benchmark.os.write
    calls = 0

    def short_once(descriptor: int, content: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_write(descriptor, content[: max(1, len(content) // 2)])
        return original_write(descriptor, content)

    target = tmp_path / "short.json"
    monkeypatch.setattr(benchmark.os, "write", short_once)
    benchmark._write_private_json_exclusive(target, {"inputs": {"value": "x" * 100}})
    assert json.loads(target.read_text()) == {"inputs": {"value": "x" * 100}}

    blocked = tmp_path / "blocked.json"
    monkeypatch.setattr(benchmark.os, "write", lambda descriptor, content: 0)
    with pytest.raises(OSError, match="made no progress"):
        benchmark._write_private_json_exclusive(blocked, {"inputs": {"x": 1}})
    assert not blocked.exists()


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


def test_live_corpus_can_stop_after_first_caught_case_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    def fail_first(intent_path: Path, **_kwargs: Any) -> dict[str, Any]:
        calls.append(intent_path)
        raise RuntimeError("effect disposition unknown")

    monkeypatch.setattr(benchmark, "run_program_loop_from_intent_path", fail_first)
    result = run_program_semantic_benchmark(
        load_program_semantic_corpus(CORPUS_PATH),
        corpus_path=CORPUS_PATH,
        work_root=tmp_path / "live",
        result_path=tmp_path / "live.json",
        mode="live",
        provider="dspy-lm-auth",
        stop_after_case_error=True,
    )

    assert len(calls) == 1
    assert result["summary"]["cases_total"] == 1
    assert result["summary"]["cases_failed"] == 1
    assert result["summary"]["threshold_pass"] is False
    assert result["cases"][0]["error"] == "effect disposition unknown"


def test_program_semantic_result_schema_rejects_authority_widening(
    tmp_path: Path,
) -> None:
    result = {
        "schema_version": benchmark.RESULT_SCHEMA,
        "corpus": {
            "schema_version": benchmark.CORPUS_SCHEMA,
            "name": "x",
            "version": 2,
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
                "runtime_replay": None,
                "runtime_replay_status": "not_required",
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
