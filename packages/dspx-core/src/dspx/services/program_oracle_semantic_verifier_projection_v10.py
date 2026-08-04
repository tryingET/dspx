# summary: "Re-derives the v10 result's setup/interruption error projection."
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_RESULT_PROJECTED_CASE_ERRORS = frozenset(
    {
        "case_processing_error",
        "interrupted_case_incomplete",
        "interrupted_effect_unresolved",
    }
)

_ROWLESS_CASE_ERRORS = {
    False: frozenset({"case_processing_error", "interrupted_case_incomplete"}),
    True: frozenset({"effect_outcome_unresolved", "interrupted_effect_unresolved"}),
}


def route_fields_are_live(
    semantic: Mapping[str, Any], route: Mapping[str, str]
) -> bool:
    return (
        semantic.get("backend_kind") == "live"
        and semantic.get("preferred_model") == route["model"]
        and semantic.get("configured_provider") == route["provider"]
        and semantic.get("configured_model") == route["model"]
        and semantic.get("executed_provider") is None
        and semantic.get("fixture_sha256") is None
    )


def rowless_case_error_is_consistent(
    classification: object, *, effect_open: bool
) -> bool:
    """Require a rowless case error to agree with its observed effect state."""
    return classification in _ROWLESS_CASE_ERRORS[effect_open]


def result_error_projection(
    events: Sequence[tuple[Mapping[str, Any], str]],
) -> str | None:
    """Return setup/interruption classification, excluding normal scored case errors."""
    for event, _ in reversed(events):
        kind = event.get("kind")
        classification = event.get("classification")
        if kind in {"preflight_error", "attempt_error"}:
            return str(classification)
        if kind == "case_error" and classification in _RESULT_PROJECTED_CASE_ERRORS:
            return str(classification)
    return None
