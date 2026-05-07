from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import (
    CoordinateIndex,
    CoordinateStore,
    ExecutionEmbedding,
    reset_embedding_engine,
)
from dspx.services.program_workflow import run_program_loop_from_intent_path

runner = CliRunner()


class FakeSharedOracleStore:
    backend_name = "fake_shared_oracle"
    redacted_database_url = (
        "postgresql://dspx_oracle:<redacted>@example.invalid/dspx_oracle"
    )

    def __init__(self) -> None:
        self.records: dict[str, ExecutionEmbedding] = {}

    def upsert(self, embedding: ExecutionEmbedding) -> bool:
        self.records[embedding.run_id] = embedding
        return True


def _write_intent(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: TicketProgram",
                "objective: Classify support ticket urgency.",
                "inputs:",
                "  - ticket_text",
                "outputs:",
                "  - urgency",
                "metric: exact_match",
                "constraints:",
                "  - use only the supplied ticket text",
                "examples:",
                "  - inputs:",
                "      ticket_text: Server is down for all users",
                "    outputs:",
                "      urgency: high",
            ]
        ),
        encoding="utf-8",
    )


def _loop_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def test_program_loop_cli_runs_one_intent_to_stateful_oracle_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "program-loop-workflow-v1"
    assert payload["status"] == "ok"
    assert payload["candidate"]["manifest_path"] == str(outdir / "manifest.json")
    assert payload["steps"]["program_gen"]["status"] == "ok"
    assert payload["steps"]["replay_check"]["status"] == "ok"
    assert payload["steps"]["oracle_index"]["status"] == "ok"
    assert payload["steps"]["oracle_index"]["result"]["indexed"] == 1
    assert payload["steps"]["oracle_report"]["status"] == "ok"
    assert payload["steps"]["candidate_state"]["status"]
    assert payload["effect"] == {
        "program_candidate_materialized": True,
        "replay_checked": True,
        "oracle_index_mutated": True,
        "oracle_index_scope": "candidate-local explicit path",
        "oracle_report_written": True,
        "candidate_state_written": True,
        "oracle_publication_preflight_written": False,
        "oracle_publication_receipt_written": False,
        "shared_oracle_mutated": False,
        "shared_oracle_publication_scope": "none",
        "workflow_summary_written": True,
        "ak_called": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
        "promotion_applied": False,
        "winner_selected": False,
    }
    assert payload["steps"]["oracle_publication"] == {
        "status": "skipped",
        "preflight_path": None,
        "receipt_path": None,
        "publication_id": None,
        "publication_label": None,
        "evidence_only": False,
        "scope": "none",
    }
    assert payload["non_authority"]["promotion_authority"] is False
    assert payload["non_authority"]["automatic_promotion"] is False

    index_path = outdir / "oracle" / "coordinates.db"
    report_path = outdir / "program_oracle_report.json"
    state_path = outdir / "program_candidate_state.json"
    workflow_path = outdir / "program_loop.json"
    assert index_path.exists()
    assert report_path.exists()
    assert state_path.exists()
    assert workflow_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "program-oracle-evidence-report-v1"
    assert report["total_records"] == 1
    assert report["non_authority"]["oracle_promotion"] is False

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["schema_version"] == "program-candidate-state-v1"
    assert state["truth_summary"]["program_materialized"] is True
    assert state["truth_summary"]["behavior_evidence_present"] is True
    assert state["truth_summary"]["oracle_report_present"] is True
    assert state["truth_summary"]["promotion_applied"] is False
    assert state["truth_summary"]["ak_called"] is False
    assert state["truth_summary"]["oracle_publication_ref_present"] is False

    index = CoordinateIndex(db_path=index_path)
    stats = index.stats()
    assert stats["total"] == 1
    assert stats["by_run_kind"]["program-oracle-evidence"] == 1


