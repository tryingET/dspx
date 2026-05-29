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
from dspx.services.program_promotion_decision import (
    ProgramPromotionDecisionError,
    build_program_promotion_decision_record,
    write_program_promotion_decision_record,
)
from dspx.services.program_promotion_refinement import (
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


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_program_review(
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
    assert (program_root / "eval_examples.py").exists()
    assert (program_root / "eval_behavior.py").exists()
    assert (program_root / "behavior_episode.json").exists()

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

    refined_review = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )
    review_path = tmp_path / "promotion" / "promotion_review_refined.json"
    _write_json(review_path, refined_review)
    return program_root, review_path


def test_program_promotion_decision_writer_refuses_to_overwrite_review_input(
    tmp_path: Path,
) -> None:
    review_path = tmp_path / "custom_refined_review.json"
    review_path.write_text(
        '{"schema_version":"program-promotion-review-refined-v1"}\n',
        encoding="utf-8",
    )
    record = {
        "schema_version": "program-promotion-decision-record-v1",
        "status": "recorded",
        "created_from": {"refined_review_path": str(review_path)},
    }

    with pytest.raises(ProgramPromotionDecisionError, match="input artifact"):
        write_program_promotion_decision_record(record, review_path)

    assert json.loads(review_path.read_text(encoding="utf-8")) == {
        "schema_version": "program-promotion-review-refined-v1"
    }

    protected_program = tmp_path / "program.py"
    protected_program.write_text("# generated program\n", encoding="utf-8")
    with pytest.raises(ProgramPromotionDecisionError, match="program.py"):
        write_program_promotion_decision_record(record, protected_program)


def test_program_promotion_decision_cli_records_local_sidecar_without_mutating_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, review_path = _materialize_program_review(tmp_path, monkeypatch)
    refined_review = json.loads(review_path.read_text(encoding="utf-8"))
    before_program_hashes = _file_hashes(program_root)
    before_review_hash = hashlib.sha256(review_path.read_bytes()).hexdigest()
    out_path = tmp_path / "promotion" / "promotion_decision_record.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "decide",
            "--review",
            str(review_path),
            "--outcome",
            "request_more_evidence",
            "--decided-by",
            "local_operator",
            "--rationale",
            "Need model-jury execution before any promotion decision.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == "program-promotion-decision-record-v1"
    assert payload["status"] == "recorded"
    assert payload["outcome"] == "request_more_evidence"
    assert payload["promotion_state_after_decision"] == "not_promoted"
    assert payload["decided_by"] == "local_operator"
    assert payload["rationale"] == (
        "Need model-jury execution before any promotion decision."
    )
    assert payload["identity"] == refined_review["identity"]
    assert payload["created_from"] == {
        "refined_review_path": str(review_path.resolve()),
        "refined_review_schema_version": "program-promotion-review-refined-v1",
    }
    assert payload["review_snapshot"] == {
        "review_status": "review_packet_ready",
        "promotion_state": "not_promoted",
        "candidate_status": "exploratory",
        "ready_for_adjudicator_review": False,
        "missing_required_evidence": [
            "no_model_jury_execution_episode",
            "no_promotion_adjudicator_decision",
        ],
    }
    assert payload["decision_constraints"] == {
        "allowed_outcomes": [
            "withhold",
            "reject",
            "request_more_evidence",
            "promote",
        ],
        "promote_requires_ready_review": True,
        "promote_allowed_by_review": False,
        "external_authority_exported": False,
    }
    assert payload["effect"] == {
        "local_decision_record_only": True,
        "program_files_mutated": False,
        "refined_review_mutated": False,
        "new_candidate_generated": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
    }
    assert payload["non_authority"] == {
        "local_decision_record_only": True,
        "automatic_promotion": False,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "program_mutation": False,
        "refined_review_mutation": False,
        "new_candidate_generation": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    assert _file_hashes(program_root) == before_program_hashes
    assert hashlib.sha256(review_path.read_bytes()).hexdigest() == before_review_hash
    assert not (program_root / "promotion_decision_record.json").exists()
    assert not (program_root / "promotion_review_refined.json").exists()
    assert (program_root / "eval_behavior.py").exists()
    assert (program_root / "behavior_episode.json").exists()


def test_program_promotion_decision_rejects_invalid_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _program_root, review_path = _materialize_program_review(tmp_path, monkeypatch)

    with pytest.raises(ProgramPromotionDecisionError, match="outcome"):
        build_program_promotion_decision_record(
            refined_review_path=review_path,
            outcome="approve",
            decided_by="local_operator",
            rationale="Not a supported local decision outcome.",
        )


def test_program_promotion_decision_rejects_blank_rationale_and_decider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _program_root, review_path = _materialize_program_review(tmp_path, monkeypatch)

    with pytest.raises(ProgramPromotionDecisionError, match="decided_by"):
        build_program_promotion_decision_record(
            refined_review_path=review_path,
            outcome="withhold",
            decided_by="  ",
            rationale="Need more evidence.",
        )

    with pytest.raises(ProgramPromotionDecisionError, match="rationale"):
        build_program_promotion_decision_record(
            refined_review_path=review_path,
            outcome="reject",
            decided_by="local_operator",
            rationale="  ",
        )


def test_program_promotion_decision_rejects_wrong_schema_review(
    tmp_path: Path,
) -> None:
    bad_review_path = tmp_path / "bad-review.json"
    _write_json(
        bad_review_path,
        {
            "schema_version": "program-promotion-review-v1",
            "promotion_state": "not_promoted",
        },
    )

    with pytest.raises(ProgramPromotionDecisionError, match="schema_version"):
        build_program_promotion_decision_record(
            refined_review_path=bad_review_path,
            outcome="withhold",
            decided_by="local_operator",
            rationale="Wrong input schema.",
        )


def test_program_promotion_decision_promote_fails_closed_when_review_not_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _program_root, review_path = _materialize_program_review(tmp_path, monkeypatch)
    refined_review = json.loads(review_path.read_text(encoding="utf-8"))
    assert refined_review["status"] == "review_packet_ready"
    assert refined_review["review_readiness"]["ready_for_adjudicator_review"] is False
    out_path = tmp_path / "promotion" / "promotion_decision_promote.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "decide",
            "--review",
            str(review_path),
            "--outcome",
            "promote",
            "--decided-by",
            "local_operator",
            "--rationale",
            "Try promote even though review is not ready.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    output = result.stdout + result.stderr
    assert "ready_for_adjudicator_review" in output
    assert "no_model_jury_execution_episode" in output
    assert not out_path.exists()
