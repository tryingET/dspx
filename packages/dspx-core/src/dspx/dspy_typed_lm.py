# summary: "Adapts one DSPx-owned provider port to DSPy 3.3's typed custom-LM contract."
# read_when:
#   - "Changing DSPy typed requests, provider translation, LM state, copy, callbacks, or effect failures."

from __future__ import annotations

from typing import Any, Final, cast

from dspy import (
    BaseLM,
    LMRequest,
    LMResponse,
    LMTransportError,
    LMUnsupportedFeatureError,
)
from dspy.core.types import LMTextPart, LMUsage

from .provider_contract import (
    EffectDisposition,
    Provider,
    ProviderInvocationError,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
)
from .stub_provider import StubProvider

_ADAPTER_STATE_SCHEMA: Final = "dspx-dspy-typed-lm-state-v1"
_ADAPTER_CLASS_PATH: Final = "dspx.dspy_typed_lm.DSPyTypedLMAdapter"
_ALLOWED_ROLES: Final = frozenset({"system", "user", "assistant"})
_ALLOWED_USAGE_KEYS: Final = frozenset(
    {"input_tokens", "output_tokens", "total_tokens"}
)
_MAX_OUTPUT_CHARS: Final = 1_000_000


class _ProviderResultFailure(Exception):
    """Internal safe classification; provider-controlled exceptions never cross it."""

    def __init__(self, *, code: str) -> None:
        super().__init__(code)
        self.code = code


