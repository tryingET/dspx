from __future__ import annotations

import os
from typing import Optional

from .capabilities import ProviderCapabilities
from .provider_registry import register_provider
from dspx.codex_exec_lm import CodexExecLM


def _factory() -> CodexExecLM:
    model = os.getenv("CODEX_MODEL", "gpt-5")
    reasoning = os.getenv("CODEX_REASONING", "minimal")
    bypass = os.getenv("CODEX_BYPASS", "1") not in {"", "0", "false", "False"}
    search = os.getenv("CODEX_SEARCH", "0") not in {"", "0", "false", "False"}
    return CodexExecLM(
        model_flag=model,
        auto_mode=not bypass,
        dangerously_bypass=bypass,
        reasoning_effort=reasoning,
        enable_search=search,
    )


def register() -> None:
    caps = ProviderCapabilities(code_exec=True, supports_tools=False, json_mode=False, multi_turn=True)
    register_provider("codex-exec", _factory, caps)
