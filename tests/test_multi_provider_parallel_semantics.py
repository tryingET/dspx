from __future__ import annotations

import time
from types import SimpleNamespace

from dspx.multi_provider_lm import MultiProviderLM


class _FakeProc:
    def __init__(self, delay: float) -> None:
        self._ready_at = time.time() + delay

    def poll(self) -> int | None:
        return 0 if time.time() >= self._ready_at else None


class _AsyncProvider:
    def __init__(self, model: str, delay: float) -> None:
        self.model = model
        self.delay = delay

    def start(self, prompt=None, messages=None):
        return SimpleNamespace(popen=_FakeProc(self.delay), started_at=time.time())

    def collect(self, run):
        return SimpleNamespace(
            text=self.model,
            started_at=run.started_at,
            ended_at=time.time(),
        )


class _CwdProvider:
    def __init__(self) -> None:
        self.cwd = None


def test_parallel_first_returns_first_completed_async_provider() -> None:
    slow = _AsyncProvider("slow", delay=0.20)
    fast = _AsyncProvider("fast", delay=0.05)
    lm = MultiProviderLM(
        [slow, fast], names=["slow", "fast"], strategy="parallel_first"
    )

    result = lm._run_parallel_first(prompt="p", messages=None)

    assert [r.text for r in result] == ["fast"]
    assert [r.name for r in result] == ["fast"]


def test_restore_cwd_restores_none_value() -> None:
    provider = _CwdProvider()
    lm = MultiProviderLM([provider])

    state = lm._apply_cwd(provider, "/tmp/dspx-isolated")
    assert provider.cwd == "/tmp/dspx-isolated"

    lm._restore_cwd(provider, state)

    assert provider.cwd is None