class DSPyTypedLMAdapter(BaseLM):
    """The sole DSPy subclass in the typed provider architecture."""

    forward_contract = "typed_lm"

    def __init__(
        self,
        provider: Provider,
        *,
        cache: bool = True,
        callbacks: list[Any] | None = None,
        num_retries: int = 0,
    ) -> None:
        if not isinstance(provider.model, str) or not provider.model.strip():
            raise ValueError("provider model must be a non-empty string")
        super().__init__(
            model=provider.model,
            model_type="text",
            cache=cache,
            callbacks=callbacks,
            num_retries=num_retries,
        )
        self.provider = provider

    # DSPy 3.3 selects this runtime contract through forward_contract, while its
    # BaseLM annotation still describes the legacy signature.
    def forward(  # type: ignore[invalid-method-override]
        self, request: LMRequest
    ) -> LMResponse:
        """Translate one validated typed request and preserve effect disposition."""

        provider_request = self._provider_request(request)
        normalized_error: LMTransportError | None = None
        try:
            result = self.provider.invoke(provider_request)
        except ProviderInvocationError as provider_error:
            code = (
                provider_error.disposition.value
                if isinstance(provider_error.disposition, EffectDisposition)
                else EffectDisposition.EFFECT_INDETERMINATE.value
            )
            normalized_error = self._transport_error(
                "DSPx provider invocation failed", code=code
            )
        except Exception:
            normalized_error = self._transport_error(
                "DSPx provider invocation effect is indeterminate",
                code=EffectDisposition.EFFECT_INDETERMINATE.value,
            )
        if normalized_error is not None:
            raise normalized_error from None

        try:
            return self._typed_response(result)
        except _ProviderResultFailure as result_failure:
            normalized_error = self._transport_error(
                "DSPx provider returned a classified failure",
                code=result_failure.code,
            )
        except Exception:
            normalized_error = self._transport_error(
                "DSPx provider response processing is indeterminate",
                code=EffectDisposition.EFFECT_INDETERMINATE.value,
            )
        raise normalized_error from None

    async def aforward(  # type: ignore[invalid-method-override]
        self, request: LMRequest
    ) -> LMResponse:
        """Reject unsupported async before dispatch; never thread-wrap sync effects."""

        del request
        raise LMUnsupportedFeatureError(
            "DSPx provider does not support native asynchronous invocation",
            features=["async"],
            model=self.model,
            provider=type(self.provider).__name__,
        )

    def dump_state(self) -> dict[str, object]:
        """Return a secret-free trusted-local reconstruction state."""

        if type(self.provider) is not StubProvider:
            raise LMUnsupportedFeatureError(
                "DSPx typed provider state is unsupported for this provider",
                features=["state:provider"],
                model=self.model,
                provider=type(self.provider).__name__,
            )
        provider_state = self.provider.dump_state()
        # Exact reconstruction validates shape before any provider data is returned.
        StubProvider.load_state(provider_state)
        return {
            "_dspy_lm_class": _ADAPTER_CLASS_PATH,
            "schema": _ADAPTER_STATE_SCHEMA,
            "model": self.model,
            "model_type": "text",
            "cache": self.cache,
            "num_retries": self.num_retries,
            "provider_state": provider_state,
        }

    @classmethod
    def load_state(
        cls,
        state: dict[str, Any],
        *,
        allow_custom_lm_class: bool = False,
    ) -> DSPyTypedLMAdapter:
        """Reconstruct only an exact allowlisted DSPx provider descriptor."""

        del allow_custom_lm_class
        payload = dict(state)
        class_path = payload.pop("_dspy_lm_class", _ADAPTER_CLASS_PATH)
        expected = {
            "schema",
            "model",
            "model_type",
            "cache",
            "num_retries",
            "provider_state",
        }
        if set(payload) != expected:
            raise ValueError("typed LM state contains unknown or missing fields")
        if class_path != _ADAPTER_CLASS_PATH:
            raise ValueError("typed LM state names an unexpected adapter class")
        if payload["schema"] != _ADAPTER_STATE_SCHEMA:
            raise ValueError("unsupported typed LM state schema")
        if payload["model_type"] != "text":
            raise ValueError("typed LM state model_type must be text")
        provider_state = payload["provider_state"]
        if not isinstance(provider_state, dict):
            raise TypeError("typed LM provider_state must be a mapping")
        provider = cls._load_provider_state(cast(dict[str, object], provider_state))
        if payload["model"] != provider.model:
            raise ValueError("typed LM state model does not match provider state")
        cache = payload["cache"]
        num_retries = payload["num_retries"]
        if not isinstance(cache, bool) or not isinstance(num_retries, int):
            raise TypeError("typed LM cache and num_retries have invalid types")
        return cls(provider, cache=cache, num_retries=num_retries)

    def copy(self, **kwargs: Any) -> DSPyTypedLMAdapter:
        """Preserve DSPy copy semantics without aliasing provider event state."""

        if kwargs.get("model", self.model) != self.model:
            raise LMUnsupportedFeatureError(
                "DSPx typed provider copies cannot change provider model identity",
                features=["copy:model"],
                model=self.model,
                provider=type(self.provider).__name__,
            )
        if type(self.provider) is not StubProvider:
            raise LMUnsupportedFeatureError(
                "DSPx typed provider copy is unsupported for this provider",
                features=["copy:provider"],
                model=self.model,
                provider=type(self.provider).__name__,
            )
        copied = cast(DSPyTypedLMAdapter, super().copy(**kwargs))
        copied.provider = self._load_provider_state(self.provider.dump_state())
        return copied

    def _provider_request(self, request: LMRequest) -> ProviderRequest:
        issues: list[str] = []
        if request.model != self.model:
            issues.append("model")
        if request.tools:
            issues.append("tools")
        if request.metadata:
            issues.append("request_metadata")
        config = request.config
        non_cache_config = (
            config.temperature,
            config.max_tokens,
            config.top_p,
            config.stop,
            config.n,
            config.logprobs,
            config.response_format,
            config.reasoning,
            config.tool_choice,
            config.prompt_cache,
        )
        if any(value is not None for value in non_cache_config) or config.extensions:
            issues.append("generation_config")
        if config.cache is not None and (
            config.cache.enabled is not self.cache
            or config.cache.rollout_id is not None
        ):
            issues.append("generation_config")

        messages: list[ProviderMessage] = []
        for message in request.messages:
            if message.role not in _ALLOWED_ROLES:
                issues.append(f"message_role:{message.role}")
            if message.name is not None:
                issues.append("message_name")
            if message.metadata:
                issues.append("message_metadata")
            if not message.parts:
                issues.append("empty_message_parts")
                continue
            text_parts: list[str] = []
            for part in message.parts:
                if not isinstance(part, LMTextPart):
                    issues.append(f"message_part:{part.type}")
                    continue
                if part.metadata:
                    issues.append("text_part_metadata")
                text_parts.append(part.text)
            messages.append(
                ProviderMessage(role=message.role, text="".join(text_parts))
            )

        if issues:
            unique_issues = list(dict.fromkeys(issues))
            raise LMUnsupportedFeatureError(
                "DSPx typed provider request contains unsupported features",
                features=unique_issues,
                model=self.model,
                provider=type(self.provider).__name__,
            )
        return ProviderRequest(model=self.model, messages=tuple(messages))

    def _typed_response(self, result: ProviderResult) -> LMResponse:
        if type(result) is not ProviderResult:
            raise TypeError("provider returned an invalid result type")
        if not isinstance(result.effect_disposition, EffectDisposition):
            raise TypeError("provider returned an invalid effect disposition")
        if result.effect_disposition is not EffectDisposition.COMPLETED_SUCCESS:
            raise _ProviderResultFailure(code=result.effect_disposition.value)
        if result.model != self.model:
            raise _ProviderResultFailure(code="provider_model_mismatch")
        if not isinstance(result.text, str) or len(result.text) > _MAX_OUTPUT_CHARS:
            raise ValueError("provider result text is invalid or exceeds the bound")

        provider_data = dict(result.provider_data)
        if provider_data != {"provider_kind": "stub"}:
            raise ValueError("provider data is not in the typed canary allowlist")
        provider_data["effect_disposition"] = result.effect_disposition.value

        usage_data = dict(result.usage)
        if set(usage_data) != _ALLOWED_USAGE_KEYS or any(
            value != 0 or isinstance(value, bool) for value in usage_data.values()
        ):
            raise ValueError("provider usage is not the exact zero-token canary shape")
        usage = LMUsage(
            input_tokens=usage_data.get("input_tokens"),
            output_tokens=usage_data.get("output_tokens"),
            total_tokens=usage_data.get("total_tokens"),
        )
        return LMResponse.from_text(
            result.text,
            model=self.model,
            usage=usage,
            provider_data=provider_data,
        )

    def _transport_error(self, message: str, *, code: str) -> LMTransportError:
        return LMTransportError(
            message,
            code=code,
            model=self.model,
            provider=type(self.provider).__name__,
        )

    @staticmethod
    def _load_provider_state(state: dict[str, object]) -> Provider:
        if state.get("kind") != "stub":
            raise ValueError("typed LM state names an unsupported provider kind")
        return StubProvider.load_state(state)
