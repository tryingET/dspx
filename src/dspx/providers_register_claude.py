from __future__ import annotations

import os
from typing import Iterable, Optional

from .capabilities import ProviderCapabilities
from .provider_registry import register_provider
from dspx.claude_cli_lm import ClaudeHeadlessLM


def _env_flag(name: str, default_false: bool = True) -> bool:
    v = os.getenv(name, "" if default_false else "1")
    return v not in {"", "0", "false", "False", "no", "No"}


def _env_list(name: str) -> Optional[Iterable[str]]:
    v = os.getenv(name)
    if not v:
        return None
    # Accept comma or space separated
    if "," in v:
        return [s.strip() for s in v.split(",") if s.strip()]
    return [s for s in v.split() if s]


def _factory() -> ClaudeHeadlessLM:
    binary = os.getenv("CLAUDE_BIN", "claude")
    fmt = os.getenv("CLAUDE_OUTPUT_FORMAT", "text")
    model = os.getenv("CLAUDE_MODEL") or None
    fb_model = os.getenv("CLAUDE_FALLBACK_MODEL") or None
    append = os.getenv("CLAUDE_APPEND_SYSTEM_PROMPT") or None
    allowed = _env_list("CLAUDE_ALLOWED_TOOLS")
    disallowed = _env_list("CLAUDE_DISALLOWED_TOOLS")
    perm_mode = os.getenv("CLAUDE_PERMISSION_MODE") or None
    mcp = os.getenv("CLAUDE_MCP_CONFIG") or None
    perm_prompt_tool = os.getenv("CLAUDE_PERMISSION_PROMPT_TOOL") or None
    resume = os.getenv("CLAUDE_RESUME") or None
    cont = _env_flag("CLAUDE_CONTINUE", default_false=True)
    cwd = os.getenv("CLAUDE_CWD") or None
    timeout = int(os.getenv("CLAUDE_TIMEOUT", "0") or 0) or None
    use_cli_cwd = _env_flag("CLAUDE_USE_CLI_CWD", default_false=False)

    return ClaudeHeadlessLM(
        binary=binary,
        output_format=fmt,
        model=model,
        fallback_model=fb_model,
        append_system_prompt=append,
        allowed_tools=allowed,
        disallowed_tools=disallowed,
        permission_mode=perm_mode,
        mcp_config=mcp,
        permission_prompt_tool=perm_prompt_tool,
        resume=resume,
        continue_latest=cont,
        cwd=cwd,
        timeout=timeout,
        use_cli_cwd=use_cli_cwd,
    )


def register() -> None:
    caps = ProviderCapabilities(
        supports_tools=True, code_exec=False, json_mode=True, multi_turn=True
    )
    register_provider("claude-cli", _factory, caps)
