from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
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

    record = report["records"][0]
    assert record["run_id"].startswith("program-oracle-evidence:")
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
    assert "example-backed" in interpretation_text
    assert "eval_examples.py" in interpretation_text
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
