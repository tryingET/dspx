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
from dspx.services.program_promotion_decision import (
    build_program_promotion_decision_record,
    write_program_promotion_decision_record,
)
from dspx.services.program_promotion_plan import (
    ProgramPromotionPlanError,
    build_program_promotion_plan,
)
from dspx.services.program_promotion_refinement import (
    build_program_promotion_refinement,
)
from dspx.services.program_refinement import build_program_refinement_proposal
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _top_file_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_adjudication_plan_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, Path, Path, Path]:
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
    source_root = Path(artifact.root_path)

    index_path = tmp_path / "oracle" / "coordinates.db"
    index_result = index_program_oracle_evidence_path(
        source_root,
        index_path=index_path,
    )
    assert index_result["indexed"] == 1
    assert index_result["errors"] == 0

    report = build_program_oracle_evidence_report(index_path=index_path)
    report_path = tmp_path / "oracle" / "program-evidence-report.json"
    _write_json(report_path, report)

    proposal = build_program_refinement_proposal(
        manifest_path=source_root / "manifest.json",
        oracle_report_path=report_path,
    )
    assert proposal["status"] == "proposed"
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)

    refined_review = build_program_promotion_refinement(
        manifest_path=source_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )
    review_path = tmp_path / "promotion" / "promotion_review_refined.json"
    _write_json(review_path, refined_review)

    decision = build_program_promotion_decision_record(
        refined_review_path=review_path,
        outcome="request_more_evidence",
        decided_by="local_operator",
        rationale="Generate one bounded second candidate for observed mismatch.",
    )
    decision_path = tmp_path / "promotion" / "promotion_decision_record.json"
    write_program_promotion_decision_record(decision, decision_path)

    comparison_path = tmp_path / "refinement" / "candidate_comparison.json"
    workflow_path = tmp_path / "refinement" / "generate_and_compare_result.json"
    candidate_root = tmp_path / "program-v2"
    result = runner.invoke(
        app,
        [
            "program-refine",
            "generate-and-compare",
            "--manifest",
            str(source_root / "manifest.json"),
            "--refinement-proposal",
            str(proposal_path),
            "--decision-record",
            str(decision_path),
            "--outdir",
            str(candidate_root),
            "--comparison-out",
            str(comparison_path),
            "--workflow-out",
            str(workflow_path),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert comparison_path.exists()
    assert (candidate_root / "manifest.json").exists()
    return (
        source_root,
        candidate_root,
        decision_path,
        comparison_path,
        review_path,
        index_path,
    )


def test_program_promote_plan_cli_writes_local_non_authoritative_plan_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        source_root,
        candidate_root,
        decision_path,
        comparison_path,
        review_path,
        index_path,
    ) = _materialize_adjudication_plan_inputs(tmp_path, monkeypatch)
    candidate_manifest = json.loads(
        (candidate_root / "manifest.json").read_text(encoding="utf-8")
    )
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    before_source_hashes = _top_file_hashes(source_root)
    before_candidate_hashes = _top_file_hashes(candidate_root)
    before_decision_hash = _sha256(decision_path)
    before_comparison_hash = _sha256(comparison_path)
    out_path = tmp_path / "promotion" / "promotion_plan.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "plan",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--decision-record",
            str(decision_path),
            "--comparison",
            str(comparison_path),
            "--review",
            str(review_path),
            "--source-manifest",
            str(source_root / "manifest.json"),
            "--target",
            "local_preferred_candidate",
            "--authority-owner",
            "local_operator",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == "program-promotion-plan-v1"
    assert payload["status"] == "planned_not_applied"
    assert payload["promotion_state"] == "not_promoted"
    assert payload["target"]["kind"] == "local_preferred_candidate"
    assert payload["target"]["apply_supported"] is False
    assert payload["authority_owner"] == {
        "kind": "human_operator",
        "id": "local_operator",
        "source": "cli",
    }
    assert payload["candidate_identity"] == {
        "request_id": candidate_manifest["request"]["request_id"],
        "candidate_id": candidate_manifest["candidate_assembly"]["candidate_id"],
        "assembly_id": candidate_manifest["candidate_assembly"]["assembly_id"],
        "episode_id": candidate_manifest["execution_episode"]["episode_id"],
        "receipt_bundle_id": candidate_manifest["receipt_bundle"]["receipt_bundle_id"],
    }
    assert payload["created_from"]["candidate_manifest_path"] == str(
        (candidate_root / "manifest.json").resolve()
    )
    assert payload["created_from"]["candidate_manifest_schema_version"] == (
        "program-candidate-assembly-v1"
    )
    assert payload["created_from"]["decision_record_schema_version"] == (
        "program-promotion-decision-record-v1"
    )
    assert payload["created_from"]["comparison_schema_version"] == (
        "program-refinement-candidate-comparison-v1"
    )
    assert payload["created_from"]["review_schema_version"] == (
        "program-promotion-review-refined-v1"
    )
    assert payload["created_from"]["candidate_behavior_episode_path"] == str(
        (candidate_root / "behavior_episode.json").resolve()
    )
    assert payload["created_from"]["candidate_behavior_episode_schema_version"] == (
        "program-behavior-episode-v1"
    )

    hashes = payload["evidence_hashes"]
    assert hashes["candidate_manifest_hash"] == _sha256(
        candidate_root / "manifest.json"
    )
    assert hashes["candidate_behavior_results_hash"] == _sha256(
        candidate_root / "behavior_results.json"
    )
    assert hashes["candidate_behavior_episode_hash"] == _sha256(
        candidate_root / "behavior_episode.json"
    )
    assert hashes["candidate_execution_episode_hash"] == _sha256(
        candidate_root / "execution_episode.json"
    )
    assert hashes["candidate_oracle_evidence_hash"] == _sha256(
        candidate_root / "oracle_evidence.json"
    )
    assert hashes["decision_record_hash"] == before_decision_hash
    assert hashes["comparison_hash"] == before_comparison_hash

    eligibility = payload["eligibility"]
    assert eligibility["status"] == "eligible_for_local_plan_only"
    assert eligibility["behavior_evidence_present"] is True
    assert eligibility["behavior_results_present"] is True
    assert eligibility["behavior_episode_present"] is True
    assert eligibility["behavior_evidence_kind"] == "behavior_results"
    assert eligibility["comparison_present"] is True
    assert eligibility["comparison_status"] == "compared"
    assert eligibility["decision_record_present"] is True
    assert eligibility["decision_outcome"] == "request_more_evidence"
    assert eligibility["allowed_for_apply"] is False
    assert "apply_not_supported" in eligibility["missing_required_evidence"]
    assert "no_external_authority_contract" in eligibility["missing_required_evidence"]
    assert "no_model_jury_execution_episode" in eligibility["missing_required_evidence"]

    audit = payload["audit_trail"]
    assert audit["candidate_manifest_hash"] == hashes["candidate_manifest_hash"]
    assert audit["decision_record_hash"] == before_decision_hash
    assert audit["comparison_hash"] == before_comparison_hash
    assert (
        audit["source_behavior_results_hash"]
        == comparison["created_from"]["source_behavior_results_hash"]
    )
    assert (
        audit["candidate_behavior_results_hash"]
        == hashes["candidate_behavior_results_hash"]
    )
    assert (
        audit["candidate_behavior_episode_hash"]
        == hashes["candidate_behavior_episode_hash"]
    )
    assert (
        audit["source_behavior_episode_hash"]
        == comparison["created_from"]["source_behavior_episode_hash"]
    )
    assert audit["created_by"] == "local_operator"
    assert audit["created_at"]

    assert payload["reversibility"] == {
        "apply_status": "not_applied",
        "rollback_required": False,
        "rollback_supported": False,
        "supersession_supported": False,
        "notes": [
            "No rollback is required because no promotion was applied.",
            "Future apply surfaces must record supersession/rollback semantics separately.",
        ],
    }
    assert payload["effect"] == {
        "local_plan_only": True,
        "candidate_program_files_mutated": False,
        "decision_record_mutated": False,
        "comparison_mutated": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
        "oracle_index_mutated": False,
    }
    assert payload["non_authority"] == {
        "local_plan_only": True,
        "automatic_promotion": False,
        "apply_promotion": False,
        "external_authority_export": False,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "winner_selection": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    assert _top_file_hashes(source_root) == before_source_hashes
    assert _top_file_hashes(candidate_root) == before_candidate_hashes
    assert _sha256(decision_path) == before_decision_hash
    assert _sha256(comparison_path) == before_comparison_hash
    assert out_path.parent == tmp_path / "promotion"
    assert out_path.parent != source_root
    assert out_path.parent != candidate_root
    assert not (source_root / "promotion_plan.json").exists()
    assert not (candidate_root / "promotion_plan.json").exists()
    assert (source_root / "eval_behavior.py").exists()
    assert (candidate_root / "eval_behavior.py").exists()
    assert (source_root / "behavior_episode.json").exists()
    assert (candidate_root / "behavior_episode.json").exists()
    assert index_path.exists()
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()


def test_program_promote_plan_rejects_unsupported_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _source_root,
        candidate_root,
        decision_path,
        comparison_path,
        _review_path,
        _index,
    ) = _materialize_adjudication_plan_inputs(tmp_path, monkeypatch)
    out_path = tmp_path / "promotion" / "ak_plan.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "plan",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--decision-record",
            str(decision_path),
            "--comparison",
            str(comparison_path),
            "--target",
            "ak",
            "--authority-owner",
            "local_operator",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "unsupported local promotion plan target" in (result.stdout + result.stderr)
    assert not out_path.exists()


def test_program_promote_plan_rejects_comparison_candidate_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _source_root,
        candidate_root,
        decision_path,
        comparison_path,
        _review_path,
        _index,
    ) = _materialize_adjudication_plan_inputs(tmp_path, monkeypatch)
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    comparison["candidate_identity"]["candidate_id"] = "prog-cand-other"
    bad_comparison_path = tmp_path / "refinement" / "bad_candidate_comparison.json"
    _write_json(bad_comparison_path, comparison)

    with pytest.raises(ProgramPromotionPlanError, match="candidate_id"):
        build_program_promotion_plan(
            manifest_path=candidate_root / "manifest.json",
            decision_record_path=decision_path,
            comparison_path=bad_comparison_path,
            target="local_preferred_candidate",
            authority_owner="local_operator",
        )


def test_program_promote_plan_does_not_create_default_oracle_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _source_root,
        candidate_root,
        decision_path,
        comparison_path,
        _review_path,
        _index,
    ) = _materialize_adjudication_plan_inputs(tmp_path, monkeypatch)
    default_index = tmp_path / "generated" / "oracle" / "coordinates.db"
    assert not default_index.exists()

    payload = build_program_promotion_plan(
        manifest_path=candidate_root / "manifest.json",
        decision_record_path=decision_path,
        comparison_path=comparison_path,
        target="local_adjudication_plan",
        authority_owner="local_operator",
    )

    assert payload["schema_version"] == "program-promotion-plan-v1"
    assert payload["effect"]["oracle_index_mutated"] is False
    assert not default_index.exists()
    assert (candidate_root / "eval_behavior.py").exists()
    assert (candidate_root / "behavior_episode.json").exists()
