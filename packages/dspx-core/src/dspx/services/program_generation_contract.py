from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

GEN_TARGET_CONTRACT_SCHEMA = "gen-target-contract-v1"
GEN_FITNESS_SUITE_SCHEMA = "gen-fitness-suite-v1"
GEN_GENERATION_GATE_PREFLIGHT_SCHEMA = "gen-generation-gate-preflight-v1"
GEN_TRACEABILITY_SCHEMA = "gen-traceability-v1"
GEN_FITNESS_RESULTS_SCHEMA = "gen-fitness-results-v1"
DESIGNMD_VISUAL_DOSSIER_REQUIREMENTS_SCHEMA = (
    "designmd.dspx-visual-dossier-requirements.v1"
)
GEN_REQUIREMENTS_INTAKE_SCHEMA = "gen-requirements-intake-v1"

GEN_TARGET_CONTRACT_VALIDATION_SCHEMA = "gen-target-contract-validation-v1"
GEN_FITNESS_SUITE_VALIDATION_SCHEMA = "gen-fitness-suite-validation-v1"
GEN_TRACEABILITY_VALIDATION_SCHEMA = "gen-traceability-validation-v1"
GEN_FITNESS_RESULTS_VALIDATION_SCHEMA = "gen-fitness-results-validation-v1"

TARGET_BOUND_RISK_TIERS = {
    "protocol_bound",
    "authority_adjacent",
    "external_mutation_capable",
}
TUTORIAL_RISK_TIER = "tutorial_local"
RISK_TIERS = {TUTORIAL_RISK_TIER, *TARGET_BOUND_RISK_TIERS}

_TUTORIAL_FORBIDDEN_ARTIFACT_FAMILIES = {"proposal", "review", "canonical"}
_REQUIRED_NON_AUTHORITY_FALSE = {
    "activation_authority",
    "promotion_authority",
    "oracle_authority",
    "governance_authority",
    "external_mutation",
}
_REQUIRED_EFFECT_FALSE = {
    "candidate_files_mutated",
    "canonical_target_mutated",
    "ak_mutated",
    "governance_mutated",
}


class ProgramGenerationContractError(ValueError):
    """Raised when generation target-fidelity contract inputs are invalid."""


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _sha256_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _load_json_or_yaml_mapping(path: Path) -> dict[str, Any]:
    source = path.expanduser().resolve()
    text = source.read_text(encoding="utf-8")
    payload = (
        json.loads(text) if source.suffix.lower() == ".json" else yaml.safe_load(text)
    )
    if not isinstance(payload, Mapping):
        raise ProgramGenerationContractError(
            f"generation contract input must be a mapping/object: {source}"
        )
    return {str(key): item for key, item in payload.items()}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.expanduser().resolve().read_bytes()).hexdigest()


def _slug(value: object, *, default: str = "case") -> str:
    text = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "").strip().lower())
    return text.strip(".-_") or default


def _payload_with_identity_hash(
    payload: dict[str, Any], *, identity_key: str
) -> dict[str, Any]:
    data = json.loads(json.dumps(payload))
    identity = _safe_mapping(data.get("identity"))
    identity[identity_key] = ""
    data["identity"] = identity
    payload.setdefault("identity", {})[identity_key] = _sha256_payload(data)
    return payload


def _normalise_refs(value: object) -> list[str]:
    refs: list[str] = []
    for item in _safe_list(value):
        text = str(item or "").strip()
        if text and text not in refs:
            refs.append(text)
    return refs


def _owner_from_refs(owner_refs: list[str], fallback: str) -> str:
    for ref in owner_refs:
        if "/Obsidian/_System/" in ref or ref.endswith("/Obsidian/_System"):
            return "obsidian/_System"
        if "_System/" in ref:
            return "owner/_System"
    return fallback


def _authority_model_stages(authority_model: Mapping[str, Any]) -> list[str]:
    stages: list[str] = []
    for key in authority_model:
        normalized = str(key).strip().lower().replace("-", "_")
        if normalized == "source":
            stages.append("source_package")
        elif normalized == "transition":
            stages.extend(["section_units", "distillation_frames", "evidence_cards"])
        elif normalized == "proposal":
            stages.append("merge_before_create")
        elif normalized == "canonical":
            stages.append("canonical_notes_after_acceptance")
        else:
            stages.append(normalized)
    out: list[str] = []
    for stage in stages:
        if stage and stage not in out:
            out.append(stage)
    return out


def _case_id(value: object, index: int) -> str:
    return f"case-{index + 1}-{_slug(value, default='adversarial')}"


def _false_fields_missing(payload: object, required: set[str]) -> list[str]:
    mapping = _safe_mapping(payload)
    return sorted(key for key in required if mapping.get(key) is not False)


def _validation_payload(
    *, schema_version: str, status: str, reasons: list[str]
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "status": status,
        "valid": status == "valid",
        "fail_closed_reasons": reasons,
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
            "provider_called": False,
            "shared_oracle_mutated": False,
        },
    }


