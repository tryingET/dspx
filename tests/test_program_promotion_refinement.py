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
from dspx.services.program_refinement import build_program_refinement_proposal
from dspx.services.program_promotion_refinement import (
    ProgramPromotionRefinementError,
    build_program_promotion_refinement,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _materialize_program_report_and_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path]:
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

    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)
    return program_root, report_path, proposal_path


def test_program_promotion_refinement_cli_builds_local_review_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    behavior = json.loads(
        (program_root / "behavior_results.json").read_text(encoding="utf-8")
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    before = _file_hashes(program_root)
    before_names = sorted(before)
    out_path = tmp_path / "promotion" / "promotion_review_refined.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == "program-promotion-review-refined-v1"
    assert payload["status"] == "review_packet_ready"
    assert payload["promotion_state"] == "not_promoted"
    assert payload["candidate_status"] == "exploratory"
    assert payload["identity"] == {
        "request_id": manifest["request"]["request_id"],
        "candidate_id": manifest["candidate_assembly"]["candidate_id"],
        "assembly_id": manifest["candidate_assembly"]["assembly_id"],
        "episode_id": manifest["execution_episode"]["episode_id"],
        "receipt_bundle_id": manifest["receipt_bundle"]["receipt_bundle_id"],
    }
    assert payload["created_from"]["manifest_path"] == str(
        (program_root / "manifest.json").resolve()
    )
    assert payload["created_from"]["behavior_results_path"] == str(
        (program_root / "behavior_results.json").resolve()
    )
    assert payload["created_from"]["oracle_report_path"] == str(report_path.resolve())
    assert payload["created_from"]["refinement_proposal_path"] == str(
        proposal_path.resolve()
    )
    assert payload["created_from"]["original_promotion_review_path"] == str(
        (program_root / "promotion_review.json").resolve()
    )
    assert payload["created_from"][
        "original_promotion_adjudication_request_path"
    ] == str((program_root / "promotion_adjudication_request.json").resolve())
    assert payload["created_from"]["original_promotion_decision_template_path"] == str(
        (program_root / "promotion_decision_template.json").resolve()
    )

    assert payload["evidence_summary"]["behavior"] == {
        "present": True,
        "status": behavior["summary"]["status"],
        "example_count": behavior["summary"]["total"],
        "status_counts": behavior["summary"]["status_counts"],
    }
    assert payload["evidence_summary"]["oracle_report"] == {
        "present": True,
        "status": "ok",
        "total_records": 1,
        "record_matched": True,
    }
    assert payload["evidence_summary"]["refinement_proposal"] == {
        "present": True,
        "status": proposal["status"],
        "proposal_id": proposal["proposal_id"],
    }
    readiness = payload["review_readiness"]
    assert readiness["behavior_evidence_present"] is True
    assert readiness["oracle_report_present"] is True
    assert readiness["refinement_proposal_present"] is True
    assert readiness["model_jury_execution_present"] is False
    assert readiness["adjudicator_decision_present"] is False
    assert readiness["ready_for_adjudicator_review"] is False
    assert readiness["missing_required_evidence"] == [
        "no_model_jury_execution_episode",
        "no_promotion_adjudicator_decision",
    ]
    assert payload["promotion_review_delta"] == {
        "behavioral_evaluation_episode": "satisfied_by_current_behavior_episode",
        "oracle_interpretation": "satisfied_by_explicit_oracle_report",
        "bounded_refinement_proposal": "available_non_authoritative",
        "promotion_authority": "unchanged_required_adjudicator",
    }
    adjudication = payload["adjudication_packet"]
    assert adjudication["status"] == "not_ready_missing_required_evidence"
    assert adjudication["original_allowed_outcomes"] == [
        "promote",
        "withhold",
        "reject",
        "request_more_evidence",
    ]
    assert adjudication["local_packet_recommended_review_outcomes"] == [
        "withhold",
        "reject",
        "request_more_evidence",
    ]
    assert adjudication["forbidden_outcomes_without_explicit_adjudicator"] == [
        "promote"
    ]
    assert "behavior_results.json" in adjudication["evidence_refs"]
    assert payload["non_authority"] == {
        "local_review_packet_only": True,
        "automatic_promotion": False,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "program_mutation": False,
        "new_candidate_generation": False,
        "promotion_authority": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    assert _file_hashes(program_root) == before
    assert sorted(_file_hashes(program_root)) == before_names
    assert not (program_root / "promotion_review_refined.json").exists()
    assert (program_root / "eval_behavior.py").exists()
    assert (program_root / "behavior_episode.json").exists()


def test_program_promotion_refinement_rejects_authority_widened_oracle_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["non_authority"]["oracle_promotion"] = True
    bad_report_path = tmp_path / "oracle" / "bad-report.json"
    _write_json(bad_report_path, report)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(bad_report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--out",
            str(tmp_path / "promotion" / "review.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "oracle_promotion" in (result.stdout + result.stderr)
    assert not (tmp_path / "promotion" / "review.json").exists()


def test_program_promotion_refinement_rejects_authority_widened_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["non_authority"]["promotion_authority"] = True
    bad_proposal_path = tmp_path / "refinement" / "bad-proposal.json"
    _write_json(bad_proposal_path, proposal)

    with pytest.raises(ProgramPromotionRefinementError, match="promotion_authority"):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            refinement_proposal_path=bad_proposal_path,
        )


def test_program_promotion_refinement_rejects_oracle_report_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    record = report["records"][0]
    record["identity"]["receipt_bundle_id"] = "prog-rb-other"
    record["identity"]["episode_id"] = "prog-ep-other"
    record["identity"]["assembly_id"] = "prog-asm-other"
    record["identity"]["candidate_id"] = "prog-cand-other"
    record["identity"]["request_id"] = "prog-req-other"
    bad_report_path = tmp_path / "oracle" / "mismatch-report.json"
    _write_json(bad_report_path, report)

    with pytest.raises(
        ProgramPromotionRefinementError, match="matching manifest identity"
    ):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=bad_report_path,
            refinement_proposal_path=proposal_path,
        )


def test_program_promotion_refinement_rejects_proposal_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["identity"]["candidate_id"] = "prog-cand-other"
    bad_proposal_path = tmp_path / "refinement" / "mismatch-proposal.json"
    _write_json(bad_proposal_path, proposal)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(bad_proposal_path),
            "--out",
            str(tmp_path / "promotion" / "review.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "candidate_id" in (result.stdout + result.stderr)
    assert not (tmp_path / "promotion" / "review.json").exists()


def test_program_promotion_refinement_degrades_without_behavior_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="NoExamplesProgram",
        objective="Answer a question.",
        inputs=["question"],
        outputs=["answer"],
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    program_root = Path(artifact.root_path)
    assert not (program_root / "behavior_results.json").exists()
    assert not (program_root / "oracle_evidence.json").exists()
    report = build_program_oracle_evidence_report(
        index_path=tmp_path / "oracle" / "coordinates.db"
    )
    report_path = tmp_path / "oracle-report.json"
    _write_json(report_path, report)
    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)
    before = _file_hashes(program_root)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--out",
            str(tmp_path / "promotion" / "promotion_review_refined.json"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "program-promotion-review-refined-v1"
    assert payload["status"] == "insufficient_behavior_evidence"
    assert payload["promotion_state"] == "not_promoted"
    assert payload["created_from"]["behavior_results_path"] is None
    assert payload["evidence_summary"]["behavior"] == {
        "present": False,
        "status": "insufficient_behavior_evidence",
        "example_count": 0,
        "status_counts": {},
    }
    assert payload["evidence_summary"]["oracle_report"] == {
        "present": True,
        "status": "no_program_oracle_evidence",
        "total_records": 0,
        "record_matched": False,
    }
    assert payload["evidence_summary"]["refinement_proposal"]["status"] == (
        "insufficient_behavior_evidence"
    )
    assert payload["review_readiness"]["missing_required_evidence"] == [
        "no_behavioral_evaluation_episode",
        "no_model_jury_execution_episode",
        "no_promotion_adjudicator_decision",
    ]
    assert (
        "behavior_results.json" not in payload["adjudication_packet"]["evidence_refs"]
    )
    assert payload["non_authority"]["automatic_promotion"] is False
    assert _file_hashes(program_root) == before
    assert not (tmp_path / "oracle" / "coordinates.db").exists()
