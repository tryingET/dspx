# summary: "Provides typed-provider metadata and bounded diagnostic sanitization without legacy invocation bridges."
# read_when:
#   - "Changing typed provider metadata, diagnostics, or direct offline invocation."

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import Any, cast

from dspy import LMRequest, LMResponse
from dspy.core.types import LMMessage, LMTextPart

from dspx.dspy_typed_lm import DSPyTypedLMAdapter
from dspx.openai_compatible_provider import (
    OpenAICompatibleProvider,
    _validated_model,
)
from dspx.provider_contract import EffectDisposition, ProviderAttemptEvent
from dspx.redaction import redact_headers, redact_url, sanitize_diagnostic_text
from dspx.stub_provider import StubProvider

_MAX_PREVIEW_CHARS = 320
_MAX_COLLECTION_ITEMS = 20
_MAX_MAPPING_ITEMS = 40
_SENSITIVE_FIELD_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "auth_storage",
    "authorization",
    "credential_path",
    "credentials_path",
    "cookie",
    "password",
    "proxy-authorization",
    "secret",
    "secret_path",
    "set-cookie",
    "token",
    "token_path",
}
_SENSITIVE_FIELD_SUFFIXES = (
    "_access_token",
    "_api_key",
    "_auth_storage",
    "_credential_path",
    "_credentials_path",
    "_password",
    "_secret",
    "_secret_path",
    "_token",
    "_token_path",
)


def _normalized_field_name(name: str) -> str:
    return str(name or "").strip().lower().replace("-", "_").replace(".", "_")


def _looks_sensitive_field(name: str) -> bool:
    lowered = str(name or "").strip().lower()
    normalized = _normalized_field_name(name)
    return (
        lowered in _SENSITIVE_FIELD_NAMES
        or normalized in _SENSITIVE_FIELD_NAMES
        or lowered.endswith(_SENSITIVE_FIELD_SUFFIXES)
        or normalized.endswith(_SENSITIVE_FIELD_SUFFIXES)
    )


def sanitize_text(text: str, *, limit: int = _MAX_PREVIEW_CHARS) -> str:
    return sanitize_diagnostic_text(text, limit=limit)


def sanitize_payload(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, MappingABC):
        out: dict[str, Any] = {}
        items = list(value.items())
        for index, (key, item) in enumerate(items):
            if index >= _MAX_MAPPING_ITEMS:
                out["__truncated_items__"] = len(items) - _MAX_MAPPING_ITEMS
                break
            key_text = str(key)
            lowered = key_text.lower()
            if lowered == "headers" and isinstance(item, MappingABC):
                out[key_text] = redact_headers(
                    {str(header): str(val) for header, val in item.items()}
                )
            elif _looks_sensitive_field(lowered):
                out[key_text] = "[REDACTED]"
            elif isinstance(item, str) and (
                lowered.endswith("_url")
                or lowered in {"artifact_uri", "base_url", "url"}
            ):
                out[key_text] = sanitize_text(redact_url(item))
            else:
                out[key_text] = sanitize_payload(item)
        return out
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        sanitized = [sanitize_payload(item) for item in items[:_MAX_COLLECTION_ITEMS]]
        if len(items) > _MAX_COLLECTION_ITEMS:
            sanitized.append(f"…[{len(items) - _MAX_COLLECTION_ITEMS} more items]")
        return sanitized
    return sanitize_text(str(value))


_sanitize_text = sanitize_text
_sanitize_payload = sanitize_payload


