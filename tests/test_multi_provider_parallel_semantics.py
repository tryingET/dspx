# summary: "Tests MultiProviderLM request propagation, policy restoration, parallel-first completion, isolation, timeout, and cleanup semantics."
# read_when:
#   - "Changing multi-provider dispatch, runtime options, concurrency, isolated working directories, error handling, or loser cleanup."

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from dspx.dtos import LMRequest, Message
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


class _FailingProvider:
    model = "failing"

    def forward(self, prompt=None, messages=None):
        raise RuntimeError("provider boom")


class _SecretFailingProvider:
    model = "secret-failing"

    def forward(self, prompt=None, messages=None):
        raise RuntimeError(
            "api_key=supersecret Authorization: Bearer bearer-secret "
            "https://user:pass@example.test/path?token=url-secret&ok=1"
        )


class _AsyncProviderNoPopen:
    def __init__(self, model: str) -> None:
        self.model = model
        self.collect_calls = 0

    def start(self, prompt=None, messages=None):
        return SimpleNamespace(started_at=time.time())

    def collect(self, run):
        self.collect_calls += 1
        return SimpleNamespace(
            text=self.model,
            started_at=run.started_at,
            ended_at=time.time(),
        )


class _CwdProvider:
    def __init__(self) -> None:
        self.cwd = None


class _DelayedCwdProvider(_SyncProvider):
    def __init__(self, model: str, delay: float) -> None:
        super().__init__(model)
        self.delay = delay
        self.seen_cwds: list[str | None] = []

    def forward(self, prompt=None, messages=None):
        time.sleep(self.delay)
        self.seen_cwds.append(self.cwd)
        return super().forward(prompt=prompt, messages=messages)


class _RecordingForwardProvider(_SyncProvider):
    def __init__(self, model: str) -> None:
        super().__init__(model)
        self.seen_messages: list[list[dict[str, object]]] = []

    def forward(self, prompt=None, messages=None):
        self.seen_messages.append(list(messages or []))
        return super().forward(prompt=prompt, messages=messages)


class _RecordingGenerateProvider:
    def __init__(self, model: str) -> None:
        self.model = model
        self.requests: list[LMRequest] = []
        self.seen_kwargs: list[dict[str, object]] = []

    def generate(self, request: LMRequest, **kwargs):
        self.requests.append(request)
        self.seen_kwargs.append(dict(kwargs))
        text = " | ".join(
            f"{message.role}:{message.content}" for message in (request.messages or [])
        )
        return SimpleNamespace(outputs=[text or self.model])


class _RecordingKwargsForwardProvider(_SyncProvider):
    def __init__(self, model: str) -> None:
        super().__init__(model)
        self.seen_kwargs: list[dict[str, object]] = []

    def forward(self, prompt=None, messages=None, **kwargs):
        self.seen_kwargs.append(dict(kwargs))
        return super().forward(prompt=prompt, messages=messages)


class _InternalTypeErrorForwardProvider(_SyncProvider):
    def forward(self, prompt=None, messages=None, **kwargs):
        raise TypeError("internal provider bug")


class _NoKwargsGenerateProvider:
    def __init__(self, model: str) -> None:
        self.model = model
        self.requests: list[LMRequest] = []

    def generate(self, request: LMRequest):
        self.requests.append(request)
        return SimpleNamespace(outputs=[self.model])


class _PolicyAwareProvider(_SyncProvider):
    def __init__(self, model: str) -> None:
        super().__init__(model)
        self.dangerously_bypass = False
        self.auto_mode = True
        self.permission_mode = None
        self.allowed_tools = ["read"]
        self.disallowed_tools = ["write"]
        self.append_system_prompt = "orig"
        self.snapshots: list[dict[str, object]] = []

    def forward(self, prompt=None, messages=None):
        self.snapshots.append(
            {
                "dangerously_bypass": self.dangerously_bypass,
                "auto_mode": self.auto_mode,
                "permission_mode": self.permission_mode,
                "allowed_tools": self.allowed_tools,
                "disallowed_tools": self.disallowed_tools,
                "append_system_prompt": self.append_system_prompt,
            }
        )
        return super().forward(prompt=prompt, messages=messages)


class _HungProc:
    def __init__(self) -> None:
        self.alive = True
        self.killed = False

    def poll(self) -> int | None:
        return None if self.alive else 0

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        self.alive = False
        self.killed = True

    def wait(self, timeout=None) -> int:
        if self.alive:
            raise TimeoutError("still alive")
        return 0


