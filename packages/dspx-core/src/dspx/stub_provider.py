# summary: "Implements a deterministic text-only DSPx provider with no DSPy inheritance or external effects."
# read_when:
#   - "Changing the typed-LM offline canary or deterministic provider event evidence."

from __future__ import annotations

from collections import deque
from _thread import RLock as ReentrantLock
from typing import Final

from .provider_contract import (
    EffectDisposition,
    ProviderAttemptEvent,
    ProviderInvocationError,
    ProviderRequest,
    ProviderResult,
)

_STATE_SCHEMA: Final = "dspx-provider-state-v1"
_PROVIDER_KIND: Final = "stub"


class StubProvider:
    """Credential-free provider canary owned by DSPx rather than DSPy."""

    def __init__(
        self,
        model: str = "stub/echo",
        *,
        explicit_response_text: str | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("stub provider model must be non-empty")
        if (
            explicit_response_text is not None
            and len(explicit_response_text) > 1_000_000
        ):
            raise ValueError("explicit stub response exceeds the size bound")
        self._model = model
        self._explicit_response_text = explicit_response_text
        self._operation_lock = ReentrantLock()
        self._events: deque[ProviderAttemptEvent] = deque(maxlen=64)
        self._attempt_total = 0
        self._terminal_effect: EffectDisposition | None = None
        self._indeterminate_latched = False

    @property
    def operation_lock(self) -> ReentrantLock:
        return self._operation_lock

    @property
    def model(self) -> str:
        with self._operation_lock:
            return self._model

    @property
    def provider_events(self) -> tuple[ProviderAttemptEvent, ...]:
        with self._operation_lock:
            return tuple(self._events)

    @property
    def attempt_total(self) -> int:
        with self._operation_lock:
            return self._attempt_total

    @property
    def attempts_truncated(self) -> bool:
        with self._operation_lock:
            return self._attempt_total > len(self._events)

    @property
    def terminal_effect(self) -> EffectDisposition | None:
        with self._operation_lock:
            return self._terminal_effect

    def _record(self, event: ProviderAttemptEvent) -> None:
        self._attempt_total += 1
        self._terminal_effect = event.disposition
        self._events.append(event)

    def invoke(self, request: ProviderRequest) -> ProviderResult:
        with self._operation_lock:
            return self._invoke(request)

    def _invoke(self, request: ProviderRequest) -> ProviderResult:
        if self._indeterminate_latched:
            raise ProviderInvocationError(
                "DSPx stub provider invocation failed",
                disposition=EffectDisposition.EFFECT_INDETERMINATE,
                provider=_PROVIDER_KIND,
            ) from None
        requested_model = (
            request.model
            if type(request) is ProviderRequest and isinstance(request.model, str)
            else "<invalid>"
        )
        if type(request) is not ProviderRequest or request.model != self.model:
            disposition = EffectDisposition.PREFLIGHT_REJECTED
            self._record(
                ProviderAttemptEvent(
                    provider_kind=_PROVIDER_KIND,
                    requested_model=requested_model,
                    observed_model=None,
                    dispatch_count=0,
                    disposition=disposition,
                )
            )
            raise ProviderInvocationError(
                "DSPx stub provider invocation failed",
                disposition=disposition,
                provider=_PROVIDER_KIND,
            ) from None
        text = (
            self._explicit_response_text
            if self._explicit_response_text is not None
            else self._render(request)
        )
        disposition = EffectDisposition.COMPLETED_SUCCESS
        self._record(
            ProviderAttemptEvent(
                provider_kind=_PROVIDER_KIND,
                requested_model=request.model,
                observed_model=self.model,
                dispatch_count=1,
                disposition=disposition,
            )
        )
        return ProviderResult(
            text=text,
            model=self.model,
            effect_disposition=disposition,
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            provider_data={"provider_kind": _PROVIDER_KIND},
        )

    def latch_indeterminate_after_dispatch(self) -> None:
        """Reclassify only the latest dispatched attempt without adding an attempt."""

        with self._operation_lock:
            self._indeterminate_latched = True
            if not self._events or self._events[-1].dispatch_count != 1:
                return
            latest = self._events[-1]
            self._events[-1] = ProviderAttemptEvent(
                provider_kind=latest.provider_kind,
                requested_model=latest.requested_model,
                observed_model=latest.observed_model,
                dispatch_count=latest.dispatch_count,
                disposition=EffectDisposition.EFFECT_INDETERMINATE,
            )
            self._terminal_effect = EffectDisposition.EFFECT_INDETERMINATE

    def dump_state(self) -> dict[str, object]:
        with self._operation_lock:
            if self._indeterminate_latched:
                raise RuntimeError("indeterminate stub provider state is terminal")
            if self._explicit_response_text is not None:
                raise ValueError("explicit replay fixture state is not serializable")
            return {
                "schema": _STATE_SCHEMA,
                "kind": _PROVIDER_KIND,
                "model": self._model,
            }

    @classmethod
    def load_state(cls, state: dict[str, object]) -> StubProvider:
        if set(state) != {"schema", "kind", "model"}:
            raise ValueError("stub provider state contains unknown or missing fields")
        if state["schema"] != _STATE_SCHEMA or state["kind"] != _PROVIDER_KIND:
            raise ValueError("unsupported stub provider state")
        model = state["model"]
        if not isinstance(model, str):
            raise TypeError("stub provider state model must be a string")
        return cls(model=model)

    @staticmethod
    def _render(request: ProviderRequest) -> str:
        if len(request.messages) == 1 and request.messages[0].role == "user":
            return f"stub: {request.messages[0].text}"
        rendered = "\n".join(
            f"{message.role}: {message.text}" for message in request.messages
        )
        return f"stub: {rendered}".rstrip()
