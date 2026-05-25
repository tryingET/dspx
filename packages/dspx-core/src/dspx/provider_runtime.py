from __future__ import annotations

import statistics
import time
from collections.abc import Mapping as MappingABC
from typing import Any, Sequence

from dspx.dtos import LMRequest
from dspx.provider_registry import create, ensure_default_providers
from dspx.redaction import redact_headers, redact_url, sanitize_diagnostic_text

_MAX_PREVIEW_CHARS = 320
_MAX_COLLECTION_ITEMS = 20
_MAX_MAPPING_ITEMS = 40
_SENSITIVE_FIELD_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "proxy-authorization",
    "secret",
    "set-cookie",
    "token",
}
_SENSITIVE_FIELD_SUFFIXES = (
    "_access_token",
    "_api_key",
    "_password",
    "_secret",
    "_token",
)


def _looks_sensitive_field(name: str) -> bool:
    lowered = str(name or "").strip().lower()
    return lowered in _SENSITIVE_FIELD_NAMES or lowered.endswith(
        _SENSITIVE_FIELD_SUFFIXES
    )


def _truncate_text(text: str, *, limit: int = _MAX_PREVIEW_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…[truncated]"


def _sanitize_text(text: str, *, limit: int = _MAX_PREVIEW_CHARS) -> str:
    return sanitize_diagnostic_text(text, limit=limit)


def _sanitize_mapping(value: MappingABC[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    items = list(value.items())
    for index, (key, item) in enumerate(items):
        if index >= _MAX_MAPPING_ITEMS:
            out["__truncated_items__"] = max(0, len(items) - _MAX_MAPPING_ITEMS)
            break
        key_text = str(key)
        lowered = key_text.lower()
        if key_text == "headers" and isinstance(item, MappingABC):
            out[key_text] = redact_headers(
                {str(header): str(val) for header, val in item.items()}
            )
            continue
        if _looks_sensitive_field(lowered):
            out[key_text] = "[REDACTED]"
            continue
        if isinstance(item, str) and (
            lowered.endswith("_url") or lowered in {"artifact_uri", "base_url", "url"}
        ):
            out[key_text] = _truncate_text(redact_url(item))
            continue
        out[key_text] = _sanitize_payload(item)
    return out


def _sanitize_payload(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, MappingABC):
        return _sanitize_mapping({str(key): item for key, item in value.items()})
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        sanitized = [_sanitize_payload(item) for item in items[:_MAX_COLLECTION_ITEMS]]
        if len(items) > _MAX_COLLECTION_ITEMS:
            sanitized.append(f"…[{len(items) - _MAX_COLLECTION_ITEMS} more items]")
        return sanitized
    return _sanitize_text(str(value))


def extract_text_from_result(result: Any) -> str:
    try:
        if hasattr(result, "outputs"):
            outputs = getattr(result, "outputs") or []
            if outputs:
                return str(outputs[0] or "").strip()
        if isinstance(result, dict):
            choices = result.get("choices") or []
            if choices:
                c0 = choices[0]
                if isinstance(c0, dict):
                    msg = c0.get("message")
                    if isinstance(msg, dict) and msg.get("content") is not None:
                        return str(msg.get("content") or "").strip()
                    if c0.get("text") is not None:
                        return str(c0.get("text") or "").strip()
        if hasattr(result, "choices"):
            choices = getattr(result, "choices") or []
            if choices:
                c0 = choices[0]
                if isinstance(c0, dict) and c0.get("text") is not None:
                    return str(c0.get("text") or "").strip()
    except Exception:
        pass
    return str(result).strip()


def usage_from_result(result: Any) -> dict[str, Any] | None:
    try:
        if hasattr(result, "usage") and isinstance(getattr(result, "usage"), dict):
            return dict(getattr(result, "usage"))
        if isinstance(result, dict) and isinstance(result.get("usage"), dict):
            return dict(result["usage"])
    except Exception:
        pass
    return None


def provider_metadata_from_instance(provider: str, lm: Any) -> dict[str, Any]:
    caps = getattr(lm, "capabilities", None)
    payload: dict[str, Any] = {
        "provider": provider,
        "model": getattr(lm, "model", None),
        "model_type": getattr(lm, "model_type", None),
    }
    if caps is not None:
        payload["capabilities"] = {
            "supports_tools": bool(getattr(caps, "supports_tools", False)),
            "code_exec": bool(getattr(caps, "code_exec", False)),
            "json_mode": bool(getattr(caps, "json_mode", False)),
            "multi_turn": bool(getattr(caps, "multi_turn", False)),
            "structured_output_format": str(
                getattr(caps, "structured_output_format", "none")
            ),
            "supports_vision": bool(getattr(caps, "supports_vision", False)),
            "supports_audio": bool(getattr(caps, "supports_audio", False)),
        }
    payload["runtime"] = {}
    meta_fn = getattr(lm, "runtime_metadata", None)
    if callable(meta_fn):
        try:
            payload["runtime"] = _sanitize_payload(meta_fn())
        except Exception as e:
            payload["runtime_error"] = _sanitize_text(str(e))
    return payload


def invoke_provider(
    lm: Any,
    *,
    prompt: str,
    max_tokens: int | None = 16,
) -> tuple[str, dict[str, Any] | None]:
    if hasattr(lm, "generate"):
        try:
            result = lm.generate(LMRequest(prompt=prompt), max_tokens=max_tokens)
        except TypeError:
            result = lm.generate(LMRequest(prompt=prompt))
    else:
        try:
            result = lm.forward(prompt=prompt, max_tokens=max_tokens)
        except TypeError:
            result = lm.forward(prompt=prompt)
    return extract_text_from_result(result), usage_from_result(result)


def describe_provider(provider: str) -> dict[str, Any]:
    ensure_default_providers()
    lm = create(provider)
    return provider_metadata_from_instance(provider, lm)


def check_provider_health(
    provider: str,
    *,
    probe: bool = False,
    prompt: str = "Reply with the single word: hello",
    max_tokens: int | None = 16,
) -> dict[str, Any]:
    ensure_default_providers()
    started = time.time()
    try:
        lm = create(provider)
    except Exception as e:
        return {
            "ok": False,
            "provider": provider,
            "error": _sanitize_text(str(e)),
            "duration_ms": round((time.time() - started) * 1000.0, 3),
        }

    health_fn = getattr(lm, "healthcheck", None)
    if callable(health_fn):
        try:
            raw_payload = health_fn(probe=probe, prompt=prompt, max_tokens=max_tokens)
        except Exception as e:
            return _sanitize_payload(
                {
                    "ok": False,
                    "provider": provider,
                    "status": "error",
                    "error": _sanitize_text(str(e)),
                    "duration_ms": round((time.time() - started) * 1000.0, 3),
                    "metadata": provider_metadata_from_instance(provider, lm),
                }
            )
        payload: dict[str, Any] = (
            dict(raw_payload)
            if isinstance(raw_payload, MappingABC)
            else {
                "ok": False,
                "provider": provider,
                "error": f"invalid health payload: {type(raw_payload).__name__}",
            }
        )
        if "duration_ms" not in payload:
            payload["duration_ms"] = round((time.time() - started) * 1000.0, 3)
        if "provider" not in payload:
            payload["provider"] = provider
        if "metadata" not in payload:
            payload["metadata"] = provider_metadata_from_instance(provider, lm)
        return _sanitize_payload(payload)

    payload = provider_metadata_from_instance(provider, lm)
    payload.update(
        {
            "ok": False,
            "provider": provider,
            "status": "unknown",
            "error": "provider has no healthcheck; run with probe=true to verify readiness",
            "duration_ms": round((time.time() - started) * 1000.0, 3),
        }
    )
    if probe:
        probe_started = time.time()
        try:
            text, usage = invoke_provider(lm, prompt=prompt, max_tokens=max_tokens)
            payload["ok"] = True
            payload.pop("error", None)
            payload["status"] = "ok"
            payload["probe"] = {
                "ok": True,
                "text": _sanitize_text(text),
                "usage": _sanitize_payload(usage),
                "duration_ms": round((time.time() - probe_started) * 1000.0, 3),
            }
        except Exception as e:
            sanitized_error = _sanitize_text(str(e))
            payload["ok"] = False
            payload["error"] = sanitized_error
            payload["probe"] = {
                "ok": False,
                "error": sanitized_error,
                "duration_ms": round((time.time() - probe_started) * 1000.0, 3),
            }
    return _sanitize_payload(payload)


def benchmark_providers(
    providers: Sequence[str],
    *,
    prompt: str,
    repeats: int = 3,
    warmup: int = 0,
    max_tokens: int | None = 16,
) -> dict[str, Any]:
    ensure_default_providers()
    started = time.time()
    results: list[dict[str, Any]] = []

    for provider in providers:
        provider_started = time.time()
        item: dict[str, Any] = {"provider": provider}
        try:
            lm = create(provider)
            item.update(provider_metadata_from_instance(provider, lm))
        except Exception as e:
            item.update(
                {
                    "ok": False,
                    "error": _sanitize_text(str(e)),
                    "durations_ms": [],
                    "successes": 0,
                    "failures": repeats,
                }
            )
            results.append(item)
            continue

        for _ in range(max(0, warmup)):
            try:
                invoke_provider(lm, prompt=prompt, max_tokens=max_tokens)
            except Exception:
                break

        durations: list[float] = []
        errors: list[str] = []
        last_text = ""
        for _ in range(max(0, repeats)):
            t0 = time.time()
            try:
                text, _usage = invoke_provider(lm, prompt=prompt, max_tokens=max_tokens)
                durations.append((time.time() - t0) * 1000.0)
                last_text = _sanitize_text(text)
            except Exception as e:
                durations.append((time.time() - t0) * 1000.0)
                errors.append(_sanitize_text(str(e)))

        successes = max(0, repeats - len(errors))
        item.update(
            {
                "ok": len(errors) == 0,
                "successes": successes,
                "failures": len(errors),
                "success_rate": (float(successes) / float(repeats)) if repeats else 0.0,
                "durations_ms": [round(d, 3) for d in durations],
                "duration_mean_ms": round(statistics.mean(durations), 3)
                if durations
                else None,
                "duration_median_ms": round(statistics.median(durations), 3)
                if durations
                else None,
                "duration_min_ms": round(min(durations), 3) if durations else None,
                "duration_max_ms": round(max(durations), 3) if durations else None,
                "last_text": last_text,
                "errors": errors[:5],
                "benchmark_duration_ms": round(
                    (time.time() - provider_started) * 1000.0, 3
                ),
            }
        )
        results.append(item)

    ranked = sorted(
        results,
        key=lambda row: (
            -float(row.get("success_rate") or 0.0),
            float(row.get("duration_median_ms") or float("inf")),
        ),
    )
    return {
        "providers": list(providers),
        "prompt": prompt,
        "repeats": repeats,
        "warmup": warmup,
        "results": results,
        "ranking": [str(row.get("provider") or "") for row in ranked],
        "duration_ms": round((time.time() - started) * 1000.0, 3),
    }
