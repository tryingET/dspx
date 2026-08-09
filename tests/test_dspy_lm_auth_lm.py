from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

import dspx.dspy_lm_auth_lm as adapter
from dspx.dspy_lm_auth_lm import DspyLMAuthLM
from dspx.services.program_oracle_semantic_adapter_v11 import (
    ReceiptSafeDspyLMAuthLM,
)


@dataclass
class _Response:
    output_text: str = "secret-output"
    model: str = "gpt-5.6-sol"
    usage: dict[str, int] | None = None


class _Inner:
    def __init__(self, result: object) -> None:
        self.result = result
        self.kwargs: dict[str, Any] | None = None
        self._uses_codex_route = True
        self.num_retries = 0

    def forward(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class _TaintedError(RuntimeError):
    def __str__(self) -> str:  # pragma: no cover - must never be called
        raise AssertionError("tainted exception stringification forbidden")


class _TaintedResponse:
    usage = {"secret": {"nested": "forbidden"}}
    model = object()

    def __str__(self) -> str:  # pragma: no cover - must never be called
        raise AssertionError("tainted response stringification forbidden")


def _lm(
    result: object, *, strict: bool = True, receipt_safe: bool = True
) -> tuple[DspyLMAuthLM, _Inner]:
    inner = _Inner(result)
    adapter_type = ReceiptSafeDspyLMAuthLM if receipt_safe else DspyLMAuthLM
    lm = adapter_type(
        model="codex/gpt-5.6-sol",
        auth_provider="codex",
        strict=True if receipt_safe else strict,
        kwargs={"reasoning_effort": "max"},
    )
    if receipt_safe:
        lm.strict = strict
    lm._inner = inner
    lm._uses_codex_route = True
    lm._stream_metadata_reader = lambda response: {"sensitive": "metadata"}
    return lm, inner


def test_receipt_mode_rejects_caller_authored_capabilities(monkeypatch):
    monkeypatch.setattr(adapter, "_check_capability", None)
    lm, inner = _lm(_Response())
    with pytest.raises(ValueError, match="receipt call shape"):
        lm.forward(
            prompt="bounded",
            outcome_receipt=object(),
            response_format={"type": "json_schema"},
            cache=False,
            num_retries=0,
            live_attempt=object(),
        )
    assert inner.kwargs is None
    assert lm.history == []


def test_receipt_safe_adapter_rejects_missing_capability(monkeypatch):
    monkeypatch.setattr(adapter, "_check_capability", None)
    lm, _ = _lm(_Response())
    with pytest.raises(ValueError, match="receipt call shape"):
        lm.forward(prompt="bounded")


def test_receipt_parser_never_stringifies_arbitrary_response():
    with pytest.raises(Exception, match="typed output text"):
        ReceiptSafeDspyLMAuthLM._receipt_text(_TaintedResponse())
    with pytest.raises(Exception, match="model shape"):
        ReceiptSafeDspyLMAuthLM._receipt_model(_TaintedResponse())


def test_receipt_adapter_constructor_is_closed():
    with pytest.raises(ValueError, match="configuration drift"):
        ReceiptSafeDspyLMAuthLM(auth_storage="forbidden")
    with pytest.raises(ValueError, match="configuration drift"):
        ReceiptSafeDspyLMAuthLM(timeout=30.0)
    with pytest.raises(ValueError, match="configuration drift"):
        ReceiptSafeDspyLMAuthLM(kwargs={"temperature": 0})


def test_default_nonstrict_behavior_remains_structured_error(monkeypatch):
    monkeypatch.setattr(adapter, "_check_capability", None)
    lm, _ = _lm(RuntimeError("ordinary failure"), strict=False, receipt_safe=False)
    response = lm.forward(prompt="bounded")
    assert response["_dspx_error"] is True
    assert response["error"] == "ordinary failure"
    assert lm.history[0].text == "ordinary failure"
    assert lm.history[0].error == "ordinary failure"
