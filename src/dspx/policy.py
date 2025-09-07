from __future__ import annotations

from typing import Optional, Mapping, Any
import os


def _as_set(val: Optional[str]) -> set[str] | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return {p.strip() for p in s.split(",") if p.strip()}


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v is not None else default


def bypass() -> bool:
    v = _env("DSPX_POLICY_BYPASS", "0")
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def allowed_tools() -> set[str] | None:
    return _as_set(_env("DSPX_POLICY_ALLOWED_TOOLS"))


def disallowed_tools() -> set[str]:
    return _as_set(_env("DSPX_POLICY_DISALLOWED_TOOLS")) or set()


def allowed_providers() -> set[str] | None:
    return _as_set(_env("DSPX_POLICY_ALLOWED_PROVIDERS"))


def disallowed_providers() -> set[str]:
    return _as_set(_env("DSPX_POLICY_DISALLOWED_PROVIDERS")) or set()


def max_timeout() -> float | None:
    v = _env("DSPX_POLICY_MAX_TIMEOUT")
    if v is None:
        return None
    try:
        t = float(v)
        return t if t > 0 else None
    except Exception:
        return None


def allow_network_mutate() -> bool:
    v = _env("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "0")
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def allowed_http_methods() -> set[str] | None:
    v = _as_set(_env("DSPX_POLICY_ALLOWED_HTTP_METHODS"))
    return {m.upper() for m in v} if v is not None else None


def disallowed_http_methods() -> set[str]:
    v = _as_set(_env("DSPX_POLICY_DISALLOWED_HTTP_METHODS")) or set()
    return {m.upper() for m in v}


def enforce_network_mutate() -> bool:
    v = _env("DSPX_POLICY_ENFORCE_NETWORK_MUTATE", "0")
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def check_tool_allowed(name: str) -> None:
    if bypass():
        return
    allow = allowed_tools()
    deny = disallowed_tools()
    if allow is not None and name not in allow:
        raise PermissionError(f"tool '{name}' is not allowed by policy")
    if name in deny:
        raise PermissionError(f"tool '{name}' is denied by policy")


def apply_timeout_policy(kwargs: Mapping[str, Any] | None) -> dict[str, Any]:
    if kwargs is None:
        return {}
    out = dict(kwargs)
    mt = max_timeout()
    if mt is not None and "timeout" in out:
        try:
            t = float(out.get("timeout"))
            if t > mt:
                out["timeout"] = mt
        except Exception:
            # ignore non-float timeouts
            pass
    return out


def check_provider_allowed(name: str) -> None:
    if bypass():
        return
    allow = allowed_providers()
    deny = disallowed_providers()
    if allow is not None and name not in allow:
        raise PermissionError(f"provider '{name}' is not allowed by policy")
    if name in deny:
        raise PermissionError(f"provider '{name}' is denied by policy")
