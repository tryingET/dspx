# summary: "Provides typed-provider metadata and bounded diagnostic sanitization without legacy invocation bridges."
# read_when:
#   - "Changing typed provider metadata, diagnostics, or direct offline invocation."

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import Any

from dspx.dspy_typed_lm import DSPyTypedLMAdapter
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
    """Return bounded identity metadata for the one supported typed adapter."""

    if provider != "stub" or type(lm.provider) is not StubProvider:
        raise ValueError("provider metadata is available only for the supported stub")

    return {
        "provider": provider,
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
        "runtime": {},
    }


def invoke_provider(
    lm: DSPyTypedLMAdapter,
    *,
    prompt: str,
    max_tokens: int | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Invoke the typed stub once; no signature retry or legacy response parsing."""

    if type(lm.provider) is not StubProvider:
        raise ValueError("typed invocation is available only for the supported stub")

    if max_tokens is not None:
        raise ValueError("typed stub invocation does not support max_tokens")
    result = lm(prompt=prompt)
    if (
        not isinstance(result, list)
        or len(result) != 1
        or not isinstance(result[0], str)
    ):
        raise RuntimeError("typed stub returned an invalid public DSPy result")
    return result[0], {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
