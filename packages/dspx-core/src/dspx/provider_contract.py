# summary: "Defines DSPx-owned provider invocation, result, and effect contracts independent of DSPy."
# read_when:
#   - "Adding a provider, changing provider effects, or adapting providers to DSPy."

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Protocol, runtime_checkable


class EffectDisposition(StrEnum):
    """What is known about provider effects after an invocation attempt."""

    NOT_STARTED = "not_started"
    PREFLIGHT_REJECTED = "preflight_rejected"
    COMPLETED_SUCCESS = "completed_success"
    COMPLETED_FAILURE = "completed_failure"
    EFFECT_INDETERMINATE = "effect_indeterminate"
    CANCELLED_BEFORE_START = "cancelled_before_start"
    CANCELLED_AFTER_START = "cancelled_after_start"


@dataclass(frozen=True, slots=True)
class ProviderAttemptEvent:
    """Bounded secret-free terminal evidence for one provider invocation attempt."""

    provider_kind: str
    requested_model: str
    observed_model: str | None
    dispatch_count: int
    disposition: EffectDisposition


@dataclass(frozen=True, slots=True)
class ProviderMessage:
    """One text-only message accepted by the first typed-provider slice."""

    role: str
    text: str


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """DSPx-owned provider request, intentionally distinct from DSPy LMRequest."""

    model: str
    messages: tuple[ProviderMessage, ...]


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """Completed provider result plus explicit effect disposition."""

    text: str
    model: str
    effect_disposition: EffectDisposition
    usage: Mapping[str, int] = field(default_factory=dict)
    provider_data: Mapping[str, Any] = field(default_factory=dict)


class ProviderInvocationError(RuntimeError):
    """Safe provider failure carrying the only authoritative effect disposition."""

    def __init__(
        self,
        message: str,
        *,
        disposition: EffectDisposition,
        provider: str,
    ) -> None:
        super().__init__(message)
        self.disposition = disposition
        self.provider = provider


@runtime_checkable
class Provider(Protocol):
    """Synchronous DSPx provider port; it has no DSPy lifecycle surface."""

    @property
    def model(self) -> str: ...

    def invoke(self, request: ProviderRequest) -> ProviderResult: ...

    def dump_state(self) -> dict[str, object]: ...
