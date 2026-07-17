# summary: "Registers the Pi RPC LM provider with subprocess, session, tool, and timeout controls."
# read_when:
#   - "Changing Pi RPC environment flags, execution defaults, or provider capabilities."

from __future__ import annotations

import os
import shlex

from dspx.capabilities import ProviderCapabilities
from dspx.pi_rpc_lm import PiRPCLM
from dspx.provider_registry import register_provider


def _truthy(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw not in {"", "0", "false", "False", "no", "No"}


def _factory() -> PiRPCLM:
    binary = os.getenv("DSPX_PI_BIN", "pi")
    provider = os.getenv("DSPX_PI_PROVIDER") or None
    model = os.getenv("DSPX_PI_MODEL") or None
    thinking = os.getenv("DSPX_PI_THINKING") or None
    cwd = os.getenv("DSPX_PI_CWD") or None
    timeout = float(os.getenv("DSPX_PI_TIMEOUT", "0") or 0) or None
    strict = _truthy("DSPX_PI_STRICT", True)
    no_tools = _truthy("DSPX_PI_NO_TOOLS", True)
    no_session = _truthy("DSPX_PI_NO_SESSION", True)
    disable_resources = _truthy("DSPX_PI_DISABLE_RESOURCES", True)

    extra_raw = os.getenv("DSPX_PI_EXTRA_FLAGS") or ""
    extra_flags = shlex.split(extra_raw) if extra_raw else []

    env: dict[str, str] = {}
    if os.getenv("DSPX_PI_API_KEY"):
        env["PI_API_KEY"] = os.getenv("DSPX_PI_API_KEY", "")

    return PiRPCLM(
        binary=binary,
        provider=provider,
        model=model,
        thinking=thinking,
        no_tools=no_tools,
        no_session=no_session,
        disable_resources=disable_resources,
        extra_flags=extra_flags,
        env=env,
        cwd=cwd,
        timeout=timeout,
        strict=strict,
    )


def register() -> None:
    caps = ProviderCapabilities(
        supports_tools=False,
        code_exec=False,
        json_mode=False,
        multi_turn=True,
    )
    register_provider("pi-rpc", _factory, caps)
