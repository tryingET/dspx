# summary: "Enforces environment-configured provider, tool, capability, and timeout policy."
# read_when:
#   - "Changing DSPx policy environment variables, bypass auditing, or allow and deny checks."

from __future__ import annotations

import logging
import os
from typing import Any, Mapping, Optional

_AUDIT_LOG = logging.getLogger("dspx.policy")


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


def _audit_policy_bypass(kind: str, target: str) -> None:
    _AUDIT_LOG.warning(
        "policy bypass active for %s '%s'",
        kind,
        target,
        extra={
            "dspx_policy_event": "policy_bypass",
            "dspx_policy_kind": kind,
            "dspx_policy_target": target,
        },
    )


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


# --- Capability gating ---


def allowed_capabilities() -> set[str] | None:
    """Comma-separated capability allowlist, e.g., 'network.read,network.mutate'.

    When set, only listed capabilities are allowed (unless bypass is enabled).
    """
    v = _as_set(_env("DSPX_POLICY_ALLOWED_CAPS"))
    return {c.strip().lower() for c in v} if v is not None else None


def disallowed_capabilities() -> set[str]:
    v = _as_set(_env("DSPX_POLICY_DISALLOWED_CAPS")) or set()
    return {c.strip().lower() for c in v}


def check_capability(cap: str) -> None:
    """Enforce capability allow/deny policy, unless bypassed.

    Known caps used by dspx: 'network.read', 'network.mutate'.
    """
    if bypass():
        _audit_policy_bypass("capability", cap)
        return
    cap = cap.strip().lower()
    allow = allowed_capabilities()
    deny = disallowed_capabilities()
    if allow is not None and cap not in allow:
        raise PermissionError(f"capability '{cap}' is not allowed by policy")
    if cap in deny:
        raise PermissionError(f"capability '{cap}' is denied by policy")


def check_tool_allowed(name: str) -> None:
    if bypass():
        _audit_policy_bypass("tool", name)
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
            raw = out.get("timeout")
            if raw is None:
                return out
            if isinstance(raw, (int, float)):
                t = float(raw)
            elif isinstance(raw, str):
                t = float(raw)
            else:
                return out
            if t > mt:
                out["timeout"] = mt
        except Exception:
            # ignore non-float timeouts
            pass
    return out


def check_provider_allowed(name: str) -> None:
    if bypass():
        _audit_policy_bypass("provider", name)
        return
    allow = allowed_providers()
    deny = disallowed_providers()
    if allow is not None and name not in allow:
        raise PermissionError(f"provider '{name}' is not allowed by policy")
    if name in deny:
        raise PermissionError(f"provider '{name}' is denied by policy")
