# summary: "Registers the OpenRouter LM provider with model, endpoint, timeout, and attribution-header configuration."
# read_when:
#   - "Changing OpenRouter environment settings, request attribution, defaults, or capabilities."

from __future__ import annotations

import os

from dspx.capabilities import ProviderCapabilities
from dspx.openrouter_lm import OpenRouterLM
from dspx.provider_registry import register_provider


def _factory() -> OpenRouterLM:
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
    timeout_s = float(os.getenv("OPENROUTER_TIMEOUT", "30") or 30.0)

    # Optional attribution headers for OpenRouter (recommended by OpenRouter docs)
    extra_headers = {}
    if os.getenv("OPENROUTER_HTTP_REFERER"):
        extra_headers["HTTP-Referer"] = os.getenv("OPENROUTER_HTTP_REFERER", "")
    if os.getenv("OPENROUTER_APP_TITLE"):
        extra_headers["X-Title"] = os.getenv("OPENROUTER_APP_TITLE", "")

    return OpenRouterLM(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout_s,
        extra_headers=extra_headers,
    )


def register() -> None:
    caps = ProviderCapabilities(
        supports_tools=False,
        code_exec=False,
        json_mode=False,
        multi_turn=True,
        structured_output_format="none",
    )
    register_provider("openrouter", _factory, caps)
