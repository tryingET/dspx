from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_jury_execution import (
    build_program_jury_execution_result,
    write_program_jury_execution_result,
)
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_promotion_decision import (
    build_program_promotion_decision_record,
    write_program_promotion_decision_record,
)
from dspx.services.program_promotion_refinement import (
    build_program_promotion_refinement,
)
from dspx.services.program_refinement import build_program_refinement_proposal
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


def _materialize_program(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="ActivationTicketProgram",
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
    return Path(artifact.root_path)


def _materialize_review_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, Path, Path]:
    program_root = _materialize_program(tmp_path, monkeypatch)

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

    jury_result = build_program_jury_execution_result(
        manifest_path=program_root / "manifest.json",
    )
    jury_path = tmp_path / "promotion" / "jury_results.json"
    write_program_jury_execution_result(jury_result, jury_path)

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

    decision = build_program_promotion_decision_record(
        refined_review_path=review_path,
        outcome="request_more_evidence",
        decided_by="softwareco-program-governance",
        rationale="Dogfood activation remains blocked until a production domain accepts more evidence.",
    )
    decision_path = tmp_path / "promotion" / "promotion_decision_record.json"
    write_program_promotion_decision_record(decision, decision_path)

    return program_root, report_path, jury_path, review_path, decision_path


def test_program_promote_activation_packet_blocks_without_required_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    before_hashes = _file_hashes(program_root)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == (
        "generated-cognition-program-production-activation-packet-v1"
    )
    assert payload["transition_type"] == (
        "generated-cognition-program.production_activation"
    )
    assert payload["status"] == "blocked"
    assert payload["owning_domain"] == "softwareco/dspx-generated-program-governance"
    assert payload["activation_target"] == "local-dogfood-only"
    assert "oracle_report" in payload["missing_required_evidence"]
    assert "jury_results" in payload["missing_required_evidence"]
    assert "refined_promotion_review" in payload["missing_required_evidence"]
    assert "rollback_plan" in payload["missing_required_evidence"]
    assert payload["boundary_checks"] == {
        "mlflow_approval_authority": False,
        "oracle_promotion_authority": False,
        "jury_promotion_authority": False,
        "dspx_activation_authority": False,
        "requires_domain_governing_body": True,
        "requires_canonical_binding_before_rollout": True,
    }
    assert payload["non_authority"]["activation_packet_only"] is True
    assert payload["effect"]["production_activation_applied"] is False
    assert _file_hashes(program_root) == before_hashes
    assert not (program_root / "activation_packet.json").exists()


def test_program_promote_activation_packet_dogfoods_review_chain_without_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    before_hashes = _file_hashes(program_root)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["next_required_action"] == "resolve_decision_outcome"
    assert payload["missing_required_evidence"] == ["decision_outcome_not_promote"]
    assert payload["decision"] == {
        "outcome": "request_more_evidence",
        "promotion_state_after_decision": "not_promoted",
        "decided_by": "softwareco-program-governance",
    }
    assert payload["canonical_binding_ref"] is None
    assert payload["evidence"]["oracle_report"]["path"] == str(report_path.resolve())
    assert payload["evidence"]["jury_results"]["path"] == str(jury_path.resolve())
    assert payload["evidence"]["refined_review"]["path"] == str(review_path.resolve())
    assert payload["evidence"]["decision_record"]["path"] == str(
        decision_path.resolve()
    )
    assert payload["effect"] == {
        "activation_packet_written": True,
        "program_files_mutated": False,
        "oracle_index_mutated": False,
        "mlflow_mutated": False,
        "ak_mutated": False,
        "external_authority_mutated": False,
        "production_activation_applied": False,
    }
    assert _file_hashes(program_root) == before_hashes
    assert not (program_root / "activation_packet.json").exists()
