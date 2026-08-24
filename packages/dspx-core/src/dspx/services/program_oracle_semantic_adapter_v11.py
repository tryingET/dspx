# summary: "Exact configuration and bounded response parsing for the Gate-4 one-shot."
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from dspx.services.program_oracle_semantic_owner_bridge_v11 import (
    DspyLMAuthLM,
    DspyLMAuthResponseError,
)
from dspx.services.program_oracle_semantic_contract_v11 import SemanticV11Error


class ReceiptSafeDspyLMAuthLM(DspyLMAuthLM):
    """Configuration shell; provider invocation exists only inside execute_live_once."""

    def __init__(
        self,
        *,
        model: str = "codex/gpt-5.6-sol",
        auth_provider: str | None = "codex",
        auth_storage: str | None = None,
        timeout: float | None = 60.0,
        strict: bool = True,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        configured = dict(kwargs or {})
        if (
            model != "codex/gpt-5.6-sol"
            or auth_provider != "codex"
            or auth_storage is not None
            or timeout != 60.0
            or strict is not True
            or set(configured) - {"reasoning_effort", "num_retries"}
            or configured.get("reasoning_effort", "max") != "max"
            or configured.get("num_retries", 0) != 0
            or any(
                configured.get(key) is not None
                for key in ("max_output_tokens", "temperature", "top_p", "truncation")
            )
        ):
            raise SemanticV11Error("v11 adapter configuration drift")
        configured.update({"reasoning_effort": "max", "num_retries": 0})
        super().__init__(
            model=model,
            auth_provider=auth_provider,
            auth_storage=auth_storage,
            timeout=timeout,
            strict=True,
            kwargs=configured,
        )

    @staticmethod
    def _field(value: Any, name: str) -> Any:
        if isinstance(value, Mapping):
            return value.get(name)
        return getattr(value, name, None)

    @classmethod
    def _receipt_text(cls, response: Any) -> str:
        output = cls._field(response, "output")
        if isinstance(output, list):
            texts: list[str] = []
            for item in output:
                if cls._field(item, "type") != "message":
                    continue
                content = cls._field(item, "content")
                if not isinstance(content, list):
                    raise DspyLMAuthResponseError(
                        "provider response content shape drift"
                    )
                for block in content:
                    if cls._field(block, "type") != "output_text":
                        continue
                    text = cls._field(block, "text")
                    if not isinstance(text, str):
                        raise DspyLMAuthResponseError(
                            "provider response text shape drift"
                        )
                    texts.append(text)
            if texts:
                return "".join(texts)
        output_text = cls._field(response, "output_text")
        if isinstance(output_text, str):
            return output_text
        raise DspyLMAuthResponseError("provider response lacks typed output text")

    @classmethod
    def _receipt_model(cls, response: Any) -> str:
        raw = cls._field(response, "model")
        if (
            not isinstance(raw, str)
            or not raw
            or len(raw.encode("utf-8")) > 128
            or any(ord(char) < 32 or ord(char) == 127 for char in raw)
        ):
            raise DspyLMAuthResponseError("provider response model shape drift")
        return raw

    def forward(
        self,
        prompt: str | None = None,
        messages: Iterable[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        del prompt, messages, kwargs
        raise SemanticV11Error("direct v11 adapter invocation is forbidden")

    def generate(self, request: Any, **kwargs: Any) -> Any:
        del request, kwargs
        raise SemanticV11Error("direct v11 adapter invocation is forbidden")
