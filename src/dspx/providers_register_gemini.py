from __future__ import annotations

import os

from .capabilities import ProviderCapabilities
from .provider_registry import register_provider
from dspx.gemini_cli_lm import GeminiCLILM


def _factory() -> GeminiCLILM:
    binary = os.getenv("GEMINI_BIN", "gemini")
    cwd = os.getenv("GEMINI_CWD") or None
    timeout = int(os.getenv("GEMINI_TIMEOUT", "0") or 0) or None
    extra = os.getenv("GEMINI_EXTRA_FLAGS") or ""
    extra_flags = [s for s in extra.split() if s]
    # Allow model selection via env GEMINI_MODEL; we simply pass env through
    env = {}
    if os.getenv("GEMINI_MODEL"):
        env["GEMINI_MODEL"] = os.getenv("GEMINI_MODEL", "")
    return GeminiCLILM(binary=binary, cwd=cwd, extra_flags=extra_flags, env=env, timeout=timeout)


def register() -> None:
    caps = ProviderCapabilities(supports_tools=True, code_exec=False, json_mode=False, multi_turn=True)
    register_provider("gemini-cli", _factory, caps)