class _HungAsyncProvider:
    def __init__(self, model: str) -> None:
        self.model = model
        self.proc = _HungProc()

    def start(self, prompt=None, messages=None):
        return SimpleNamespace(popen=self.proc, started_at=time.time())

    def collect(self, run):
        return SimpleNamespace(
            text=self.model,
            started_at=run.started_at,
            ended_at=time.time(),
        )

    def terminate(self, run) -> None:
        return None


def test_collect_concat_materializes_messages_for_all_providers() -> None:
    left = _RecordingForwardProvider("left")
    right = _RecordingForwardProvider("right")
    lm = MultiProviderLM(
        [left, right],
        names=["left", "right"],
        strategy="collect_concat",
    )

    source_messages = [
        {"role": "system", "content": "ctx"},
        {"role": "user", "content": "hello"},
    ]
    lm.forward(messages=(message for message in source_messages))

    assert left.seen_messages == [source_messages]
    assert right.seen_messages == [source_messages]


def test_generate_fails_closed_when_all_providers_fail() -> None:
    lm = MultiProviderLM([_FailingProvider()], names=["bad"])

    try:
        lm.forward(prompt="hello")
    except RuntimeError as exc:
        assert "All providers failed" in str(exc)
    else:  # pragma: no cover - defensive assertion clarity
        raise AssertionError("forward should fail closed")

    try:
        lm.generate(LMRequest(prompt="hello"))
    except RuntimeError as exc:
        assert "All providers failed" in str(exc)
        assert "provider boom" in str(exc)
    else:  # pragma: no cover - defensive assertion clarity
        raise AssertionError("generate should fail closed")


def test_all_provider_failure_errors_are_redacted() -> None:
    lm = MultiProviderLM([_SecretFailingProvider()], names=["bad"])

    try:
        lm.forward(prompt="hello")
    except RuntimeError as exc:
        text = str(exc)
        assert "All providers failed" in text
        assert "[REDACTED]" in text
        assert "supersecret" not in text
        assert "bearer-secret" not in text
        assert "url-secret" not in text
        assert "user:pass" not in text
    else:  # pragma: no cover - defensive assertion clarity
        raise AssertionError("forward should fail closed")


def test_generate_preserves_message_history_for_generate_only_providers() -> None:
    left = _RecordingGenerateProvider("left")
    right = _RecordingGenerateProvider("right")
    lm = MultiProviderLM(
        [left, right],
        names=["left", "right"],
        strategy="collect_concat",
    )

    request = LMRequest(
        messages=[
            Message(role="system", content="ctx"),
            Message(role="user", content="hello"),
        ]
    )
    lm.generate(request)

    expected = [
        {"role": "system", "content": "ctx"},
        {"role": "user", "content": "hello"},
    ]
    for provider in (left, right):
        assert provider.requests
        seen = [message.model_dump() for message in provider.requests[0].messages or []]
        assert seen == expected
        assert provider.requests[0].prompt is None


def test_generate_propagates_runtime_options_to_child_providers() -> None:
    provider = _RecordingGenerateProvider("child")
    lm = MultiProviderLM([provider], names=["child"])

    lm.generate(LMRequest(prompt="hello", options={"temperature": 0}), max_tokens=7)

    assert provider.requests[0].options == {"temperature": 0, "max_tokens": 7}
    assert provider.seen_kwargs == [{"temperature": 0, "max_tokens": 7}]


def test_forward_propagates_runtime_options_to_child_providers() -> None:
    provider = _RecordingKwargsForwardProvider("child")
    lm = MultiProviderLM([provider], names=["child"])

    lm.forward(prompt="hello", max_tokens=7)

    assert provider.seen_kwargs == [{"max_tokens": 7}]


def test_generate_preserves_options_for_provider_without_kwargs() -> None:
    provider = _NoKwargsGenerateProvider("child")
    lm = MultiProviderLM([provider], names=["child"])

    lm.generate(LMRequest(prompt="hello"), max_tokens=7)

    assert provider.requests[0].options == {"max_tokens": 7}


def test_forward_does_not_mask_provider_internal_type_error() -> None:
    lm = MultiProviderLM([_InternalTypeErrorForwardProvider("child")], names=["child"])

    try:
        lm.forward(prompt="hello", max_tokens=7)
    except RuntimeError as exc:
        assert "All providers failed" in str(exc)
        assert "internal provider bug" in str(exc)
    else:  # pragma: no cover - defensive assertion clarity
        raise AssertionError("internal TypeError should remain a provider failure")


