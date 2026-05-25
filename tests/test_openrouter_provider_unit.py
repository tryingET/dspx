from __future__ import annotations

import httpx
import pytest

from dspx.openrouter_lm import OpenRouterLM, _extract_text
from dspx.provider_registry import ensure_default_providers, create


def test_provider_registry_includes_openrouter() -> None:
    ensure_default_providers()
    lm = create("openrouter")
    assert lm is not None


def test_openrouter_extract_text_from_openai_like_response() -> None:
    txt = _extract_text(
        {"choices": [{"message": {"role": "assistant", "content": "hello"}}]}
    )
    assert txt == "hello"


def test_openrouter_forward_requires_api_key() -> None:
    lm = OpenRouterLM(api_key=None, client=None, strict=True)
    with pytest.raises(RuntimeError):
        lm.forward(prompt="hi")


def test_openrouter_injected_client_does_not_require_preconfigured_base_url() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    lm = OpenRouterLM(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = lm.forward(prompt="hi")

    assert result.choices[0]["text"] == "ok"
    assert seen_urls == ["https://openrouter.ai/api/v1/chat/completions"]
