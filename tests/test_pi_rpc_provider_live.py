from __future__ import annotations

import os
import shutil

import pytest

from dspx.pi_rpc_lm import PiRPCLM


@pytest.mark.skipif(
    os.getenv("DSPX_RUN_LIVE_TESTS", "0").lower() not in {"1", "true", "yes"},
    reason="set DSPX_RUN_LIVE_TESTS=1 to run live pi rpc tests",
)
@pytest.mark.skipif(shutil.which("pi") is None, reason="pi CLI not found")
@pytest.mark.skipif(
    not os.getenv("DSPX_PI_LIVE_PROVIDER"),
    reason="set DSPX_PI_LIVE_PROVIDER (and optionally DSPX_PI_LIVE_MODEL)",
)
def test_pi_rpc_live_smoke() -> None:
    provider = os.getenv("DSPX_PI_LIVE_PROVIDER") or None
    model = os.getenv("DSPX_PI_LIVE_MODEL") or None
    thinking = os.getenv("DSPX_PI_LIVE_THINKING") or None

    lm = PiRPCLM(
        binary="pi",
        provider=provider,
        model=model,
        thinking=thinking,
        no_tools=True,
        no_session=True,
        disable_resources=True,
        strict=True,
        timeout=float(os.getenv("DSPX_PI_LIVE_TIMEOUT", "90") or 90.0),
    )
    resp = lm.forward(prompt="Reply with the single word: hello")
    text = str((resp.choices[0]).get("text") or "")
    assert "hello" in text.lower()