def validate_generation_target_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Validate declared sufficiency of a generation target contract.

    This is a deterministic preflight validator. It verifies completeness and
    guardrail shape; it does not prove semantic truth of the target protocol.
    """

    reasons: list[str] = []
    if contract.get("schema_version") != GEN_TARGET_CONTRACT_SCHEMA:
        reasons.append("invalid_schema_version")

    identity = _safe_mapping(contract.get("identity"))
    if not _first_text(identity.get("intent_sha256")):
        reasons.append("missing_intent_sha256")
    if not _first_text(identity.get("contract_sha256")):
        reasons.append("missing_contract_sha256")
    if not _first_text(identity.get("validator_version"), identity.get("validator")):
        reasons.append("missing_validator_version")

    risk_tier = _first_text(contract.get("risk_tier"))
    if risk_tier not in RISK_TIERS:
        reasons.append("ambiguous_risk_tier")

    target = _safe_mapping(contract.get("target"))
    owner_refs = _string_list(target.get("owner_refs"))
    artifact_families = set(
        _string_list(_safe_mapping(contract.get("protocol")).get("artifact_families"))
    )
    requests = _safe_mapping(contract.get("requests"))
    has_authority_refs = bool(_safe_list(requests.get("authority_refs"))) or bool(
        _safe_list(target.get("authority_refs"))
    )
    adapter_materialization_requested = requests.get("adapter_materialization") is True
    publication_requested = requests.get("shared_oracle_publication") is True
    promotion_or_activation_requested = any(
        requests.get(key) is True
        for key in ("promotion_evidence", "export_evidence", "activation_evidence")
    )

    tutorial_escape_hatch_used = risk_tier == TUTORIAL_RISK_TIER
    if tutorial_escape_hatch_used:
        if owner_refs:
            reasons.append("tutorial_profile_disallows_owner_refs")
        if adapter_materialization_requested:
            reasons.append("tutorial_profile_disallows_adapter_materialization")
        if has_authority_refs:
            reasons.append("tutorial_profile_disallows_authority_refs")
        if publication_requested:
            reasons.append("tutorial_profile_disallows_publication")
        if promotion_or_activation_requested:
            reasons.append("tutorial_profile_disallows_promotion_export_activation")
        if artifact_families & _TUTORIAL_FORBIDDEN_ARTIFACT_FAMILIES:
            reasons.append("tutorial_profile_disallows_target_artifact_families")
    elif risk_tier in TARGET_BOUND_RISK_TIERS:
        if not _first_text(target.get("owner")):
            reasons.append("missing_target_owner")
        if not owner_refs:
            reasons.append("missing_target_owner_ref")
        protocol = _safe_mapping(contract.get("protocol"))
        if not _string_list(protocol.get("required_stages")):
            reasons.append("missing_required_protocol_stage")
        if not artifact_families:
            reasons.append("missing_artifact_family_boundary")
        if not _string_list(protocol.get("forbidden_shortcuts")):
            reasons.append("missing_forbidden_shortcut_list")
        source_policy = _safe_mapping(contract.get("source_policy"))
        if source_policy.get("provenance_required") is not True:
            reasons.append("missing_source_provenance_policy")
        if not _first_text(source_policy.get("language_policy")):
            reasons.append("missing_source_language_policy")
        contract_source = _first_text(contract.get("contract_source"))
        confirmation_status = _first_text(contract.get("confirmation_status"))
        if contract_source in {None, "objective_only", "inferred_from_objective"}:
            reasons.append("insufficient_target_contract")
        if contract_source == "generated_from_docs" and confirmation_status not in {
            "operator_confirmed_for_generation_gate",
            "domain_confirmed_for_generation_gate",
        }:
            reasons.append("generated_from_docs_requires_confirmation")
        fitness = _safe_mapping(contract.get("fitness"))
        if not _string_list(fitness.get("required_adversarial_cases")):
            reasons.append("missing_adversarial_fitness_case")

    non_authority_missing = _false_fields_missing(
        contract.get("non_authority"), _REQUIRED_NON_AUTHORITY_FALSE
    )
    if non_authority_missing:
        reasons.append("missing_non_authority_flags:" + ",".join(non_authority_missing))
    effect_missing = _false_fields_missing(
        contract.get("effect"), _REQUIRED_EFFECT_FALSE
    )
    if effect_missing:
        reasons.append("missing_effect_flags:" + ",".join(effect_missing))

    status = "blocked" if reasons else "valid"
    payload = _validation_payload(
        schema_version=GEN_TARGET_CONTRACT_VALIDATION_SCHEMA,
        status=status,
        reasons=sorted(set(reasons)),
    )
    payload.update(
        {
            "risk_tier": risk_tier,
            "tutorial_contract_profile_used": tutorial_escape_hatch_used,
            "target_protocol_fidelity_claimed": status == "valid"
            and not tutorial_escape_hatch_used,
            "adapter_materialization_allowed": status == "valid"
            and not tutorial_escape_hatch_used,
            "verifier_guarantee": "declared_contract_sufficiency_only",
            "verifier_non_guarantee": "semantic_truth_of_target_protocol",
        }
    )
    return payload


def validate_generation_fitness_suite(
    suite: Mapping[str, Any], *, target_contract: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Validate that an adversarial fitness suite is mechanically checkable."""

    reasons: list[str] = []
    if suite.get("schema_version") != GEN_FITNESS_SUITE_SCHEMA:
        reasons.append("invalid_schema_version")

    identity = _safe_mapping(suite.get("identity"))
    suite_contract_sha = _first_text(identity.get("target_contract_sha256"))
    if not suite_contract_sha:
        reasons.append("missing_target_contract_sha256")
    if not _first_text(identity.get("suite_sha256")):
        reasons.append("missing_suite_sha256")
    if target_contract is not None:
        contract_sha = _first_text(
            _safe_mapping(target_contract.get("identity")).get("contract_sha256")
        )
        if contract_sha and suite_contract_sha and contract_sha != suite_contract_sha:
            reasons.append("target_contract_sha256_mismatch")

    cases = _safe_list(suite.get("cases"))
    if not cases:
        reasons.append("missing_adversarial_fitness_case")
    for index, raw_case in enumerate(cases):
        case = _safe_mapping(raw_case)
        prefix = f"case_{index}"
        if not _first_text(case.get("input_fixture"), case.get("fixture_ref")):
            reasons.append(f"{prefix}:missing_fixture_ref")
        if not _string_list(case.get("allowed_artifact_families")):
            reasons.append(f"{prefix}:missing_allowed_artifact_families")
        if not _string_list(case.get("forbidden_outputs_or_effects")):
            reasons.append(f"{prefix}:missing_forbidden_outputs_or_effects")
        if not _safe_list(case.get("source_provenance_assertions")):
            reasons.append(f"{prefix}:missing_source_provenance_assertions")
        if not _safe_list(case.get("target_stage_assertions")):
            reasons.append(f"{prefix}:missing_target_stage_assertions")
        if not _first_text(
            case.get("expected_failure_label"), case.get("expected_status")
        ):
            reasons.append(f"{prefix}:missing_expected_failure_label")
        if not _first_text(case.get("command"), case.get("validator")):
            reasons.append(f"{prefix}:missing_executable_or_mechanical_check")

    status = "blocked" if reasons else "valid"
    return _validation_payload(
        schema_version=GEN_FITNESS_SUITE_VALIDATION_SCHEMA,
        status=status,
        reasons=sorted(set(reasons)),
    )


