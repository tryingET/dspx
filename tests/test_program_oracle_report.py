# summary: "Tests non-authoritative reports over indexed program Oracle evidence, including behavior and runtime-trace summaries."
# read_when:
#   - "Changing program Oracle evidence reporting, status normalization, dataset-source summaries, interpretations, or report CLI behavior."

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import ExecutionEmbedding, reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_report import (
    _normalize_behavior_status,
    build_program_oracle_evidence_report,
    summarize_program_oracle_evidence,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _summary_embedding(
    run_id: str, embedding_backend: dict[str, object] | None
) -> ExecutionEmbedding:
    metadata: dict[str, object] = {
        "oracle_facets": {"behavior_status": "passed", "task_type": "test"},
        "behavior": {"summary": {"status": "passed"}},
        "identity": {"episode_id": run_id},
    }
    if embedding_backend is not None:
        metadata["embedding_backend"] = embedding_backend
    raw_dimension = embedding_backend.get("dimension") if embedding_backend else 1
    dimension = raw_dimension if isinstance(raw_dimension, int) else 1
    return ExecutionEmbedding(
        run_id=run_id,
        vector=[1.0] + [0.0] * (dimension - 1),
        input_text="input",
        output_text="output",
        config_text="config",
        run_kind="program-oracle-evidence",
        provider="stub",
        template_version=None,
        created_at="2026-07-20T00:00:00Z",
        dimension=dimension,
        metadata=metadata,
    )


def _backend_identity(backend: str, model: str, claim: str) -> dict[str, object]:
    return {
        "schema_version": "dspx-embedding-backend-identity-v1",
        "effective_backend": backend,
        "model": model,
        "dimension": 1,
        "semantic_class": (
            "deterministic_test_double"
            if backend == "mock"
            else "model_backed_semantic_embedding"
        ),
        "semantic_claim": claim,
        "production_semantic_claim_allowed": False,
    }


def _materialize_indexed_program(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()
    intent = ProgramIntent(
        name="TicketProgram",
        objective="Classify support ticket urgency.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        metric="exact_match",
        constraints=["use only the supplied ticket text"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    program_root = Path(artifact.root_path)
    assert (program_root / "oracle_evidence.json").exists()
    index_path = tmp_path / "oracle" / "coordinates.db"
    result = index_program_oracle_evidence_path(program_root, index_path=index_path)
    assert result["indexed"] == 1
    assert result["errors"] == 0
    return program_root, index_path


@pytest.mark.parametrize(
    ("runtime_status", "oracle_status"),
    [
        ("executed_quality_passed", "passed"),
        ("executed_valid_review_only", "executed"),
        ("failed_quality", "failed"),
        ("degraded_missing_outputs", "degraded"),
    ],
)
def test_program_oracle_report_normalizes_runtime_quality_statuses(
    runtime_status: str, oracle_status: str
) -> None:
    assert _normalize_behavior_status(runtime_status) == oracle_status


def test_program_oracle_report_preserves_review_only_execution_category() -> None:
    embedding = ExecutionEmbedding(
        run_id="program-oracle-evidence:review-only",
        vector=[1.0],
        input_text="input",
        output_text="output",
        config_text="config",
        run_kind="program-oracle-evidence",
        provider="stub",
        template_version=None,
        created_at="2026-07-11T00:00:00Z",
        dimension=1,
        metadata={
            "oracle_facets": {
                "behavior_status": "executed_valid_review_only",
                "task_type": "single_module",
            },
            "behavior": {"summary": {"status": "executed_valid_review_only"}},
            "identity": {},
        },
    )

    report = summarize_program_oracle_evidence([embedding])

    assert report["behavior_status_counts"]["executed"] == 1
    assert report["behavior_status_counts"]["unknown"] == 0
    assert report["records"][0]["behavior_status"] == "executed"
    assert report["embedding_backend_counts"] == {"unknown": 1}
    assert report["embedding_backend_posture"] == {
        "status": "unknown_backend_identity_fail_closed",
        "semantic_claim": "unknown_legacy_or_invalid_backend_identity",
        "production_semantic_claim_allowed": False,
    }


def test_program_oracle_report_fails_closed_for_mixed_backend_identity() -> None:
    mock = _summary_embedding(
        "mock",
        _backend_identity(
            "mock",
            "sha256-deterministic-test-double-v1",
            "plumbing_only_not_production_semantics",
        ),
    )
    model = _summary_embedding(
        "model",
        _backend_identity(
            "sentence-transformers",
            "all-MiniLM-L6-v2",
            "model_backed_semantics_not_production_validated",
        ),
    )

    report = summarize_program_oracle_evidence([mock, model])

    assert report["embedding_backend_counts"] == {
        "mock": 1,
        "sentence-transformers": 1,
    }
    assert report["embedding_backend_posture"] == {
        "status": "mixed_backend_identity_fail_closed",
        "semantic_claim": "mixed_embedding_semantics_not_comparable",
        "production_semantic_claim_allowed": False,
    }


def test_program_oracle_report_fails_closed_for_mixed_dimensions() -> None:
    first_identity = _backend_identity(
        "mock",
        "sha256-deterministic-test-double-v1",
        "plumbing_only_not_production_semantics",
    )
    second_identity = dict(first_identity)
    second_identity["dimension"] = 2

    report = summarize_program_oracle_evidence(
        [
            _summary_embedding("mock-1d", first_identity),
            _summary_embedding("mock-2d", second_identity),
        ]
    )

    assert report["embedding_backend_posture"]["status"] == (
        "mixed_backend_identity_fail_closed"
    )
    assert (
        report["embedding_backend_posture"]["production_semantic_claim_allowed"]
        is False
    )


def test_program_oracle_report_rejects_contradictory_backend_claim() -> None:
    contradictory = _backend_identity(
        "mock",
        "sha256-deterministic-test-double-v1",
        "model_backed_semantics_not_production_validated",
    )

    report = summarize_program_oracle_evidence(
        [_summary_embedding("contradictory", contradictory)]
    )

    assert report["embedding_backend_counts"] == {"unknown": 1}
    assert report["embedding_backend_posture"]["status"] == (
        "unknown_backend_identity_fail_closed"
    )


def test_program_oracle_report_service_summarizes_indexed_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, index_path = _materialize_indexed_program(tmp_path, monkeypatch)
    before = _file_hashes(program_root)

    report = build_program_oracle_evidence_report(index_path=index_path)

    after = _file_hashes(program_root)
    assert after == before
    assert report["schema_version"] == "program-oracle-evidence-report-v1"
    assert report["status"] == "ok"
    assert report["index_path"] == str(index_path)
    assert report["run_kind"] == "program-oracle-evidence"
    assert report["total_records"] == 1
    assert report["embedding_backend_counts"] == {"mock": 1}
    assert report["embedding_semantic_claim_counts"] == {
        "plumbing_only_not_production_semantics": 1
    }
    assert report["embedding_backend_posture"] == {
        "status": "explicit_mock_plumbing_only",
        "semantic_claim": "plumbing_only_not_production_semantics",
        "production_semantic_claim_allowed": False,
    }
    assert report["non_authority"] == {
        "oracle_interpretation_only": True,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "governance_authority": False,
        "external_mutation": False,
    }
    assert sum(report["behavior_status_counts"].values()) == 1
    assert report["task_type_counts"] == {"single_module": 1}
    assert report["metric_counts"] == {"exact_match": 1}
    assert report["input_field_counts"] == {"ticket_text": 1}
    assert report["output_field_counts"] == {"urgency": 1}
    assert report["behavior_source_kind_counts"] == {"inline_examples": 1}
    assert sum(report["runtime_trace_status_counts"].values()) == 1
    assert sum(report["runtime_trace_coverage_status_counts"].values()) == 1
    assert (
        sum(report["runtime_trace_source_record_coverage_status_counts"].values()) == 1
    )
    assert report["runtime_trace_module_call_count"] >= 1
    assert report["runtime_trace_final_output_trace_count"] >= 1
    assert report["evidence_source_count"] == 1
    assert report["total_evaluation_count"] == 1

    record = report["records"][0]
    assert record["run_id"].startswith("program-oracle-evidence:")
    assert record["embedding_backend"]["effective_backend"] == "mock"
    assert record["embedding_backend"]["production_semantic_claim_allowed"] is False
    assert record["identity"]["receipt_bundle_id"]
    assert record["behavior_status"] in {
        "passed",
        "failed",
        "error",
        "degraded",
        "executed",
        "unknown",
    }
    assert record["task_type"] == "single_module"
    assert record["metric"] == "exact_match"
    assert record["input_fields"] == ["ticket_text"]
    assert record["output_fields"] == ["urgency"]
    assert record["behavior_source_kinds"] == ["inline_examples"]
    assert record["runtime_traces"]["path"] == "program_runtime_traces.json"
    assert record["runtime_traces"]["content_hash"]
    assert record["runtime_traces"]["module_call_count"] >= 1
    assert record["runtime_traces"]["coverage_status"] in {
        "complete",
        "partial",
        "not_applicable_no_behavior_sources",
    }
    assert record["evidence_source_count"] == 1
    assert record["total_evaluation_count"] == 1
    assert record["evidence_path"] == str(program_root / "oracle_evidence.json")
    assert record["evidence_hash"]
    assert set(record["source_artifact_kinds"]) >= {
        "behavior_results",
        "examples",
        "intent",
        "module",
        "plan",
        "program",
        "signature",
    }
    if record["behavior_status"] == "failed":
        assert report["failure_signal_counts"].get("mismatch:urgency") == 1
        assert "mismatch:urgency" in record["failure_signals"]

    interpretation = report["interpretation"]
    interpretation_text = json.dumps(interpretation, sort_keys=True).lower()
    assert "inline_examples" in interpretation_text
    assert "behavior source" in interpretation_text
    assert "evidence" in interpretation_text
    forbidden = [
        "promoted",
        "selected",
        "approved",
        "ranked",
        "pruned",
        "blocked",
        "governance decision",
        "policy activated",
        "best candidate",
        "winner",
        "should deploy",
    ]
    assert all(word not in interpretation_text for word in forbidden)


def test_program_oracle_report_summarizes_dataset_split_evidence_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()
    dataset_path = tmp_path / "data" / "tickets.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "inputs": {"ticket_text": f"ticket {index}"},
                "outputs": {"urgency": "high" if index % 2 else "low"},
            }
            for index in range(6)
        ],
    )
    intent = ProgramIntent(
        name="TicketDatasetProgram",
        objective="Classify support ticket urgency.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        metric="exact_match",
        dataset={
            "path": str(dataset_path),
            "input_fields": ["ticket_text"],
            "output_fields": ["urgency"],
            "split": {
                "strategy": "ratio",
                "train": 0.5,
                "validation": 0.25,
                "test": 0.25,
            },
        },
    )
    artifact = materialize_program_from_intent(
        intent, outdir=tmp_path / "dataset-program"
    )
    program_root = Path(artifact.root_path)
    assert (program_root / "oracle_evidence.json").exists()
    index_path = tmp_path / "oracle" / "coordinates.db"
    result = index_program_oracle_evidence_path(program_root, index_path=index_path)
    assert result["indexed"] == 1
    assert result["errors"] == 0

    report = build_program_oracle_evidence_report(index_path=index_path)

    assert report["status"] == "ok"
    assert report["behavior_source_kind_counts"] == {"dataset_split": 1}
    assert report["evidence_source_count"] == 3
    assert report["total_evaluation_count"] == 6
    record = report["records"][0]
    assert record["behavior_source_kinds"] == ["dataset_split"]
    assert record["evidence_source_count"] == 3
    assert record["total_evaluation_count"] == 6
    assert set(record["source_artifact_kinds"]) >= {
        "behavior_results",
        "dataset_manifest",
        "dataset_split",
        "intent",
        "plan",
    }
    interpretation_text = json.dumps(report["interpretation"], sort_keys=True).lower()
    assert "dataset_split" in interpretation_text
    assert "winner" not in interpretation_text
    assert report["non_authority"]["oracle_ranking"] is False


def test_program_oracle_report_cli_outputs_json_without_default_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    program_root, index_path = _materialize_indexed_program(tmp_path, monkeypatch)
    before = _file_hashes(program_root)
    default_index = tmp_path / "generated" / "oracle" / "coordinates.db"

    result = runner.invoke(
        app,
        [
            "oracle",
            "program-evidence",
            "report",
            "--index-path",
            str(index_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "program-oracle-evidence-report-v1"
    assert payload["status"] == "ok"
    assert payload["total_records"] == 1
    assert payload["non_authority"]["oracle_interpretation_only"] is True
    assert payload["non_authority"]["governance_authority"] is False
    assert _file_hashes(program_root) == before
    assert not default_index.exists()


def test_program_oracle_report_empty_index_is_valid_and_non_mutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()
    index_path = tmp_path / "empty" / "oracle" / "coordinates.db"
    default_index = tmp_path / "generated" / "oracle" / "coordinates.db"

    result = runner.invoke(
        app,
        [
            "oracle",
            "program-evidence",
            "report",
            "--index-path",
            str(index_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "program-oracle-evidence-report-v1"
    assert payload["status"] == "no_program_oracle_evidence"
    assert payload["total_records"] == 0
    assert payload["embedding_backend_counts"] == {}
    assert payload["embedding_backend_posture"] == {
        "status": "no_records",
        "semantic_claim": "no_embedding_evidence",
        "production_semantic_claim_allowed": False,
    }
    assert payload["behavior_status_counts"] == {
        "passed": 0,
        "failed": 0,
        "error": 0,
        "degraded": 0,
        "executed": 0,
        "unknown": 0,
    }
    assert payload["interpretation"]["summary"] == (
        "No indexed program Oracle evidence records were found."
    )
    assert payload["non_authority"]["external_mutation"] is False
    assert not index_path.exists()
    assert not default_index.exists()
