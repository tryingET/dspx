# summary: "Tests the guided local program-architect loop and its non-authoritative outputs."
# read_when:
#   - "Changing the program-architect loop, candidate filtering, output preflights, or Oracle report options."

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from program_architecture_shared import (
    runner,
)


@pytest.mark.slow
def test_program_architect_loop_runs_guided_local_architecture_flow(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    outdir = tmp_path / "architect_loop"

    result = runner.invoke(
        app,
        [
            "program-architect",
            "loop",
            "--prompt",
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            "--outdir",
            str(outdir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "program-architect-loop-v1"
    assert (outdir / "normalization.json").exists()
    assert (outdir / "normalized_intent.json").exists()
    assert (outdir / "architecture_plan.json").exists()
    assert (outdir / "tournament.json").exists()
    assert (outdir / "architecture_recommendation.json").exists()
    assert (outdir / "program_architect_loop.json").exists()
    assert payload == json.loads((outdir / "program_architect_loop.json").read_text())
    assert payload["steps"]["normalization"]["status"] == "normalized"
    assert payload["steps"]["architecture_plan"]["candidate_count"] == 2
    assert payload["steps"]["tournament"]["materialized_candidate_count"] == 2
    assert payload["steps"]["recommendation"]["next_move_count"] >= 1
    assert payload["effect"]["candidate_programs_materialized"] is True
    assert payload["effect"]["receipts_replay_checked"] is True
    assert payload["effect"]["oracle_index_mutated"] is False
    assert payload["effect"]["shared_oracle_mutated"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["effect"]["promotion_applied"] is False
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["governance_mutated"] is False
    assert payload["non_authority"]["guided_architecture_loop_only"] is True
    assert payload["non_authority"]["winner_selection"] is False
    assert not (outdir / "manifest.json").exists()
    assert not (outdir / "program.py").exists()


@pytest.mark.slow
def test_program_architect_loop_rejects_unknown_candidate_without_partial_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    outdir = tmp_path / "architect_loop"

    result = runner.invoke(
        app,
        [
            "program-architect",
            "loop",
            "--prompt",
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            "--outdir",
            str(outdir),
            "--candidate",
            "does_not_exist",
        ],
    )

    assert result.exit_code == 2
    assert "unknown architecture candidate id" in result.output
    assert not (outdir / "normalization.json").exists()
    assert not (outdir / "normalized_intent.json").exists()
    assert not (outdir / "architecture_plan.json").exists()
    assert not (outdir / "tournament.json").exists()
    assert not (outdir / "architecture_recommendation.json").exists()
    assert not (outdir / "program_architect_loop.json").exists()
    assert not (outdir / "tournament" / "candidates").exists()


@pytest.mark.slow
def test_program_architect_loop_rejects_non_empty_outdir_before_partial_overwrite(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    outdir = tmp_path / "architect_loop"
    first = runner.invoke(
        app,
        [
            "program-architect",
            "loop",
            "--prompt",
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            "--outdir",
            str(outdir),
        ],
    )
    assert first.exit_code == 0, first.output
    before = (outdir / "normalized_intent.json").read_text()

    second = runner.invoke(
        app,
        [
            "program-architect",
            "loop",
            "--prompt",
            "Answer a completely different question from context.",
            "--outdir",
            str(outdir),
        ],
    )

    assert second.exit_code == 2
    assert "architecture loop outdir is not empty" in second.output
    assert (outdir / "normalized_intent.json").read_text() == before


@pytest.mark.slow
def test_program_architect_loop_with_oracle_reports_is_candidate_local(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    outdir = tmp_path / "architect_loop"

    result = runner.invoke(
        app,
        [
            "program-architect",
            "loop",
            "--prompt",
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            "--outdir",
            str(outdir),
            "--candidate",
            "prompt_inferred_pipeline",
            "--with-oracle-reports",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["effect"]["oracle_index_mutated"] is True
    assert payload["effect"]["oracle_index_scope"] == "candidate_local_explicit_paths"
    assert payload["effect"]["shared_oracle_mutated"] is False
    candidate_root = outdir / "tournament" / "candidates" / "prompt_inferred_pipeline"
    assert (candidate_root / "oracle" / "coordinates.db").exists()
    assert (candidate_root / "program_oracle_report.json").exists()
    recommendation = json.loads(
        (outdir / "architecture_recommendation.json").read_text()
    )
    assert recommendation["effect"]["winner_selected"] is False
    assert recommendation["effect"]["promotion_applied"] is False
