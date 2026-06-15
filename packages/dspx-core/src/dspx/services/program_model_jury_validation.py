from __future__ import annotations

from typing import Any, Mapping

PROGRAM_MODEL_JURY_RESULTS_SCHEMA = "program-model-jury-results-v1"
ALLOWED_MODEL_JURY_RESULT_STATUSES = frozenset({"executed", "executed_with_failures"})

REQUIRED_FALSE_MODEL_JURY_EFFECT_FLAGS = (
    "program_files_mutated",
    "promotion_review_mutated",
    "new_candidate_generated",
    "oracle_index_mutated",
    "external_authority_mutated",
    "ak_mutated",
    "governance_mutated",
)

REQUIRED_FALSE_MODEL_JURY_NON_AUTHORITY_FLAGS = (
    "promotion_approval",
    "ranking_or_winner_selection",
    "domain_acceptance",
    "external_authority_apply",
    "canonical_mutation",
)


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def validate_program_model_jury_results_contract(
    payload: Mapping[str, Any],
    *,
    label: str = "program model jury results",
    error_type: type[ValueError] = ValueError,
) -> None:
    """Validate shared non-authoritative program model-jury evidence semantics."""

    if payload.get("schema_version") != PROGRAM_MODEL_JURY_RESULTS_SCHEMA:
        raise error_type(
            f"{label} schema_version must be {PROGRAM_MODEL_JURY_RESULTS_SCHEMA}"
        )
    if payload.get("status") not in ALLOWED_MODEL_JURY_RESULT_STATUSES:
        raise error_type(f"{label} must have status executed or executed_with_failures")
    non_authority = _safe_mapping(payload.get("non_authority"))
    invalid_non_authority = [
        key
        for key in REQUIRED_FALSE_MODEL_JURY_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid_non_authority:
        raise error_type(
            f"{label} widens non-authority flags: " + ", ".join(invalid_non_authority)
        )
    effect = _safe_mapping(payload.get("effect"))
    if effect.get("model_jury_evidence_only") is not True:
        raise error_type(f"{label} must be evidence-only")
    invalid_effect = [
        key
        for key in REQUIRED_FALSE_MODEL_JURY_EFFECT_FLAGS
        if effect.get(key) is not False
    ]
    if invalid_effect:
        raise error_type(f"{label} widens effect flags: " + ", ".join(invalid_effect))
    jury = _safe_mapping(payload.get("jury"))
    if jury.get("provider_backed_model_calls") is not True:
        raise error_type(f"{label} must record provider-backed model calls")
    juror_results = [
        item
        for item in _safe_list(payload.get("juror_results"))
        if isinstance(item, Mapping)
    ]
    if not any(str(item.get("status") or "") == "judged" for item in juror_results):
        raise error_type(f"{label} must include at least one judged juror result")
    adjudicator = _safe_mapping(payload.get("adjudicator"))
    if adjudicator.get("promotion_authority") is not False:
        raise error_type(f"{label} adjudicator must not claim promotion authority")
    interpretation = _safe_mapping(payload.get("interpretation"))
    if interpretation.get("ready_for_promotion_decision") is not False:
        raise error_type(f"{label} must not claim promotion-decision readiness")