def test_policy_overrides_are_restored_after_run() -> None:
    provider = _PolicyAwareProvider("ok")
    lm = MultiProviderLM(
        [provider],
        policy_bypass_permissions=True,
        policy_allowed_tools="bash",
        policy_disallowed_tools="kill",
        policy_append_system_prompt="append",
    )

    assert provider.dangerously_bypass is False
    assert provider.auto_mode is True
    assert provider.permission_mode is None
    assert provider.allowed_tools == ["read"]
    assert provider.disallowed_tools == ["write"]
    assert provider.append_system_prompt == "orig"

    lm.forward(prompt="hello")

    assert provider.snapshots == [
        {
            "dangerously_bypass": True,
            "auto_mode": False,
            "permission_mode": "acceptEdits",
            "allowed_tools": "bash",
            "disallowed_tools": "kill",
            "append_system_prompt": "append",
        }
    ]
    assert provider.dangerously_bypass is False
    assert provider.auto_mode is True
    assert provider.permission_mode is None
    assert provider.allowed_tools == ["read"]
    assert provider.disallowed_tools == ["write"]
    assert provider.append_system_prompt == "orig"


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


def test_parallel_first_collects_async_provider_without_popen_handle() -> None:
    provider = _AsyncProviderNoPopen("async-no-popen")
    lm = MultiProviderLM(
        [provider],
        names=["async-no-popen"],
        strategy="parallel_first",
    )

    result = lm._run_parallel_first(prompt="p", messages=None)

    assert [r.text for r in result] == ["async-no-popen"]
    assert provider.collect_calls == 1


