# summary: "Validates and records local program promotion decisions from refined reviews, comparisons, or delegated adjudication evidence."
# read_when:
#   - "Changing promotion decision outcomes, identity binding, delegation, comparison decisions, or non-authority guarantees."
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from dspx.security import identity_mismatch_keys
from dspx.services.artifact_boundary import prepare_sidecar_output_path
from dspx.services.program_promotion_refinement import (
    validate_program_promotion_review_refined_contract,
)
from dspx.services.program_refinement import load_program_manifest

PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA = "program-promotion-decision-record-v1"
PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA = "program-promotion-review-refined-v1"
PROGRAM_ADJUDICATOR_DELEGATION_SCHEMA = "program-adjudicator-delegation-v1"
PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA = "program-evidence-adjudication-v1"
PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA = (
    "program-refinement-candidate-comparison-v1"
)

ALLOWED_PROGRAM_PROMOTION_DECISION_OUTCOMES = (
    "withhold",
    "reject",
    "request_more_evidence",
    "promote",
)
ALLOWED_COMPARISON_DECISION_OUTCOMES = (
    "withhold",
    "reject",
    "request_more_evidence",
)

_REQUIRED_FALSE_REFINED_REVIEW_NON_AUTHORITY_FLAGS = (
    "automatic_promotion",
    "oracle_ranking",
    "oracle_pruning",
    "oracle_promotion",
    "program_mutation",
    "new_candidate_generation",
    "promotion_authority",
    "governance_authority",
    "external_mutation",
)

_REQUIRED_FALSE_COMPARISON_NON_AUTHORITY_FLAGS = (
    "oracle_ranking",
    "oracle_pruning",
    "oracle_promotion",
    "winner_selection",
    "automatic_promotion",
    "program_mutation",
    "new_candidate_generation",
    "governance_authority",
    "external_mutation",
)