def provider_metadata_from_instance(
    provider: str, lm: DSPyTypedLMAdapter
) -> dict[str, Any]:
    """Return the backward-compatible metadata contract plus bounded runtime data."""

    if not isinstance(provider, str):
        raise TypeError("provider metadata name must be a string")
    canonical_provider = provider.strip().lower()
    if canonical_provider == "stub" and type(lm.provider) is StubProvider:
        selected = cast(StubProvider | OpenAICompatibleProvider, lm.provider)
    elif (
        canonical_provider == "openai-compatible"
        and type(lm.provider) is OpenAICompatibleProvider
    ):
        selected = cast(StubProvider | OpenAICompatibleProvider, lm.provider)
    else:
        raise ValueError("provider metadata does not match a supported provider")
    with selected.operation_lock:
        runtime = {
            "provider_kind": canonical_provider,
            "base_endpoint": (
                redact_url(selected.base_endpoint)
                if type(selected) is OpenAICompatibleProvider
                else None
            ),
            "effective_timeout": (
                selected.effective_timeout
                if type(selected) is OpenAICompatibleProvider
                else None
            ),
        }
        return {
            "provider": canonical_provider,
            "model": lm.model,
            "model_type": lm.model_type,
            "typed_contract": "typed_lm",
            "capabilities": {
                "supports_tools": False,
                "code_exec": False,
                "json_mode": False,
                "multi_turn": True,
                "structured_output_format": "none",
                "supports_vision": False,
                "supports_audio": False,
            },
            "runtime": runtime,
        }


def _safe_attempt_model(value: object) -> str | None:
    if value == "<invalid>":
        return "<invalid>"
    if not isinstance(value, str):
        return None
    try:
        return _validated_model(value)
    except (TypeError, ValueError):
        return None


def provider_attempts_from_instance(lm: DSPyTypedLMAdapter) -> list[dict[str, Any]]:
    """Project only the exact allowlisted retained provider-attempt fields."""

    if type(lm.provider) not in {StubProvider, OpenAICompatibleProvider}:
        raise ValueError("provider attempts require a supported provider")
    provider = cast(StubProvider | OpenAICompatibleProvider, lm.provider)
    with provider.operation_lock:
        return _project_provider_attempts_locked(provider)


def _project_provider_attempts_locked(
    provider: StubProvider | OpenAICompatibleProvider,
) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for event in provider.provider_events:
        if type(event) is not ProviderAttemptEvent:
            raise ValueError("provider attempt event has an invalid type")
        if (
            event.provider_kind not in {"stub", "openai-compatible"}
            or _safe_attempt_model(event.requested_model) is None
            or (
                event.observed_model is not None
                and _safe_attempt_model(event.observed_model) is None
            )
            or event.dispatch_count not in {0, 1}
            or not isinstance(event.disposition, EffectDisposition)
        ):
            raise ValueError("provider attempt event has invalid fields")
        projected.append(
            {
                "provider_kind": event.provider_kind,
                "requested_model": event.requested_model,
                "observed_model": event.observed_model,
                "dispatch_count": event.dispatch_count,
                "effect_disposition": event.disposition.value,
            }
        )
    return projected


def provider_effect_evidence_from_instance(
    lm: DSPyTypedLMAdapter,
) -> dict[str, Any]:
    """Return the bounded additive provider-effect evidence envelope."""

    if type(lm.provider) not in {StubProvider, OpenAICompatibleProvider}:
        raise ValueError("provider evidence requires a supported provider")
    provider = cast(StubProvider | OpenAICompatibleProvider, lm.provider)
    with provider.operation_lock:
        terminal = provider.terminal_effect
        return {
            "schema_version": "dspx-provider-effect-evidence-v1",
            "attempt_total": provider.attempt_total,
            "attempts_truncated": provider.attempts_truncated,
            "terminal_effect": terminal.value if terminal is not None else None,
            "attempts": _project_provider_attempts_locked(provider),
        }


def invoke_provider(
    lm: DSPyTypedLMAdapter,
    *,
    prompt: str,
    max_tokens: int | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Invoke one supported typed provider without retry or response facsimiles."""

    if type(lm.provider) not in {StubProvider, OpenAICompatibleProvider}:
        raise ValueError("typed invocation requires a supported provider")
    if max_tokens is not None:
        raise ValueError("typed provider invocation does not support max_tokens")
    response = lm(
        request=LMRequest(
            model=lm.model,
            messages=[LMMessage(role="user", parts=[LMTextPart(text=prompt)])],
        )
    )
    if not isinstance(response, LMResponse) or not isinstance(response.text, str):
        raise RuntimeError("typed provider returned an invalid DSPy response")
    usage = response.usage
    if usage is None or all(
        value is None
        for value in (usage.input_tokens, usage.output_tokens, usage.total_tokens)
    ):
        return response.text, None
    return response.text, {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }
