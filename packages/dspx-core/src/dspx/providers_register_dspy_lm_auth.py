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


_CODEX_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh"}


def _model_supports_vision(model: str, auth_provider: str | None = None) -> bool:
    return model.startswith("codex/") or auth_provider == "codex"


def _factory() -> DspyLMAuthLM:
    model = os.getenv("DSPX_LM_AUTH_MODEL", "codex/gpt-5.5")
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
    uses_codex_route = model.startswith("codex/")
    if os.getenv("DSPX_LM_AUTH_MAX_TOKENS") is not None and not uses_codex_route:
        try:
            kwargs["max_tokens"] = int(os.getenv("DSPX_LM_AUTH_MAX_TOKENS", "0") or 0)
        except Exception:
            pass
    reasoning_effort = os.getenv("DSPX_LM_AUTH_REASONING_EFFORT")
    if reasoning_effort:
        if uses_codex_route and reasoning_effort not in _CODEX_REASONING_EFFORTS:
            allowed = ", ".join(sorted(_CODEX_REASONING_EFFORTS))
            raise ValueError(
                "DSPX_LM_AUTH_REASONING_EFFORT must be one of "
                f"{allowed} for codex/* models; got {reasoning_effort!r}"
            )
        kwargs["reasoning_effort"] = reasoning_effort
    return DspyLMAuthLM(
        model=model,
        auth_provider=auth_provider,
        auth_storage=auth_storage,
        timeout=timeout,
        strict=strict,
        kwargs=kwargs,
    )


def register() -> None:
    model = os.getenv("DSPX_LM_AUTH_MODEL", "codex/gpt-5.5")
    auth_provider = os.getenv("DSPX_LM_AUTH_PROVIDER") or None
    caps = ProviderCapabilities(
        supports_tools=False,
        code_exec=False,
        json_mode=True,
        multi_turn=True,
        structured_output_format="json",
        supports_vision=_model_supports_vision(model, auth_provider),
    )
    register_provider("dspy-lm-auth", _factory, caps)
