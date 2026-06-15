from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_refinement_episode import (
    ProgramRefinementEpisodeError,
    run_program_refinement_episode,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_program_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    _setup_env(tmp_path, monkeypatch)
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
    assert (program_root / "behavior_results.json").exists()
    assert (program_root / "oracle_evidence.json").exists()

    index_path = tmp_path / "oracle" / "coordinates.db"
    index_result = index_program_oracle_evidence_path(
        program_root,
        index_path=index_path,
    )
    assert index_result["indexed"] == 1
    assert index_result["errors"] == 0

    report = build_program_oracle_evidence_report(index_path=index_path)
    report_path = tmp_path / "oracle" / "program-evidence-report.json"
    _write_json(report_path, report)
    return program_root, report_path


def test_program_refinement_episode_cli_materializes_second_candidate_and_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    before_source_hashes = _file_hashes(program_root)
    outdir = tmp_path / "refinement-episode"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "episode",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--outdir",
            str(outdir),
            "--decision-outcome",
            "request_more_evidence",
            "--decided-by",
            "operator-test",
            "--rationale",
            "collect one bounded second candidate before any promotion review",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["schema_version"] == "program-refinement-episode-v1"
    assert payload["status"] in {
        "second_candidate_compared",
        "second_candidate_materialized_with_insufficient_behavior_evidence",
    }
    assert payload["non_authority"]["promotion_authority"] is False
    assert payload["non_authority"]["winner_selection"] is False
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["external_authority_mutated"] is False
    assert payload["effect"]["governance_mutated"] is False
    assert payload["effect"]["promotion_applied"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["steps"]["decision_record"]["outcome"] == "request_more_evidence"
    assert payload["steps"]["second_candidate"]["manifest_path"]

    for key in (
        "refinement_proposal.json",
        "promotion_review_refined.json",
        "promotion_decision_record.json",
        "program_candidate_comparison.json",
        "program_candidate_state.refinement.json",
        "program_refinement_episode.json",
    ):
        assert (outdir / key).exists(), key
    assert (outdir / "second_candidate" / "manifest.json").exists()

    state = json.loads(
        (outdir / "program_candidate_state.refinement.json").read_text(encoding="utf-8")
    )
    assert state["truth_summary"]["decision_record_present"] is True
    assert state["truth_summary"]["comparison_present"] is True
    assert state["truth_summary"]["ak_called"] is False
    assert state["truth_summary"]["winner_selected"] is False
    assert _file_hashes(program_root) == before_source_hashes


def test_program_refinement_episode_rejects_second_candidate_without_request_more_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "refinement-episode"

    with pytest.raises(ProgramRefinementEpisodeError, match="request_more_evidence"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="withhold without collecting another local candidate",
            generate_second_candidate=True,
        )

    assert not outdir.exists()


def test_program_refinement_episode_rejects_duplicate_or_source_root_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "refinement-episode"

    with pytest.raises(ProgramRefinementEpisodeError, match="duplicates"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate",
            proposal_out=outdir / "same.json",
            review_out=outdir / "same.json",
        )

    with pytest.raises(
        ProgramRefinementEpisodeError, match="source generated program root"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate",
            proposal_out=program_root / "refinement_proposal.json",
        )

    with pytest.raises(
        ProgramRefinementEpisodeError, match="second_candidate_outdir conflicts"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate",
            proposal_out=outdir / "sidecar.json",
            second_candidate_outdir=outdir / "sidecar.json" / "second_candidate",
        )
