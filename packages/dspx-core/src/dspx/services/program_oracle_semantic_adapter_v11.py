# summary: "Opt-in receipt-safe DSPx adapter used only by Oracle semantic v11."
from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from typing import Any

import dspx.dspy_lm_auth_lm as base
from dspx.dspy_lm_auth_lm import (
    DspyLMAuthLM,
    DspyLMAuthMinimalResponse,
    DspyLMAuthResponseError,
    DspyLmAuthCall,
)
from dspx.services.program_oracle_semantic_contract_v11 import SemanticV11Error
from dspx.services.program_oracle_semantic_identity_v11 import PreparedReceipt


class ReceiptSafeDspyLMAuthLM(DspyLMAuthLM):
    """Exact v11 adapter with no generic response/error/usage retention."""

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
        configured["reasoning_effort"] = "max"
        configured["num_retries"] = 0
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
        """Read only the exact typed Responses output; never stringify objects."""

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
    ) -> DspyLMAuthMinimalResponse:
        if (
            not isinstance(prompt, str)
            or not prompt
            or messages is not None
            or set(kwargs)
            != {
                "prepared_receipt",
                "response_format",
                "cache",
                "num_retries",
            }
            or type(kwargs.get("prepared_receipt")) is not PreparedReceipt
            or kwargs.get("cache") is not False
            or kwargs.get("num_retries") != 0
        ):
            raise SemanticV11Error("v11 receipt call shape drift")
        prepared = kwargs["prepared_receipt"]
        if type(prepared) is not PreparedReceipt:  # narrowed above
            raise SemanticV11Error("v11 prepared-receipt capability drift")
        semantic = prepared.semantic_request
        expected_input = [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ]
        if (
            set(semantic)
            != {
                "input",
                "instructions",
                "model",
                "reasoning",
                "store",
                "stream",
                "text",
            }
            or semantic.get("input") != expected_input
            or semantic.get("instructions") != "You are a helpful assistant."
            or semantic.get("text") != {"format": kwargs["response_format"]}
            or semantic.get("model") != "openai/gpt-5.6-sol"
            or semantic.get("reasoning") != {"effort": "max", "summary": "auto"}
            or semantic.get("store") is not False
            or semantic.get("stream") is not True
            or self.requested_model != "codex/gpt-5.6-sol"
            or self.auth_provider != "codex"
            or self.auth_storage is not None
            or self.timeout != 60.0
            or self.strict is not True
            or self.kwargs != {"reasoning_effort": "max", "num_retries": 0}
        ):
            raise SemanticV11Error("v11 adapter/request configuration drift")
        started = time.time()
        failed = True
        try:
            prepared.require_effect_capability()
            if base._check_capability is not None:
                base._check_capability("network.mutate")
            inner = self._build_inner()
            if (
                type(inner) is not prepared.owner_lm_type
                or self._uses_codex_route is not True
                or getattr(inner, "_uses_codex_route", None) is not True
                or getattr(inner, "num_retries", None) != 0
            ):
                raise SemanticV11Error("v11 owner route/retry configuration drift")
            prepared.require_effect_capability()
            response = inner.forward(
                prompt=prompt,
                messages=None,
                outcome_receipt=prepared._provider_receipt,
                response_format=kwargs["response_format"],
                cache=False,
                num_retries=0,
            )
            text = self._receipt_text(response)
            if len(text.encode("utf-8")) > self.MAX_RESPONSE_TEXT_BYTES:
                raise DspyLMAuthResponseError("provider response exceeds bounded size")
            model = self._receipt_model(response)
            failed = False
            return DspyLMAuthMinimalResponse(
                model=model,
                choices=[{"text": text}],
                usage={},
                raw=None,
            )
        except BaseException:
            # Preserve the exact interruption; never stringify or serialize it.
            raise
        finally:
            self.history.append(
                DspyLmAuthCall(
                    model=self.requested_model,
                    auth_provider=self.auth_provider,
                    started_at=started,
                    ended_at=time.time(),
                    text="",
                    usage=None,
                    transport=None,
                    error="receipt_mode_error" if failed else None,
                )
            )
