# summary: "Exposes the explicit stub-only provider support matrix for the DSPy 3.3 typed cutover."
# read_when:
#   - "Changing supported providers, provider selection, or replay-fixture construction."

from __future__ import annotations

import json
import os
import re
from typing import Final, Never

from .capabilities import ProviderCapabilities
from .dspy_typed_lm import DSPyTypedLMAdapter
from .policy import check_provider_allowed
from .stub_provider import StubProvider

SUPPORTED_PROVIDER_NAMES: Final = ("stub",)
REMOVED_PROVIDER_NAMES: Final = frozenset(
    {
        "claude-cli",
        "codex-exec",
        "dspy-lm-auth",
        "gemini-cli",
        "multi",
        "openai-compatible",
        "openrouter",
        "pi-rpc",
        "vllm-local",
    }
)
_PROVIDER_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_REPLAY_FIXTURE_ENV: Final = "DSPX_REPLAY_FIXTURE_JSON"
_STUB_MODEL: Final = "stub/echo"

_STUB_CAPABILITIES: Final = ProviderCapabilities(
    code_exec=False,
    supports_tools=False,
    json_mode=False,
    multi_turn=True,
    structured_output_format="none",
    supports_vision=False,
    supports_audio=False,
)


class ProviderSelectionRequiredError(RuntimeError):
    """Raised when a caller did not explicitly select a supported provider."""


class UnsupportedProviderError(RuntimeError):
    """Raised for a provider deliberately removed by the typed hard cutover."""


class UnknownProviderError(RuntimeError):
    """Raised for a name outside both supported and removed provider sets."""


def supported_provider_names() -> tuple[str, ...]:
    return SUPPORTED_PROVIDER_NAMES


def create(name: str = "stub", *, model: str = "stub/echo") -> DSPyTypedLMAdapter:
    """Create one compiled-in provider; arbitrary registration is unsupported."""

    normalized = _validated_name(name)
    check_provider_allowed(normalized)
    if normalized == "stub":
        if model != _STUB_MODEL:
            raise ValueError(f"stub provider model must be {_STUB_MODEL!r}")
        return DSPyTypedLMAdapter(StubProvider(model=_STUB_MODEL))
    _raise_unsupported_or_unknown(normalized)


def create_from_env(
    env_var: str = "DSPX_PROVIDER",
    *,
    allow_stub_default: bool = False,
) -> DSPyTypedLMAdapter:
    """Resolve an explicit provider selection without live-provider fallback."""

    raw_name = os.getenv(env_var)
    if raw_name is None or not raw_name.strip():
        if not allow_stub_default:
            raise ProviderSelectionRequiredError(
                f"{env_var} must select one of: {', '.join(SUPPORTED_PROVIDER_NAMES)}"
            )
        name = "stub"
    else:
        name = raw_name.strip().lower()

    normalized = _validated_name(name)
    check_provider_allowed(normalized)
    if normalized != "stub":
        _raise_unsupported_or_unknown(normalized)
    fixture_text = _explicit_replay_fixture_text()
    return DSPyTypedLMAdapter(
        StubProvider(model=_STUB_MODEL, explicit_response_text=fixture_text)
    )


def capabilities(name: str) -> ProviderCapabilities:
    normalized = _validated_name(name)
    check_provider_allowed(normalized)
    if normalized == "stub":
        return _STUB_CAPABILITIES
    _raise_unsupported_or_unknown(normalized)


def _explicit_replay_fixture_text() -> str | None:
    raw = os.getenv(_REPLAY_FIXTURE_ENV)
    if raw is None:
        return None
    if len(raw) > 1_000_000:
        raise ValueError("explicit replay fixture exceeds the size bound")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("explicit replay fixture must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("explicit replay fixture must contain a JSON object")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _validated_name(name: str) -> str:
    if not isinstance(name, str):
        raise TypeError("provider name must be a string")
    normalized = name.strip().lower()
    if not _PROVIDER_NAME.fullmatch(normalized):
        raise UnknownProviderError("provider name is invalid")
    return normalized


def _raise_unsupported_or_unknown(name: str) -> Never:
    if name in REMOVED_PROVIDER_NAMES:
        raise UnsupportedProviderError(
            f"provider {name!r} is unsupported after the typed hard cutover; "
            f"supported={SUPPORTED_PROVIDER_NAMES!r}"
        )
    raise UnknownProviderError(
        f"unknown provider {name!r}; supported={SUPPORTED_PROVIDER_NAMES!r}"
    )