_DECISION_RECORD_NON_AUTHORITY = {
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

_DECISION_RECORD_EFFECT = {
    "local_decision_record_only": True,
    "program_files_mutated": False,
    "refined_review_mutated": False,
    "new_candidate_generated": False,
    "external_authority_mutated": False,
    "governance_mutated": False,
}

_REQUIRED_FALSE_DECISION_RECORD_NON_AUTHORITY_FLAGS = tuple(
    key for key, value in _DECISION_RECORD_NON_AUTHORITY.items() if value is False
)
_REQUIRED_FALSE_DECISION_RECORD_EFFECT_FLAGS = tuple(
    key for key, value in _DECISION_RECORD_EFFECT.items() if value is False
)
_OPTIONAL_FALSE_DECISION_RECORD_NON_AUTHORITY_FLAGS = (
    "promotion_authority",
    "winner_selection",
)


class ProgramPromotionDecisionError(ValueError):
    """Raised when local program promotion decision recording is invalid."""


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramPromotionDecisionError(f"{label} not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramPromotionDecisionError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramPromotionDecisionError(
            f"{label} must contain a JSON object: {source}"
        )
    return payload


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _identity_exactly_matches(
    actual: Mapping[str, Any], expected: Mapping[str, Any]
) -> bool:
    if not actual or not expected:
        return False
    for key, expected_value in expected.items():
        if expected_value is not None and actual.get(key) != expected_value:
            return False
    return True


def _assert_false_flags(
    payload: Mapping[str, Any], required_false: tuple[str, ...], *, label: str
) -> None:
    invalid = [key for key in required_false if payload.get(key) is not False]
    if invalid:
        raise ProgramPromotionDecisionError(
            f"{label} widens non-authority flags or effect flags: " + ", ".join(invalid)
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_refined_promotion_review(path: Path) -> dict[str, Any]:
    """Load a program-promotion-review-refined-v1 packet for local decision recording."""

    source = path.expanduser().resolve()
    review = _load_json_object(source, label="refined promotion review")
    validate_program_promotion_review_refined_contract(
        review,
        refined_review_path=source,
        error_type=ProgramPromotionDecisionError,
    )
    return review


def validate_decision_input(
    refined_review: Mapping[str, Any],
    *,
    outcome: str,
    decided_by: str,
    rationale: str,
) -> None:
    """Validate explicit adjudicator/operator input for local decision recording."""

    normalized_outcome = str(outcome or "").strip()
    if normalized_outcome not in ALLOWED_PROGRAM_PROMOTION_DECISION_OUTCOMES:
        raise ProgramPromotionDecisionError(
            "program promotion decision outcome must be one of: "
            + ", ".join(ALLOWED_PROGRAM_PROMOTION_DECISION_OUTCOMES)
        )
    if not str(decided_by or "").strip():
        raise ProgramPromotionDecisionError(
            "program promotion decision requires decided_by"
        )
    if not str(rationale or "").strip():
        raise ProgramPromotionDecisionError(
            "program promotion decision requires rationale"
        )
    readiness = _safe_mapping(refined_review.get("review_readiness"))
    ready_for_adjudicator_review = readiness.get("ready_for_adjudicator_review") is True
    if normalized_outcome == "promote" and not ready_for_adjudicator_review:
        missing = _safe_string_list(readiness.get("missing_required_evidence"))
        suffix = f"; missing required evidence: {', '.join(missing)}" if missing else ""
        raise ProgramPromotionDecisionError(
            "promote outcome is not allowed unless review_readiness.ready_for_adjudicator_review is true"
            + suffix
        )


def _promotion_state_after_decision(outcome: str) -> str:
    if outcome == "promote":
        return "local_promotion_decision_recorded"
    return "not_promoted"


def validate_program_promotion_decision_record_contract(
    decision_record: Mapping[str, Any],
    *,
    expected_identities: list[Mapping[str, Any]] | None = None,
    require_non_promoting: bool = False,
) -> None:
    """Validate a promotion-decision sidecar before a downstream consumer trusts it."""

    if (
        decision_record.get("schema_version")
        != PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA
    ):
        raise ProgramPromotionDecisionError(
            "program promotion decision record schema_version must be "
            + PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA
        )
    if decision_record.get("status") != "recorded":
        raise ProgramPromotionDecisionError(
            "program promotion decision record must have status recorded"
        )

    normalized_outcome = str(decision_record.get("outcome") or "").strip()
    if normalized_outcome not in ALLOWED_PROGRAM_PROMOTION_DECISION_OUTCOMES:
        raise ProgramPromotionDecisionError(
            "program promotion decision record outcome must be one of: "
            + ", ".join(ALLOWED_PROGRAM_PROMOTION_DECISION_OUTCOMES)
        )
    if (
        require_non_promoting
        and normalized_outcome not in ALLOWED_COMPARISON_DECISION_OUTCOMES
    ):
        raise ProgramPromotionDecisionError(
            "program promotion decision record outcome must be non-promoting"
        )

    expected_state = _promotion_state_after_decision(normalized_outcome)
    if require_non_promoting:
        expected_state = "not_promoted"
    if decision_record.get("promotion_state_after_decision") != expected_state:
        raise ProgramPromotionDecisionError(
            "program promotion decision record promotion_state_after_decision must be "
            + expected_state
        )

    identity = _safe_mapping(decision_record.get("identity"))
    expected_identity_options = [
        expected for expected in expected_identities or [] if expected
    ]
    if expected_identity_options and not any(
        _identity_exactly_matches(identity, expected)
        for expected in expected_identity_options
    ):
        mismatch_keys = sorted(
            {
                str(key)
                for expected in expected_identity_options
                for key, expected_value in expected.items()
                if expected_value is not None and identity.get(key) != expected_value
            }
        )
        suffix = ": " + ", ".join(mismatch_keys) if mismatch_keys else ""
        raise ProgramPromotionDecisionError(
            "program promotion decision record identity does not match expected identity"
            + suffix
        )

    effect = _safe_mapping(decision_record.get("effect"))
    if effect.get("local_decision_record_only") is not True:
        raise ProgramPromotionDecisionError(
            "program promotion decision record effect must be local_decision_record_only"
        )
    _assert_false_flags(
        effect,
        _REQUIRED_FALSE_DECISION_RECORD_EFFECT_FLAGS,
        label="program promotion decision record",
    )

    non_authority = _safe_mapping(decision_record.get("non_authority"))
    if non_authority.get("local_decision_record_only") is not True:
        raise ProgramPromotionDecisionError(
            "program promotion decision record must be local-only"
        )
    _assert_false_flags(
        non_authority,
        _REQUIRED_FALSE_DECISION_RECORD_NON_AUTHORITY_FLAGS,
        label="program promotion decision record",
    )
    for key in _OPTIONAL_FALSE_DECISION_RECORD_NON_AUTHORITY_FLAGS:
        if key in non_authority and non_authority.get(key) is not False:
            raise ProgramPromotionDecisionError(
                "program promotion decision record widens non-authority flags or effect flags: "
                + key
            )


def _load_program_evidence_adjudication(path: Path) -> dict[str, Any]:
    adjudication = _load_json_object(path, label="program evidence adjudication")
    if adjudication.get("schema_version") != PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA:
        raise ProgramPromotionDecisionError(
            "program evidence adjudication schema_version must be "
            + PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA
        )
    if adjudication.get("status") != "evidence_adjudicated":
        raise ProgramPromotionDecisionError(
            "program evidence adjudication must have status evidence_adjudicated"
        )
    non_authority = _safe_mapping(adjudication.get("non_authority"))
    for key in (
        "activation_authority",
        "governance_authority",
        "oracle_authority",
        "promotion_authority",
    ):
        if non_authority.get(key) is not False:
            raise ProgramPromotionDecisionError(
                f"program evidence adjudication must record non_authority.{key}=false"
            )
    for key in ("automatic_promotion", "winner_selection"):
        if key in non_authority and non_authority.get(key) is not False:
            raise ProgramPromotionDecisionError(
                f"program evidence adjudication must not widen non_authority.{key}"
            )
    return adjudication


def _manifest_identity(manifest: Mapping[str, Any]) -> dict[str, str | None]:
    request = _safe_mapping(manifest.get("request"))
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    return {
        "request_id": _first_text(
            request.get("request_id"),
            candidate_assembly.get("request_id"),
            execution_episode.get("request_id"),
            receipt_bundle.get("request_id"),
        ),
        "candidate_id": _first_text(
            candidate_assembly.get("candidate_id"),
            execution_episode.get("candidate_id"),
            receipt_bundle.get("candidate_id"),
        ),
        "assembly_id": _first_text(
            candidate_assembly.get("assembly_id"), execution_episode.get("assembly_id")
        ),
        "episode_id": _first_text(
            execution_episode.get("episode_id"), receipt_bundle.get("episode_id")
        ),
        "receipt_bundle_id": _first_text(receipt_bundle.get("receipt_bundle_id")),
    }


def _assert_delegation_binds_adjudication(
    delegation: Mapping[str, Any], adjudication: Mapping[str, Any]
) -> None:
    manifest_ref = _safe_mapping(delegation.get("manifest"))
    manifest_path = _first_text(manifest_ref.get("path"))
    if not manifest_path:
        raise ProgramPromotionDecisionError(
            "program adjudicator delegation must include manifest.path for identity binding"
        )
    manifest_file = Path(manifest_path)
    expected_hash = _first_text(manifest_ref.get("sha256"))
    if not expected_hash:
        raise ProgramPromotionDecisionError(
            "program adjudicator delegation must include manifest.sha256 for identity binding"
        )
    actual_hash = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise ProgramPromotionDecisionError(
            "program adjudicator delegation manifest hash does not match referenced manifest"
        )
    try:
        manifest = load_program_manifest(manifest_file)
    except ValueError as exc:
        raise ProgramPromotionDecisionError(str(exc)) from exc
    expected_identity = _manifest_identity(manifest)
    actual_identity = _safe_mapping(adjudication.get("identity"))
    mismatches = identity_mismatch_keys(actual_identity, expected_identity)
    if mismatches:
        raise ProgramPromotionDecisionError(
            "program adjudicator delegation manifest identity does not match evidence adjudication identity: "
            + ", ".join(sorted(mismatches))
        )


def _dspx_adjudicator_outcome(aggregate: Mapping[str, Any]) -> str:
    recommendation = str(aggregate.get("recommendation") or "").strip()
    if aggregate.get("ready_for_domain_decision") is True:
        return "withhold"
    if recommendation == "revise_or_collect_missing_evidence":
        return "request_more_evidence"
    return "withhold"


def _load_program_adjudicator_delegation(path: Path) -> dict[str, Any]:
    delegation = _load_json_object(path, label="program adjudicator delegation")
    if delegation.get("schema_version") != PROGRAM_ADJUDICATOR_DELEGATION_SCHEMA:
        raise ProgramPromotionDecisionError(
            "program adjudicator delegation schema_version must be "
            + PROGRAM_ADJUDICATOR_DELEGATION_SCHEMA
        )
    if delegation.get("status") != "delegated":
        raise ProgramPromotionDecisionError(
            "program adjudicator delegation must have status delegated"
        )
    generated_adjudicator = _safe_mapping(
        delegation.get("generated_program_adjudicator")
    )
    if generated_adjudicator.get("approved_to_decide") is not True:
        raise ProgramPromotionDecisionError(
            "generated program adjudicator must be approved_to_decide"
        )
    if not str(generated_adjudicator.get("id") or "").strip():
        raise ProgramPromotionDecisionError(
            "program adjudicator delegation must name generated_program_adjudicator.id"
        )
    non_authority = _safe_mapping(delegation.get("non_authority"))
    for key in (
        "activation_authority",
        "governance_authority",
        "oracle_authority",
        "promotion_authority",
    ):
        if non_authority.get(key) is not False:
            raise ProgramPromotionDecisionError(
                f"program adjudicator delegation must record non_authority.{key}=false"
            )
    return delegation


def _dspx_adjudicator_rationale(adjudication: Mapping[str, Any], outcome: str) -> str:
    aggregate = _safe_mapping(adjudication.get("aggregate"))
    missing = _safe_string_list(aggregate.get("missing_evidence"))
    counts = _safe_mapping(aggregate.get("judgment_counts"))
    parts = [
        "DSPx adjudicator recorded a local generated-program decision from verified meta-adjudication evidence.",
        f"Outcome is {outcome}; activation_approved remains false.",
    ]
    if missing:
        parts.append("Missing evidence: " + ", ".join(missing) + ".")
    if counts:
        rendered_counts = ", ".join(
            f"{key}={value}" for key, value in sorted(counts.items())
        )
        parts.append("Role judgments: " + rendered_counts + ".")
    parts.append(
        "This is evidence-only and does not mutate AK, governance, Oracle authority, or production activation."
    )
    return " ".join(parts)


def _review_snapshot(refined_review: Mapping[str, Any]) -> dict[str, Any]:
    readiness = _safe_mapping(refined_review.get("review_readiness"))
    return {
        "review_status": refined_review.get("status"),
        "promotion_state": refined_review.get("promotion_state"),
        "candidate_status": refined_review.get("candidate_status"),
        "ready_for_adjudicator_review": readiness.get("ready_for_adjudicator_review")
        is True,
        "missing_required_evidence": _safe_string_list(
            readiness.get("missing_required_evidence")
        ),
    }


def _load_candidate_comparison(path: Path) -> dict[str, Any]:
    comparison = _load_json_object(path, label="program candidate comparison")
    if (
        comparison.get("schema_version")
        != PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA
    ):
        raise ProgramPromotionDecisionError(
            "program candidate comparison schema_version must be "
            + PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA
        )
    non_authority = _safe_mapping(comparison.get("non_authority"))
    if non_authority.get("local_comparison_only") is not True:
        raise ProgramPromotionDecisionError(
            "program candidate comparison must be local-only"
        )
    invalid = [
        key
        for key in _REQUIRED_FALSE_COMPARISON_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid:
        raise ProgramPromotionDecisionError(
            "program candidate comparison widens non-authority flags: "
            + ", ".join(invalid)
        )
    source_identity = _safe_mapping(comparison.get("source_identity"))
    if not any(str(value or "").strip() for value in source_identity.values()):
        raise ProgramPromotionDecisionError(
            "program candidate comparison must include source_identity"
        )
    candidate_identity = _safe_mapping(comparison.get("candidate_identity"))
    if not any(str(value or "").strip() for value in candidate_identity.values()):
        raise ProgramPromotionDecisionError(
            "program candidate comparison must include candidate_identity"
        )
    return comparison


def _comparison_snapshot(comparison: Mapping[str, Any]) -> dict[str, Any]:
    behavior_comparison = _safe_mapping(comparison.get("behavior_comparison"))
    interpretation = _safe_mapping(comparison.get("interpretation"))
    return {
        "comparison_status": comparison.get("status"),
        "source_identity": _safe_mapping(comparison.get("source_identity")),
        "candidate_identity": _safe_mapping(comparison.get("candidate_identity")),
        "behavior_delta": _safe_mapping(behavior_comparison.get("delta")),
        "interpretation": {
            key: interpretation.get(key)
            for key in ("summary", "improvement_observed", "needs_more_evidence")
            if key in interpretation
        },
    }


def build_program_comparison_decision_record(
    *,
    comparison_path: Path,
    outcome: str,
    decided_by: str,
    rationale: str,
    decided_at: str | None = None,
) -> dict[str, Any]:
    """Build a local decision sidecar from source-vs-candidate comparison evidence."""

    comparison_path = comparison_path.expanduser().resolve()
    comparison = _load_candidate_comparison(comparison_path)
    normalized_outcome = str(outcome or "").strip()
    if normalized_outcome not in ALLOWED_COMPARISON_DECISION_OUTCOMES:
        raise ProgramPromotionDecisionError(
            "program comparison decision outcome must be one of: "
            + ", ".join(ALLOWED_COMPARISON_DECISION_OUTCOMES)
        )
    normalized_decided_by = str(decided_by or "").strip()
    normalized_rationale = str(rationale or "").strip()
    if not normalized_decided_by:
        raise ProgramPromotionDecisionError(
            "program comparison decision requires decided_by"
        )
    if not normalized_rationale:
        raise ProgramPromotionDecisionError(
            "program comparison decision requires rationale"
        )
    return {
        "schema_version": PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA,
        "status": "recorded",
        "outcome": normalized_outcome,
        "promotion_state_after_decision": "not_promoted",
        "decided_by": normalized_decided_by,
        "decided_at": decided_at or _utc_now_iso(),
        "rationale": normalized_rationale,
        "identity": _safe_mapping(comparison.get("source_identity")),
        "created_from": {
            "comparison_path": str(comparison_path),
            "comparison_schema_version": comparison.get("schema_version"),
            "comparison_hash": hashlib.sha256(comparison_path.read_bytes()).hexdigest(),
        },
        "review_snapshot": {
            "review_status": "comparison_decision_recorded_from_local_candidate_comparison",
            "promotion_state": "not_promoted",
            "candidate_status": comparison.get("status") or "unknown",
            "ready_for_adjudicator_review": False,
            "missing_required_evidence": [
                "no_refined_promotion_review",
                "no_model_jury_execution_episode",
                "no_external_authority_contract",
            ],
        },
        "comparison_snapshot": _comparison_snapshot(comparison),
        "decision_constraints": {
            "allowed_outcomes": list(ALLOWED_COMPARISON_DECISION_OUTCOMES),
            "promote_requires_ready_review": True,
            "promote_allowed_by_review": False,
            "external_authority_exported": False,
            "source": "program_refinement_candidate_comparison",
        },
        "effect": dict(_DECISION_RECORD_EFFECT),
        "non_authority": {
            **_DECISION_RECORD_NON_AUTHORITY,
            "comparison_decision_only": True,
            "promotion_authority": False,
            "winner_selection": False,
        },
        "notes": [
            "This is a local decision record over comparison evidence only.",
            "It does not choose a winner, promote, export external authority, update governance, or make Oracle authoritative.",
            "Use program-promote plan for a separate local non-applying planning sidecar.",
        ],
    }


def build_program_promotion_decision_record(
    *,
    refined_review_path: Path,
    outcome: str,
    decided_by: str,
    rationale: str,
    decided_at: str | None = None,
) -> dict[str, Any]:
    """Build a local decision sidecar without mutating review or program artifacts."""

    refined_review_path = refined_review_path.expanduser().resolve()
    refined_review = load_refined_promotion_review(refined_review_path)
    normalized_outcome = str(outcome or "").strip()
    normalized_decided_by = str(decided_by or "").strip()
    normalized_rationale = str(rationale or "").strip()
    validate_decision_input(
        refined_review,
        outcome=normalized_outcome,
        decided_by=normalized_decided_by,
        rationale=normalized_rationale,
    )
    readiness = _safe_mapping(refined_review.get("review_readiness"))
    promote_allowed_by_review = readiness.get("ready_for_adjudicator_review") is True
    return {
        "schema_version": PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA,
        "status": "recorded",
        "outcome": normalized_outcome,
        "promotion_state_after_decision": _promotion_state_after_decision(
            normalized_outcome
        ),
        "decided_by": normalized_decided_by,
        "decided_at": decided_at or _utc_now_iso(),
        "rationale": normalized_rationale,
        "identity": _safe_mapping(refined_review.get("identity")),
        "created_from": {
            "refined_review_path": str(refined_review_path),
            "refined_review_schema_version": refined_review.get("schema_version"),
        },
        "review_snapshot": _review_snapshot(refined_review),
        "decision_constraints": {
            "allowed_outcomes": list(ALLOWED_PROGRAM_PROMOTION_DECISION_OUTCOMES),
            "promote_requires_ready_review": True,
            "promote_allowed_by_review": promote_allowed_by_review,
            "external_authority_exported": False,
        },
        "effect": dict(_DECISION_RECORD_EFFECT),
        "non_authority": dict(_DECISION_RECORD_NON_AUTHORITY),
        "notes": [
            "This is a local adjudicator decision record sidecar only.",
            "It does not mutate generated program artifacts or the refined review packet.",
            "It does not export external authority, update governance, or make Oracle authoritative.",
        ],
    }


def build_generated_program_adjudicator_decision_record(
    *,
    evidence_adjudication_path: Path,
    adjudicator_delegation_path: Path,
    decided_at: str | None = None,
) -> dict[str, Any]:
    """Build a local generated-program adjudicator decision after DSPx/meta delegation."""

    evidence_adjudication_path = evidence_adjudication_path.expanduser().resolve()
    adjudicator_delegation_path = adjudicator_delegation_path.expanduser().resolve()
    adjudication = _load_program_evidence_adjudication(evidence_adjudication_path)
    delegation = _load_program_adjudicator_delegation(adjudicator_delegation_path)
    _assert_delegation_binds_adjudication(delegation, adjudication)
    generated_adjudicator = _safe_mapping(
        delegation.get("generated_program_adjudicator")
    )
    aggregate = _safe_mapping(adjudication.get("aggregate"))
    outcome = _dspx_adjudicator_outcome(aggregate)
    decided_by = str(generated_adjudicator.get("id") or "").strip()
    rationale = _dspx_adjudicator_rationale(adjudication, outcome)
    missing_required_evidence = _safe_string_list(aggregate.get("missing_evidence"))
    return {
        "schema_version": PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA,
        "status": "recorded",
        "outcome": outcome,
        "promotion_state_after_decision": _promotion_state_after_decision(outcome),
        "decided_by": decided_by,
        "decided_at": decided_at or _utc_now_iso(),
        "rationale": rationale,
        "identity": _safe_mapping(adjudication.get("identity")),
        "created_from": {
            "program_evidence_adjudication_path": str(evidence_adjudication_path),
            "program_evidence_adjudication_schema_version": adjudication.get(
                "schema_version"
            ),
            "program_adjudicator_delegation_path": str(adjudicator_delegation_path),
            "program_adjudicator_delegation_schema_version": delegation.get(
                "schema_version"
            ),
        },
        "adjudicator_delegation": {
            "decided_by": _safe_mapping(delegation.get("dspx_meta_adjudicator")).get(
                "id"
            ),
            "generated_program_adjudicator": generated_adjudicator,
            "delegation_status": delegation.get("status"),
        },
        "review_snapshot": {
            "review_status": "generated_program_adjudicator_decided_from_delegated_dspx_evidence",
            "promotion_state": "not_promoted",
            "candidate_status": "exploratory",
            "ready_for_adjudicator_review": aggregate.get("ready_for_domain_decision")
            is True,
            "missing_required_evidence": missing_required_evidence,
        },
        "decision_constraints": {
            "allowed_outcomes": ["withhold", "reject", "request_more_evidence"],
            "promote_requires_ready_review": True,
            "promote_allowed_by_review": False,
            "external_authority_exported": False,
            "source": "program_adjudicator_delegation_and_program_evidence_adjudication",
        },
        "effect": dict(_DECISION_RECORD_EFFECT),
        "non_authority": {
            **_DECISION_RECORD_NON_AUTHORITY,
            "dspx_adjudicator_evidence_only": True,
            "delegated_generated_program_adjudicator_only": True,
            "promotion_authority": False,
        },
        "notes": [
            "The DSPx/meta adjudicator delegated local decision scope to the generated-program adjudicator.",
            "This record is the generated-program adjudicator decision, not the DSPx/meta delegation decision.",
            "It does not export external authority, update governance, or activate production.",
        ],
    }


def build_dspx_adjudicator_decision_record(
    *,
    evidence_adjudication_path: Path,
    decided_by: str = "dspx_program_adjudicator_v1",
    decided_at: str | None = None,
) -> dict[str, Any]:
    """Build a legacy direct DSPx adjudicator decision sidecar without delegation."""

    evidence_adjudication_path = evidence_adjudication_path.expanduser().resolve()
    adjudication = _load_program_evidence_adjudication(evidence_adjudication_path)
    aggregate = _safe_mapping(adjudication.get("aggregate"))
    outcome = _dspx_adjudicator_outcome(aggregate)
    normalized_decided_by = str(decided_by or "").strip()
    if not normalized_decided_by:
        raise ProgramPromotionDecisionError(
            "DSPx adjudicator decision requires decided_by"
        )
    rationale = _dspx_adjudicator_rationale(adjudication, outcome)
    missing_required_evidence = _safe_string_list(aggregate.get("missing_evidence"))
    return {
        "schema_version": PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA,
        "status": "recorded",
        "outcome": outcome,
        "promotion_state_after_decision": _promotion_state_after_decision(outcome),
        "decided_by": normalized_decided_by,
        "decided_at": decided_at or _utc_now_iso(),
        "rationale": rationale,
        "identity": _safe_mapping(adjudication.get("identity")),
        "created_from": {
            "program_evidence_adjudication_path": str(evidence_adjudication_path),
            "program_evidence_adjudication_schema_version": adjudication.get(
                "schema_version"
            ),
        },
        "review_snapshot": {
            "review_status": "dspx_adjudicated_from_program_evidence",
            "promotion_state": "not_promoted",
            "candidate_status": "exploratory",
            "ready_for_adjudicator_review": aggregate.get("ready_for_domain_decision")
            is True,
            "missing_required_evidence": missing_required_evidence,
        },
        "decision_constraints": {
            "allowed_outcomes": ["withhold", "reject", "request_more_evidence"],
            "promote_requires_ready_review": True,
            "promote_allowed_by_review": False,
            "external_authority_exported": False,
            "source": "dspx_program_evidence_adjudication",
        },
        "effect": dict(_DECISION_RECORD_EFFECT),
        "non_authority": {
            **_DECISION_RECORD_NON_AUTHORITY,
            "dspx_adjudicator_evidence_only": True,
            "promotion_authority": False,
        },
        "notes": [
            "This is a legacy direct DSPx adjudicator decision record sidecar only.",
            "Prefer generated-program-adjudicator-decision with a program-adjudicator-delegation sidecar when modeling both adjudicator layers.",
            "It does not export external authority, update governance, or activate production.",
        ],
    }


def write_program_promotion_decision_record(
    record: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Write the local decision sidecar and return its JSON-compatible payload."""

    payload = dict(record)
    try:
        out_path = prepare_sidecar_output_path(
            out_path,
            payload=payload,
            artifact_label="program promotion decision record",
            payload_artifact_root_policy="forbid",
        )
    except ValueError as exc:
        raise ProgramPromotionDecisionError(str(exc)) from exc
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
