# summary: "Actual owned clean-worker handshake/deadline/reaping; no HTTP or provider interpretation."
# Entries run inside a fresh `-I -S` interpreter; the parent names them, never pickles them.
import ctypes
import os
from pathlib import Path
import signal
import time

import pytest

from dspx.image_admission import ImageContractError
from dspx.image_supervision import (
    parent_ready,
    require_admitted_worker_budget,
    supervise_image_worker,
    worker_identity,
)
from dspx.image_worker import worker_entry

_HERE = "test_image_supervision"


def status():
    return {
        "status": "prepared",
        "commitment_sha256": "1" * 64,
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": None,
    }


@worker_entry
def _handshake(params):
    identity = worker_identity()
    assert identity.parent_pid == params["parent"] == os.getppid()
    assert os.environ["MLFLOW_ENABLE"] == "0"
    assert os.environ["DSPX_PROVIDER"] == "stub"
    parent_ready({"phase": "ready"})
    assert Path(params["checkpoint"]).read_bytes() == b"parent-initialized"
    return status()


def test_parent_handshake_precedes_worker_continuation(tmp_path):
    checkpoint = tmp_path / "released"

    def initialize(record):
        assert record == {"phase": "ready"}
        checkpoint.write_bytes(b"parent-initialized")

    params = {"parent": os.getpid(), "checkpoint": str(checkpoint)}
    assert (
        supervise_image_worker(
            f"{_HERE}:_handshake", params, wall_ms=10_000, parent_action=initialize
        )
        == status()
    )


@worker_entry
def _interrupted(params):
    Path(params["checkpoint"]).write_text(str(os.getpid()))
    if params["interruption"] == "baseexception":
        raise KeyboardInterrupt("private-canary-must-not-escape")
    if params["interruption"] == "signal":
        os.kill(os.getpid(), signal.SIGKILL)
    time.sleep(30)
    return status()


@pytest.mark.parametrize("interruption", ["deadline", "baseexception", "signal"])
def test_owned_worker_is_reaped_after_interruption(tmp_path, interruption):
    checkpoint = tmp_path / "pid"
    started = time.monotonic()
    with pytest.raises(ImageContractError) as error:
        supervise_image_worker(
            f"{_HERE}:_interrupted",
            {"checkpoint": str(checkpoint), "interruption": interruption},
            wall_ms=3000,
        )
    assert str(error.value) == "image_interruption"
    assert time.monotonic() - started < 6
    pid = int(checkpoint.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)


@worker_entry
def _admitted_deadline(params):
    require_admitted_worker_budget(params["deadlines"])
    Path(params["entered"]).write_bytes(b"forbidden")
    return status()


@pytest.mark.parametrize("bound", ["wall", "expiry"])
def test_admitted_deadline_cannot_extend_original_worker_budget(tmp_path, bound):
    entered = tmp_path / "effect-entered"
    now = time.time_ns() // 1_000_000
    deadlines = {
        "not_before_utc_ms": now - 1000,
        "expires_utc_ms": now + (100 if bound == "expiry" else 30_000),
        "total_wall_ms": 9_999 if bound == "wall" else 10_000,
        "per_request_io_timeout_ms": 100,
    }
    with pytest.raises(ImageContractError, match="image_budget"):
        supervise_image_worker(
            f"{_HERE}:_admitted_deadline",
            {"deadlines": deadlines, "entered": str(entered)},
            wall_ms=10_000,
        )
    assert not entered.exists()


@worker_entry
def _monotonic_origin(params):
    initial = worker_identity().deadline
    require_admitted_worker_budget(params["deadlines"])
    time.sleep(0.02)
    require_admitted_worker_budget(params["deadlines"])
    assert worker_identity().deadline == initial
    return status()


def test_admitted_deadline_check_does_not_refresh_monotonic_origin():
    now = time.time_ns() // 1_000_000
    deadlines = {
        "not_before_utc_ms": now - 1000,
        "expires_utc_ms": now + 30_000,
        "total_wall_ms": 10_000,
        "per_request_io_timeout_ms": 100,
    }
    assert (
        supervise_image_worker(
            f"{_HERE}:_monotonic_origin", {"deadlines": deadlines}, wall_ms=10_000
        )
        == status()
    )


@worker_entry
def _descendant(params):
    checkpoint = Path(params["checkpoint"])
    exit_kind = params["exit_kind"]
    pid = os.fork()
    if pid == 0:
        os.closerange(3, 1024)
        if exit_kind == "escaped":
            os.setsid()
        if exit_kind == "term_ignored":
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        checkpoint.write_text(str(os.getpid()))
        time.sleep(30)
        os._exit(0)
    until = time.monotonic() + 2
    while not checkpoint.exists() and time.monotonic() < until:
        time.sleep(0.001)
    assert checkpoint.exists()
    if exit_kind not in {"normal", "escaped"}:
        time.sleep(30)
    return status()


