from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from dspx.services.program_jury_execution import (
    build_program_jury_execution_result,
    write_program_jury_execution_result,
)
from dspx.services.program_runtime_episode import run_program_runtime_episode
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
    validate_program_meta_adjudication_plan_contract,
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
)
from program_activation_packet_shared import _write_oracle_publication_receipt
from program_meta_adjudication_helpers import (
    _materialize_obsidian_like_candidate,
    _write_minimal_activation_packet,
    runner,
)


def _remove_candidate_behavior_sidecars(candidate_root: Path) -> None:
    for name in ("behavior_results.json", "behavior_episode.json"):
        path = candidate_root / name
        if path.exists():
            path.unlink()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_runtime_inputs(tmp_path: Path) -> Path:
    inputs_path = tmp_path / "runtime_inputs.json"
    inputs_path.write_text(
        json.dumps(
            {
                "marker_markdown": "# Close Reading\nUse source-grounded evidence.",
                "source_package_json": '{"source_id":"zotero:user:demo/DEMO2026"}',
                "existing_wiki_index_json": "{}",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return inputs_path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _valid_generation_target_contract(contract_sha: str = "contract-sha") -> dict:
    return {
        "schema_version": "gen-target-contract-v1",
        "identity": {
            "intent_sha256": "intent-sha",
            "contract_sha256": contract_sha,
            "validator_version": "v1",
        },
        "target": {
            "id": "obsidian_pdf_transition",
            "owner": "obsidian/_System",
            "owner_refs": ["/vault/_System/architecture/pdf-transition.md"],
        },
        "contract_source": "hand_authored",
        "confirmation_status": "operator_confirmed_for_generation_gate",
        "risk_tier": "authority_adjacent",
        "protocol": {
            "required_stages": ["source_package", "review"],
            "artifact_families": ["source", "transition", "review"],
            "forbidden_shortcuts": ["draft_canonical_note_before_review"],
        },
        "source_policy": {
            "provenance_required": True,
            "language_policy": "preserve_source_language",
        },
        "fitness": {"required_adversarial_cases": ["target_shortcut"]},
        "requests": {},
        "non_authority": {
            "activation_authority": False,
            "promotion_authority": False,
            "oracle_authority": False,
            "governance_authority": False,
            "external_mutation": False,
        },
        "effect": {
            "candidate_files_mutated": False,
            "canonical_target_mutated": False,
            "ak_mutated": False,
            "governance_mutated": False,
        },
    }


def _valid_generation_fitness_suite(
    *, target_contract_sha: str = "contract-sha", suite_sha: str = "suite-sha"
) -> dict:
    return {
        "schema_version": "gen-fitness-suite-v1",
        "identity": {
            "target_contract_sha256": target_contract_sha,
            "suite_sha256": suite_sha,
        },
        "cases": [
            {
                "case_id": "target-protocol-fidelity",
                "input_fixture": "fixtures/source.json",
                "allowed_artifact_families": ["transition", "review"],
                "forbidden_outputs_or_effects": ["draft_canonical_note_before_review"],
                "source_provenance_assertions": [{"required": True}],
                "target_stage_assertions": [{"stage": "review"}],
                "expected_failure_label": "target_shortcut",
                "validator": "dspx.local_check",
            }
        ],
    }


def _valid_generation_fitness_results(
    *,
    candidate_sha: str,
    target_contract_sha: str = "contract-sha",
    suite_sha: str = "suite-sha",
) -> dict:
    return {
        "schema_version": "gen-fitness-results-v1",
        "identity": {
            "candidate_manifest_sha256": candidate_sha,
            "target_contract_sha256": target_contract_sha,
            "fitness_suite_sha256": suite_sha,
        },
        "status": "fitness_failed",
        "rendered_state": "withheld_for_target_protocol_failure",
        "cases": [
            {
                "case_id": "target-protocol-fidelity",
                "status": "failed",
                "evidence_refs": ["generation_traceability.json"],
            }
        ],
    }


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


def test_meta_adjudication_plan_tracks_present_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    jury = build_program_jury_execution_result(
        manifest_path=candidate_root / "manifest.json"
    )
    jury_path = tmp_path / "promotion" / "jury_results.json"
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
        plan["sidecars"]["jury_results"]["schema_version"] == "program-jury-results-v2"
    )
    assert plan["sidecars"]["program_adjudicator_delegation"]["status"] == "present"
    assert (
        plan["sidecars"]["program_adjudicator_delegation"]["schema_version"]
        == "program-adjudicator-delegation-v1"
    )
    assert "program_jury_results" not in plan["missing_evidence"]
    assert "program_adjudicator_delegation" not in plan["missing_evidence"]


def _candidate_identity(candidate_root: Path) -> dict[str, str | None]:
    manifest = json.loads(
        (candidate_root / "manifest.json").read_text(encoding="utf-8")
    )
    request = manifest["request"]
    candidate = manifest["candidate_assembly"]
    execution = manifest["execution_episode"]
    receipt = manifest["receipt_bundle"]
    return {
        "request_id": request["request_id"],
        "candidate_id": candidate["candidate_id"],
        "assembly_id": candidate["assembly_id"],
        "episode_id": execution["episode_id"],
        "receipt_bundle_id": receipt["receipt_bundle_id"],
    }


def _write_decision_record(path: Path, *, candidate_root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "program-promotion-decision-record-v1",
                "status": "recorded",
                "outcome": "withhold",
                "promotion_state_after_decision": "not_promoted",
                "decided_by": "local-adjudicator",
                "rationale": "Insufficient evidence for activation.",
                "identity": _candidate_identity(candidate_root),
                "effect": {
                    "local_decision_record_only": True,
                    "program_files_mutated": False,
                    "refined_review_mutated": False,
                    "new_candidate_generated": False,
                    "external_authority_mutated": False,
                    "governance_mutated": False,
                },
                "non_authority": {
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
                    "promotion_authority": False,
                    "winner_selection": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_adjudicator_chain(candidate_root: Path, tmp_path: Path) -> dict[str, Path]:
    _ = tmp_path
    requirements_path = candidate_root / "jury_requirements.json"
    selection_path = candidate_root / "meta_jury_selection.json"
    verification_path = candidate_root / "jury_verification.json"
    formation_path = candidate_root / "program_adjudicator_formation.json"
    adjudicator_verification_path = (
        candidate_root / "program_adjudicator_verification.json"
    )
    delegation_path = candidate_root / "program_adjudicator_delegation.json"

    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_jury_requirements(requirements, requirements_path)
    selection = build_program_meta_jury_selection(
        jury_requirements_path=requirements_path
    )
    write_program_meta_jury_selection(selection, selection_path)
    verification = build_program_jury_verification(jury_selection_path=selection_path)
    write_program_jury_verification(verification, verification_path)
    formation = build_program_adjudicator_formation(
        jury_verification_path=verification_path
    )
    write_program_adjudicator_formation(formation, formation_path)
    adjudicator_verification = build_program_adjudicator_verification(
        adjudicator_formation_path=formation_path
    )
    write_program_adjudicator_verification(
        adjudicator_verification,
        adjudicator_verification_path,
    )
    delegation = build_program_adjudicator_delegation(
        manifest_path=candidate_root / "manifest.json",
        adjudicator_verification_path=adjudicator_verification_path,
    )
    write_program_adjudicator_delegation(delegation, delegation_path)
    return {
        "requirements": requirements_path,
        "selection": selection_path,
        "verification": verification_path,
        "formation": formation_path,
        "adjudicator_verification": adjudicator_verification_path,
        "delegation": delegation_path,
    }


def _write_refined_review(path: Path, *, candidate_root: Path, tmp_path: Path) -> None:
    oracle_report_path = tmp_path / "oracle" / "program_oracle_report.json"
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    oracle_report_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    oracle_report_path.write_text(
        json.dumps(
            {"schema_version": "program-oracle-evidence-report-v1", "records": []},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    proposal_path.write_text(
        json.dumps(
            {"schema_version": "program-refinement-proposal-v1", "status": "proposed"},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    created_from_paths = {
        "manifest": candidate_root / "manifest.json",
        "oracle_report": oracle_report_path,
        "refinement_proposal": proposal_path,
        "original_promotion_review": candidate_root / "promotion_review.json",
        "original_promotion_adjudication_request": candidate_root
        / "promotion_adjudication_request.json",
        "original_promotion_decision_template": candidate_root
        / "promotion_decision_template.json",
        "behavior_results": candidate_root / "behavior_results.json",
        "behavior_episode": candidate_root / "behavior_episode.json",
    }
    created_from: dict[str, str] = {}
    for key, source_path in created_from_paths.items():
        created_from[f"{key}_path"] = str(source_path.resolve())
        created_from[f"{key}_sha256"] = _sha256_file(source_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "program-promotion-review-refined-v1",
                "status": "needs_more_evidence",
                "promotion_state": "not_promoted",
                "identity": _candidate_identity(candidate_root),
                "created_from": created_from,
                "evidence_summary": {"model_jury_results": {"present": False}},
                "non_authority": {
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
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_meta_adjudication_plan_revalidates_adjudicator_chain_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    paths = _write_adjudicator_chain(candidate_root, tmp_path)

    tampered_selection = json.loads(paths["selection"].read_text(encoding="utf-8"))
    tampered_selection["non_authority"]["promotion_authority"] = True
    paths["selection"].write_text(
        json.dumps(tampered_selection, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json"
    )

    assert plan["sidecars"]["meta_jury_selection"]["status"] == "contract_invalid"
    assert "promotion_authority" in plan["sidecars"]["meta_jury_selection"]["warning"]

    forged_plan = dict(plan)
    forged_sidecars = {key: dict(value) for key, value in plan["sidecars"].items()}
    forged_sidecars["meta_jury_selection"] = {
        **forged_sidecars["meta_jury_selection"],
        "status": "present",
        "sha256": _sha256_file(paths["selection"]),
    }
    forged_plan["sidecars"] = forged_sidecars

    with pytest.raises(ValueError, match="jury_verification|promotion_authority"):
        validate_program_meta_adjudication_plan_contract(
            forged_plan,
            expected_identities=[forged_plan["identity"]],
            valid_manifest_hashes=[forged_plan["manifest"]["sha256"]],
        )


def test_meta_adjudication_plan_revalidates_delegation_chain_refs(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    paths = _write_adjudicator_chain(candidate_root, tmp_path)

    tampered_delegation = json.loads(paths["delegation"].read_text(encoding="utf-8"))
    tampered_delegation["program_adjudicator_verification"]["sha256"] = "0" * 64
    paths["delegation"].write_text(
        json.dumps(tampered_delegation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        program_adjudicator_delegation_path=paths["delegation"],
    )

    assert (
        plan["sidecars"]["program_adjudicator_delegation"]["status"]
        == "contract_invalid"
    )
    assert (
        "program_adjudicator_verification"
        in plan["sidecars"]["program_adjudicator_delegation"]["warning"]
    )

    forged_plan = dict(plan)
    forged_sidecars = {key: dict(value) for key, value in plan["sidecars"].items()}
    forged_sidecars["program_adjudicator_delegation"] = {
        **forged_sidecars["program_adjudicator_delegation"],
        "status": "present",
        "sha256": _sha256_file(paths["delegation"]),
    }
    forged_plan["sidecars"] = forged_sidecars

    with pytest.raises(ValueError, match="program_adjudicator_verification"):
        validate_program_meta_adjudication_plan_contract(
            forged_plan,
            expected_identities=[forged_plan["identity"]],
            valid_manifest_hashes=[forged_plan["manifest"]["sha256"]],
        )


def test_meta_adjudication_plan_revalidates_target_fidelity_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    fitness_results_path = tmp_path / "generation_fitness_results.json"
    fitness_results_path.write_text(
        json.dumps(
            {
                "schema_version": "gen-fitness-results-v1",
                "identity": {
                    "candidate_manifest_sha256": _sha256_file(
                        candidate_root / "manifest.json"
                    ),
                    "target_contract_sha256": "contract-sha",
                    "fitness_suite_sha256": "suite-sha",
                },
                "status": "fitness_passed",
                "rendered_state": "approval_granted",
                "cases": [
                    {
                        "case_id": "target-protocol-fidelity",
                        "status": "passed",
                        "evidence_refs": ["generation_traceability.json"],
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        generation_fitness_results_path=fitness_results_path,
    )

    sidecar = plan["sidecars"]["generation_fitness_results"]
    assert sidecar["status"] == "contract_invalid"
    assert "fitness_passed_requires_command_safe_rendering" in sidecar["warning"]

    forged_plan = dict(plan)
    forged_sidecars = {key: dict(value) for key, value in plan["sidecars"].items()}
    forged_sidecars["generation_fitness_results"] = {
        **forged_sidecars["generation_fitness_results"],
        "status": "present",
        "sha256": _sha256_file(fitness_results_path),
    }
    forged_plan["sidecars"] = forged_sidecars

    with pytest.raises(
        ValueError, match="fitness_passed_requires_command_safe_rendering"
    ):
        validate_program_meta_adjudication_plan_contract(
            forged_plan,
            expected_identities=[forged_plan["identity"]],
            valid_manifest_hashes=[forged_plan["manifest"]["sha256"]],
        )


def test_meta_adjudication_plan_rejects_foreign_target_fidelity_sidecar(
    tmp_path: Path, monkeypatch
) -> None:
    current_dir = tmp_path / "current"
    foreign_dir = tmp_path / "foreign"
    current_dir.mkdir()
    foreign_dir.mkdir()
    current_root = _materialize_obsidian_like_candidate(current_dir, monkeypatch)
    foreign_root = _materialize_obsidian_like_candidate(foreign_dir, monkeypatch)
    fitness_results_path = tmp_path / "foreign_generation_fitness_results.json"
    fitness_results_path.write_text(
        json.dumps(
            {
                "schema_version": "gen-fitness-results-v1",
                "identity": {
                    "candidate_manifest_sha256": _sha256_file(
                        foreign_root / "manifest.json"
                    ),
                    "target_contract_sha256": "contract-sha",
                    "fitness_suite_sha256": "suite-sha",
                },
                "status": "fitness_passed",
                "rendered_state": "eligible_for_downstream_evidence_review",
                "cases": [
                    {
                        "case_id": "target-protocol-fidelity",
                        "status": "passed",
                        "evidence_refs": ["generation_traceability.json"],
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    plan = build_program_meta_adjudication_plan(
        manifest_path=current_root / "manifest.json",
        generation_fitness_results_path=fitness_results_path,
    )

    sidecar = plan["sidecars"]["generation_fitness_results"]
    assert sidecar["status"] == "contract_invalid"
    assert "candidate_manifest_sha256" in sidecar["warning"]

    forged_plan = dict(plan)
    forged_sidecars = {key: dict(value) for key, value in plan["sidecars"].items()}
    forged_sidecars["generation_fitness_results"] = {
        **forged_sidecars["generation_fitness_results"],
        "status": "present",
        "sha256": _sha256_file(fitness_results_path),
    }
    forged_plan["sidecars"] = forged_sidecars

    with pytest.raises(ValueError, match="candidate_manifest_sha256"):
        validate_program_meta_adjudication_plan_contract(
            forged_plan,
            expected_identities=[forged_plan["identity"]],
            valid_manifest_hashes=[forged_plan["manifest"]["sha256"]],
        )


def test_meta_adjudication_plan_rejects_malformed_candidate_manifest_hash(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    fitness_results_path = tmp_path / "generation_fitness_results.json"
    payload = _valid_generation_fitness_results(
        candidate_sha="not-a-sha",
        target_contract_sha="contract-sha",
        suite_sha="suite-sha",
    )
    _write_json(fitness_results_path, payload)

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        generation_fitness_results_path=fitness_results_path,
    )

    sidecar = plan["sidecars"]["generation_fitness_results"]
    assert sidecar["status"] == "contract_invalid"
    assert "candidate_manifest_sha256" in sidecar["warning"]

    forged_plan = dict(plan)
    forged_sidecars = {key: dict(value) for key, value in plan["sidecars"].items()}
    forged_sidecars["generation_fitness_results"] = {
        **forged_sidecars["generation_fitness_results"],
        "status": "present",
        "sha256": _sha256_file(fitness_results_path),
    }
    forged_plan["sidecars"] = forged_sidecars

    with pytest.raises(ValueError, match="candidate_manifest_sha256"):
        validate_program_meta_adjudication_plan_contract(
            forged_plan,
            expected_identities=[forged_plan["identity"]],
            valid_manifest_hashes=[forged_plan["manifest"]["sha256"]],
        )


def test_meta_adjudication_plan_rejects_target_fidelity_sibling_hash_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    target_contract_path = tmp_path / "generation_target_contract.json"
    fitness_suite_path = tmp_path / "generation_fitness_suite.json"
    fitness_results_path = tmp_path / "generation_fitness_results.json"
    _write_json(target_contract_path, _valid_generation_target_contract("contract-sha"))
    _write_json(
        fitness_suite_path,
        _valid_generation_fitness_suite(
            target_contract_sha="contract-sha", suite_sha="suite-sha"
        ),
    )
    _write_json(
        fitness_results_path,
        _valid_generation_fitness_results(
            candidate_sha=_sha256_file(candidate_root / "manifest.json"),
            target_contract_sha="other-contract-sha",
            suite_sha="suite-sha",
        ),
    )

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        generation_target_contract_path=target_contract_path,
        generation_fitness_suite_path=fitness_suite_path,
        generation_fitness_results_path=fitness_results_path,
    )

    sidecar = plan["sidecars"]["generation_fitness_results"]
    assert sidecar["status"] == "contract_invalid"
    assert "target_contract_sha256" in sidecar["warning"]

    forged_plan = dict(plan)
    forged_sidecars = {key: dict(value) for key, value in plan["sidecars"].items()}
    forged_sidecars["generation_fitness_results"] = {
        **forged_sidecars["generation_fitness_results"],
        "status": "present",
        "sha256": _sha256_file(fitness_results_path),
    }
    forged_plan["sidecars"] = forged_sidecars

    with pytest.raises(ValueError, match="target_contract_sha256"):
        validate_program_meta_adjudication_plan_contract(
            forged_plan,
            expected_identities=[forged_plan["identity"]],
            valid_manifest_hashes=[forged_plan["manifest"]["sha256"]],
        )


def test_meta_adjudication_plan_rejects_adjudicator_ref_outside_plan_graph(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    paths = _write_adjudicator_chain(candidate_root, tmp_path)
    alternate_selection_path = tmp_path / "alternate_meta_jury_selection.json"
    alternate_selection_path.write_text(
        paths["selection"].read_text(encoding="utf-8"), encoding="utf-8"
    )
    formation = json.loads(paths["formation"].read_text(encoding="utf-8"))
    formation["jury_selection"] = {
        "path": str(alternate_selection_path),
        "sha256": _sha256_file(alternate_selection_path),
        "schema_version": "program-meta-jury-selection-v1",
    }
    _write_json(paths["formation"], formation)

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
    )

    sidecar = plan["sidecars"]["program_adjudicator_formation"]
    assert sidecar["status"] == "contract_invalid"
    assert "plan sidecar meta_jury_selection" in sidecar["warning"]

    forged_plan = dict(plan)
    forged_sidecars = {key: dict(value) for key, value in plan["sidecars"].items()}
    forged_sidecars["program_adjudicator_formation"] = {
        **forged_sidecars["program_adjudicator_formation"],
        "status": "present",
        "sha256": _sha256_file(paths["formation"]),
    }
    forged_plan["sidecars"] = forged_sidecars

    with pytest.raises(ValueError, match="plan sidecar meta_jury_selection"):
        validate_program_meta_adjudication_plan_contract(
            forged_plan,
            expected_identities=[forged_plan["identity"]],
            valid_manifest_hashes=[forged_plan["manifest"]["sha256"]],
        )


def test_meta_adjudication_plan_rejects_malformed_minimum_jurors(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_path = candidate_root / "jury_requirements.json"
    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    requirements["minimum_jurors"] = "many"
    write_program_jury_requirements(requirements, requirements_path)

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json"
    )

    assert plan["sidecars"]["jury_requirements"]["status"] == "contract_invalid"
    assert "minimum_jurors" in plan["sidecars"]["jury_requirements"]["warning"]


def test_meta_adjudication_plan_rejects_foreign_jury_results_at_plan_build(
    tmp_path: Path, monkeypatch
) -> None:
    current_dir = tmp_path / "current"
    foreign_dir = tmp_path / "foreign"
    current_dir.mkdir()
    foreign_dir.mkdir()
    current_root = _materialize_obsidian_like_candidate(current_dir, monkeypatch)
    foreign_root = _materialize_obsidian_like_candidate(foreign_dir, monkeypatch)
    jury_path = tmp_path / "foreign_jury_results.json"
    jury = build_program_jury_execution_result(
        manifest_path=foreign_root / "manifest.json"
    )
    write_program_jury_execution_result(jury, jury_path)

    plan = build_program_meta_adjudication_plan(
        manifest_path=current_root / "manifest.json",
        jury_results_path=jury_path,
    )

    assert plan["sidecars"]["jury_results"]["status"] == "contract_invalid"
    assert "manifest sha256" in plan["sidecars"]["jury_results"]["warning"]


def test_meta_adjudication_plan_revalidates_jury_results_contract(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    jury_path = tmp_path / "promotion" / "jury_results.json"
    jury = build_program_jury_execution_result(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_jury_execution_result(jury, jury_path)

    tampered_jury = json.loads(jury_path.read_text(encoding="utf-8"))
    tampered_jury["created_from"]["behavior_results_sha256"] = "0" * 64
    jury_path.write_text(
        json.dumps(tampered_jury, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        jury_results_path=jury_path,
    )

    assert plan["sidecars"]["jury_results"]["status"] == "contract_invalid"
    assert "behavior results sha256" in plan["sidecars"]["jury_results"]["warning"]

    forged_plan = dict(plan)
    forged_sidecars = {key: dict(value) for key, value in plan["sidecars"].items()}
    forged_sidecars["jury_results"] = {
        **forged_sidecars["jury_results"],
        "status": "present",
        "sha256": _sha256_file(jury_path),
    }
    forged_plan["sidecars"] = forged_sidecars

    with pytest.raises(ValueError, match="behavior results sha256"):
        validate_program_meta_adjudication_plan_contract(
            forged_plan,
            expected_identities=[forged_plan["identity"]],
            valid_manifest_hashes=[forged_plan["manifest"]["sha256"]],
        )


def test_meta_adjudication_plan_revalidates_refined_review_contract(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    review_path = tmp_path / "promotion" / "promotion_review_refined.json"
    _write_refined_review(review_path, candidate_root=candidate_root, tmp_path=tmp_path)

    valid_plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        review_path=review_path,
    )
    assert valid_plan["sidecars"]["review"]["status"] == "present"

    tampered_review = json.loads(review_path.read_text(encoding="utf-8"))
    tampered_review["non_authority"]["promotion_authority"] = True
    review_path.write_text(
        json.dumps(tampered_review, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        review_path=review_path,
    )
    assert plan["sidecars"]["review"]["status"] == "contract_invalid"
    assert "promotion_authority" in plan["sidecars"]["review"]["warning"]

    forged_plan = dict(plan)
    forged_sidecars = {key: dict(value) for key, value in plan["sidecars"].items()}
    forged_sidecars["review"] = {
        **forged_sidecars["review"],
        "status": "present",
        "sha256": _sha256_file(review_path),
    }
    forged_plan["sidecars"] = forged_sidecars

    with pytest.raises(ValueError, match="promotion_authority"):
        validate_program_meta_adjudication_plan_contract(
            forged_plan,
            expected_identities=[forged_plan["identity"]],
            valid_manifest_hashes=[forged_plan["manifest"]["sha256"]],
        )


def test_meta_adjudication_plan_revalidates_decision_record_contract(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    decision_path = tmp_path / "promotion" / "promotion_decision_record.json"
    _write_decision_record(decision_path, candidate_root=candidate_root)

    valid_plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        decision_record_path=decision_path,
    )
    assert valid_plan["sidecars"]["decision_record"]["status"] == "present"

    tampered_decision = json.loads(decision_path.read_text(encoding="utf-8"))
    tampered_decision["non_authority"]["promotion_authority"] = True
    decision_path.write_text(
        json.dumps(tampered_decision, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        decision_record_path=decision_path,
    )
    assert plan["sidecars"]["decision_record"]["status"] == "contract_invalid"
    assert "promotion_authority" in plan["sidecars"]["decision_record"]["warning"]

    forged_plan = dict(plan)
    forged_sidecars = {key: dict(value) for key, value in plan["sidecars"].items()}
    forged_sidecars["decision_record"] = {
        **forged_sidecars["decision_record"],
        "status": "present",
        "sha256": _sha256_file(decision_path),
    }
    forged_plan["sidecars"] = forged_sidecars

    with pytest.raises(ValueError, match="promotion_authority"):
        validate_program_meta_adjudication_plan_contract(
            forged_plan,
            expected_identities=[forged_plan["identity"]],
            valid_manifest_hashes=[forged_plan["manifest"]["sha256"]],
        )


def test_meta_adjudication_plan_consumes_valid_runtime_episode(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    runtime_out = tmp_path / "runtime-episode"
    run_program_runtime_episode(
        manifest_path=candidate_root / "manifest.json",
        inputs_path=_write_runtime_inputs(tmp_path),
        outdir=runtime_out,
        skip_oracle_index=True,
    )
    runtime_episode_path = runtime_out / "runtime_episode.json"
    _remove_candidate_behavior_sidecars(candidate_root)

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        runtime_episode_path=runtime_episode_path,
    )

    runtime_status = plan["sidecars"]["runtime_episode"]
    assert runtime_status["status"] == "present"
    assert runtime_status["schema_version"] == "program-runtime-episode-v1"
    assert runtime_status["sha256"]
    assert "behavior_evidence" not in plan["missing_evidence"]
    assert not any(
        item["step"] == "run_runtime_episode" for item in plan["next_commands"]
    )


def test_meta_adjudication_plan_marks_invalid_runtime_episode_contract_invalid(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    runtime_out = tmp_path / "runtime-episode"
    run_program_runtime_episode(
        manifest_path=candidate_root / "manifest.json",
        inputs_path=_write_runtime_inputs(tmp_path),
        outdir=runtime_out,
        skip_oracle_index=True,
    )
    runtime_episode_path = runtime_out / "runtime_episode.json"
    _remove_candidate_behavior_sidecars(candidate_root)
    traces_path = runtime_out / "program_runtime_traces.json"
    traces = json.loads(traces_path.read_text(encoding="utf-8"))
    traces["sources"][0]["content_hash"] = "0" * 64
    traces_path.write_text(json.dumps(traces, indent=2, sort_keys=True) + "\n")

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        runtime_episode_path=runtime_episode_path,
    )

    runtime_status = plan["sidecars"]["runtime_episode"]
    assert runtime_status["present"] is True
    assert runtime_status["status"] == "contract_invalid"
    assert (
        "runtime episode program_runtime_traces_sha256 does not match current file"
        in runtime_status["warning"]
    )
    assert "behavior_evidence" in plan["missing_evidence"]
    assert any(item["step"] == "run_runtime_episode" for item in plan["next_commands"])


def test_meta_adjudication_plan_contract_rejects_runtime_episode_contract_drift(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    runtime_out = tmp_path / "runtime-episode"
    run_program_runtime_episode(
        manifest_path=candidate_root / "manifest.json",
        inputs_path=_write_runtime_inputs(tmp_path),
        outdir=runtime_out,
        skip_oracle_index=True,
    )
    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        runtime_episode_path=runtime_out / "runtime_episode.json",
    )
    traces_path = runtime_out / "program_runtime_traces.json"
    traces = json.loads(traces_path.read_text(encoding="utf-8"))
    traces["sources"][0]["content_hash"] = "0" * 64
    traces_path.write_text(json.dumps(traces, indent=2, sort_keys=True) + "\n")

    with pytest.raises(
        ValueError,
        match="runtime episode program_runtime_traces_sha256 does not match current file",
    ):
        validate_program_meta_adjudication_plan_contract(
            plan,
            expected_identities=[plan["identity"]],
            valid_manifest_hashes={plan["manifest"]["sha256"]},
        )


def test_meta_adjudication_plan_cli_accepts_runtime_episode(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    runtime_out = tmp_path / "runtime-episode"
    run_program_runtime_episode(
        manifest_path=candidate_root / "manifest.json",
        inputs_path=_write_runtime_inputs(tmp_path),
        outdir=runtime_out,
        skip_oracle_index=True,
    )
    out = tmp_path / "meta-adjudication-plan.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "meta-adjudication-plan",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--runtime-episode",
            str(runtime_out / "runtime_episode.json"),
            "--out",
            str(out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["sidecars"]["runtime_episode"]["status"] == "present"
    assert out.exists()


def test_meta_adjudication_plan_validates_oracle_publication_receipt_contract(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        candidate_root, tmp_path / "oracle" / "program_oracle_publication_receipt.json"
    )

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        oracle_publication_receipt_path=receipt_path,
    )

    receipt_status = plan["sidecars"]["oracle_publication_receipt"]
    assert receipt_status["status"] == "present"
    assert (
        receipt_status["schema_version"]
        == "program-oracle-shared-publication-receipt-v1"
    )
    assert receipt_status["sha256"]


def test_meta_adjudication_plan_rejects_oracle_publication_receipt_contract_drift(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        candidate_root, tmp_path / "oracle" / "program_oracle_publication_receipt.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["record"]["non_authority"]["oracle_promotion"] = True
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        oracle_publication_receipt_path=receipt_path,
    )

    receipt_status = plan["sidecars"]["oracle_publication_receipt"]
    assert receipt_status["present"] is True
    assert receipt_status["status"] == "contract_invalid"
    assert (
        "record does not match supplied preflight planned_record"
        in receipt_status["warning"]
    )


def test_meta_adjudication_plan_rejects_oracle_publication_receipt_stale_preflight(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        candidate_root, tmp_path / "oracle" / "program_oracle_publication_receipt.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    preflight_path = receipt_path.parent / Path(receipt["source"]["preflight_file"])
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["planned_record"]["candidate_id"] = "drifted-candidate"
    preflight_path.write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n")

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        oracle_publication_receipt_path=receipt_path,
    )

    receipt_status = plan["sidecars"]["oracle_publication_receipt"]
    assert receipt_status["status"] == "contract_invalid"
    assert (
        "source.preflight_sha256 does not match current preflight"
        in receipt_status["warning"]
    )


def test_meta_adjudication_plan_contract_rejects_oracle_receipt_preflight_drift(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        candidate_root, tmp_path / "oracle" / "program_oracle_publication_receipt.json"
    )
    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        oracle_publication_receipt_path=receipt_path,
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    preflight_path = receipt_path.parent / Path(receipt["source"]["preflight_file"])
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["planned_record"]["candidate_id"] = "drifted-candidate"
    preflight_path.write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n")

    with pytest.raises(
        ValueError,
        match="source.preflight_sha256 does not match current preflight",
    ):
        validate_program_meta_adjudication_plan_contract(
            plan,
            expected_identities=[plan["identity"]],
            valid_manifest_hashes={plan["manifest"]["sha256"]},
        )


def test_meta_adjudication_plan_treats_schema_mismatch_sidecars_as_missing(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    wrong_jury_path = tmp_path / "promotion" / "wrong_jury_results.json"
    wrong_jury_path.parent.mkdir(parents=True, exist_ok=True)
    wrong_jury_path.write_text(
        json.dumps({"schema_version": "wrong-schema"}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        jury_results_path=wrong_jury_path,
    )

    assert plan["sidecars"]["jury_results"]["present"] is True
    assert plan["sidecars"]["jury_results"]["status"] == "schema_mismatch"
    assert "program_jury_results" in plan["missing_evidence"]
    assert not any(
        "--jury-results" in item["command"] for item in plan["next_commands"]
    )


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


def test_meta_adjudication_plan_cli_rejects_output_inside_generated_artifact_root(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    before_manifest = (candidate_root / "manifest.json").read_text(encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "meta-adjudication-plan",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--out",
            str(candidate_root / "manifest.json"),
        ],
    )

    assert result.exit_code == 2
    assert "meta-adjudication plan must not overwrite manifest.json" in result.output
    assert (candidate_root / "manifest.json").read_text(
        encoding="utf-8"
    ) == before_manifest


def test_write_meta_adjudication_plan_rejects_wrong_schema(tmp_path: Path) -> None:
    try:
        write_program_meta_adjudication_plan(
            {"schema_version": "wrong-schema"}, tmp_path / "plan.json"
        )
    except ValueError as exc:
        assert "program-meta-adjudication-plan-v1" in str(exc)
    else:  # pragma: no cover - defensive clarity
        raise AssertionError("expected wrong schema to be rejected")
