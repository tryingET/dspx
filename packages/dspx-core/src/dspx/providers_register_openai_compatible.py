from __future__ import annotations

import os
from typing import TypedDict

from dspx.capabilities import ProviderCapabilities
from dspx.openai_compatible_lm import OpenAICompatibleLM
from dspx.provider_registry import register_provider


class _OpenAICompatibleKwargs(TypedDict):
    base_url: str
    model: str
    api_key: str | None
    timeout: float
    strict: bool
    provider_label: str
    json_mode: bool


def _truthy(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"", "0", "false", "no"}


def _common_kwargs(prefix: str, *, provider_label: str) -> _OpenAICompatibleKwargs:
    base_url = os.getenv(f"{prefix}_API_BASE", "http://127.0.0.1:8000/v1")
    model = os.getenv(f"{prefix}_MODEL", "local-model")
    api_key = os.getenv(f"{prefix}_API_KEY")
    timeout = float(os.getenv(f"{prefix}_TIMEOUT", "30") or 30.0)
    json_mode = _truthy(f"{prefix}_JSON_MODE", False)
    return {
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "timeout": timeout,
        "strict": True,
        "provider_label": provider_label,
        "json_mode": json_mode,
    }


def _factory_openai_compatible() -> OpenAICompatibleLM:
    return OpenAICompatibleLM(
        **_common_kwargs("DSPX_OPENAI_COMPAT", provider_label="openai-compatible")
    )


def _factory_vllm_local() -> OpenAICompatibleLM:
    kwargs = _common_kwargs("DSPX_VLLM", provider_label="vllm-local")
    kwargs.setdefault("base_url", "http://127.0.0.1:8000/v1")
    return OpenAICompatibleLM(**kwargs)


def _registered_capabilities(prefix: str) -> ProviderCapabilities:
    json_mode = _truthy(f"{prefix}_JSON_MODE", False)
    return ProviderCapabilities(
        supports_tools=False,
        code_exec=False,
        json_mode=json_mode,
        multi_turn=True,
        structured_output_format="json" if json_mode else "none",
    )


def register_openai_compatible() -> None:
    register_provider(
        "openai-compatible",
        _factory_openai_compatible,
        _registered_capabilities("DSPX_OPENAI_COMPAT"),
    )


def register_vllm_local() -> None:
    register_provider(
        "vllm-local",
        _factory_vllm_local,
        _registered_capabilities("DSPX_VLLM"),
    )


def register() -> None:
    register_openai_compatible()
    register_vllm_local()
