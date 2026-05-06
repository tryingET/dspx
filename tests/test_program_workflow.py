from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import CoordinateIndex, reset_embedding_engine

runner = CliRunner()


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
        "workflow_summary_written": True,
        "ak_called": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
        "promotion_applied": False,
        "winner_selected": False,
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
