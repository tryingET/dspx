from __future__ import annotations

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
