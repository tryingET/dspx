from __future__ import annotations

import httpx
import pytest

from dspx.openai_compatible_lm import OpenAICompatibleLM
from dspx.openrouter_lm import OpenRouterLM
from dspx.security import ByteLimitExceededError, DEFAULT_HTTP_RESPONSE_MAX_BYTES


def _huge_client() -> httpx.Client:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (DEFAULT_HTTP_RESPONSE_MAX_BYTES + 1))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openrouter_provider_rejects_oversized_response() -> None:
    lm = OpenRouterLM(api_key="test-key", client=_huge_client())

    with pytest.raises(ByteLimitExceededError):
        lm.forward(prompt="hi")


def test_openai_compatible_provider_rejects_oversized_response() -> None:
    lm = OpenAICompatibleLM(
        api_key="test-key",
        base_url="https://api.example.test/v1",
        client=_huge_client(),
    )

    with pytest.raises(ByteLimitExceededError):
        lm.forward(prompt="hi")


def test_openai_compatible_provider_uses_absolute_url_for_injected_client() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    lm = OpenAICompatibleLM(
        api_key="test-key",
        base_url="https://api.example.test/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = lm.forward(prompt="hi")

    assert result.choices[0]["text"] == "ok"
    assert seen_urls == ["https://api.example.test/v1/chat/completions"]
