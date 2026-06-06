from __future__ import annotations

import os

import pytest

from dspx.openrouter_lm import OpenRouterLM


pytestmark = [pytest.mark.live, pytest.mark.network, pytest.mark.model]


@pytest.mark.skipif(
    os.getenv("DSPX_RUN_LIVE_TESTS", "0") not in {"1", "true", "yes"},
    reason="set DSPX_RUN_LIVE_TESTS=1 to run live network tests",
)
@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="set OPENROUTER_API_KEY to run live OpenRouter test",
)
def test_openrouter_live_call_returns_text() -> None:
    lm = OpenRouterLM(strict=True)
    resp = lm.forward(
        prompt="Reply with the single word: hello", max_tokens=16, temperature=0
    )
    text = ((resp.get("choices") or [{}])[0]).get("text") or ""
    assert "hello" in str(text).lower()
