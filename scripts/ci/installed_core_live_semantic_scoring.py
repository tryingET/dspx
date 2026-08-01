# summary: "Independently scores the exact bounded semantic case from current behavior evidence."
# read_when:
#   - "Changing installed live semantic case binding, concept coverage, or quality checks."

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, cast

from installed_core_proof_io import InstalledCoreGoldenPathError


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstalledCoreGoldenPathError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise InstalledCoreGoldenPathError(f"{label} must be an array")
    return value


def _expect(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise InstalledCoreGoldenPathError(
            f"{label} drift: expected {expected!r}, observed {value!r}"
        )


def _contains(text: str, term: str) -> bool:
    normalized = " ".join(text.casefold().split())
    needle = " ".join(term.casefold().split())
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", normalized) is not None


def verify_semantic_case(
    *, case: Mapping[str, Any], behavior: Mapping[str, Any], row: Mapping[str, Any]
) -> float:
    """Derive semantic score from the exact case and current observed output."""

    intent = _mapping(case.get("intent"), "semantic case intent")
    intent_examples = _sequence(intent.get("examples"), "semantic case examples")
    behavior_examples = _sequence(behavior.get("examples"), "behavior examples")
    _expect(len(intent_examples), 1, "semantic case example count")
    _expect(len(behavior_examples), 1, "behavior example count")
    declared = _mapping(intent_examples[0], "semantic case example")
    observed = _mapping(behavior_examples[0], "behavior example")
    _expect(observed.get("status"), "passed", "behavior example status")
    _expect(observed.get("inputs"), declared.get("inputs"), "behavior example inputs")
    _expect(
        observed.get("expected_outputs"),
        declared.get("outputs"),
        "behavior expected outputs",
    )
    response_field = str(case.get("response_field") or "")
    outputs = _mapping(observed.get("observed_outputs"), "behavior observed outputs")
    response = outputs.get(response_field)
    if not isinstance(response, str) or not response.strip():
        raise InstalledCoreGoldenPathError("bounded semantic response is unavailable")
    groups = _sequence(case.get("required_concept_groups"), "required concept groups")
    forbidden = _sequence(case.get("forbidden_concepts"), "forbidden concepts")
    matched = 0
    missing: list[int] = []
    for index, raw_group in enumerate(groups):
        group = _sequence(raw_group, f"required concept group {index}")
        if any(_contains(response, str(phrase)) for phrase in group):
            matched += 1
        else:
            missing.append(index)
    forbidden_hits = [
        str(phrase) for phrase in forbidden if _contains(response, str(phrase))
    ]
    score = round(matched / len(groups), 6) if groups else 0.0
    _expect(missing, [], "independent semantic missing groups")
    _expect(forbidden_hits, [], "independent semantic forbidden hits")
    _expect(row.get("required_groups_total"), len(groups), "benchmark group total")
    _expect(row.get("required_groups_matched"), matched, "benchmark groups matched")
    _expect(row.get("missing_group_indexes"), missing, "benchmark missing groups")
    _expect(row.get("forbidden_hits"), forbidden_hits, "benchmark forbidden hits")
    _expect(row.get("score"), score, "benchmark independently derived score")
    _expect(
        row.get("response_sha256"),
        hashlib.sha256(response.encode("utf-8")).hexdigest(),
        "benchmark response hash",
    )
    quality = _mapping(observed.get("quality_evaluation"), "quality evaluation")
    _expect(quality.get("status"), "passed", "quality status")
    _expect(quality.get("quality_approved"), False, "quality approval authority")
    criteria = _sequence(quality.get("criteria"), "quality criteria")
    declared_criteria = _sequence(
        intent.get("quality_criteria"), "declared quality criteria"
    )
    _expect(len(criteria), 1, "quality criterion count")
    _expect(len(declared_criteria), 1, "declared quality criterion count")
    criterion = _mapping(criteria[0], "quality criterion")
    declared_criterion = _mapping(declared_criteria[0], "declared quality criterion")
    _expect(criterion.get("id"), declared_criterion.get("id"), "quality criterion id")
    _expect(criterion.get("score"), score, "quality criterion score")
    _expect(criterion.get("missing_group_indexes"), missing, "quality missing groups")
    _expect(criterion.get("forbidden_hits"), forbidden_hits, "quality forbidden hits")
    return score
