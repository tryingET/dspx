# summary: "Implements a deterministic text-only DSPx provider with no DSPy inheritance or external effects."
# read_when:
#   - "Changing the typed-LM offline canary or deterministic provider event evidence."

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Final

from .provider_contract import (
    EffectDisposition,
    ProviderRequest,
    ProviderResult,
)

_STATE_SCHEMA: Final = "dspx-provider-state-v1"
_PROVIDER_KIND: Final = "stub"


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    """Bounded non-secret provider event; prompts and responses are not retained."""

    kind: str
    model: str
    message_count: int
    disposition: EffectDisposition


class StubProvider:
    """Credential-free provider canary owned by DSPx rather than DSPy."""

    def __init__(self, model: str = "stub/echo") -> None:
        if not model.strip():
            raise ValueError("stub provider model must be non-empty")
        self._model = model
        self._events: deque[ProviderEvent] = deque(maxlen=64)

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider_events(self) -> tuple[ProviderEvent, ...]:
        return tuple(self._events)

    def invoke(self, request: ProviderRequest) -> ProviderResult:
        if request.model != self.model:
            raise ValueError("provider request model does not match stub provider")
        text = self._render(request)
        disposition = EffectDisposition.COMPLETED_SUCCESS
        self._events.append(
            ProviderEvent(
                kind="invoke",
                model=self.model,
                message_count=len(request.messages),
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

    def dump_state(self) -> dict[str, object]:
        return {
            "schema": _STATE_SCHEMA,
            "kind": _PROVIDER_KIND,
            "model": self.model,
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
