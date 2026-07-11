# summary: "Tests program-adjudicator formation, verification, delegation, provenance binding, and non-authority safeguards."
# read_when:
#   - "Changing meta-adjudicator formation, program-adjudicator verification, delegation CLI flows, or authority-boundary checks."

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from dspx.services.program_meta_adjudication import (
    build_program_adjudicator_delegation,
    build_program_adjudicator_formation,
    build_program_adjudicator_verification,
    build_program_jury_requirements,
    build_program_jury_verification,
    build_program_meta_jury_selection,
    write_program_adjudicator_delegation,
    write_program_adjudicator_formation,
    write_program_adjudicator_verification,
    write_program_jury_requirements,
    write_program_jury_verification,
    write_program_meta_jury_selection,
)
from program_meta_adjudication_helpers import (
    _materialize_obsidian_like_candidate,
    runner,
)


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
