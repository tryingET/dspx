from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA = "program-promotion-decision-record-v1"
PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA = "program-promotion-review-refined-v1"

ALLOWED_PROGRAM_PROMOTION_DECISION_OUTCOMES = (
    "withhold",
    "reject",
    "request_more_evidence",
    "promote",
)

_FORBIDDEN_OUTPUT_NAMES = {
    "manifest.json",
    "manifest.json.meta.json",
    "promotion_review.json",
    "promotion_adjudication_request.json",
    "promotion_decision_template.json",
    "promotion_review_refined.json",
    "behavior_results.json",
    "oracle_evidence.json",
    "execution_episode.json",
}

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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_refined_promotion_review(path: Path) -> dict[str, Any]:
    """Load a program-promotion-review-refined-v1 packet for local decision recording."""

    review = _load_json_object(path, label="refined promotion review")
    if review.get("schema_version") != PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA:
        raise ProgramPromotionDecisionError(
            "refined promotion review schema_version must be "
            + PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA
        )
    if review.get("promotion_state") != "not_promoted":
        raise ProgramPromotionDecisionError(
            "refined promotion review must keep promotion_state not_promoted"
        )
    non_authority = _safe_mapping(review.get("non_authority"))
    if non_authority.get("local_review_packet_only") is not True:
        raise ProgramPromotionDecisionError(
            "refined promotion review must be a local review packet only"
        )
    invalid = [
        key
        for key in _REQUIRED_FALSE_REFINED_REVIEW_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid:
        raise ProgramPromotionDecisionError(
            "refined promotion review widens non-authority flags: " + ", ".join(invalid)
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


def write_program_promotion_decision_record(
    record: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Write the local decision sidecar and return its JSON-compatible payload."""

    out_path = out_path.expanduser().resolve()
    if out_path.name in _FORBIDDEN_OUTPUT_NAMES:
        raise ProgramPromotionDecisionError(
            f"program promotion decision record must not overwrite {out_path.name}"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(record)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
