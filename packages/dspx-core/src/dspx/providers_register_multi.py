# summary: "Registers the configurable multi-provider LM factory and its isolation and policy options."
# read_when:
#   - "Changing multi-provider selection, environment settings, isolation, or registry capabilities."

from __future__ import annotations

import math
import os
from typing import List

from .capabilities import ProviderCapabilities
from .provider_registry import register_provider, ensure_default_providers, create
from dspx.multi_provider_lm import MultiProviderLM


def _parse_list(env_name: str, default: str) -> List[str]:
    v = os.getenv(env_name, default)
    if "," in v:
        return [s.strip() for s in v.split(",") if s.strip()]
    return [s for s in v.split() if s]


def _positive_timeout(env_name: str, default: float) -> float:
    raw = os.getenv(env_name)
    try:
        value = default if raw is None else float(raw)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be a positive finite number") from exc
    if value <= 0.0 or not math.isfinite(value):
        raise ValueError(f"{env_name} must be a positive finite number")
    return value


def _factory() -> MultiProviderLM:
    ensure_default_providers()
    names = _parse_list("DSPX_MULTI_PROVIDERS", "pi-rpc,claude-cli,gemini-cli")
    strategy = os.getenv("DSPX_MULTI_STRATEGY", "sequential_first")
    parallel_isolated = os.getenv("DSPX_MULTI_PARALLEL_ISOLATED", "0") not in {
        "",
        "0",
        "false",
        "False",
    }
    base_cwd = os.getenv("DSPX_MULTI_BASE_CWD") or None
    isolation_mode = os.getenv("DSPX_MULTI_ISOLATION_MODE", "mirror")
    policy_bypass = os.getenv("DSPX_MULTI_POLICY_BYPASS", "") not in {
        "",
        "0",
        "false",
        "False",
    }
    policy_allowed = os.getenv("DSPX_MULTI_POLICY_ALLOWED_TOOLS") or None
    policy_disallowed = os.getenv("DSPX_MULTI_POLICY_DISALLOWED_TOOLS") or None
    policy_append = os.getenv("DSPX_MULTI_POLICY_APPEND_SYSTEM_PROMPT") or None
    abort_on_validate = os.getenv("DSPX_MULTI_ABORT_ON_VALIDATE", "1") not in {
        "",
        "0",
        "false",
        "False",
    }
    cleanup_isolated = os.getenv("DSPX_MULTI_CLEANUP_ISOLATED", "1") not in {
        "",
        "0",
        "false",
        "False",
    }
    worktree_commitish = os.getenv("DSPX_MULTI_WORKTREE_COMMITISH", "HEAD")
    provider_timeout_s = _positive_timeout("DSPX_MULTI_TIMEOUT", 60.0)
    provs = []
    resolved_names: List[str] = []
    resolution_errors: list[str] = []
    for n in names:
        try:
            provs.append(create(n))
            resolved_names.append(n)
        except Exception as exc:
            resolution_errors.append(f"{n}: {exc}")
            continue
    if not provs:
        joined = "; ".join(resolution_errors) if resolution_errors else "unknown"
        raise RuntimeError(
            "failed to resolve any providers for DSPX_MULTI_PROVIDERS: " + joined
        )
    names = resolved_names
    return MultiProviderLM(
        providers=provs,
        names=names,
        strategy=strategy,
        parallel_isolated=parallel_isolated,
        base_cwd=base_cwd,
        isolation_mode=isolation_mode,
        worktree_commitish=worktree_commitish,
        abort_others_on_validate=abort_on_validate,
        cleanup_isolated=cleanup_isolated,
        provider_timeout_s=provider_timeout_s,
        policy_bypass_permissions=True if policy_bypass else None,
        policy_allowed_tools=policy_allowed,
        policy_disallowed_tools=policy_disallowed,
        policy_append_system_prompt=policy_append,
    )


def register() -> None:
    # Capabilities: union of underlying at runtime; advertise generic multi-turn
    caps = ProviderCapabilities(
        supports_tools=True, code_exec=True, json_mode=False, multi_turn=True
    )
    register_provider("multi", _factory, caps)