def test_program_loop_can_skip_oracle_index_and_still_write_candidate_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--skip-oracle-index",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "program-loop-workflow-v1"
    assert payload["status"] == "ok"
    assert payload["steps"]["oracle_index"]["status"] == "skipped"
    assert payload["steps"]["oracle_report"]["status"] == "skipped"
    assert payload["effect"]["oracle_index_mutated"] is False
    assert payload["effect"]["oracle_report_written"] is False
    assert (outdir / "program_candidate_state.json").exists()
    assert (outdir / "program_loop.json").exists()
    assert not (outdir / "program_oracle_report.json").exists()
    assert not (outdir / "oracle" / "coordinates.db").exists()

    state = json.loads((outdir / "program_candidate_state.json").read_text())
    assert state["truth_summary"]["program_materialized"] is True
    assert state["truth_summary"]["oracle_report_present"] is False
    assert state["truth_summary"]["ak_called"] is False


def test_program_loop_shared_publication_opt_in_writes_receipt_as_evidence_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)
    store = FakeSharedOracleStore()

    payload = run_program_loop_from_intent_path(
        intent_path,
        outdir=outdir,
        publish_to_shared="retained",
        publisher_id="pi-test",
        publisher_role="operator",
        publisher_assertion="share synthetic behavior evidence for future Oracle retrieval",
        redaction_status="checked",
        retention_class="retained_behavior_memory",
        shared_publication_store=cast(CoordinateStore, store),
    )

    assert payload["status"] == "ok"
    publication_step = payload["steps"]["oracle_publication"]
    assert publication_step["status"] == "published"
    assert publication_step["publication_id"].startswith("prog-oracle-pub-")
    assert publication_step["publication_label"] == "retained"
    assert publication_step["evidence_only"] is True
    assert publication_step["scope"] == "explicit_shared_publication_opt_in"
    assert payload["effect"]["oracle_publication_preflight_written"] is True
    assert payload["effect"]["oracle_publication_receipt_written"] is True
    assert payload["effect"]["shared_oracle_mutated"] is True
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["governance_mutated"] is False
    assert payload["effect"]["promotion_applied"] is False
    assert len(store.records) == 1

    receipt_path = outdir / "program_oracle_publication_receipt.json"
    preflight_path = outdir / "program_oracle_publication_preflight.json"
    state_path = outdir / "program_candidate_state.json"
    assert receipt_path.exists()
    assert preflight_path.exists()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == "program-oracle-shared-publication-receipt-v1"
    assert receipt["effect"]["shared_oracle_mutated"] is True
    assert receipt["effect"]["ak_called"] is False
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["truth_summary"]["oracle_publication_ref_present"] is True
    assert state["shared_oracle_publication"] == {
        "evidence_ref_present": True,
        "evidence_only": True,
        "activation_authority": False,
        "promotion_authority": False,
    }
    assert state["truth_summary"]["promotion_applied"] is False
    assert state["truth_summary"]["winner_selected"] is False


def test_program_loop_cli_publish_to_shared_fails_closed_without_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    monkeypatch.delenv("DSPX_ORACLE_STORE", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_POSTGRES_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--publish-to-shared",
            "retained",
            "--publisher-id",
            "pi-test",
            "--publisher-role",
            "operator",
            "--publisher-assertion",
            "share synthetic behavior evidence for future Oracle retrieval",
            "--redaction-status",
            "checked",
            "--retention-class",
            "retained_behavior_memory",
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "configured and available Postgres/pgvector Oracle backend" in result.output
    assert not (outdir / "program_oracle_publication_receipt.json").exists()
    assert not (outdir / "program_loop.json").exists()


def test_program_loop_publish_to_shared_requires_publisher_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    _write_intent(intent_path)

    with pytest.raises(ValueError, match="publisher_id is required"):
        run_program_loop_from_intent_path(
            intent_path,
            outdir=tmp_path / "candidate",
            publish_to_shared="retained",
            publisher_role="operator",
            publisher_assertion="share synthetic behavior evidence",
            redaction_status="checked",
            retention_class="retained_behavior_memory",
            shared_publication_store=cast(CoordinateStore, FakeSharedOracleStore()),
        )
