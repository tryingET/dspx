# summary: "Regression tests for response-observed dspy-lm-auth model identity."
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import dspx.dspy_lm_auth_lm as adapter_module
from dspx.dspy_lm_auth_lm import DspyLMAuthLM, DspyLMAuthResponseError
from dspx.dtos import LMRequest


class _Inner:
    def __init__(self, response: Any) -> None:
        self.response = response

    def forward(self, **_kwargs: Any) -> Any:
        return self.response


def _lm(monkeypatch: pytest.MonkeyPatch, response: Any) -> DspyLMAuthLM:
    monkeypatch.setattr(adapter_module, "_check_capability", None)
    lm = DspyLMAuthLM(model="codex/configured", auth_provider="codex")
    lm.model = "configured/fallback-must-not-leak"
    monkeypatch.setattr(lm, "_build_inner", lambda: _Inner(response))
    return lm


@pytest.mark.parametrize(
    "response",
    [
        {"model": " observed/model ", "choices": [{"text": "ok"}], "usage": {}},
        SimpleNamespace(model=" observed/model ", choices=[{"text": "ok"}], usage={}),
    ],
)
def test_generate_uses_only_nonempty_response_observed_model(
    monkeypatch: pytest.MonkeyPatch, response: Any
) -> None:
    result = _lm(monkeypatch, response).generate(LMRequest(prompt="offline"))
    assert result.outputs == ["ok"]
    assert result.model == "observed/model"


@pytest.mark.parametrize(
    "response",
    [
        {"choices": [{"text": "ok"}], "usage": {}},
        {"model": "  ", "choices": [{"text": "ok"}], "usage": {}},
        SimpleNamespace(choices=[{"text": "ok"}], usage={}),
        SimpleNamespace(model=None, choices=[{"text": "ok"}], usage={}),
    ],
)
def test_generate_never_falls_back_when_response_model_is_missing(
    monkeypatch: pytest.MonkeyPatch, response: Any
) -> None:
    result = _lm(monkeypatch, response).generate(LMRequest(prompt="offline"))
    assert result.outputs == ["ok"]
    assert result.model is None


def test_generate_rejects_unbounded_response_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = {
        "model": "observed/model",
        "choices": [{"text": "x" * (DspyLMAuthLM.MAX_RESPONSE_TEXT_BYTES + 1)}],
        "usage": {},
    }
    with pytest.raises(DspyLMAuthResponseError, match="bounded size"):
        _lm(monkeypatch, response).generate(LMRequest(prompt="offline"))
