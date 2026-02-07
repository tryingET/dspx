from __future__ import annotations

import json
from types import SimpleNamespace

from dspx.templates import render_simple_signature
import dspx.services.signatures_service as sigsvc


def test_build_signature_strategy_prompt_respects_json_mode() -> None:
    p_json = sigsvc.build_signature_strategy_prompt(
        "Extract names",
        class_name_hint="SigNames",
        template_version="v1",
        json_mode=True,
    )
    assert "strict JSON object" in p_json

    p_text = sigsvc.build_signature_strategy_prompt(
        "Extract names",
        class_name_hint="SigNames",
        template_version="v1",
        json_mode=False,
    )
    assert "wrap JSON once" in p_text


def test_generate_native_payload_spec_first(monkeypatch) -> None:
    out = json.dumps(
        {
            "class_name": "TotallyDifferent",
            "description": "Extract people from text",
            "inputs": [{"name": "text", "type": "str", "desc": "input text"}],
            "outputs": [
                {"name": "people", "type": "list[str]", "desc": "person names"}
            ],
        }
    )

    def _fake_predict(_sig: str):
        class _P:
            def __call__(self, **kwargs):
                return SimpleNamespace(spec_json=out)

        return _P()

    monkeypatch.setattr(sigsvc.dspy, "Predict", _fake_predict)

    payload = sigsvc._generate_native_payload(
        prompt_for_model="task",
        fallback_description="Extract people from text",
        class_name_hint="SigPeople",
        json_mode=True,
        max_attempts=1,
        enforce_class_name=True,
    )

    assert payload["candidate_source"] == "spec"
    assert payload["signature_name"] == "SigPeople"
    assert "class SigPeople(dspy.Signature):" in payload["code"]
    assert "people: list[str] = dspy.OutputField" in payload["code"]


def test_generate_native_payload_retries_and_selects_better_candidate(
    monkeypatch,
) -> None:
    outputs = [
        "nonsense",
        json.dumps(
            {
                "class_name": "SigEntity",
                "description": "Extract entities",
                "inputs": [{"name": "text", "type": "str", "desc": "input"}],
                "outputs": [
                    {
                        "name": "entities",
                        "type": "list[str]",
                        "desc": "entity list",
                    }
                ],
            }
        ),
    ]
    state = {"i": 0}

    def _fake_predict(_sig: str):
        class _P:
            def __call__(self, **kwargs):
                idx = min(state["i"], len(outputs) - 1)
                state["i"] += 1
                return SimpleNamespace(spec_json=outputs[idx])

        return _P()

    monkeypatch.setattr(sigsvc.dspy, "Predict", _fake_predict)

    payload = sigsvc._generate_native_payload(
        prompt_for_model="task",
        fallback_description="Extract entities",
        class_name_hint="SigEntity",
        json_mode=False,
        max_attempts=2,
        enforce_class_name=True,
    )

    assert payload["attempts_used"] == 2
    assert payload["candidate_source"] == "spec"
    assert payload["fallback_used"] is False
    assert payload["validation_pass_rate"] == 1.0
    assert payload["smoke_pass_rate"] == 1.0
    assert "entities: list[str] = dspy.OutputField" in payload["code"]


def test_generate_native_payload_marks_fallback_used(monkeypatch) -> None:
    def _fake_predict(_sig: str):
        class _P:
            def __call__(self, **kwargs):
                return SimpleNamespace(spec_json="not-json-or-code")

        return _P()

    monkeypatch.setattr(sigsvc.dspy, "Predict", _fake_predict)

    payload = sigsvc._generate_native_payload(
        prompt_for_model="task",
        fallback_description="Fallback scenario",
        class_name_hint="SigFallback",
        json_mode=True,
        max_attempts=1,
        enforce_class_name=True,
    )

    assert payload["candidate_source"] == "fallback"
    assert payload["fallback_used"] is True
    assert payload["validation_pass_rate"] == 1.0
    assert payload["smoke_pass_rate"] == 1.0


def test_validate_and_score_signature_code() -> None:
    good = render_simple_signature("SigGood", "good")
    bad = "import dspy\n\nclass Bad(dspy.Signature):\n    x ="

    ok_good, _ = sigsvc.validate_signature_code(good, expected_class_name="SigGood")
    ok_bad, errs_bad = sigsvc.validate_signature_code(bad)

    assert ok_good
    assert not ok_bad
    assert errs_bad
    assert sigsvc.score_signature_code(
        good, expected_class_name="SigGood"
    ) > sigsvc.score_signature_code(bad)
