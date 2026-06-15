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
    workflow_payload = json.loads(
        (outdir / "program_refinement_episode.json").read_text(encoding="utf-8")
    )
    assert workflow_payload == payload
    assert workflow_payload["effect"]["workflow_summary_written"] is True

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


def test_program_refinement_episode_can_write_local_promotion_plan(
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
            "collect one bounded second candidate and local plan only",
            "--promotion-plan",
            "--promotion-plan-target",
            "local_preferred_candidate",
            "--promotion-plan-authority-owner",
            "operator-test",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["status"] == "local_promotion_plan_written"
    assert payload["steps"]["promotion_plan"] == {
        "status": "planned_not_applied",
        "path": str((outdir / "promotion_plan.json").resolve()),
        "target": "local_preferred_candidate",
        "allowed_for_apply": False,
    }
    assert payload["effect"]["local_promotion_plan_written"] is True
    assert payload["effect"]["promotion_applied"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["non_authority"]["local_promotion_plan_only"] is True
    assert payload["non_authority"]["promotion_authority"] is False

    plan = json.loads((outdir / "promotion_plan.json").read_text(encoding="utf-8"))
    assert plan["schema_version"] == "program-promotion-plan-v1"
    assert plan["status"] == "planned_not_applied"
    assert plan["promotion_state"] == "not_promoted"
    assert plan["eligibility"]["allowed_for_apply"] is False
    assert plan["effect"]["external_authority_mutated"] is False
    assert plan["effect"]["governance_mutated"] is False
    assert plan["non_authority"]["winner_selection"] is False

    second_candidate = outdir / "second_candidate"
    assert (second_candidate / "manifest.json").exists()
    candidate_manifest = json.loads(
        (second_candidate / "manifest.json").read_text(encoding="utf-8")
    )
    state = json.loads(
        (outdir / "program_candidate_state.refinement.json").read_text(encoding="utf-8")
    )
    assert (
        state["candidate_identity"]["candidate_id"]
        == candidate_manifest["candidate_assembly"]["candidate_id"]
    )
    assert state["truth_summary"]["promotion_plan_present"] is True
    assert state["truth_summary"]["oracle_report_present"] is False
    assert state["truth_summary"]["winner_selected"] is False
    assert state["evidence_state"]["oracle_report"]["present"] is False
    assert state["promotion_state"]["promotion_plan"]["allowed_for_apply"] is False
    assert state["created_from"]["source_manifest_path"] == str(
        (program_root / "manifest.json").resolve()
    )
    assert not (program_root / "promotion_plan.json").exists()
    assert not (second_candidate / "promotion_plan.json").exists()
    assert _file_hashes(program_root) == before_source_hashes


def test_program_refinement_episode_records_decision_without_second_candidate(
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
            "withhold",
            "--decided-by",
            "operator-test",
            "--rationale",
            "withhold without collecting another local candidate",
            "--no-generate-second-candidate",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["schema_version"] == "program-refinement-episode-v1"
    assert payload["status"] == "decision_recorded"
    assert payload["steps"]["decision_record"]["outcome"] == "withhold"
    assert payload["steps"]["second_candidate"] == {
        "status": "skipped",
        "root_path": None,
        "manifest_path": None,
        "comparison_path": None,
        "comparison_status": None,
    }
    assert payload["effect"]["local_second_candidate_generated"] is False
    assert payload["effect"]["local_comparison_written"] is False
    assert payload["effect"]["external_authority_mutated"] is False
    assert payload["effect"]["winner_selected"] is False
    assert (outdir / "program_refinement_episode.json").exists()
    assert (outdir / "program_candidate_state.refinement.json").exists()
    assert not (outdir / "second_candidate").exists()
    assert not (outdir / "program_candidate_comparison.json").exists()
    state = json.loads(
        (outdir / "program_candidate_state.refinement.json").read_text(encoding="utf-8")
    )
    assert state["truth_summary"]["decision_record_present"] is True
    assert state["truth_summary"]["comparison_present"] is False
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


def test_program_refinement_episode_rejects_promotion_plan_without_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "refinement-episode"

    with pytest.raises(
        ProgramRefinementEpisodeError, match="second-candidate comparison"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="withhold without collecting another local candidate",
            generate_second_candidate=False,
            generate_promotion_plan=True,
            promotion_plan_target="local_preferred_candidate",
            promotion_plan_authority_owner="operator-test",
        )

    assert not outdir.exists()


def test_program_refinement_episode_rejects_invalid_promotion_plan_options_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "refinement-episode"

    with pytest.raises(ProgramRefinementEpisodeError, match="require --promotion-plan"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate and local plan only",
            promotion_plan_target="local_preferred_candidate",
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="unsupported"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate and local plan only",
            generate_promotion_plan=True,
            promotion_plan_target="deployment",
            promotion_plan_authority_owner="operator-test",
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="promotion_plan_target"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate and local plan only",
            generate_promotion_plan=True,
            promotion_plan_authority_owner="operator-test",
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="control artifact name"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate and local plan only",
            generate_promotion_plan=True,
            promotion_plan_target="local_preferred_candidate",
            promotion_plan_authority_owner="operator-test",
            promotion_plan_out=outdir / "manifest.json",
        )

    assert not outdir.exists()


def test_program_refinement_episode_rejects_promotion_plan_path_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "refinement-episode"

    with pytest.raises(
        ProgramRefinementEpisodeError, match="source generated program root"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate and local plan only",
            generate_promotion_plan=True,
            promotion_plan_target="local_preferred_candidate",
            promotion_plan_authority_owner="operator-test",
            promotion_plan_out=program_root / "promotion_plan.json",
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="conflicts"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate and local plan only",
            generate_promotion_plan=True,
            promotion_plan_target="local_preferred_candidate",
            promotion_plan_authority_owner="operator-test",
            promotion_plan_out=outdir / "second_candidate" / "promotion_plan.json",
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
