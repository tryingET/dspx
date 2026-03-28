from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

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


def test_run_generate_dto_prefers_active_lm_capabilities_for_json_mode(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeLM:
        capabilities = SimpleNamespace(json_mode=True)

    def _fake_generate_native_payload(**kwargs):
        captured.update(kwargs)
        return {
            "code": render_simple_signature("SigNames", "Extract names"),
            "signature_name": "SigNames",
            "task_description": "Extract names",
            "backend": "native",
            "strategy": "spec-first",
            "candidate_source": "spec",
            "candidate_score": 1.0,
            "candidate_valid": True,
            "candidate_errors": [],
            "attempts_used": 1,
            "max_attempts": 1,
            "attempts_exhausted": True,
            "fallback_used": False,
            "validation_pass_count": 1,
            "validation_total": 1,
            "validation_pass_rate": 1.0,
            "smoke_pass_count": 1,
            "smoke_total": 1,
            "smoke_pass_rate": 1.0,
            "json_mode": kwargs["json_mode"],
        }

    monkeypatch.setattr(
        sigsvc, "_generate_native_payload", _fake_generate_native_payload
    )
    monkeypatch.setattr(sigsvc, "load_config_env", lambda *args, **kwargs: {})
    monkeypatch.setattr(sigsvc, "enable_mlflow_from_env", lambda *args, **kwargs: None)
    monkeypatch.setattr(sigsvc, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(sigsvc.dspy, "configure", lambda **kwargs: None)
    monkeypatch.setenv("DSPX_PROVIDER", "vllm-local")
    monkeypatch.setenv("DSPX_VLLM_JSON_MODE", "0")

    req = sigsvc.SignatureGenRequest(
        prompt="Extract names",
        template_version="v1",
        options={"class_name": "SigNames"},
    )
    res = sigsvc.run_generate_dto(req, lm=cast(Any, _FakeLM()))

    assert captured["json_mode"] is True
    assert res.metadata["json_mode"] is True


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


def test_signature_smoke_rejects_top_level_side_effects(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    marker = "signature-marker.txt"
    code = f"""
import dspy
(__import__('pathlib').Path({marker!r}).write_text('executed', encoding='utf-8'))

class SigSafe(dspy.Signature):
    text: str = dspy.InputField(desc='input text')
    output: str = dspy.OutputField(desc='output text')
"""

    ok, errors = sigsvc._smoke_signature_code(code, expected_class_name="SigSafe")

    assert ok is False
    assert errors
    assert not (tmp_path / marker).exists()


def test_signature_smoke_rejects_disallowed_multi_imports(tmp_path: Path) -> None:
    code = """
import dspy, os

class SigSafe(dspy.Signature):
    text: str = dspy.InputField(desc='input text')
    output: str = dspy.OutputField(desc='output text')
"""

    ok, errors = sigsvc._smoke_signature_code(code, expected_class_name="SigSafe")

    assert ok is False
    assert any("import_not_allowed:os" in err for err in errors)


def test_signature_smoke_rejects_class_keyword_side_effects(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    marker = tmp_path / "signature-class-keyword-marker.txt"
    code = f"""
import dspy

class SigSafe(
    dspy.Signature,
    metaclass=(open({marker.as_posix()!r}, 'w', encoding='utf-8'), type)[1],
):
    text: str = dspy.InputField(desc='input text')
    output: str = dspy.OutputField(desc='output text')
"""

    ok, errors = sigsvc._smoke_signature_code(code, expected_class_name="SigSafe")

    assert ok is False
    assert errors
    assert not marker.exists()
