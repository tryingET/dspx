from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import dspy

from dspx.services.program_model_jury_judgment import (
    JUDGMENT_KEYS,
    judgment_field_text_from_completion,
    parse_model_judgment,
)
from dspx.services.program_foundry_gepa_comparison_model_jury import (
    _run_closed_juror,
)
from dspx.services.program_model_jury_provider_runtime import (
    ProgramModelJuryExecutionError,
)


def _judgment() -> dict[str, object]:
    return {
        "outcome": "supports_review_evidence",
        "rationale": "bounded rationale",
        "evidence_strengths": ["receipt"],
        "concerns": [],
        "improvement_requests": [],
        "confidence": "high",
    }


def test_closed_judgment_round_trips_exact_fields() -> None:
    expected = _judgment()
    assert parse_model_judgment(json.dumps(expected), juror_id="quality") == expected


@pytest.mark.parametrize(
    "missing",
    ["rationale", "improvement_requests", "confidence"],
)
def test_foundry_composed_path_rejects_missing_required_fields(
    missing: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = _judgment()
    value.pop(missing)

    class FakePredict:
        def __call__(self, **kwargs):
            del kwargs
            return SimpleNamespace(judgment_json=json.dumps(value))

    monkeypatch.setattr(dspy, "Predict", lambda signature: FakePredict())
    with pytest.raises(ProgramModelJuryExecutionError, match="closed schema"):
        _run_closed_juror(
            juror={"id": "quality"},
            rubric={"criteria": []},
            candidate_identity={"sha256": "a" * 64},
            evidence_json="{}",
            adjudicator={"kind": "local"},
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"unknown": "echoed evidence"}),
        lambda value: value.pop("concerns"),
        lambda value: value.update({"confidence": "certain"}),
        lambda value: value.update({"rationale": "x" * 4097}),
        lambda value: value.update({"concerns": ["x"] * 17}),
        lambda value: value.update({"evidence_strengths": ["bad\x00text"]}),
    ],
)
def test_closed_judgment_rejects_widening_and_unbounded_text(mutate) -> None:
    value = _judgment()
    mutate(value)
    with pytest.raises(ProgramModelJuryExecutionError):
        parse_model_judgment(value, juror_id="quality")


def test_bare_judgment_object_completion_is_rewrapped_as_field_text() -> None:
    expected = _judgment()
    text = judgment_field_text_from_completion(json.dumps(expected))
    assert text is not None
    assert json.loads(text) == expected
    assert parse_model_judgment(text, juror_id="quality") == expected


def test_bare_judgment_object_with_extra_key_is_not_rewrapped() -> None:
    value = _judgment()
    value["extra"] = "widening"
    assert judgment_field_text_from_completion(json.dumps(value)) is None


def test_bare_judgment_object_with_missing_key_is_not_rewrapped() -> None:
    value = _judgment()
    value.pop("confidence")
    assert judgment_field_text_from_completion(json.dumps(value)) is None


def test_wrapped_judgment_string_completion_passes_through_unchanged() -> None:
    inner = json.dumps(_judgment())
    assert (
        judgment_field_text_from_completion(json.dumps({"judgment_json": inner}))
        == inner
    )


def test_wrapped_judgment_object_completion_is_serialized_as_json_text() -> None:
    expected = _judgment()
    text = judgment_field_text_from_completion(json.dumps({"judgment_json": expected}))
    assert text is not None
    assert json.loads(text) == expected


@pytest.mark.parametrize(
    "completion",
    [
        "[]",
        '["outcome"]',
        '"outcome"',
        "42",
        "null",
        "not json at all",
        json.dumps({"judgment_json": ["outcome"]}),
        json.dumps({"judgment_json": 7}),
        json.dumps({"judgment_json": "{}", "outcome": "withhold"}),
        "{" + json.dumps(_judgment())[1:-1] + ", trailing garbage}",
    ],
)
def test_non_object_and_foreign_completions_are_not_rewrapped(
    completion: str,
) -> None:
    assert judgment_field_text_from_completion(completion) is None


def test_judgment_key_contract_is_pinned() -> None:
    assert JUDGMENT_KEYS == frozenset(_judgment())