def build_generation_target_contract_from_intent(
    intent_path: Path,
) -> dict[str, Any]:
    """Build a deterministic target-fidelity contract from structured intent fields.

    This builder intentionally does not infer a target protocol from objective text.
    Target-bound fields must be present in explicit intent options, promotion refs,
    constraints, or declared artifacts; otherwise the result is a tutorial/local
    contract and cannot claim target-protocol fidelity.
    """

    from dspx.services.program_intent import load_program_intent

    source = intent_path.expanduser().resolve()
    intent = load_program_intent(source)
    options = _safe_mapping(intent.options)
    promotion = _safe_mapping(intent.promotion)
    external_authority = _safe_mapping(promotion.get("external_authority"))

    owner_refs = _normalise_refs(
        [
            options.get("primary_architecture"),
            *_safe_list(options.get("related_architectures")),
            *_safe_list(options.get("owner_refs")),
            *_safe_list(options.get("target_owner_refs")),
        ]
    )
    authority_refs = _safe_list(external_authority.get("refs")) + _safe_list(
        options.get("authority_refs")
    )
    target_bound = bool(owner_refs or authority_refs)
    expected_families = _string_list(options.get("expected_artifact_family"))
    authority_model = _safe_mapping(options.get("authority_model"))
    artifact_families = list(
        dict.fromkeys([*authority_model.keys(), *expected_families])
    )
    forbidden_shortcuts = list(
        dict.fromkeys(
            [
                *_string_list(options.get("forbidden_effects")),
                *[item for item in intent.constraints if "forbidden" in item.lower()],
            ]
        )
    )
    required_stages = _string_list(
        _safe_mapping(options.get("target_protocol")).get("required_stages")
    ) or _authority_model_stages(authority_model)
    if not required_stages and target_bound:
        required_stages = ["target_protocol_review"]

    requested_review_or_proposal = any(
        "review" in family.lower() or "proposal" in family.lower()
        for family in artifact_families
    ) or any("review" in output.lower() for output in intent.outputs)
    promotion_or_activation_requested = bool(authority_refs or promotion)
    risk_tier = str(options.get("risk_tier") or "").strip()
    if risk_tier not in RISK_TIERS:
        if promotion_or_activation_requested or requested_review_or_proposal:
            risk_tier = "authority_adjacent"
        elif target_bound:
            risk_tier = "protocol_bound"
        else:
            risk_tier = TUTORIAL_RISK_TIER

    adversarial_cases = _string_list(
        _safe_mapping(options.get("fitness")).get("required_adversarial_cases")
    )
    if not adversarial_cases:
        adversarial_cases = forbidden_shortcuts[:]
    if not adversarial_cases and target_bound:
        adversarial_cases = ["target_protocol_shortcut_regression"]

    target_owner = str(options.get("target_owner") or "").strip()
    if not target_owner:
        target_owner = _owner_from_refs(
            owner_refs,
            str(
                _safe_mapping(authority_refs[0]).get("system")
                if authority_refs and isinstance(authority_refs[0], Mapping)
                else "local"
            ),
        )

    payload: dict[str, Any] = {
        "schema_version": GEN_TARGET_CONTRACT_SCHEMA,
        "identity": {
            "intent_sha256": _sha256_file(source),
            "contract_sha256": "",
            "validator": "dspx.gen_target_contract.v1",
            "validator_version": "v1",
        },
        "target": {
            "id": str(options.get("scenario_name") or intent.name),
            "owner": target_owner,
            "owner_refs": owner_refs,
            "owner_ref_custody": "local_path_reference_not_publishable_without_redaction"
            if owner_refs
            else "none",
            "authority_refs": authority_refs,
        },
        "contract_source": "generated_from_structured_intent"
        if target_bound
        else "tutorial_local_embedded_profile",
        "confirmation_status": "structured_intent_fields_declared"
        if target_bound
        else "not_required_for_tutorial_local",
        "risk_tier": risk_tier,
        "protocol": {
            "required_stages": required_stages,
            "artifact_families": artifact_families or ["local_example"],
            "forbidden_shortcuts": forbidden_shortcuts
            or (["skip_declared_target_protocol"] if target_bound else []),
        },
        "source_policy": {
            "provenance_required": target_bound,
            "language_policy": str(
                options.get("language_policy") or "preserve_source_language"
            ),
        },
        "fitness": {"required_adversarial_cases": adversarial_cases},
        "requests": {
            "adapter_materialization": bool(requested_review_or_proposal),
            "shared_oracle_publication": False,
            "promotion_evidence": bool(promotion_or_activation_requested),
            "export_evidence": False,
            "activation_evidence": False,
        },
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
            "provider_called": False,
            "shared_oracle_mutated": False,
        },
        "profile_extension": {
            "intent_name": intent.name,
            "task_type": intent.task_type,
            "inputs": intent.inputs,
            "outputs": intent.outputs,
        },
    }
    return _payload_with_identity_hash(payload, identity_key="contract_sha256")


