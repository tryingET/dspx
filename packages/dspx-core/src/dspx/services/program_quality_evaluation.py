# summary: "Normalizes and evaluates bounded intent-native concept-coverage quality criteria for generated program outputs."
# read_when:
#   - "Changing quality-criteria validation, concept matching, scoring, or runtime status projection."
"""Bounded intent-native quality criteria for generated program behavior."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, cast

QUALITY_EVALUATION_SCHEMA = "program-quality-evaluation-v1"
QUALITY_CRITERIA_EVALUATOR = "concept_coverage"
QUALITY_STATUS_TO_BEHAVIOR_STATUS = {
    "executed_quality_passed": "passed",
    "executed_valid_review_only": "executed",
    "failed_quality": "failed",
}
_SUCCESSFUL_QUALITY_EXECUTION_STATUSES = {
    "executed",
    "executed_valid_review_only",
}
_MAX_CRITERIA = 20
_MAX_GROUPS = 20
_MAX_TERMS_PER_GROUP = 10
_MAX_FORBIDDEN = 50
_MAX_TERM_CHARS = 256
_MAX_RESPONSE_CHARS = 20_000
_ALLOWED_KEYS = {
    "id",
    "output_field",
    "evaluator",
    "required_concept_groups",
    "forbidden_concepts",
    "min_score",
}
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def _bounded_term(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    text = value.strip()
    if len(text) > _MAX_TERM_CHARS:
        raise ValueError(f"{label} exceeds {_MAX_TERM_CHARS} characters")
    return text


def normalize_quality_criteria(
    value: object, *, outputs: list[str]
) -> list[dict[str, Any]]:
    """Validate and canonicalize the bounded v1 quality criteria contract."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_CRITERIA:
        raise ValueError(
            f"quality_criteria must be a list of at most {_MAX_CRITERIA} items"
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise ValueError(f"quality_criteria[{index}] must be an object")
        item = dict(raw)
        unknown = set(item) - _ALLOWED_KEYS
        if unknown:
            raise ValueError(
                f"quality_criteria[{index}] has unknown fields: {sorted(unknown)}"
            )
        criterion_id = str(item.get("id") or "").strip()
        if not _ID_RE.fullmatch(criterion_id):
            raise ValueError(f"quality_criteria[{index}].id is invalid")
        if criterion_id in seen:
            raise ValueError(f"duplicate quality criterion id: {criterion_id}")
        seen.add(criterion_id)
        output_field = str(item.get("output_field") or "").strip()
        if output_field not in outputs:
            raise ValueError(
                f"quality criterion {criterion_id!r} references undeclared output {output_field!r}"
            )
        evaluator = str(item.get("evaluator") or "").strip()
        if evaluator != QUALITY_CRITERIA_EVALUATOR:
            raise ValueError(
                f"quality criterion {criterion_id!r} evaluator must be {QUALITY_CRITERIA_EVALUATOR}"
            )
        groups = item.get("required_concept_groups")
        if not isinstance(groups, list) or not groups or len(groups) > _MAX_GROUPS:
            raise ValueError(
                f"quality criterion {criterion_id!r} requires 1-{_MAX_GROUPS} concept groups"
            )
        normalized_groups: list[list[str]] = []
        for group_index, group in enumerate(groups):
            if (
                not isinstance(group, list)
                or not group
                or len(group) > _MAX_TERMS_PER_GROUP
            ):
                raise ValueError(
                    f"quality criterion {criterion_id!r} group {group_index} must contain 1-{_MAX_TERMS_PER_GROUP} terms"
                )
            normalized_groups.append(
                [
                    _bounded_term(
                        term,
                        label=f"quality criterion {criterion_id!r} group term",
                    )
                    for term in group
                ]
            )
        forbidden = item.get("forbidden_concepts", [])
        if not isinstance(forbidden, list) or len(forbidden) > _MAX_FORBIDDEN:
            raise ValueError(
                f"quality criterion {criterion_id!r} forbidden_concepts must contain at most {_MAX_FORBIDDEN} terms"
            )
        normalized_forbidden = [
            _bounded_term(
                term, label=f"quality criterion {criterion_id!r} forbidden term"
            )
            for term in forbidden
        ]
        min_score = item.get("min_score", 1.0)
        if (
            isinstance(min_score, bool)
            or not isinstance(min_score, (int, float))
            or not math.isfinite(float(min_score))
            or not 0 <= float(min_score) <= 1
        ):
            raise ValueError(
                f"quality criterion {criterion_id!r} min_score must be finite and between 0 and 1"
            )
        normalized.append(
            {
                "id": criterion_id,
                "output_field": output_field,
                "evaluator": evaluator,
                "required_concept_groups": normalized_groups,
                "forbidden_concepts": normalized_forbidden,
                "min_score": float(min_score),
            }
        )
    return normalized


def _contains(text: str, term: str) -> bool:
    normalized = " ".join(text.casefold().split())
    needle = " ".join(term.casefold().split())
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", normalized) is not None


def declared_quality_output_fields(criteria: object) -> set[str]:
    """Return output fields governed by an already-normalized quality contract."""
    if not isinstance(criteria, list):
        return set()
    fields: set[str] = set()
    for item in criteria:
        if not isinstance(item, Mapping):
            continue
        item = cast(Mapping[str, object], item)
        output_field = item.get("output_field")
        if isinstance(output_field, str) and output_field:
            fields.add(output_field)
    return fields


def normalize_declared_quality_behavior_status(status: object) -> str | None:
    """Map declared-quality runtime statuses into Oracle behavior categories."""
    return QUALITY_STATUS_TO_BEHAVIOR_STATUS.get(str(status or "").strip().lower())


def runtime_status_with_declared_quality(
    execution_status: str, quality_status: object
) -> str:
    """Project declared quality over successful execution without hiding review mode."""
    if (
        execution_status not in _SUCCESSFUL_QUALITY_EXECUTION_STATUSES
        or quality_status == "not_declared"
    ):
        return execution_status
    if quality_status != "passed":
        return "failed_quality"
    if execution_status == "executed_valid_review_only":
        return execution_status
    return "executed_quality_passed"


def evaluate_declared_quality(
    criteria: object, observed_outputs: Mapping[str, Any]
) -> dict[str, Any]:
    """Evaluate already-normalized criteria without models, I/O, or authority effects."""
    if not isinstance(criteria, list) or not criteria:
        return {
            "schema_version": QUALITY_EVALUATION_SCHEMA,
            "status": "not_declared",
            "criteria_total": 0,
            "criteria_passed": 0,
            "criteria_failed": 0,
            "criteria": [],
            "quality_approved": False,
        }
    rows: list[dict[str, Any]] = []
    for raw in criteria:
        criterion = cast(dict[str, Any], raw)
        output_field = str(criterion["output_field"])
        response = observed_outputs.get(output_field)
        missing_output = not isinstance(response, str) or not response
        bounded_response = response if isinstance(response, str) else ""
        if len(bounded_response) > _MAX_RESPONSE_CHARS:
            missing_output = True
            bounded_response = ""
        groups = cast(list[list[str]], criterion["required_concept_groups"])
        matched = [
            any(_contains(bounded_response, term) for term in group) for group in groups
        ]
        forbidden_hits = [
            term
            for term in cast(list[str], criterion["forbidden_concepts"])
            if _contains(bounded_response, term)
        ]
        score = 0.0 if missing_output or forbidden_hits else sum(matched) / len(groups)
        passed = (
            score >= float(criterion["min_score"])
            and not missing_output
            and not forbidden_hits
        )
        rows.append(
            {
                "id": criterion["id"],
                "output_field": output_field,
                "evaluator": QUALITY_CRITERIA_EVALUATOR,
                "status": "passed" if passed else "failed",
                "score": round(score, 6),
                "min_score": criterion["min_score"],
                "required_groups_total": len(groups),
                "required_groups_matched": sum(matched),
                "missing_group_indexes": [
                    index for index, value in enumerate(matched) if not value
                ],
                "forbidden_hits": forbidden_hits,
                "missing_output": missing_output,
            }
        )
    passed_count = sum(row["status"] == "passed" for row in rows)
    return {
        "schema_version": QUALITY_EVALUATION_SCHEMA,
        "status": "passed" if passed_count == len(rows) else "failed",
        "criteria_total": len(rows),
        "criteria_passed": passed_count,
        "criteria_failed": len(rows) - passed_count,
        "criteria": rows,
        "quality_approved": False,
    }
