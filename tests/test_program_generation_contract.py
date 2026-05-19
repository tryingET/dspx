from __future__ import annotations

import json
from pathlib import Path

from dspx.services.program_generation_contract import (
    DESIGNMD_VISUAL_DOSSIER_REQUIREMENTS_SCHEMA,
    GEN_GENERATION_GATE_PREFLIGHT_SCHEMA,
    GEN_TARGET_CONTRACT_SCHEMA,
    build_designmd_visual_dossier_program_intent_from_requirements,
    build_designmd_visual_dossier_target_contract_from_requirements,
    build_generation_fitness_results,
    build_generation_gate_preflight,
    build_generation_requirements_intake_artifacts,
    build_generation_traceability,
    validate_designmd_visual_dossier_requirements_packet,
    validate_generation_fitness_results,
    validate_generation_fitness_suite,
    validate_generation_target_contract,
    validate_generation_traceability,
    write_generation_gate_preflight,
)


QUARANTINED_NEGATIVE_FIXTURE = Path(
    "tests/fixtures/program_gen/pdf_transition/quarantined_invalid_outputs.json"
)


def _quarantined_negative_fixture() -> dict:
    return json.loads(QUARANTINED_NEGATIVE_FIXTURE.read_text(encoding="utf-8"))


def _base_contract(**overrides):
    payload = {
        "schema_version": GEN_TARGET_CONTRACT_SCHEMA,
        "identity": {
            "intent_sha256": "intent-sha",
            "contract_sha256": "contract-sha",
            "validator_version": "v1",
        },
        "target": {
            "id": "obsidian_pdf_transition",
            "owner": "obsidian/_System",
            "owner_refs": [
                "/vault/_System/architecture/pdf-transition-architecture.md"
            ],
        },
        "contract_source": "hand_authored",
        "confirmation_status": "operator_confirmed_for_generation_gate",
        "risk_tier": "authority_adjacent",
        "protocol": {
            "required_stages": ["source_package", "section_units", "review"],
            "artifact_families": ["source", "transition", "proposal", "review"],
            "forbidden_shortcuts": ["draft_canonical_note_before_review"],
        },
        "source_policy": {
            "provenance_required": True,
            "language_policy": "preserve_source_language",
        },
        "fitness": {
            "required_adversarial_cases": [
                "plausible_section_heading_inflated_into_wiki_create"
            ]
        },
        "requests": {"adapter_materialization": True},
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
    payload.update(overrides)
    return payload


def _designmd_requirements_packet(**overrides):
    payload = {
        "schemaVersion": DESIGNMD_VISUAL_DOSSIER_REQUIREMENTS_SCHEMA,
        "id": "vdspx_test",
        "projectId": "default",
        "sourceId": "vsrc_test",
        "analysisRunId": "vrun_test",
        "dossierDraftId": "vdossier_test",
        "generatedAt": "2026-05-18T00:00:00.000Z",
        "ownerBoundary": {
            "designmdMayDefineRequirements": True,
            "dspxOwnsTargetProtocol": True,
            "noProgramGenExecution": True,
            "statement": "DSPx owner surface must own/review target protocol and program-gen.",
        },
        "inputRefs": {
            "sourceIndexSchema": "designmd.visual-source-index.v1",
            "analysisRunSchema": "designmd.analysis-run.v1",
            "dossierDraftSchema": "designmd.dossier-draft.v1",
            "sourceIndexSha256": "source-sha",
            "designMdSha256": "design-sha",
            "designMdCurrentSha256": "design-sha",
            "freshness": {"status": "current"},
        },
        "requiredTargetProtocolContent": ["Authority statements"],
        "requiredOutputSchemas": ["designmd.component-inventory.v1"],
        "roleCoverage": ["visual designer"],
        "fixtureRequirements": ["stale DESIGN.md hash case"],
        "fitnessGates": ["DSPx target-protocol owner review"],
        "failClosedBlockers": ["Candidate attempts to mutate DESIGN.md"],
        "acceptedOutputPosture": ["proposal_context", "review_evidence"],
        "forbiddenClaims": ["accepted_contract_truth", "reviewed_dossier_guidance"],
        "authority": {
            "statement": "Does not mutate DESIGN.md or create AK/society authority."
        },
    }
    payload.update(overrides)
    return payload


def _base_suite(**overrides):
    payload = {
        "schema_version": "gen-fitness-suite-v1",
        "identity": {
            "target_contract_sha256": "contract-sha",
            "suite_sha256": "suite-sha",
        },
        "cases": [
            {
                "case_id": "bad-wiki-create",
                "fixture_ref": "fixtures/obsidian/bad-wiki-create.json",
                "allowed_artifact_families": ["transition", "proposal", "review"],
                "forbidden_outputs_or_effects": ["canonical_note_draft"],
                "source_provenance_assertions": ["source_refs_present"],
                "target_stage_assertions": ["merge_before_create_checked"],
                "expected_failure_label": "withheld_for_target_protocol_failure",
                "command": "dspx program-gen fitness-check --case bad-wiki-create",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_designmd_visual_dossier_requirements_normalize_to_target_contract() -> None:
    packet = _designmd_requirements_packet()

    validation = validate_designmd_visual_dossier_requirements_packet(packet)
    contract = build_designmd_visual_dossier_target_contract_from_requirements(packet)
    contract_validation = validate_generation_target_contract(contract)

    assert validation["status"] == "valid"
    assert contract["schema_version"] == GEN_TARGET_CONTRACT_SCHEMA
    assert contract["target"]["id"] == "designmd_visual_dossier"
    assert contract["identity"]["requirements_packet_sha256"]
    assert (
        "designmd.component-inventory.v1" in contract["protocol"]["artifact_families"]
    )
    assert "accepted_contract_truth" in contract["protocol"]["forbidden_shortcuts"]
    assert contract_validation["status"] == "valid"


def test_designmd_visual_dossier_requirements_intake_builds_native_gate_artifacts() -> (
    None
):
    artifacts = build_generation_requirements_intake_artifacts(
        profile="designmd-visual-dossier",
        requirements=_designmd_requirements_packet(),
    )

    assert artifacts["schema_version"] == "gen-requirements-intake-v1"
    assert artifacts["target_contract"]["schema_version"] == GEN_TARGET_CONTRACT_SCHEMA
    assert artifacts["fitness_suite"]["schema_version"] == "gen-fitness-suite-v1"
    assert artifacts["generation_gate_preflight"]["schema_version"] == (
        GEN_GENERATION_GATE_PREFLIGHT_SCHEMA
    )
    assert artifacts["generation_gate_preflight"]["generation_allowed"] is True
    assert artifacts["verifier_non_guarantee"] == (
        "semantic_truth_domain_acceptance_or_production_activation"
    )


def test_designmd_visual_dossier_requirements_build_minimal_program_intent() -> None:
    packet = _designmd_requirements_packet()
    intent = build_designmd_visual_dossier_program_intent_from_requirements(packet)
    artifacts = build_generation_requirements_intake_artifacts(
        profile="designmd-visual-dossier",
        requirements=packet,
        include_intent=True,
    )

    assert intent["schema_version"] == "program-intent-v2"
    assert intent["task_type"] == "single_module"
    assert "visual_source_packet_json" in intent["inputs"]
    assert "receipt_bundle_json" in intent["outputs"]
    assert "visual designer" in intent["options"]["role_coverage"]
    assert intent["options"]["accepted_output_posture"] == [
        "proposal_context",
        "review_evidence",
    ]
    assert "program_intent" in artifacts
    assert artifacts["program_intent"]["options"]["requirements_profile"] == (
        "designmd-visual-dossier"
    )


def test_designmd_visual_dossier_program_intent_name_is_python_identifier() -> None:
    intent = build_designmd_visual_dossier_program_intent_from_requirements(
        _designmd_requirements_packet(sourceId="1779.vsrc-calicoach")
    )

    assert intent["name"] == "DesignmdVisualDossier_1779_vsrc_calicoachProgram"
    assert intent["name"].isidentifier()


def test_designmd_visual_dossier_program_intent_name_rejects_unicode_word_traps() -> (
    None
):
    intent = build_designmd_visual_dossier_program_intent_from_requirements(
        _designmd_requirements_packet(sourceId="a²")
    )

    assert intent["name"] == "DesignmdVisualDossieraProgram"
    assert intent["name"].isidentifier()


def test_designmd_visual_dossier_requirements_freshness_ignores_empty_stale_reasons() -> (
    None
):
    packet = _designmd_requirements_packet(
        inputRefs={
            "sourceIndexSchema": "designmd.visual-source-index.v1",
            "analysisRunSchema": "designmd.analysis-run.v1",
            "dossierDraftSchema": "designmd.dossier-draft.v1",
            "sourceIndexSha256": "source-sha",
            "designMdSha256": "design-sha",
            "designMdCurrentSha256": "design-sha",
            "freshness": {
                "freshAgainstSource": True,
                "freshAgainstDesign": True,
                "staleReasons": [],
                "statement": "Fresh against current source index and DESIGN.md hash.",
            },
        }
    )

    validation = validate_designmd_visual_dossier_requirements_packet(packet)

    assert validation["status"] == "valid"
    assert "stale_input_refs" not in validation["fail_closed_reasons"]


def test_designmd_visual_dossier_requirements_intake_blocks_incomplete_packet() -> None:
    packet = _designmd_requirements_packet(
        inputRefs={"sourceIndexSchema": "designmd.visual-source-index.v1"},
        roleCoverage=[],
        acceptedOutputPosture=["accepted_contract_truth"],
    )

    validation = validate_designmd_visual_dossier_requirements_packet(packet)
    artifacts = build_generation_requirements_intake_artifacts(
        profile="designmd-visual-dossier", requirements=packet
    )
    preflight = artifacts["generation_gate_preflight"]

    assert validation["status"] == "blocked"
    assert preflight["status"] == "generation_blocked"
    assert preflight["generation_allowed"] is False
    assert "missing_sourceIndexSha256" in preflight["fail_closed_reasons"]
    assert "invalid_accepted_output_posture" in preflight["fail_closed_reasons"]


def test_valid_target_bound_contract_allows_target_fidelity_claim() -> None:
    result = validate_generation_target_contract(_base_contract())

    assert result["status"] == "valid"
    assert result["target_protocol_fidelity_claimed"] is True
    assert result["adapter_materialization_allowed"] is True
    assert result["verifier_non_guarantee"] == "semantic_truth_of_target_protocol"


def test_missing_owner_ref_blocks_target_bound_contract() -> None:
    contract = _base_contract(target={"id": "x", "owner": "owner", "owner_refs": []})

    result = validate_generation_target_contract(contract)

    assert result["status"] == "blocked"
    assert "missing_target_owner_ref" in result["fail_closed_reasons"]


def test_objective_only_contract_blocks_target_bound_generation() -> None:
    contract = _base_contract(contract_source="objective_only")

    result = validate_generation_target_contract(contract)

    assert result["status"] == "blocked"
    assert "insufficient_target_contract" in result["fail_closed_reasons"]


def test_generated_from_docs_requires_confirmation() -> None:
    contract = _base_contract(
        contract_source="generated_from_docs",
        confirmation_status="draft_not_confirmed",
    )

    result = validate_generation_target_contract(contract)

    assert result["status"] == "blocked"
    assert "generated_from_docs_requires_confirmation" in result["fail_closed_reasons"]


def test_tutorial_profile_cannot_bypass_owner_refs_or_review_artifacts() -> None:
    contract = _base_contract(
        risk_tier="tutorial_local",
        protocol={
            "required_stages": [],
            "artifact_families": ["proposal", "review"],
            "forbidden_shortcuts": [],
        },
        requests={"adapter_materialization": True},
    )

    result = validate_generation_target_contract(contract)

    assert result["status"] == "blocked"
    assert "tutorial_profile_disallows_owner_refs" in result["fail_closed_reasons"]
    assert (
        "tutorial_profile_disallows_adapter_materialization"
        in result["fail_closed_reasons"]
    )
    assert (
        "tutorial_profile_disallows_target_artifact_families"
        in result["fail_closed_reasons"]
    )


def test_tutorial_profile_valid_when_local_and_no_target_claim() -> None:
    contract = _base_contract(
        risk_tier="tutorial_local",
        target={"id": "ticket_demo", "owner": "local", "owner_refs": []},
        protocol={
            "required_stages": [],
            "artifact_families": ["local_example"],
            "forbidden_shortcuts": [],
        },
        requests={},
    )

    result = validate_generation_target_contract(contract)

    assert result["status"] == "valid"
    assert result["tutorial_contract_profile_used"] is True
    assert result["target_protocol_fidelity_claimed"] is False
    assert result["adapter_materialization_allowed"] is False


def test_fitness_suite_requires_executable_adversarial_cases() -> None:
    suite = _base_suite(cases=[{"case_id": "empty"}])

    result = validate_generation_fitness_suite(suite, target_contract=_base_contract())

    assert result["status"] == "blocked"
    reasons = result["fail_closed_reasons"]
    assert "case_0:missing_fixture_ref" in reasons
    assert "case_0:missing_executable_or_mechanical_check" in reasons


def test_generation_gate_blocks_when_suite_hash_does_not_match_contract() -> None:
    suite = _base_suite(
        identity={"target_contract_sha256": "different", "suite_sha256": "suite-sha"}
    )

    result = build_generation_gate_preflight(
        target_contract=_base_contract(), fitness_suite=suite
    )

    assert result["schema_version"] == GEN_GENERATION_GATE_PREFLIGHT_SCHEMA
    assert result["status"] == "generation_blocked"
    assert "target_contract_sha256_mismatch" in result["fail_closed_reasons"]
    assert result["effect"]["candidate_files_mutated"] is False


def test_generation_gate_allows_valid_contract_and_suite(tmp_path: Path) -> None:
    result = build_generation_gate_preflight(
        target_contract=_base_contract(), fitness_suite=_base_suite()
    )
    out = tmp_path / "generation_gate_preflight.json"

    written = write_generation_gate_preflight(result, out)

    assert result["status"] == "generation_allowed"
    assert written["generation_allowed"] is True
    assert out.exists()


def test_traceability_requires_requirements_and_evidence_refs() -> None:
    result = validate_generation_traceability(
        {
            "schema_version": "gen-traceability-v1",
            "identity": {
                "candidate_manifest_sha256": "manifest-sha",
                "target_contract_sha256": "contract-sha",
            },
            "requirements": [
                {
                    "requirement_id": "source_grounding",
                    "generated_surfaces": ["module.py"],
                    "evidence_refs": ["generation_fitness_results.json"],
                    "status": "covered",
                }
            ],
        }
    )

    assert result["status"] == "valid"


def test_build_traceability_and_fitness_results_are_safe_review_eligible() -> None:
    manifest = {
        "schema_version": "program-candidate-assembly-v1",
        "candidate_assembly": {
            "surfaces": [
                {"kind": "program", "path": "program.py"},
                {"kind": "module", "path": "module.py"},
                {"kind": "jury_rubric", "path": "jury_rubric.json"},
            ]
        },
        "program_plan": {
            "evaluation_strategy": {"jurors": [{"perspective": "source_grounding"}]}
        },
    }
    traceability = build_generation_traceability(
        target_contract=_base_contract(), candidate_manifest=manifest
    )

    trace_validation = validate_generation_traceability(traceability)
    results = build_generation_fitness_results(
        candidate_manifest=manifest,
        target_contract=_base_contract(),
        fitness_suite=_base_suite(),
        traceability=traceability,
    )

    assert trace_validation["status"] == "valid"
    assert traceability["requirements"][0]["status"] == "covered"
    assert results["status"] == "fitness_passed"
    assert results["rendered_state"] == "eligible_for_downstream_evidence_review"
    assert validate_generation_fitness_results(results)["status"] == "valid"


def test_quarantined_pdf_outputs_are_negative_target_fidelity_fixtures() -> None:
    fixture = _quarantined_negative_fixture()

    assert fixture["schema_version"] == "gen-target-fidelity-negative-fixtures-v1"
    assert (
        fixture["required_rejection_contract"][
            "generation_fitness_results_required_for_downstream_review"
        ]
        is True
    )
    assert (
        fixture["required_rejection_contract"]["canonical_obsidian_mutation_allowed"]
        is False
    )
    assert {record["doc_id"] for record in fixture["records"]} == {
        "doc:46c8f2bb",
        "doc:deddff66",
        "doc:f7cf59ed",
        "doc:pdf-transition-demo",
    }
    for record in fixture["records"]:
        assert record["classification"] == "quarantined_invalid_or_untrusted"
        assert "missing_generation_fitness_results" in record["negative_labels"]
        assert (
            "generation_fitness_results.json"
            in record["missing_required_generation_sidecars"]
        )
        assert record["expected_generation_fitness_status"] == (
            "target_fidelity_unknown"
        )
        assert record["non_authority"]["canonical_acceptance"] is False
        assert record["non_authority"]["production_activation"] is False


def test_missing_traceability_keeps_fitness_unknown_not_approved() -> None:
    fixture = _quarantined_negative_fixture()
    results = build_generation_fitness_results(
        candidate_manifest={"schema_version": "program-candidate-assembly-v1"},
        target_contract=_base_contract(),
        fitness_suite=_base_suite(),
    )

    assert all(
        record["expected_generation_fitness_status"] == results["status"]
        for record in fixture["records"]
    )
    assert results["status"] == "target_fidelity_unknown"
    assert results["rendered_state"] == "target_fidelity_unknown"
    assert validate_generation_fitness_results(results)["status"] == "valid"


def test_uncovered_traceability_fails_target_fitness() -> None:
    traceability = {
        "schema_version": "gen-traceability-v1",
        "identity": {
            "candidate_manifest_sha256": "manifest-sha",
            "target_contract_sha256": "contract-sha",
        },
        "requirements": [
            {
                "requirement_id": "merge-before-create",
                "generated_surfaces": ["module.py"],
                "evidence_refs": ["generation_fitness_results.json"],
                "status": "uncovered",
            }
        ],
    }

    results = build_generation_fitness_results(
        candidate_manifest={"schema_version": "program-candidate-assembly-v1"},
        target_contract=_base_contract(),
        fitness_suite=_base_suite(),
        traceability=traceability,
    )

    assert validate_generation_traceability(traceability)["status"] == "valid"
    assert results["status"] == "fitness_failed"
    assert results["rendered_state"] == "withheld_for_target_protocol_failure"
    assert validate_generation_fitness_results(results)["status"] == "valid"


def test_fitness_passed_requires_command_safe_rendering() -> None:
    result = validate_generation_fitness_results(
        {
            "schema_version": "gen-fitness-results-v1",
            "identity": {
                "candidate_manifest_sha256": "manifest-sha",
                "target_contract_sha256": "contract-sha",
                "fitness_suite_sha256": "suite-sha",
            },
            "status": "fitness_passed",
            "rendered_state": "approved",
            "cases": [
                {
                    "case_id": "positive",
                    "status": "passed",
                    "evidence_refs": ["case-result.json"],
                }
            ],
        }
    )

    assert result["status"] == "blocked"
    assert (
        "fitness_passed_requires_command_safe_rendering"
        in result["fail_closed_reasons"]
    )