def build_generation_fitness_suite_from_target_contract(
    target_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic, mechanical adversarial suite skeleton."""

    contract_identity = _safe_mapping(target_contract.get("identity"))
    target_contract_sha = _first_text(contract_identity.get("contract_sha256")) or ""
    required_cases = _string_list(
        _safe_mapping(target_contract.get("fitness")).get("required_adversarial_cases")
    )
    protocol = _safe_mapping(target_contract.get("protocol"))
    allowed_families = _string_list(protocol.get("artifact_families")) or [
        "local_example"
    ]
    forbidden = _string_list(protocol.get("forbidden_shortcuts")) or [
        "skip_declared_target_protocol"
    ]
    cases = []
    for index, case_name in enumerate(required_cases or ["target_protocol_regression"]):
        cases.append(
            {
                "case_id": _case_id(case_name, index),
                "fixture_ref": f"declared://{_slug(case_name, default='target-protocol-regression')}",
                "allowed_artifact_families": allowed_families,
                "forbidden_outputs_or_effects": forbidden,
                "source_provenance_assertions": ["source_refs_present"],
                "target_stage_assertions": _string_list(protocol.get("required_stages"))
                or ["target_protocol_stage_declared"],
                "expected_failure_label": "withheld_for_target_protocol_failure",
                "validator": "dspx.gen_fitness_suite.declared_mechanical_check.v1",
            }
        )
    payload: dict[str, Any] = {
        "schema_version": GEN_FITNESS_SUITE_SCHEMA,
        "identity": {
            "target_contract_sha256": target_contract_sha,
            "suite_sha256": "",
            "validator": "dspx.gen_fitness_suite.v1",
            "validator_version": "v1",
        },
        "cases": cases,
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
            "provider_called": False,
            "shared_oracle_mutated": False,
        },
    }
    return _payload_with_identity_hash(payload, identity_key="suite_sha256")


def load_generation_target_contract(path: Path) -> dict[str, Any]:
    return _load_json_or_yaml_mapping(path)


def load_generation_fitness_suite(path: Path) -> dict[str, Any]:
    return _load_json_or_yaml_mapping(path)


def load_generation_gate_preflight(path: Path) -> dict[str, Any]:
    return _load_json_or_yaml_mapping(path)


def load_generation_traceability(path: Path) -> dict[str, Any]:
    return _load_json_or_yaml_mapping(path)


def load_candidate_manifest(path: Path) -> dict[str, Any]:
    return _load_json_or_yaml_mapping(path)


def _candidate_manifest_sha256(candidate_manifest: Mapping[str, Any]) -> str:
    return _sha256_payload(candidate_manifest)


def _candidate_surface_paths(candidate_manifest: Mapping[str, Any]) -> list[str]:
    assembly = _safe_mapping(candidate_manifest.get("candidate_assembly"))
    surfaces = _safe_list(assembly.get("surfaces"))
    paths: list[str] = []
    for surface in surfaces:
        path = _first_text(_safe_mapping(surface).get("path"))
        if path and path not in paths:
            paths.append(path)
    for fallback in ("program.py", "module.py", "signature.py", "manifest.json"):
        if fallback not in paths:
            paths.append(fallback)
    return paths


def _candidate_jury_coverage(candidate_manifest: Mapping[str, Any]) -> list[str]:
    plan = _safe_mapping(candidate_manifest.get("program_plan"))
    strategy = _safe_mapping(plan.get("evaluation_strategy"))
    jurors = _safe_list(strategy.get("jurors"))
    coverage: list[str] = []
    for juror in jurors:
        perspective = _first_text(_safe_mapping(juror).get("perspective"))
        if perspective and perspective not in coverage:
            coverage.append(perspective)
    return coverage


def _requirement_id(value: object, index: int) -> str:
    return f"req-{index + 1}-{_slug(value, default='target-stage')}"


def build_generation_traceability(
    *, target_contract: Mapping[str, Any], candidate_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Build post-generation traceability from target requirements to surfaces."""

    contract_sha = (
        _first_text(
            _safe_mapping(target_contract.get("identity")).get("contract_sha256")
        )
        or ""
    )
    required_stages = _string_list(
        _safe_mapping(target_contract.get("protocol")).get("required_stages")
    )
    surfaces = _candidate_surface_paths(candidate_manifest)
    jury_coverage = _candidate_jury_coverage(candidate_manifest)
    requirements = []
    for index, stage in enumerate(required_stages or ["target_protocol_declared"]):
        requirements.append(
            {
                "requirement_id": _requirement_id(stage, index),
                "target_stage": stage,
                "generated_surfaces": surfaces,
                "evidence_refs": ["manifest.json", "generation_fitness_results.json"],
                "juror_adjudicator_coverage": jury_coverage,
                "status": "covered" if surfaces else "uncovered",
            }
        )
    payload: dict[str, Any] = {
        "schema_version": GEN_TRACEABILITY_SCHEMA,
        "identity": {
            "candidate_manifest_sha256": _candidate_manifest_sha256(candidate_manifest),
            "target_contract_sha256": contract_sha,
            "validator": "dspx.gen_traceability.v1",
            "validator_version": "v1",
        },
        "requirements": requirements,
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
            "provider_called": False,
            "shared_oracle_mutated": False,
        },
        "verifier_guarantee": "traceability_shape_and_declared_surface_coverage_only",
        "verifier_non_guarantee": "semantic_truth_of_target_protocol",
    }
    return payload


