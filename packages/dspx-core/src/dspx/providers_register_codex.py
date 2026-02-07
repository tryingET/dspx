from __future__ import annotations

import os

from .capabilities import ProviderCapabilities
from .provider_registry import register_provider
from dspx.codex_exec_lm import CodexExecLM
from tempfile import TemporaryDirectory
from pathlib import Path


_SANDBOX_HOLDERS: list[TemporaryDirectory] = []  # keep refs to avoid GC cleanup


def _factory() -> CodexExecLM:
    model = os.getenv("CODEX_MODEL", "gpt-5")
    reasoning = os.getenv("CODEX_REASONING", "minimal")
    bypass = os.getenv("CODEX_BYPASS", "1") not in {"", "0", "false", "False"}
    search = os.getenv("CODEX_SEARCH", "0") not in {"", "0", "false", "False"}
    timeout = int(os.getenv("CODEX_TIMEOUT", "0") or 0) or None
    workspace = os.getenv("DSPX_CODEX_WORKSPACE")
    # Optional isolated worktree for safety: create ephemeral cwd
    if os.getenv("DSPX_SANDBOX_WORKTREE", "0") not in {"", "0", "false", "False"}:
        td = TemporaryDirectory(prefix="dspx_sbx_")
        _SANDBOX_HOLDERS.append(td)
        workspace = td.name
        # Create minimal README for traceability
        try:
            Path(workspace, "README.txt").write_text(
                "Temporary sandbox worktree for CodexExecLM (created by DSPX_SANDBOX_WORKTREE=1)",
                encoding="utf-8",
            )
        except Exception:
            pass
    return CodexExecLM(
        model_flag=model,
        auto_mode=not bypass,
        dangerously_bypass=bypass,
        reasoning_effort=reasoning,
        enable_search=search,
        workspace=workspace,
        timeout=timeout,
    )


def register() -> None:
    caps = ProviderCapabilities(
        code_exec=True, supports_tools=False, json_mode=False, multi_turn=True
    )
    register_provider("codex-exec", _factory, caps)
