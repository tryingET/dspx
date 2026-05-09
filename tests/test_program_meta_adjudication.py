from __future__ import annotations

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
from dspx.services.program_promotion_decision import (
    build_generated_program_adjudicator_decision_record,
    write_program_promotion_decision_record,
)
from dspx.services.program_meta_adjudication import (
    build_program_adjudication_behavior_trace,
    build_program_adjudication_gepa_example,
    build_program_adjudicator_delegation,
    build_program_adjudicator_formation,
    build_program_adjudicator_verification,
    build_program_evidence_adjudication,
    build_program_jury_requirements,
    build_program_jury_verification,
    build_program_meta_adjudication_plan,
    build_program_meta_jury_selection,
    build_program_target_profile,
    write_program_adjudication_behavior_trace,
    write_program_adjudication_gepa_example,
    write_program_adjudicator_delegation,
    write_program_adjudicator_formation,
    write_program_adjudicator_verification,
    write_program_evidence_adjudication,
    write_program_jury_requirements,
    write_program_jury_verification,
    write_program_meta_adjudication_plan,
    write_program_meta_jury_selection,
    write_program_target_profile,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _setup_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_obsidian_like_candidate(tmp_path: Path, monkeypatch) -> Path:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="ObsidianPdfTransitionReviewer",
        objective=(
            "Transform PDF source package evidence into review-only Obsidian Wiki "
            "transition proposals without canonical Atlas or Wiki mutation."
        ),
        inputs=["marker_markdown", "source_package_json", "existing_wiki_index_json"],
        outputs=["review_packet_json", "merge_create_proposals_json"],
        metric="exact_match",
        constraints=[
            "Preserve Zotero/source identity and source refs.",
            "All Wiki or Atlas targets require review_required=true.",
            "Canonical mutation is forbidden during generation.",
        ],
        examples=[
            {
                "inputs": {
                    "marker_markdown": "# Close Reading\nUse source-grounded evidence.",
                    "source_package_json": '{"source_id":"zotero:user:demo/DEMO2026"}',
                    "existing_wiki_index_json": "{}",
                },
                "outputs": {
                    "review_packet_json": '{"canonical_mutation_performed":false}',
                    "merge_create_proposals_json": "[]",
                },
            }
        ],
        promotion={
            "adjudicator": {"kind": "ai_agent", "id": "dspx_program_adjudicator_v1"}
        },
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    return Path(artifact.root_path)


def test_meta_adjudication_plan_derives_target_sensitive_jury_requirements(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json"
    )

    assert plan["schema_version"] == "program-meta-adjudication-plan-v1"
    assert plan["status"] == "planned_not_executed"
    assert plan["effect"]["provider_called"] is False
    assert plan["non_authority"]["activation_authority"] is False
    assert (
        plan["oracle_postgres_behavior_memory"]["publication_allowed_by_this_plan"]
        is False
    )
    assert plan["gepa_improvement_lane"]["activation_authority"] is False

    risk_ids = {risk["risk_id"] for risk in plan["target_profile"]["risks"]}
    assert "source_grounding" in risk_ids
    assert "canonical_mutation_boundary" in risk_ids
    assert "review_queue_boundary" in risk_ids

    perspectives = {
        item["perspective"]
        for item in plan["jury_requirements"]["required_perspectives"]
    }
    assert "source_grounding" in perspectives
    assert "canonical_mutation_safety" in perspectives
    assert "review_surface" in perspectives
    assert "authority_boundary" in perspectives
    assert "program_jury_results" in plan["missing_evidence"]
    assert "jury_panel_verification" in plan["missing_evidence"]
    assert "program_adjudicator_delegation" in plan["missing_evidence"]
    assert any(
        cmd["step"] == "run_deterministic_jury_baseline"
        for cmd in plan["next_commands"]
    )
    assert any(
        cmd["step"] == "delegate_generated_program_adjudicator"
        for cmd in plan["next_commands"]
    )
    assert any(
        cmd["step"] == "generated_program_adjudicator_decision"
        for cmd in plan["next_commands"]
    )


def test_target_profile_and_jury_requirements_write_first_class_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    profile_path = tmp_path / "target_profile.json"
    requirements_path = tmp_path / "jury_requirements.json"

    profile = build_program_target_profile(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_target_profile(profile, profile_path)
    requirements = build_program_jury_requirements(target_profile_path=profile_path)
    write_program_jury_requirements(requirements, requirements_path)

    assert profile["schema_version"] == "program-target-profile-v1"
    assert profile["identity"]["candidate_id"]
    assert profile["manifest"]["path"] == str(candidate_root / "manifest.json")
    assert profile["effect"]["provider_called"] is False
    assert profile["non_authority"]["activation_authority"] is False
    risk_ids = {risk["risk_id"] for risk in profile["risks"]}
    assert "canonical_mutation_boundary" in risk_ids

    assert requirements["schema_version"] == "program-jury-requirements-v1"
    assert requirements["target_profile"]["path"] == str(profile_path.resolve())
    assert requirements["effect"]["provider_called"] is False
    perspectives = {
        item["perspective"] for item in requirements["required_perspectives"]
    }
    assert "canonical_mutation_safety" in perspectives
    assert "review_surface" in perspectives

    written_profile = json.loads(profile_path.read_text(encoding="utf-8"))
    written_requirements = json.loads(requirements_path.read_text(encoding="utf-8"))
    assert written_profile["schema_version"] == "program-target-profile-v1"
    assert written_requirements["schema_version"] == "program-jury-requirements-v1"


def test_target_profile_and_jury_requirements_cli_write_json(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    profile_out = tmp_path / "target-profile.json"
    requirements_out = tmp_path / "jury-requirements.json"

    profile_result = runner.invoke(
        app,
        [
            "program-promote",
            "target-profile",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--out",
            str(profile_out),
            "--json",
        ],
    )
    assert profile_result.exit_code == 0, profile_result.output
    profile_payload = json.loads(profile_result.output)
    assert profile_payload["schema_version"] == "program-target-profile-v1"

    requirements_result = runner.invoke(
        app,
        [
            "program-promote",
            "jury-requirements",
            "--target-profile",
            str(profile_out),
            "--out",
            str(requirements_out),
            "--json",
        ],
    )
    assert requirements_result.exit_code == 0, requirements_result.output
    requirements_payload = json.loads(requirements_result.output)
    assert requirements_payload["schema_version"] == "program-jury-requirements-v1"
    assert requirements_payload["target_profile"]["path"] == str(profile_out.resolve())
    assert requirements_out.exists()


def test_meta_jury_selection_and_verification_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    profile_path = tmp_path / "target_profile.json"
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    verification_path = tmp_path / "jury_verification.json"

    profile = build_program_target_profile(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_target_profile(profile, profile_path)
    requirements = build_program_jury_requirements(target_profile_path=profile_path)
    write_program_jury_requirements(requirements, requirements_path)

    selection = build_program_meta_jury_selection(
        jury_requirements_path=requirements_path
    )
    write_program_meta_jury_selection(selection, selection_path)
    verification = build_program_jury_verification(jury_selection_path=selection_path)
    write_program_jury_verification(verification, verification_path)

    assert selection["schema_version"] == "program-meta-jury-selection-v1"
    assert selection["status"] == "selected"
    assert selection["effect"]["provider_called"] is False
    assert selection["non_authority"]["activation_authority"] is False
    assert selection["coverage"]["missing_perspectives"] == []
    selected_perspectives = {
        juror["perspective"] for juror in selection["selected_jurors"]
    }
    assert "authority_boundary" in selected_perspectives
    assert "canonical_mutation_safety" in selected_perspectives
    assert all(juror["model_backed"] is False for juror in selection["selected_jurors"])

    assert verification["schema_version"] == "program-jury-verification-v1"
    assert verification["status"] == "verified"
    assert verification["approved_for_program_adjudicator_formation"] is True
    assert verification["dspx_adjudicator"]["model_backed"] is False
    assert verification["effect"]["provider_called"] is False
    assert verification["failed_checks"] == []
    assert all(check["ok"] is True for check in verification["checks"])

    written_selection = json.loads(selection_path.read_text(encoding="utf-8"))
    written_verification = json.loads(verification_path.read_text(encoding="utf-8"))
    assert written_selection["schema_version"] == "program-meta-jury-selection-v1"
    assert written_verification["schema_version"] == "program-jury-verification-v1"


def test_meta_jury_selection_and_verification_cli_write_json(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_out = tmp_path / "jury-requirements.json"
    selection_out = tmp_path / "meta-jury-selection.json"
    verification_out = tmp_path / "jury-verification.json"

    requirements_result = runner.invoke(
        app,
        [
            "program-promote",
            "jury-requirements",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--out",
            str(requirements_out),
            "--json",
        ],
    )
    assert requirements_result.exit_code == 0, requirements_result.output

    selection_result = runner.invoke(
        app,
        [
            "program-promote",
            "jury-panel",
            "--jury-requirements",
            str(requirements_out),
            "--out",
            str(selection_out),
            "--json",
        ],
    )
    assert selection_result.exit_code == 0, selection_result.output
    selection_payload = json.loads(selection_result.output)
    assert selection_payload["schema_version"] == "program-meta-jury-selection-v1"
    assert selection_payload["status"] == "selected"

    verification_result = runner.invoke(
        app,
        [
            "program-promote",
            "verify-jury-panel",
            "--jury-selection",
            str(selection_out),
            "--out",
            str(verification_out),
            "--json",
        ],
    )
    assert verification_result.exit_code == 0, verification_result.output
    verification_payload = json.loads(verification_result.output)
    assert verification_payload["schema_version"] == "program-jury-verification-v1"
    assert verification_payload["status"] == "verified"
    assert verification_out.exists()


def test_jury_verification_rejects_incomplete_selection(tmp_path: Path) -> None:
    selection_path = tmp_path / "bad-selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "schema_version": "program-meta-jury-selection-v1",
                "status": "selection_incomplete",
                "minimum_jurors": 2,
                "selected_jurors": [
                    {
                        "juror_id": "meta_juror_behavior",
                        "perspective": "behavior_evidence",
                        "model_backed": False,
                    }
                ],
                "coverage": {
                    "required_perspectives": [
                        "behavior_evidence",
                        "authority_boundary",
                    ],
                    "selected_perspectives": ["behavior_evidence"],
                    "missing_perspectives": ["authority_boundary"],
                },
                "selection_constraints": {"require_authority_boundary_reviewer": True},
                "non_authority": {"activation_authority": False},
                "effect": {"provider_called": False},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    verification = build_program_jury_verification(jury_selection_path=selection_path)

    assert verification["status"] == "revise_jury_selection"
    assert verification["approved_for_program_adjudicator_formation"] is False
    assert "minimum_jurors_satisfied" in verification["failed_checks"]
    assert "authority_boundary_present" in verification["failed_checks"]


def test_program_adjudicator_formation_and_verification_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    formation_path = tmp_path / "program_adjudicator_formation.json"
    adjudicator_verification_path = tmp_path / "program_adjudicator_verification.json"
    delegation_path = tmp_path / "program_adjudicator_delegation.json"

    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_jury_requirements(requirements, requirements_path)
    selection = build_program_meta_jury_selection(
        jury_requirements_path=requirements_path
    )
    write_program_meta_jury_selection(selection, selection_path)
    jury_verification = build_program_jury_verification(
        jury_selection_path=selection_path
    )
    write_program_jury_verification(jury_verification, jury_verification_path)

    formation = build_program_adjudicator_formation(
        jury_verification_path=jury_verification_path
    )
    write_program_adjudicator_formation(formation, formation_path)
    adjudicator_verification = build_program_adjudicator_verification(
        adjudicator_formation_path=formation_path
    )
    write_program_adjudicator_verification(
        adjudicator_verification, adjudicator_verification_path
    )
    delegation = build_program_adjudicator_delegation(
        manifest_path=candidate_root / "manifest.json",
        adjudicator_verification_path=adjudicator_verification_path,
    )
    write_program_adjudicator_delegation(delegation, delegation_path)

    assert formation["schema_version"] == "program-adjudicator-formation-v1"
    assert formation["status"] == "formed"
    assert formation["effect"]["provider_called"] is False
    assert formation["non_authority"]["activation_authority"] is False
    adjudicator = formation["program_adjudicator"]
    perspectives = {role["perspective"] for role in adjudicator["roles"]}
    assert "authority_boundary" in perspectives
    assert "canonical_mutation_safety" in perspectives
    assert "production activation" in adjudicator["forbidden_outputs"]
    assert "canonical target mutation" in adjudicator["forbidden_outputs"]

    assert (
        adjudicator_verification["schema_version"]
        == "program-adjudicator-verification-v1"
    )
    assert adjudicator_verification["status"] == "verified"
    assert (
        adjudicator_verification["approved_for_program_evidence_adjudication"] is True
    )
    assert adjudicator_verification["failed_checks"] == []
    assert adjudicator_verification["effect"]["provider_called"] is False
    assert all(check["ok"] is True for check in adjudicator_verification["checks"])

    assert delegation["schema_version"] == "program-adjudicator-delegation-v1"
    assert delegation["status"] == "delegated"
    assert delegation["dspx_meta_adjudicator"]["id"] == "dspx_meta_adjudicator_v1"
    assert delegation["generated_program_adjudicator"] == {
        "id": "dspx_program_adjudicator_v1",
        "kind": "ai_agent",
        "authority": "required_for_promotion",
        "status": "pending",
        "approved_to_decide": True,
        "decision_scope": "generated_program_local_promotion_decision_only",
        "promotion_authority": False,
        "activation_authority": False,
        "source": "manifest.program_promotion_review.adjudicator",
    }
    assert delegation["non_authority"]["promotion_authority"] is False
    assert delegation["effect"]["governance_mutated"] is False

    written_formation = json.loads(formation_path.read_text(encoding="utf-8"))
    written_verification = json.loads(
        adjudicator_verification_path.read_text(encoding="utf-8")
    )
    assert written_formation["schema_version"] == "program-adjudicator-formation-v1"
    assert (
        written_verification["schema_version"] == "program-adjudicator-verification-v1"
    )


def test_program_adjudicator_formation_and_verification_cli_write_json(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_out = tmp_path / "jury-requirements.json"
    selection_out = tmp_path / "meta-jury-selection.json"
    jury_verification_out = tmp_path / "jury-verification.json"
    formation_out = tmp_path / "adjudicator-formation.json"
    adjudicator_verification_out = tmp_path / "adjudicator-verification.json"
    delegation_out = tmp_path / "adjudicator-delegation.json"

    for args in (
        [
            "program-promote",
            "jury-requirements",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--out",
            str(requirements_out),
            "--json",
        ],
        [
            "program-promote",
            "jury-panel",
            "--jury-requirements",
            str(requirements_out),
            "--out",
            str(selection_out),
            "--json",
        ],
        [
            "program-promote",
            "verify-jury-panel",
            "--jury-selection",
            str(selection_out),
            "--out",
            str(jury_verification_out),
            "--json",
        ],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output

    formation_result = runner.invoke(
        app,
        [
            "program-promote",
            "adjudicator-formation",
            "--jury-verification",
            str(jury_verification_out),
            "--out",
            str(formation_out),
            "--json",
        ],
    )
    assert formation_result.exit_code == 0, formation_result.output
    formation_payload = json.loads(formation_result.output)
    assert formation_payload["schema_version"] == "program-adjudicator-formation-v1"
    assert formation_payload["status"] == "formed"

    verification_result = runner.invoke(
        app,
        [
            "program-promote",
            "verify-program-adjudicator",
            "--adjudicator-formation",
            str(formation_out),
            "--out",
            str(adjudicator_verification_out),
            "--json",
        ],
    )
    assert verification_result.exit_code == 0, verification_result.output
    verification_payload = json.loads(verification_result.output)
    assert (
        verification_payload["schema_version"] == "program-adjudicator-verification-v1"
    )
    assert verification_payload["status"] == "verified"
    assert adjudicator_verification_out.exists()

    delegation_result = runner.invoke(
        app,
        [
            "program-promote",
            "adjudicator-delegation",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--adjudicator-verification",
            str(adjudicator_verification_out),
            "--out",
            str(delegation_out),
            "--json",
        ],
    )
    assert delegation_result.exit_code == 0, delegation_result.output
    delegation_payload = json.loads(delegation_result.output)
    assert delegation_payload["schema_version"] == "program-adjudicator-delegation-v1"
    assert delegation_payload["status"] == "delegated"
    assert (
        delegation_payload["generated_program_adjudicator"]["id"]
        == "dspx_program_adjudicator_v1"
    )
    assert delegation_out.exists()


def _write_minimal_activation_packet(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "generated-cognition-program-production-activation-packet-v1",
                "canonical_binding_ref": None,
                "boundary_checks": {
                    "dspx_activation_authority": False,
                    "jury_promotion_authority": False,
                    "oracle_promotion_authority": False,
                },
                "effect": {
                    "production_activation_applied": False,
                    "ak_mutated": False,
                    "external_authority_mutated": False,
                },
                "non_authority": {"governance_authority": False},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_program_evidence_adjudication_and_behavior_trace_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    formation_path = tmp_path / "program_adjudicator_formation.json"
    adjudicator_verification_path = tmp_path / "program_adjudicator_verification.json"
    delegation_path = tmp_path / "program_adjudicator_delegation.json"
    activation_packet_path = candidate_root / "activation_packet.json"
    evidence_adjudication_path = tmp_path / "program_evidence_adjudication.json"
    trace_path = tmp_path / "adjudication_behavior_trace.json"

    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_jury_requirements(requirements, requirements_path)
    selection = build_program_meta_jury_selection(
        jury_requirements_path=requirements_path
    )
    write_program_meta_jury_selection(selection, selection_path)
    jury_verification = build_program_jury_verification(
        jury_selection_path=selection_path
    )
    write_program_jury_verification(jury_verification, jury_verification_path)
    formation = build_program_adjudicator_formation(
        jury_verification_path=jury_verification_path
    )
    write_program_adjudicator_formation(formation, formation_path)
    adjudicator_verification = build_program_adjudicator_verification(
        adjudicator_formation_path=formation_path
    )
    write_program_adjudicator_verification(
        adjudicator_verification, adjudicator_verification_path
    )
    delegation = build_program_adjudicator_delegation(
        manifest_path=candidate_root / "manifest.json",
        adjudicator_verification_path=adjudicator_verification_path,
    )
    write_program_adjudicator_delegation(delegation, delegation_path)
    _write_minimal_activation_packet(activation_packet_path)

    adjudication = build_program_evidence_adjudication(
        adjudicator_verification_path=adjudicator_verification_path,
        manifest_path=candidate_root / "manifest.json",
        activation_packet_path=activation_packet_path,
    )
    write_program_evidence_adjudication(adjudication, evidence_adjudication_path)
    trace = build_program_adjudication_behavior_trace(
        evidence_adjudication_path=evidence_adjudication_path
    )
    write_program_adjudication_behavior_trace(trace, trace_path)

    assert adjudication["schema_version"] == "program-evidence-adjudication-v1"
    assert adjudication["status"] == "evidence_adjudicated"
    assert adjudication["non_authority"]["activation_authority"] is False
    assert adjudication["effect"]["provider_called"] is False
    assert adjudication["aggregate"]["activation_approved"] is False
    assert isinstance(adjudication["aggregate"]["ready_for_domain_decision"], bool)
    assert {item["perspective"] for item in adjudication["role_judgments"]} >= {
        "behavior_evidence",
        "authority_boundary",
    }

    assert trace["schema_version"] == "program-adjudication-behavior-trace-v1"
    assert trace["status"] == "trace_ready_for_publication_preflight"
    assert (
        trace["oracle_postgres_publication"]["shared_oracle_write_performed"] is False
    )
    assert trace["gepa_improvement_lane"]["activation_authority"] is False
    assert trace_path.exists()

    decision_path = tmp_path / "promotion_decision_record.json"
    decision = build_generated_program_adjudicator_decision_record(
        evidence_adjudication_path=evidence_adjudication_path,
        adjudicator_delegation_path=delegation_path,
    )
    write_program_promotion_decision_record(decision, decision_path)

    assert decision["schema_version"] == "program-promotion-decision-record-v1"
    assert decision["status"] == "recorded"
    assert decision["decided_by"] == "dspx_program_adjudicator_v1"
    assert (
        decision["adjudicator_delegation"]["decided_by"] == "dspx_meta_adjudicator_v1"
    )
    expected_outcome = (
        "withhold"
        if adjudication["aggregate"]["ready_for_domain_decision"] is True
        else "request_more_evidence"
    )
    assert decision["outcome"] == expected_outcome
    assert decision["review_snapshot"]["ready_for_adjudicator_review"] is (
        adjudication["aggregate"]["ready_for_domain_decision"] is True
    )
    assert decision["non_authority"]["dspx_adjudicator_evidence_only"] is True
    assert decision["non_authority"]["promotion_authority"] is False
    assert decision["effect"]["governance_mutated"] is False
    assert decision_path.exists()


def test_generated_program_adjudicator_decision_uses_dspx_meta_delegation(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "program_evidence_adjudication.json"
    delegation_path = tmp_path / "program_adjudicator_delegation.json"
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": "program-evidence-adjudication-v1",
                "status": "evidence_adjudicated",
                "identity": {"candidate_id": "prog-cand-ready"},
                "aggregate": {
                    "recommendation": "ready_for_domain_decision_not_activation",
                    "ready_for_domain_decision": True,
                    "activation_approved": False,
                    "missing_evidence": ["canonical binding ref before rollout"],
                    "judgment_counts": {"supports_domain_review": 7},
                },
                "non_authority": {
                    "activation_authority": False,
                    "governance_authority": False,
                    "oracle_authority": False,
                    "promotion_authority": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    delegation_path.write_text(
        json.dumps(
            {
                "schema_version": "program-adjudicator-delegation-v1",
                "status": "delegated",
                "dspx_meta_adjudicator": {"id": "dspx_meta_adjudicator_v1"},
                "generated_program_adjudicator": {
                    "id": "dspx_program_adjudicator_v1",
                    "kind": "ai_agent",
                    "approved_to_decide": True,
                    "decision_scope": "generated_program_local_promotion_decision_only",
                },
                "non_authority": {
                    "activation_authority": False,
                    "governance_authority": False,
                    "oracle_authority": False,
                    "promotion_authority": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    decision = build_generated_program_adjudicator_decision_record(
        evidence_adjudication_path=evidence_path,
        adjudicator_delegation_path=delegation_path,
    )

    assert decision["outcome"] == "withhold"
    assert decision["decided_by"] == "dspx_program_adjudicator_v1"
    assert (
        decision["adjudicator_delegation"]["decided_by"] == "dspx_meta_adjudicator_v1"
    )
    assert decision["review_snapshot"]["ready_for_adjudicator_review"] is True
    assert (
        "canonical binding ref before rollout"
        in decision["review_snapshot"]["missing_required_evidence"]
    )
    assert decision["non_authority"]["promotion_authority"] is False


def test_program_evidence_adjudication_and_behavior_trace_cli_write_json(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_out = tmp_path / "jury-requirements.json"
    selection_out = tmp_path / "meta-jury-selection.json"
    jury_verification_out = tmp_path / "jury-verification.json"
    formation_out = tmp_path / "adjudicator-formation.json"
    adjudicator_verification_out = tmp_path / "adjudicator-verification.json"
    delegation_out = tmp_path / "adjudicator-delegation.json"
    activation_packet_path = candidate_root / "activation_packet.json"
    evidence_out = tmp_path / "evidence-adjudication.json"
    trace_out = tmp_path / "adjudication-trace.json"
    _write_minimal_activation_packet(activation_packet_path)

    for args in (
        [
            "program-promote",
            "jury-requirements",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--out",
            str(requirements_out),
            "--json",
        ],
        [
            "program-promote",
            "jury-panel",
            "--jury-requirements",
            str(requirements_out),
            "--out",
            str(selection_out),
            "--json",
        ],
        [
            "program-promote",
            "verify-jury-panel",
            "--jury-selection",
            str(selection_out),
            "--out",
            str(jury_verification_out),
            "--json",
        ],
        [
            "program-promote",
            "adjudicator-formation",
            "--jury-verification",
            str(jury_verification_out),
            "--out",
            str(formation_out),
            "--json",
        ],
        [
            "program-promote",
            "verify-program-adjudicator",
            "--adjudicator-formation",
            str(formation_out),
            "--out",
            str(adjudicator_verification_out),
            "--json",
        ],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output

    delegation_result = runner.invoke(
        app,
        [
            "program-promote",
            "adjudicator-delegation",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--adjudicator-verification",
            str(adjudicator_verification_out),
            "--out",
            str(delegation_out),
            "--json",
        ],
    )
    assert delegation_result.exit_code == 0, delegation_result.output

    adjudication_result = runner.invoke(
        app,
        [
            "program-promote",
            "evidence-adjudication",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--adjudicator-verification",
            str(adjudicator_verification_out),
            "--activation-packet",
            str(activation_packet_path),
            "--out",
            str(evidence_out),
            "--json",
        ],
    )
    assert adjudication_result.exit_code == 0, adjudication_result.output
    adjudication_payload = json.loads(adjudication_result.output)
    assert adjudication_payload["schema_version"] == "program-evidence-adjudication-v1"
    assert adjudication_payload["aggregate"]["activation_approved"] is False

    trace_result = runner.invoke(
        app,
        [
            "program-promote",
            "adjudication-behavior-trace",
            "--evidence-adjudication",
            str(evidence_out),
            "--out",
            str(trace_out),
            "--json",
        ],
    )
    assert trace_result.exit_code == 0, trace_result.output
    trace_payload = json.loads(trace_result.output)
    assert trace_payload["schema_version"] == "program-adjudication-behavior-trace-v1"
    assert (
        trace_payload["oracle_postgres_publication"]["shared_oracle_write_performed"]
        is False
    )
    assert trace_out.exists()

    decision_out = tmp_path / "generated-adjudicator-decision.json"
    decision_result = runner.invoke(
        app,
        [
            "program-promote",
            "generated-adjudicator-decision",
            "--evidence-adjudication",
            str(evidence_out),
            "--adjudicator-delegation",
            str(delegation_out),
            "--out",
            str(decision_out),
            "--json",
        ],
    )
    assert decision_result.exit_code == 0, decision_result.output
    decision_payload = json.loads(decision_result.output)
    assert decision_payload["schema_version"] == "program-promotion-decision-record-v1"
    assert decision_payload["decided_by"] == "dspx_program_adjudicator_v1"
    assert (
        decision_payload["adjudicator_delegation"]["decided_by"]
        == "dspx_meta_adjudicator_v1"
    )
    expected_outcome = (
        "withhold"
        if adjudication_payload["aggregate"]["ready_for_domain_decision"] is True
        else "request_more_evidence"
    )
    assert decision_payload["outcome"] == expected_outcome
    assert decision_payload["review_snapshot"]["ready_for_adjudicator_review"] is (
        adjudication_payload["aggregate"]["ready_for_domain_decision"] is True
    )
    assert decision_payload["non_authority"]["promotion_authority"] is False
    assert decision_out.exists()


def test_program_adjudication_gepa_example_sidecar(tmp_path: Path, monkeypatch) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    formation_path = tmp_path / "program_adjudicator_formation.json"
    adjudicator_verification_path = tmp_path / "program_adjudicator_verification.json"
    activation_packet_path = candidate_root / "activation_packet.json"
    evidence_adjudication_path = tmp_path / "program_evidence_adjudication.json"
    trace_path = tmp_path / "adjudication_behavior_trace.json"
    gepa_example_path = tmp_path / "adjudication_gepa_example.json"

    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_jury_requirements(requirements, requirements_path)
    selection = build_program_meta_jury_selection(
        jury_requirements_path=requirements_path
    )
    write_program_meta_jury_selection(selection, selection_path)
    jury_verification = build_program_jury_verification(
        jury_selection_path=selection_path
    )
    write_program_jury_verification(jury_verification, jury_verification_path)
    formation = build_program_adjudicator_formation(
        jury_verification_path=jury_verification_path
    )
    write_program_adjudicator_formation(formation, formation_path)
    adjudicator_verification = build_program_adjudicator_verification(
        adjudicator_formation_path=formation_path
    )
    write_program_adjudicator_verification(
        adjudicator_verification, adjudicator_verification_path
    )
    _write_minimal_activation_packet(activation_packet_path)
    adjudication = build_program_evidence_adjudication(
        adjudicator_verification_path=adjudicator_verification_path,
        manifest_path=candidate_root / "manifest.json",
        activation_packet_path=activation_packet_path,
    )
    write_program_evidence_adjudication(adjudication, evidence_adjudication_path)
    trace = build_program_adjudication_behavior_trace(
        evidence_adjudication_path=evidence_adjudication_path
    )
    write_program_adjudication_behavior_trace(trace, trace_path)

    example = build_program_adjudication_gepa_example(trace_path=trace_path)
    write_program_adjudication_gepa_example(example, gepa_example_path)

    assert example["schema_version"] == "program-adjudication-gepa-example-v1"
    assert example["status"] == "curated_pending_outcome_label"
    assert example["label"]["usable_for_gepa_training"] is False
    assert example["expected_output"]["activation_authority"] is False
    assert example["gepa_improvement_lane"]["activation_authority"] is False
    assert gepa_example_path.exists()


def test_program_adjudication_gepa_example_cli_write_json(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_out = tmp_path / "jury-requirements.json"
    selection_out = tmp_path / "meta-jury-selection.json"
    jury_verification_out = tmp_path / "jury-verification.json"
    formation_out = tmp_path / "adjudicator-formation.json"
    adjudicator_verification_out = tmp_path / "adjudicator-verification.json"
    activation_packet_path = candidate_root / "activation_packet.json"
    evidence_out = tmp_path / "evidence-adjudication.json"
    trace_out = tmp_path / "adjudication-trace.json"
    gepa_example_out = tmp_path / "adjudication-gepa-example.json"
    _write_minimal_activation_packet(activation_packet_path)

    for args in (
        [
            "program-promote",
            "jury-requirements",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--out",
            str(requirements_out),
            "--json",
        ],
        [
            "program-promote",
            "jury-panel",
            "--jury-requirements",
            str(requirements_out),
            "--out",
            str(selection_out),
            "--json",
        ],
        [
            "program-promote",
            "verify-jury-panel",
            "--jury-selection",
            str(selection_out),
            "--out",
            str(jury_verification_out),
            "--json",
        ],
        [
            "program-promote",
            "adjudicator-formation",
            "--jury-verification",
            str(jury_verification_out),
            "--out",
            str(formation_out),
            "--json",
        ],
        [
            "program-promote",
            "verify-program-adjudicator",
            "--adjudicator-formation",
            str(formation_out),
            "--out",
            str(adjudicator_verification_out),
            "--json",
        ],
        [
            "program-promote",
            "evidence-adjudication",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--adjudicator-verification",
            str(adjudicator_verification_out),
            "--activation-packet",
            str(activation_packet_path),
            "--out",
            str(evidence_out),
            "--json",
        ],
        [
            "program-promote",
            "adjudication-behavior-trace",
            "--evidence-adjudication",
            str(evidence_out),
            "--out",
            str(trace_out),
            "--json",
        ],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output

    result = runner.invoke(
        app,
        [
            "program-promote",
            "adjudication-gepa-example",
            "--trace",
            str(trace_out),
            "--out",
            str(gepa_example_out),
            "--outcome-label",
            "domain_accepted_for_review",
            "--feedback",
            "Good authority boundary preservation.",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "program-adjudication-gepa-example-v1"
    assert payload["status"] == "curated_with_outcome_label"
    assert payload["label"]["usable_for_gepa_training"] is True
    assert gepa_example_out.exists()


def test_program_evidence_adjudication_rejects_unverified_adjudicator(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    adjudicator_verification_path = tmp_path / "bad-adjudicator-verification.json"
    adjudicator_verification_path.write_text(
        json.dumps(
            {
                "schema_version": "program-adjudicator-verification-v1",
                "status": "revise_program_adjudicator",
                "approved_for_program_evidence_adjudication": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be verified"):
        build_program_evidence_adjudication(
            adjudicator_verification_path=adjudicator_verification_path,
            manifest_path=candidate_root / "manifest.json",
        )


def test_program_adjudicator_formation_rejects_unverified_selection_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    mismatched_selection_path = tmp_path / "mismatched_meta_jury_selection.json"

    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_jury_requirements(requirements, requirements_path)
    selection = build_program_meta_jury_selection(
        jury_requirements_path=requirements_path
    )
    write_program_meta_jury_selection(selection, selection_path)
    jury_verification = build_program_jury_verification(
        jury_selection_path=selection_path
    )
    write_program_jury_verification(jury_verification, jury_verification_path)

    mismatched_selection = dict(selection)
    mismatched_selection["selected_jurors"] = selection["selected_jurors"][:-1]
    write_program_meta_jury_selection(mismatched_selection, mismatched_selection_path)

    with pytest.raises(ValueError, match="verified jury selection hash"):
        build_program_adjudicator_formation(
            jury_verification_path=jury_verification_path,
            jury_selection_path=mismatched_selection_path,
        )


def test_program_adjudicator_formation_rejects_missing_verified_selection_hash(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"

    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_jury_requirements(requirements, requirements_path)
    selection = build_program_meta_jury_selection(
        jury_requirements_path=requirements_path
    )
    write_program_meta_jury_selection(selection, selection_path)
    jury_verification = build_program_jury_verification(
        jury_selection_path=selection_path
    )
    jury_verification["jury_selection"].pop("sha256")
    write_program_jury_verification(jury_verification, jury_verification_path)

    with pytest.raises(ValueError, match="bind the verified jury selection sha256"):
        build_program_adjudicator_formation(
            jury_verification_path=jury_verification_path,
            jury_selection_path=selection_path,
        )


def test_program_adjudicator_verification_rejects_forged_formation_provenance(
    tmp_path: Path,
) -> None:
    formation_path = tmp_path / "forged-formation.json"
    formation_path.write_text(
        json.dumps(
            {
                "schema_version": "program-adjudicator-formation-v1",
                "status": "formed",
                "program_adjudicator": {
                    "id": "forged",
                    "model_backed": False,
                    "roles": [
                        {
                            "role_id": "program_adjudicator_authority_boundary",
                            "perspective": "authority_boundary",
                            "model_backed": False,
                        }
                    ],
                    "forbidden_outputs": [
                        "production activation",
                        "canonical target mutation",
                        "AK/governance mutation",
                        "Oracle promotion authority",
                    ],
                },
                "non_authority": {
                    "activation_authority": False,
                    "promotion_authority": False,
                    "oracle_authority": False,
                    "governance_authority": False,
                    "external_authority": False,
                    "external_mutation": False,
                },
                "effect": {
                    "candidate_files_mutated": False,
                    "canonical_target_mutated": False,
                    "ak_mutated": False,
                    "governance_mutated": False,
                    "oracle_index_mutated": False,
                    "shared_oracle_mutated": False,
                    "provider_called": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    verification = build_program_adjudicator_verification(
        adjudicator_formation_path=formation_path
    )

    assert verification["status"] == "revise_program_adjudicator"
    assert (
        "verified_jury_provenance_present_and_hash_bound"
        in verification["failed_checks"]
    )
    assert (
        "jury_selection_provenance_present_and_hash_bound"
        in verification["failed_checks"]
    )


def test_program_adjudicator_verification_rejects_authority_effect_drift(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    formation_path = tmp_path / "program_adjudicator_formation.json"

    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_jury_requirements(requirements, requirements_path)
    selection = build_program_meta_jury_selection(
        jury_requirements_path=requirements_path
    )
    write_program_meta_jury_selection(selection, selection_path)
    jury_verification = build_program_jury_verification(
        jury_selection_path=selection_path
    )
    write_program_jury_verification(jury_verification, jury_verification_path)
    formation = build_program_adjudicator_formation(
        jury_verification_path=jury_verification_path
    )
    formation["effect"]["ak_mutated"] = True
    write_program_adjudicator_formation(formation, formation_path)

    verification = build_program_adjudicator_verification(
        adjudicator_formation_path=formation_path
    )

    assert verification["status"] == "revise_program_adjudicator"
    assert "formation_has_no_authority_effect" in verification["failed_checks"]


def test_program_adjudicator_verification_rejects_authority_drift(
    tmp_path: Path,
) -> None:
    formation_path = tmp_path / "bad-formation.json"
    formation_path.write_text(
        json.dumps(
            {
                "schema_version": "program-adjudicator-formation-v1",
                "status": "formed",
                "program_adjudicator": {
                    "id": "bad",
                    "model_backed": False,
                    "roles": [
                        {
                            "role_id": "program_adjudicator_behavior",
                            "perspective": "behavior_evidence",
                            "model_backed": False,
                        }
                    ],
                    "forbidden_outputs": ["production activation"],
                },
                "non_authority": {"activation_authority": False},
                "effect": {"provider_called": False},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    verification = build_program_adjudicator_verification(
        adjudicator_formation_path=formation_path
    )

    assert verification["status"] == "revise_program_adjudicator"
    assert verification["approved_for_program_evidence_adjudication"] is False
    assert "authority_boundary_role_present" in verification["failed_checks"]
    assert (
        "forbidden_outputs_preserve_authority_boundary" in verification["failed_checks"]
    )


def test_meta_adjudication_plan_tracks_present_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    jury = build_program_jury_execution_result(
        manifest_path=candidate_root / "manifest.json"
    )
    jury_path = candidate_root / "jury_results.json"
    write_program_jury_execution_result(jury, jury_path)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    formation_path = tmp_path / "program_adjudicator_formation.json"
    adjudicator_verification_path = tmp_path / "program_adjudicator_verification.json"
    delegation_path = tmp_path / "program_adjudicator_delegation.json"
    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_jury_requirements(requirements, requirements_path)
    selection = build_program_meta_jury_selection(
        jury_requirements_path=requirements_path
    )
    write_program_meta_jury_selection(selection, selection_path)
    jury_verification = build_program_jury_verification(
        jury_selection_path=selection_path
    )
    write_program_jury_verification(jury_verification, jury_verification_path)
    formation = build_program_adjudicator_formation(
        jury_verification_path=jury_verification_path
    )
    write_program_adjudicator_formation(formation, formation_path)
    adjudicator_verification = build_program_adjudicator_verification(
        adjudicator_formation_path=formation_path
    )
    write_program_adjudicator_verification(
        adjudicator_verification, adjudicator_verification_path
    )
    delegation = build_program_adjudicator_delegation(
        manifest_path=candidate_root / "manifest.json",
        adjudicator_verification_path=adjudicator_verification_path,
    )
    write_program_adjudicator_delegation(delegation, delegation_path)

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        jury_results_path=jury_path,
        program_adjudicator_delegation_path=delegation_path,
    )

    assert plan["sidecars"]["jury_results"]["status"] == "present"
    assert (
        plan["sidecars"]["jury_results"]["schema_version"] == "program-jury-results-v1"
    )
    assert plan["sidecars"]["program_adjudicator_delegation"]["status"] == "present"
    assert (
        plan["sidecars"]["program_adjudicator_delegation"]["schema_version"]
        == "program-adjudicator-delegation-v1"
    )
    assert "program_jury_results" not in plan["missing_evidence"]
    assert "program_adjudicator_delegation" not in plan["missing_evidence"]


def test_meta_adjudication_plan_cli_writes_json(tmp_path: Path, monkeypatch) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    out = tmp_path / "meta-adjudication-plan.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "meta-adjudication-plan",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--out",
            str(out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "program-meta-adjudication-plan-v1"
    assert out.exists()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["manifest"]["path"] == str(candidate_root / "manifest.json")
    assert written["effect"]["candidate_files_mutated"] is False


def test_write_meta_adjudication_plan_rejects_wrong_schema(tmp_path: Path) -> None:
    try:
        write_program_meta_adjudication_plan(
            {"schema_version": "wrong-schema"}, tmp_path / "plan.json"
        )
    except ValueError as exc:
        assert "program-meta-adjudication-plan-v1" in str(exc)
    else:  # pragma: no cover - defensive clarity
        raise AssertionError("expected wrong schema to be rejected")
