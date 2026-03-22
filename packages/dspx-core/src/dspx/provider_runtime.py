from __future__ import annotations

import statistics
import time
from typing import Any, Sequence

from dspx.dtos import LMRequest
from dspx.provider_registry import create, ensure_default_providers


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
            payload["runtime"] = meta_fn()
        except Exception as e:
            payload["runtime_error"] = str(e)
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
            "error": str(e),
            "duration_ms": round((time.time() - started) * 1000.0, 3),
        }

    health_fn = getattr(lm, "healthcheck", None)
    if callable(health_fn):
        payload = health_fn(probe=probe, prompt=prompt, max_tokens=max_tokens)
        if "duration_ms" not in payload:
            payload["duration_ms"] = round((time.time() - started) * 1000.0, 3)
        if "provider" not in payload:
            payload["provider"] = provider
        if "metadata" not in payload:
            payload["metadata"] = provider_metadata_from_instance(provider, lm)
        return payload

    payload = provider_metadata_from_instance(provider, lm)
    payload.update(
        {
            "ok": True,
            "provider": provider,
            "duration_ms": round((time.time() - started) * 1000.0, 3),
        }
    )
    if probe:
        probe_started = time.time()
        try:
            text, usage = invoke_provider(lm, prompt=prompt, max_tokens=max_tokens)
            payload["probe"] = {
                "ok": True,
                "text": text,
                "usage": usage,
                "duration_ms": round((time.time() - probe_started) * 1000.0, 3),
            }
        except Exception as e:
            payload["ok"] = False
            payload["error"] = str(e)
            payload["probe"] = {
                "ok": False,
                "error": str(e),
                "duration_ms": round((time.time() - probe_started) * 1000.0, 3),
            }
    return payload


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
                    "error": str(e),
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
                last_text = text
            except Exception as e:
                durations.append((time.time() - t0) * 1000.0)
                errors.append(str(e))

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
