from __future__ import annotations

import time
from pathlib import Path
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


class _SyncProvider:
    def __init__(self, model: str) -> None:
        self.model = model
        self.cwd = None

    def forward(self, prompt=None, messages=None):
        return SimpleNamespace(choices=[{"text": self.model}])


class _CwdProvider:
    def __init__(self) -> None:
        self.cwd = None


def test_parallel_first_returns_first_completed_async_provider() -> None:
    slow = _AsyncProvider("slow", delay=0.20)
    fast = _AsyncProvider("fast", delay=0.05)
    lm = MultiProviderLM(
        [slow, fast], names=["slow", "fast"], strategy="parallel_first"
    )

    started = time.time()
    result = lm._run_parallel_first(prompt="p", messages=None)
    elapsed = time.time() - started

    assert [r.text for r in result] == ["fast"]
    assert [r.name for r in result] == ["fast"]
    assert elapsed < 0.15


def test_parallel_first_mixed_async_and_sync_preserves_true_first_completion() -> None:
    delayed = _AsyncProvider("async-delayed", delay=0.15)
    immediate = _SyncProvider("sync-immediate")
    lm = MultiProviderLM(
        [delayed, immediate],
        names=["async-delayed", "sync-immediate"],
        strategy="parallel_first",
    )

    started = time.time()
    result = lm._run_parallel_first(prompt="p", messages=None)
    elapsed = time.time() - started

    assert [r.text for r in result] == ["sync-immediate"]
    assert [r.name for r in result] == ["sync-immediate"]
    assert elapsed < 0.10


def test_parallel_first_sync_isolated_cleanup_runs_on_fast_return(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    base = tmp_path / "base"
    base.mkdir()
    (base / "input.txt").write_text("ok\n", encoding="utf-8")

    lm = MultiProviderLM(
        [_SyncProvider("left"), _SyncProvider("right")],
        names=["left", "right"],
        strategy="parallel_first",
        parallel_isolated=True,
        base_cwd=str(base),
        cleanup_isolated=True,
    )

    result = lm._run_parallel_first(prompt="p", messages=None)

    assert [r.text for r in result] == ["left"]
    assert not any(path.name.startswith("dspx_multi_") for path in tmp_path.iterdir())


class _SlowSyncProvider(_SyncProvider):
    def __init__(self, model: str, delay: float) -> None:
        super().__init__(model)
        self.delay = delay

    def forward(self, prompt=None, messages=None):
        time.sleep(self.delay)
        return super().forward(prompt=prompt, messages=messages)


def test_parallel_first_sync_isolated_cleanup_waits_for_slow_losers(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    base = tmp_path / "base"
    base.mkdir()
    (base / "input.txt").write_text("ok\n", encoding="utf-8")

    lm = MultiProviderLM(
        [_SlowSyncProvider("fast", 0.0), _SlowSyncProvider("slow", 0.5)],
        names=["fast", "slow"],
        strategy="parallel_first",
        parallel_isolated=True,
        base_cwd=str(base),
        cleanup_isolated=True,
    )

    result = lm._run_parallel_first(prompt="p", messages=None)

    assert [r.text for r in result] == ["fast"]

    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not any(path.name.startswith("dspx_multi_") for path in tmp_path.iterdir()):
            break
        time.sleep(0.05)

    assert not any(path.name.startswith("dspx_multi_") for path in tmp_path.iterdir())


def test_restore_cwd_restores_none_value() -> None:
    provider = _CwdProvider()
    lm = MultiProviderLM([provider])

    state = lm._apply_cwd(provider, "/tmp/dspx-isolated")
    assert provider.cwd == "/tmp/dspx-isolated"

    lm._restore_cwd(provider, state)

    assert provider.cwd is None
