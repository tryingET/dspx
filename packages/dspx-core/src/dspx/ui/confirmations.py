from __future__ import annotations

from typing import Any, Mapping, Tuple
from dspx.tools.descriptors import ToolDescriptor


MUTATING_CAPS = {"network.mutate", "filesystem.write", "code.exec"}


def _policy_bypass() -> bool:
    try:
        from dspx.policy import bypass
    except Exception:
        return False
    return bool(bypass())


def _policy_allow_network_mutate() -> bool:
    try:
        from dspx.policy import allow_network_mutate
    except Exception:
        return False
    return bool(allow_network_mutate())


def needs_confirmation(desc: ToolDescriptor) -> bool:
    caps = set(desc.capabilities or [])
    if not caps & MUTATING_CAPS:
        return False
    if _policy_bypass():
        return False
    if caps == {"network.mutate"} and _policy_allow_network_mutate():
        return False
    return True


def build_preview(desc: ToolDescriptor, params: Mapping[str, Any] | None) -> str:
    params = dict(params or {})
    if desc.kind == "openapi" and desc.openapi is not None:
        # Build URL preview
        try:
            from dspx.tools.openapi.caller import _build_url as _u

            try:
                from dspx.redaction import redact_url as _redact
            except Exception:

                def _redact(u: str) -> str:
                    return u

            server = desc.openapi.server or ""
            path = desc.openapi.path or ""
            url = _redact(_u(server, path, params))
        except Exception:
            url = desc.openapi.path or "(unknown path)"
        method = str(desc.openapi.method or "GET").upper()
        return f"{method} {url}"
    # Fallback JSON preview
    try:
        import json as _json

        return _json.dumps(
            {
                "tool": desc.name,
                "capabilities": desc.capabilities,
                "params": params,
            },
            ensure_ascii=False,
        )
    except Exception:
        return f"{desc.name} {params}"


def confirm_and_preview(
    desc: ToolDescriptor, params: Mapping[str, Any] | None
) -> Tuple[bool, str]:
    """Return (requires_confirmation, preview_text)."""
    return needs_confirmation(desc), build_preview(desc, params)