@pytest.mark.parametrize("exit_kind", ["normal", "deadline", "term_ignored", "escaped"])
def test_owned_descendant_settled_independently_of_leader(tmp_path, exit_kind):
    """Independent PID IPC; close inherited pipes so EOF is not settlement proof."""
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    checkpoint = tmp_path / "descendant"
    child_pid = None
    try:
        with pytest.raises(ImageContractError, match="image_interruption"):
            supervise_image_worker(
                f"{_HERE}:_descendant",
                {"checkpoint": str(checkpoint), "exit_kind": exit_kind},
                wall_ms=4000,
            )
        child_pid = int(checkpoint.read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
        with pytest.raises(ChildProcessError):
            os.waitpid(child_pid, os.WNOHANG)
    finally:
        # Red cleanup: only this test's explicitly attributable adopted child.
        if child_pid is None and checkpoint.exists():
            child_pid = int(checkpoint.read_text())
        if child_pid is not None:
            try:
                observed = os.waitid(
                    os.P_PID, child_pid, os.WEXITED | os.WNOHANG | os.WNOWAIT
                )
                if (
                    observed is None
                ):  # live, owned, unreaped child; PID cannot be reused
                    os.kill(child_pid, signal.SIGKILL)
                os.waitpid(child_pid, 0)
            except ChildProcessError:
                pass
        assert libc.prctl(36, previous.value, 0, 0, 0) == 0


def test_unsupervised_identity_denied():
    with pytest.raises(ImageContractError, match="image_custody"):
        worker_identity()


@worker_entry
def _late_initializer(params):
    Path(params["worker"]).write_text(str(os.getpid()))
    parent_ready({"phase": "ready"})
    Path(params["effect"]).write_bytes(b"must-not-be-released")
    return status()


def test_parent_initialization_io_cannot_suspend_original_watchdog(tmp_path):
    worker_pid_path = tmp_path / "worker"
    initializer_pid_path = tmp_path / "initializer"
    late = tmp_path / "late-publication"
    effect = tmp_path / "forbidden-effect"

    def initialize(record):
        assert record == {"phase": "ready"}
        initializer_pid_path.write_text(str(os.getpid()))
        time.sleep(30)
        late.write_bytes(b"must-not-publish-after-deadline")

    started = time.monotonic()
    with pytest.raises(ImageContractError):
        supervise_image_worker(
            f"{_HERE}:_late_initializer",
            {"worker": str(worker_pid_path), "effect": str(effect)},
            wall_ms=3000,
            parent_action=initialize,
        )
    assert time.monotonic() - started < 6
    assert initializer_pid_path.exists() and worker_pid_path.exists()
    for path in (initializer_pid_path, worker_pid_path):
        pid = int(path.read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        with pytest.raises(ChildProcessError):
            os.waitpid(pid, os.WNOHANG)
    assert not late.exists() and not effect.exists()


@pytest.mark.parametrize(
    ("entry", "params"),
    [
        ("not an entry", {}),
        ("os.path", {}),
        (f"{_HERE}:_handshake", {"bytes": "x" * 70_000}),
        (f"{_HERE}:_handshake", {"nested": {"too": float("nan")}}),
        (f"{_HERE}:_handshake", ["not", "a", "closed", "record"]),
    ],
)
def test_parent_rejects_unclosed_control_before_spawn(entry, params, monkeypatch):
    """Control is closed bounded data naming an entry; no pickle or ambient path."""
    import subprocess

    spawned = []
    monkeypatch.setattr(
        subprocess, "Popen", lambda *args, **kwargs: spawned.append(True)
    )
    with pytest.raises(ImageContractError):
        supervise_image_worker(entry, params, wall_ms=1000)
    assert spawned == []


def _undeclared(params):
    Path(params["checkpoint"]).write_bytes(b"undeclared-entry-ran")
    return status()


def test_worker_runs_only_declared_entries(tmp_path):
    checkpoint = tmp_path / "ran"
    with pytest.raises(ImageContractError, match="image_custody"):
        supervise_image_worker(
            f"{_HERE}:_undeclared", {"checkpoint": str(checkpoint)}, wall_ms=10_000
        )
    assert not checkpoint.exists()


@worker_entry
def _grant_entry(params):
    from dspx.image_worker import worker_binding

    binding = worker_binding()
    identity = worker_identity()
    assert binding["worker_pid"] == identity.pid == os.getpid()
    assert binding["worker_start_identity"] == identity.start_identity
    assert binding["worker_deadline_ns"] == identity.deadline_ns
    parent_ready({"binding": binding})
    assert Path(params["checkpoint"]).read_bytes() == b"bound"
    return status()


def test_permit_grant_binds_the_ready_handshake_to_the_spawned_worker(tmp_path):
    """The parent's own view of the child it spawned must equal the worker's claim."""
    from dspx.image_worker import supervised_worker

    checkpoint = tmp_path / "bound"
    seen = []

    def initialize(record):
        expected = supervised_worker()
        assert record == {"binding": expected}, (record, expected)
        grant = expected["grant_sha256"]
        assert type(grant) is str and len(grant) == 64
        checkpoint.write_bytes(b"bound")

    result = supervise_image_worker(
        f"{_HERE}:_grant_entry",
        {"checkpoint": str(checkpoint)},
        wall_ms=10_000,
        parent_action=lambda record: (seen.append(True), initialize(record)),
    )
    assert result == status() and checkpoint.read_bytes() == b"bound"
    with pytest.raises(ImageContractError, match="image_custody"):
        supervised_worker()  # only valid while that worker is supervised
