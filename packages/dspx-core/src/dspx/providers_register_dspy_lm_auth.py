from __future__ import annotations

import os

from dspx.capabilities import ProviderCapabilities
from dspx.dspy_lm_auth_lm import DspyLMAuthLM
from dspx.provider_registry import register_provider


def _truthy(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw not in {"", "0", "false", "False", "no", "No"}


def _factory() -> DspyLMAuthLM:
    model = os.getenv("DSPX_LM_AUTH_MODEL", "codex/gpt-5.4")
    auth_provider = os.getenv("DSPX_LM_AUTH_PROVIDER") or None
    auth_storage = os.getenv("DSPX_LM_AUTH_STORAGE") or None
    timeout = float(os.getenv("DSPX_LM_AUTH_TIMEOUT", "60") or 60.0)
    strict = _truthy("DSPX_LM_AUTH_STRICT", True)
    kwargs: dict[str, object] = {}
    if os.getenv("DSPX_LM_AUTH_TEMPERATURE") is not None:
        try:
            kwargs["temperature"] = float(
                os.getenv("DSPX_LM_AUTH_TEMPERATURE", "0") or 0.0
            )
        except Exception:
            pass
    if os.getenv("DSPX_LM_AUTH_MAX_TOKENS") is not None:
        try:
            kwargs["max_tokens"] = int(os.getenv("DSPX_LM_AUTH_MAX_TOKENS", "0") or 0)
        except Exception:
            pass
    return DspyLMAuthLM(
        model=model,
        auth_provider=auth_provider,
        auth_storage=auth_storage,
        timeout=timeout,
        strict=strict,
        kwargs=kwargs,
    )


def register() -> None:
    caps = ProviderCapabilities(
        supports_tools=False,
        code_exec=False,
        json_mode=True,
        multi_turn=True,
        structured_output_format="json",
    )
    register_provider("dspy-lm-auth", _factory, caps)