def test_parallel_first_shared_provider_instances_do_not_bleed_cwd() -> None:
    from threading import Barrier, BrokenBarrierError, Thread

    barrier = Barrier(2)

    class _SharedProvider(_SyncProvider):
        def __init__(self) -> None:
            super().__init__("shared")
            self.seen_cwds: list[str | None] = []

        def forward(self, prompt=None, messages=None):
            try:
                barrier.wait(timeout=0.1)
            except BrokenBarrierError:
                pass
            self.seen_cwds.append(self.cwd)
            time.sleep(0.05)
            return SimpleNamespace(choices=[{"text": self.cwd}])

    provider = _SharedProvider()
    base = Path(tempfile.mkdtemp(prefix="dspx-shared-cwd-"))
    left_cwd = base / "left"
    right_cwd = base / "right"
    left_cwd.mkdir()
    right_cwd.mkdir()

    left = MultiProviderLM(
        [provider],
        names=["shared"],
        strategy="parallel_first",
        base_cwd=str(left_cwd),
    )
    right = MultiProviderLM(
        [provider],
        names=["shared"],
        strategy="parallel_first",
        base_cwd=str(right_cwd),
    )

    out: dict[str, str] = {}

    def _run(name: str, lm: MultiProviderLM) -> None:
        out[name] = lm._run_parallel_first(prompt="p", messages=None)[0].text

    threads = [
        Thread(target=_run, args=("left", left)),
        Thread(target=_run, args=("right", right)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert out == {
        "left": str(left_cwd),
        "right": str(right_cwd),
    }
    assert provider.seen_cwds == [
        str(left_cwd),
        str(right_cwd),
    ] or provider.seen_cwds == [
        str(right_cwd),
        str(left_cwd),
    ]


def test_parallel_first_times_out_never_ready_async_provider() -> None:
    class _NeverReadyProvider:
        def __init__(self) -> None:
            self.model = "never-ready"
            self.terminated = 0

        def start(self, prompt=None, messages=None):
            return SimpleNamespace(started_at=time.time())

        def ready(self, run):
            return False

        def terminate(self, run) -> None:
            self.terminated += 1

    provider = _NeverReadyProvider()
    lm = MultiProviderLM(
        [provider],
        names=["never-ready"],
        strategy="parallel_first",
    )
    lm._parallel_ready_timeout_s = 0.1

    result = lm._run_parallel_first(prompt="p", messages=None)[0]

    assert isinstance(result.error, TimeoutError)
    assert provider.terminated == 1
    assert result.ended_at >= result.started_at + 0.08


def test_parallel_first_readiness_exceptions_fail_closed_until_collect_is_safe() -> (
    None
):
    class _FlakyReadyProvider:
        def __init__(self) -> None:
            self.model = "flaky-ready"

        def start(self, prompt=None, messages=None):
            return SimpleNamespace(ready_at=time.time() + 0.1, first=True)

        def ready(self, run):
            if run.first:
                run.first = False
                raise RuntimeError("transient readiness failure")
            return time.time() >= run.ready_at

        def collect(self, run):
            if time.time() < run.ready_at:
                raise RuntimeError("collected too early")
            return SimpleNamespace(
                text="done",
                started_at=run.ready_at - 0.1,
                ended_at=time.time(),
            )

    lm = MultiProviderLM(
        [_FlakyReadyProvider()],
        names=["flaky-ready"],
        strategy="parallel_first",
    )
    lm._parallel_ready_timeout_s = 0.5

    result = lm._run_parallel_first(prompt="p", messages=None)[0]

    assert result.text == "done"
    assert result.error is None


def test_parallel_first_sync_isolated_cleanup_runs_on_fast_return(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    tempfile.tempdir = None
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
    tempfile.tempdir = None
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


def test_git_worktree_isolation_falls_back_to_mirror_for_dirty_repo(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "DSPx Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    tracked = repo / "tracked.txt"
    tracked.write_text("clean\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "tracked.txt"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    tracked.write_text("dirty\n", encoding="utf-8")

    lm = MultiProviderLM(
        [_CwdProvider()],
        parallel_isolated=True,
        base_cwd=str(repo),
        isolation_mode="git-worktree",
    )

    prepared, info = lm._prepare_isolated_cwds(1)
    try:
        assert info["mode"] == "mirror"
        assert prepared[0] is not None
        assert (
            Path(prepared[0]).joinpath("tracked.txt").read_text(encoding="utf-8")
            == "dirty\n"
        )
    finally:
        lm._cleanup_isolated(info)


def test_parallel_first_sync_workers_keep_isolated_cwd_until_completion(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    tempfile.tempdir = None
    base = tmp_path / "base"
    base.mkdir()
    (base / "input.txt").write_text("ok\n", encoding="utf-8")

    fast = _SyncProvider("fast")
    slow = _DelayedCwdProvider("slow", delay=0.2)
    lm = MultiProviderLM(
        [fast, slow],
        names=["fast", "slow"],
        strategy="parallel_first",
        parallel_isolated=True,
        base_cwd=str(base),
        cleanup_isolated=True,
    )

    result = lm._run_parallel_first(prompt="p", messages=None)

    assert [r.text for r in result] == ["fast"]

    deadline = time.time() + 1.0
    while time.time() < deadline and not slow.seen_cwds:
        time.sleep(0.02)

    assert slow.seen_cwds
    assert slow.seen_cwds[0] is not None
    assert slow.seen_cwds[0] != str(base)


def test_parallel_first_cleanup_force_kills_hung_async_loser(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    tempfile.tempdir = None
    base = tmp_path / "base"
    base.mkdir()
    (base / "input.txt").write_text("ok\n", encoding="utf-8")

    fast = _AsyncProvider("fast", delay=0.0)
    hung = _HungAsyncProvider("hung")
    lm = MultiProviderLM(
        [fast, hung],
        names=["fast", "hung"],
        strategy="parallel_first",
        parallel_isolated=True,
        base_cwd=str(base),
        cleanup_isolated=True,
    )
    lm._async_cleanup_grace_s = 0.1
    lm._async_cleanup_poll_s = 0.01
    lm._async_cleanup_kill_wait_s = 0.01

    result = lm._run_parallel_first(prompt="p", messages=None)

    assert [r.text for r in result] == ["fast"]

    deadline = time.time() + 1.0
    while time.time() < deadline:
        if hung.proc.killed and not any(
            path.name.startswith("dspx_multi_") for path in tmp_path.iterdir()
        ):
            break
        time.sleep(0.02)

    assert hung.proc.killed is True
    assert not any(path.name.startswith("dspx_multi_") for path in tmp_path.iterdir())


def test_restore_cwd_restores_none_value() -> None:
    provider = _CwdProvider()
    lm = MultiProviderLM([provider])

    state = lm._apply_cwd(provider, "/tmp/dspx-isolated")
    assert provider.cwd == "/tmp/dspx-isolated"

    lm._restore_cwd(provider, state)

    assert provider.cwd is None