def _traceability_status(traceability: Mapping[str, Any]) -> str:
    validation = validate_generation_traceability(traceability)
    if validation.get("status") != "valid":
        return "target_fidelity_unknown"
    requirements = [
        _safe_mapping(item) for item in _safe_list(traceability.get("requirements"))
    ]
    if not requirements:
        return "target_fidelity_unknown"
    if any(_first_text(item.get("status")) != "covered" for item in requirements):
        return "fitness_failed"
    return "fitness_passed"


def build_generation_fitness_results(
    *,
    candidate_manifest: Mapping[str, Any],
    target_contract: Mapping[str, Any],
    fitness_suite: Mapping[str, Any],
    traceability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build post-generation mechanical target-fitness results.

    These results are local evidence. Passing means only eligible for downstream
    evidence review; it is not approval, promotion, activation, or domain acceptance.
    """

    candidate_sha = _candidate_manifest_sha256(candidate_manifest)
    contract_sha = (
        _first_text(
            _safe_mapping(target_contract.get("identity")).get("contract_sha256")
        )
        or ""
    )
    suite_sha = (
        _first_text(_safe_mapping(fitness_suite.get("identity")).get("suite_sha256"))
        or ""
    )
    suite_validation = validate_generation_fitness_suite(
        fitness_suite, target_contract=target_contract
    )
    trace_status = (
        _traceability_status(traceability)
        if traceability is not None
        else "target_fidelity_unknown"
    )
    if suite_validation.get("status") != "valid":
        status = "fitness_failed"
    else:
        status = trace_status
    if status == "fitness_passed":
        rendered_state = "eligible_for_downstream_evidence_review"
    elif status == "fitness_failed":
        rendered_state = "withheld_for_target_protocol_failure"
    else:
        rendered_state = "target_fidelity_unknown"

    case_status = "passed" if status == "fitness_passed" else "failed"
    if status == "target_fidelity_unknown":
        case_status = "unknown"
    cases = []
    for raw_case in _safe_list(fitness_suite.get("cases")):
        case = _safe_mapping(raw_case)
        case_id = _first_text(case.get("case_id")) or "target-fitness-case"
        cases.append(
            {
                "case_id": case_id,
                "status": case_status,
                "evidence_refs": ["generation_traceability.json", "manifest.json"],
                "mechanical_check": _first_text(
                    case.get("validator"), case.get("command")
                ),
                "expected_failure_label": _first_text(
                    case.get("expected_failure_label"), case.get("expected_status")
                ),
            }
        )
    if not cases:
        cases.append(
            {
                "case_id": "missing-fitness-suite-case",
                "status": "failed",
                "evidence_refs": ["generation_fitness_suite.json"],
            }
        )
        status = "fitness_failed"
        rendered_state = "withheld_for_target_protocol_failure"

    payload: dict[str, Any] = {
        "schema_version": GEN_FITNESS_RESULTS_SCHEMA,
        "identity": {
            "candidate_manifest_sha256": candidate_sha,
            "target_contract_sha256": contract_sha,
            "fitness_suite_sha256": suite_sha,
            "validator": "dspx.gen_fitness_results.v1",
            "validator_version": "v1",
        },
        "status": status,
        "rendered_state": rendered_state,
        "cases": cases,
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
            "provider_called": False,
            "shared_oracle_mutated": False,
        },
        "verifier_guarantee": "mechanical_traceability_and_suite_result_shape_only",
        "verifier_non_guarantee": "semantic_truth_domain_acceptance_or_activation",
    }
    return payload


def build_generation_gate_preflight(
    *, target_contract: Mapping[str, Any], fitness_suite: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a non-mutating generation gate preflight packet."""

    contract_validation = validate_generation_target_contract(target_contract)
    suite_validation = validate_generation_fitness_suite(
        fitness_suite, target_contract=target_contract
    )
    reasons = sorted(
        set(contract_validation["fail_closed_reasons"])
        | set(suite_validation["fail_closed_reasons"])
    )
    allowed = not reasons
    return {
        "schema_version": GEN_GENERATION_GATE_PREFLIGHT_SCHEMA,
        "status": "generation_allowed" if allowed else "generation_blocked",
        "generation_allowed": allowed,
        "fail_closed_reasons": reasons,
        "target_contract_validation": contract_validation,
        "fitness_suite_validation": suite_validation,
        "identity": {
            "target_contract_sha256": _first_text(
                _safe_mapping(target_contract.get("identity")).get("contract_sha256")
            ),
            "fitness_suite_sha256": _first_text(
                _safe_mapping(fitness_suite.get("identity")).get("suite_sha256")
            ),
            "preflight_sha256": _sha256_payload(
                {
                    "target_contract": target_contract,
                    "fitness_suite": fitness_suite,
                }
            ),
        },
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
            "provider_called": False,
            "shared_oracle_mutated": False,
        },
        "verifier_guarantee": "declared_contract_and_suite_sufficiency_only",
        "verifier_non_guarantee": "semantic_truth_of_target_protocol",
    }


def validate_generation_traceability(payload: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if payload.get("schema_version") != GEN_TRACEABILITY_SCHEMA:
        reasons.append("invalid_schema_version")
    identity = _safe_mapping(payload.get("identity"))
    if not _first_text(identity.get("candidate_manifest_sha256")):
        reasons.append("missing_candidate_manifest_sha256")
    if not _first_text(identity.get("target_contract_sha256")):
        reasons.append("missing_target_contract_sha256")
    entries = _safe_list(payload.get("requirements"))
    if not entries:
        reasons.append("missing_requirement_traceability")
    for index, raw_entry in enumerate(entries):
        entry = _safe_mapping(raw_entry)
        prefix = f"requirement_{index}"
        if not _first_text(entry.get("requirement_id")):
            reasons.append(f"{prefix}:missing_requirement_id")
        if not _string_list(entry.get("generated_surfaces")):
            reasons.append(f"{prefix}:missing_generated_surface")
        if not _string_list(entry.get("evidence_refs")):
            reasons.append(f"{prefix}:missing_evidence_ref")
        if not _first_text(entry.get("status")):
            reasons.append(f"{prefix}:missing_status")
    status = "blocked" if reasons else "valid"
    return _validation_payload(
        schema_version=GEN_TRACEABILITY_VALIDATION_SCHEMA,
        status=status,
        reasons=sorted(set(reasons)),
    )


def validate_generation_fitness_results(payload: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if payload.get("schema_version") != GEN_FITNESS_RESULTS_SCHEMA:
        reasons.append("invalid_schema_version")
    identity = _safe_mapping(payload.get("identity"))
    for key in (
        "candidate_manifest_sha256",
        "target_contract_sha256",
        "fitness_suite_sha256",
    ):
        if not _first_text(identity.get(key)):
            reasons.append(f"missing_{key}")
    status_value = _first_text(payload.get("status"))
    if status_value not in {
        "fitness_passed",
        "fitness_failed",
        "target_fidelity_unknown",
    }:
        reasons.append("invalid_fitness_status")
    if status_value == "fitness_passed" and payload.get("rendered_state") != (
        "eligible_for_downstream_evidence_review"
    ):
        reasons.append("fitness_passed_requires_command_safe_rendering")
    cases = _safe_list(payload.get("cases"))
    if not cases:
        reasons.append("missing_fitness_case_results")
    for index, raw_case in enumerate(cases):
        case = _safe_mapping(raw_case)
        prefix = f"case_{index}"
        if not _first_text(case.get("case_id")):
            reasons.append(f"{prefix}:missing_case_id")
        if not _first_text(case.get("status")):
            reasons.append(f"{prefix}:missing_status")
        if not _string_list(case.get("evidence_refs")):
            reasons.append(f"{prefix}:missing_evidence_ref")
    status = "blocked" if reasons else "valid"
    return _validation_payload(
        schema_version=GEN_FITNESS_RESULTS_VALIDATION_SCHEMA,
        status=status,
        reasons=sorted(set(reasons)),
    )


def validate_designmd_visual_dossier_requirements_packet(
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate DesignMD visual-dossier requirements as DSPx intake only."""

    reasons: list[str] = []
    if packet.get("schemaVersion") != DESIGNMD_VISUAL_DOSSIER_REQUIREMENTS_SCHEMA:
        reasons.append("invalid_schema_version")

    for key in ("id", "projectId", "sourceId", "analysisRunId", "dossierDraftId"):
        if not _first_text(packet.get(key)):
            reasons.append(f"missing_{key}")

    owner_boundary = _safe_mapping(packet.get("ownerBoundary"))
    if owner_boundary.get("dspxOwnsTargetProtocol") is not True:
        reasons.append("missing_dspx_owner_boundary")
    if owner_boundary.get("noProgramGenExecution") is not True:
        reasons.append("missing_no_program_gen_execution_boundary")

    input_refs = _safe_mapping(packet.get("inputRefs"))
    for key in ("sourceIndexSha256", "designMdSha256", "designMdCurrentSha256"):
        if not _first_text(input_refs.get(key)):
            reasons.append(f"missing_{key}")
    if input_refs.get("sourceIndexSchema") != "designmd.visual-source-index.v1":
        reasons.append("missing_visual_source_index_schema")
    if input_refs.get("dossierDraftSchema") != "designmd.dossier-draft.v1":
        reasons.append("missing_dossier_draft_schema")

    freshness = _safe_mapping(input_refs.get("freshness"))
    if not freshness:
        reasons.append("missing_freshness")
    else:
        stale_reasons = _safe_list(freshness.get("staleReasons"))
        if freshness.get("freshAgainstSource") is False:
            reasons.append("stale_source_index")
        if freshness.get("freshAgainstDesign") is False:
            reasons.append("stale_design_md")
        if stale_reasons:
            reasons.append("stale_input_refs")

    required_lists = {
        "requiredTargetProtocolContent": "missing_target_protocol_requirements",
        "requiredOutputSchemas": "missing_required_output_schemas",
        "roleCoverage": "missing_role_coverage",
        "fixtureRequirements": "missing_fixture_requirements",
        "fitnessGates": "missing_fitness_gates",
        "failClosedBlockers": "missing_fail_closed_blockers",
        "forbiddenClaims": "missing_forbidden_claims",
    }
    for key, reason in required_lists.items():
        if not _string_list(packet.get(key)):
            reasons.append(reason)

    accepted_posture = set(_string_list(packet.get("acceptedOutputPosture")))
    if accepted_posture != {"proposal_context", "review_evidence"}:
        reasons.append("invalid_accepted_output_posture")

    forbidden_claims = set(_string_list(packet.get("forbiddenClaims")))
    for claim in ("accepted_contract_truth", "reviewed_dossier_guidance"):
        if claim not in forbidden_claims:
            reasons.append(f"missing_forbidden_claim:{claim}")

    authority_text = json.dumps(packet.get("authority", {}), sort_keys=True).lower()
    if (
        "mutate design.md" not in authority_text
        and "mutates design.md" not in authority_text
    ):
        reasons.append("missing_designmd_non_mutation_authority_statement")

    status = "blocked" if reasons else "valid"
    return _validation_payload(
        schema_version="designmd-visual-dossier-requirements-validation-v1",
        status=status,
        reasons=sorted(set(reasons)),
    )


def build_designmd_visual_dossier_target_contract_from_requirements(
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize a DesignMD requirements packet into gen-target-contract-v1."""

    incoming_sha = _sha256_payload(packet)
    input_refs = _safe_mapping(packet.get("inputRefs"))
    protocol_requirements = _string_list(packet.get("requiredTargetProtocolContent"))
    required_outputs = _string_list(packet.get("requiredOutputSchemas"))
    fixture_requirements = _string_list(packet.get("fixtureRequirements"))
    fail_closed = _string_list(packet.get("failClosedBlockers"))
    forbidden_claims = _string_list(packet.get("forbiddenClaims"))
    role_coverage = _string_list(packet.get("roleCoverage"))
    payload: dict[str, Any] = {
        "schema_version": GEN_TARGET_CONTRACT_SCHEMA,
        "identity": {
            "intent_sha256": incoming_sha,
            "contract_sha256": "",
            "validator": "dspx.gen_target_contract.v1",
            "validator_version": "v1",
            "requirements_packet_schema": packet.get("schemaVersion"),
            "requirements_packet_sha256": incoming_sha,
        },
        "target": {
            "id": "designmd_visual_dossier",
            "owner": "designmd-foundry",
            "owner_refs": [
                "designmd-foundry/docs/decisions/ADR-0006-dspx-visual-dossier-target-protocol-handoff-boundary.md",
                "designmd-foundry/docs/design-core/dspx-visual-dossier-requirements-packet.md",
                "dspx/docs/project/designmd-visual-dossier-target-protocol-contract.md",
            ],
            "owner_ref_custody": "cross_repo_reference_not_publishable_without_redaction",
            "authority_refs": [],
        },
        "contract_source": "structured_requirements_packet",
        "confirmation_status": "domain_confirmed_for_generation_gate",
        "risk_tier": "authority_adjacent",
        "protocol": {
            "required_stages": [
                "validated_visual_source_packet",
                "role_findings",
                "component_inventory",
                "synthesis_and_coverage_gaps",
                "dossier_builder_traceability",
                "review_evidence_only",
            ],
            "artifact_families": [
                *required_outputs,
                "traceability_matrix",
                "receipt_bundle",
                "review_evidence",
            ],
            "forbidden_shortcuts": [
                *forbidden_claims,
                *fail_closed,
                "skip_designmd_review_record",
                "mutate_designmd_contract",
            ],
        },
        "source_policy": {
            "provenance_required": True,
            "language_policy": "preserve_designmd_packet_labels_and_uncertainty",
            "source_index_sha256": input_refs.get("sourceIndexSha256"),
            "design_md_sha256": input_refs.get("designMdSha256"),
            "design_md_current_sha256": input_refs.get("designMdCurrentSha256"),
        },
        "fitness": {
            "required_adversarial_cases": fixture_requirements
            or fail_closed
            or ["designmd_visual_dossier_target_protocol_regression"],
            "role_coverage": role_coverage,
            "requirements": protocol_requirements,
        },
        "requests": {
            "adapter_materialization": True,
            "shared_oracle_publication": False,
            "promotion_evidence": False,
            "export_evidence": False,
            "activation_evidence": False,
        },
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
            "provider_called": False,
            "shared_oracle_mutated": False,
        },
        "profile_extension": {
            "profile": "designmd-visual-dossier",
            "project_id": packet.get("projectId"),
            "source_id": packet.get("sourceId"),
            "analysis_run_id": packet.get("analysisRunId"),
            "dossier_draft_id": packet.get("dossierDraftId"),
            "accepted_output_posture": _string_list(
                packet.get("acceptedOutputPosture")
            ),
        },
    }
    return _payload_with_identity_hash(payload, identity_key="contract_sha256")


def build_generation_requirements_intake_artifacts(
    *, profile: str, requirements: Mapping[str, Any]
) -> dict[str, Any]:
    """Normalize external requirements into DSPx-native gate artifacts."""

    if profile != "designmd-visual-dossier":
        raise ProgramGenerationContractError(
            f"unsupported requirements profile: {profile}"
        )
    requirements_validation = validate_designmd_visual_dossier_requirements_packet(
        requirements
    )
    target_contract = build_designmd_visual_dossier_target_contract_from_requirements(
        requirements
    )
    fitness_suite = build_generation_fitness_suite_from_target_contract(target_contract)
    generation_gate_preflight = build_generation_gate_preflight(
        target_contract=target_contract, fitness_suite=fitness_suite
    )
    if requirements_validation.get("status") != "valid":
        reasons = sorted(
            set(generation_gate_preflight.get("fail_closed_reasons") or [])
            | set(requirements_validation.get("fail_closed_reasons") or [])
        )
        generation_gate_preflight["status"] = "generation_blocked"
        generation_gate_preflight["generation_allowed"] = False
        generation_gate_preflight["fail_closed_reasons"] = reasons
    return {
        "schema_version": GEN_REQUIREMENTS_INTAKE_SCHEMA,
        "profile": profile,
        "requirements_validation": requirements_validation,
        "target_contract": target_contract,
        "fitness_suite": fitness_suite,
        "generation_gate_preflight": generation_gate_preflight,
        "verifier_guarantee": "requirements_normalized_to_dspx_native_generation_gate_artifacts",
        "verifier_non_guarantee": "semantic_truth_domain_acceptance_or_production_activation",
    }


def write_generation_json(payload: Mapping[str, Any], out: Path) -> dict[str, Any]:
    out_path = out.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    out_path.write_text(_json_text(data), encoding="utf-8")
    return data


def write_generation_gate_preflight(
    payload: Mapping[str, Any], out: Path
) -> dict[str, Any]:
    return write_generation_json(payload, out)
