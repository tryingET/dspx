# summary: "One parent-owned bounded clean image worker; safe IPC and no successor/resume."
# read_when:
#   - "Changing worker identity, deadlines, settlement or process interruption custody."

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import errno
import os
import secrets
import signal
import subprocess
import threading
import time
from typing import Any, Callable, cast

from .image_admission import (
    ImageContractError,
    canonical,
    closed,
    hash_value,
    parse_json,
    require,
    sha,
)

_LOCAL = threading.local()
_STATUS = "status commitment_sha256 fixture_evidence live_authorized failure_code"
_FAILURES = {
    "validation",
    "budget",
    "policy",
    "io",
    "response",
    "interruption",
    "finalization",
    "durability",
    "privacy",
}


@dataclass(frozen=True, slots=True)
class WorkerIdentity:
    pid: int
    parent_pid: int
    start_identity: str
    deadline: float
    started_utc_ms: int
    wall_ms: int
    deadline_ns: int


def start_identity(pid: int) -> str:
    # Proc metadata only, not caller-selected paths or payload-bearing IPC.
    with open(f"/proc/{pid}/stat", "rb") as handle:
        row = handle.read(4096)
    require(len(row) < 4096 and b") " in row, "image_custody")
    return row.rsplit(b") ", 1)[1].split()[19].decode("ascii")


def worker_identity() -> WorkerIdentity:
    from .image_worker import require_clean_boundary

    value = getattr(_LOCAL, "identity", None)
    if type(value) is not WorkerIdentity:
        raise ImageContractError("image_custody") from None
    require(
        value.pid == os.getpid()
        and value.parent_pid == os.getppid()
        and value.start_identity == start_identity(os.getpid()),
        "image_custody",
    )
    require(time.monotonic() < value.deadline, "image_budget")
    require_clean_boundary()  # guard live and unpoisoned at every identity check
    return value


def worker_status_fd() -> int | None:
    fd = getattr(_LOCAL, "write_fd", None)
    return fd if type(fd) is int else None


def bind_worker(identity: WorkerIdentity, *, status_fd: int, permit_fd: int) -> None:
    """Clean worker only: wait for the parent permit, then bind the original budget."""
    require(getattr(_LOCAL, "identity", None) is None, "image_custody")
    permit = os.read(permit_fd, 33)  # b"1" + the parent's one-use 32-byte grant
    require(len(permit) == 33 and permit[:1] == b"1", "image_interruption")
    _LOCAL.grant_sha256 = sha(permit[1:])
    _LOCAL.identity = identity
    _LOCAL.write_fd, _LOCAL.permit_fd = status_fd, permit_fd
    _LOCAL.ready_sent = False
    worker_identity()


def worker_deadline() -> float:
    return worker_identity().deadline


def require_admitted_worker_budget(deadlines: object) -> None:
    """Reject a worker whose original parent budget exceeds its admission.

    Never construct a new deadline from the time of session creation. Preparation,
    generated import and finalization must all fit the original worker lifetime.
    """
    identity = worker_identity()
    row = closed(
        deadlines,
        "not_before_utc_ms expires_utc_ms total_wall_ms per_request_io_timeout_ms",
    )
    require(
        all(type(value) is int and value > 0 for value in row.values()), "image_budget"
    )
    require(
        identity.wall_ms <= row["total_wall_ms"]
        and row["not_before_utc_ms"] <= identity.started_utc_ms
        and identity.started_utc_ms + identity.wall_ms <= row["expires_utc_ms"]
        and row["not_before_utc_ms"]
        <= time.time_ns() // 1_000_000
        < row["expires_utc_ms"],
        "image_budget",
    )


def safe_status(value: object) -> dict[str, Any]:
    row = closed(value, _STATUS)
    require(
        row["status"] in {"prepared", "completed", "failed"}
        and hash_value(row["commitment_sha256"])
        and type(row["fixture_evidence"]) is bool
        and type(row["live_authorized"]) is bool
        and (row["failure_code"] is None or row["failure_code"] in _FAILURES),
        "image_custody",
    )
    return row


def _signal_owned(pid: int, start: str, sig: signal.Signals) -> None:
    require(start_identity(pid) == start, "image_interruption")
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        os.kill(pid, sig)  # owned unreaped PID, before setsid completed


def parent_ready(record: dict[str, Any]) -> None:
    worker_identity()
    require(not getattr(_LOCAL, "ready_sent", False), "image_custody")
    raw = b"R" + canonical(record) + b"\n"
    require(len(raw) <= 4096, "image_budget")
    _LOCAL.ready_sent = True
    require(os.write(_LOCAL.write_fd, raw) == len(raw), "image_interruption")
    require(os.read(_LOCAL.permit_fd, 1) == b"1", "image_interruption")
    worker_identity()


_SUPERVISION_LOCK = threading.Lock()


def _owned_members(pid: int) -> list[tuple[int, str, str]]:
    """Session membership is exclusive to descendants while leader stays unreaped."""
    records = []
    for entry in os.scandir("/proc"):
        if not entry.name.isdecimal():
            continue
        member = int(entry.name)
        try:
            with open(f"/proc/{member}/stat", "rb") as handle:
                fields = handle.read(4096).rsplit(b") ", 1)[1].split()
            records.append(
                (
                    member,
                    fields[19].decode("ascii"),
                    fields[0].decode("ascii"),
                    int(fields[1]),
                    int(fields[3]),
                )
            )
        except (FileNotFoundError, ProcessLookupError):
            continue
    # A single-thread parent entered with no children. Its sole child is this
    # invocation, so newly adopted children (including setsid escapees) are owned.
    owned = {pid} | {
        member
        for member, _, _, parent, session in records
        if parent == os.getpid() or session == pid
    }
    while True:
        descendants = {member for member, _, _, parent, _ in records if parent in owned}
        if descendants <= owned:
            break
        owned.update(descendants)
    return [
        (member, identity, state)
        for member, identity, state, _, _ in records
        if member in owned
    ]


def _settle_owned(
    pid: int, start: str, libc: ctypes.CDLL, admitted: set[int] | None = None
) -> tuple[bool, bool]:
    require(start_identity(pid) == start, "image_interruption")
    expected = {pid} | (set() if admitted is None else admitted)
    unexpected = any(member not in expected for member, _, _ in _owned_members(pid))
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for member, identity, state in _owned_members(pid):
            if state == "Z":
                continue
            fd = -1
            try:
                fd = libc.pidfd_open(member, 0)
                if fd < 0 and ctypes.get_errno() == errno.ESRCH:
                    continue
                require(fd >= 0, "image_interruption")
                require(start_identity(member) == identity, "image_interruption")
                sent = libc.pidfd_send_signal(fd, int(sig), None, 0)
                require(
                    sent == 0 or ctypes.get_errno() == errno.ESRCH, "image_interruption"
                )
            except (ProcessLookupError, FileNotFoundError):
                pass
            finally:
                if fd >= 0:
                    os.close(fd)
        until = time.monotonic() + 0.5
        while time.monotonic() < until:
            members = _owned_members(pid)
            for member, _, _ in members:
                if member == pid:
                    continue
                unexpected = unexpected or member not in expected
                try:
                    os.waitpid(member, os.WNOHANG)  # only explicitly owned members
                except ChildProcessError:
                    pass  # nested parent has not settled/adopted it yet
            remaining = _owned_members(pid)
            if (
                len(remaining) == 1
                and remaining[0][0] == pid
                and remaining[0][2] == "Z"
            ):
                os.waitpid(pid, 0)  # last, so the session/PID could not be reused
                return True, unexpected
            time.sleep(0.005)
    return False, unexpected


def supervise_image_worker(
    entry: str,
    params: dict[str, object],
    *,
    wall_ms: int,
    fds: tuple[int, ...] = (),
    parent_action: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Run one declared entry in a fresh clean worker; restore the caller's state."""
    from .image_worker import validate_entry

    validate_entry(entry, params)
    require(
        type(fds) is tuple and all(type(fd) is int and fd > 2 for fd in fds),
        "image_custody",
    )
    with _SUPERVISION_LOCK:
        require(threading.active_count() == 1, "image_custody")
        with open(f"/proc/self/task/{os.getpid()}/children", "rb") as children:
            require(children.read(4096).strip() == b"", "image_custody")
        libc = ctypes.CDLL(None, use_errno=True)
        require(
            all(
                hasattr(libc, name)
                for name in ("prctl", "pidfd_open", "pidfd_send_signal")
            ),
            "image_custody",
        )
        libc.pidfd_open.argtypes = [ctypes.c_int, ctypes.c_uint]
        libc.pidfd_open.restype = ctypes.c_int
        libc.pidfd_send_signal.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint,
        ]
        libc.pidfd_send_signal.restype = ctypes.c_int
        previous = ctypes.c_int()
        require(libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0, "image_custody")
        require(libc.prctl(36, 1, 0, 0, 0) == 0, "image_custody")
        try:
            return _supervise_image_worker(
                entry,
                params,
                fds=fds,
                wall_ms=wall_ms,
                parent_action=parent_action,
                libc=libc,
            )
        finally:
            require(libc.prctl(36, previous.value, 0, 0, 0) == 0, "image_interruption")


def _supervise_image_worker(
    entry: str,
    params: dict[str, object],
    *,
    fds: tuple[int, ...],
    wall_ms: int,
    parent_action: Callable[[dict[str, object]], None] | None = None,
    libc: ctypes.CDLL,
) -> dict[str, object]:
    """One clean exec, handshake before work, fixed environment, bounded TERM/KILL/reap.

    The worker is a fresh `-I -S` interpreter (owner refinement 13975): no parent
    hook, trace, history or patch is inherited. No worker refreshes its deadline.
    """
    from .image_worker import (
        set_supervised,
        worker_command,
        worker_environment,
        worker_paths,
    )

    require(type(wall_ms) is int and 0 < wall_ms <= 180_000, "image_budget")
    deadline_ns = time.monotonic_ns() + wall_ms * 1_000_000
    deadline = deadline_ns / 1_000_000_000
    control = canonical(
        {
            "entry": entry,
            "params": params,
            "paths": worker_paths(),
            "deadline_ns": deadline_ns,
            "started_utc_ms": time.time_ns() // 1_000_000,
            "wall_ms": wall_ms,
            "parent_pid": os.getpid(),
        }
    )
    require(len(control) <= 60_000, "image_budget")
    control_read, control_write = os.pipe2(os.O_CLOEXEC)
    read_fd, write_fd = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
    permit_read, permit_write = os.pipe2(os.O_CLOEXEC)
    try:
        process = subprocess.Popen(
            worker_command(control_read, write_fd, permit_read),
            pass_fds=(control_read, write_fd, permit_read, *fds),
            close_fds=True,
            start_new_session=True,
            env=worker_environment(),
            cwd="/",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        for fd in (control_read, control_write, read_fd, write_fd, permit_read):
            os.close(fd)
        os.close(permit_write)
        raise ImageContractError("image_custody") from None
    pid = process.pid
    os.close(control_read)
    try:
        # <= 60 000 bytes fits the default 64 KiB pipe buffer: this never blocks.
        view = memoryview(control)
        while view:
            view = view[os.write(control_write, view) :]
    except OSError:
        pass  # an exited worker is settled below; its status decides the outcome
    finally:
        os.close(control_write)
    os.close(write_fd)
    os.close(permit_read)
    grant = secrets.token_bytes(32)  # only ever written to the anonymous permit pipe
    try:
        start = start_identity(pid)
        set_supervised(
            {
                "worker_pid": pid,
                "worker_start_identity": start,
                "worker_deadline_ns": deadline_ns,
                "grant_sha256": sha(grant),
            }
        )
    except BaseException:
        process.kill()  # unreaped child: its PID cannot be reused before wait()
        process.wait()
        os.close(read_fd)
        os.close(permit_write)
        raise ImageContractError("image_interruption") from None
    raw = bytearray()
    settled = False
    failed = False
    result: dict[str, Any] | None = None
    ready_seen = False
    exited = False
    failure_code = "image_interruption"
    initializer_pid: int | None = None
    admitted_initializers: set[int] = set()

    def consume() -> None:
        nonlocal result, ready_seen, failure_code, initializer_pid, exited
        while b"\n" in raw:
            frame, _, rest = raw.partition(b"\n")
            raw[:] = rest
            require(len(frame) <= 4096, "image_budget")
            if frame.startswith(b"R"):
                if parent_action is None:
                    raise ImageContractError("image_custody") from None
                # A ready frame drained after exit never starts parent publication.
                require(
                    not ready_seen and result is None and not exited, "image_custody"
                )
                ready_seen = True
                ready_record = parse_json(bytes(frame[1:]), limit=4096)
                # Parent authorization is already reserved. Only its IO publication
                # is delegated; the parent keeps polling the ORIGINAL deadline.
                job = os.fork()
                if job == 0:
                    os.close(read_fd)
                    os.close(permit_write)
                    try:
                        os.setsid()
                        parent_action(ready_record)
                        os._exit(0)
                    except BaseException:
                        os._exit(1)
                initializer_pid = job
                admitted_initializers.add(job)
            elif frame.startswith(b"F"):
                code = closed(parse_json(bytes(frame[1:])), "failure_code")[
                    "failure_code"
                ]
                require(type(code) is str, "image_custody")
                failure_code = code
            elif frame.startswith(b"S"):
                require(result is None, "image_custody")
                result = safe_status(parse_json(bytes(frame[1:]), limit=4096))
            else:
                require(False, "image_custody")

    try:
        require(os.write(permit_write, b"1" + grant) == 33, "image_interruption")
        while time.monotonic() < deadline:
            try:
                raw.extend(os.read(read_fd, 4096))
                require(len(raw) <= 4096, "image_budget")
            except BlockingIOError:
                pass
            consume()
            if initializer_pid is not None:
                done = os.waitid(
                    os.P_PID, initializer_pid, os.WEXITED | os.WNOHANG | os.WNOWAIT
                )
                if done is not None:
                    require(
                        done.si_code == os.CLD_EXITED and done.si_status == 0,
                        "image_durability",
                    )
                    os.waitpid(initializer_pid, 0)
                    admitted_initializers.remove(initializer_pid)
                    initializer_pid = None
                    require(time.monotonic() < deadline, "image_budget")
                    require(os.write(permit_write, b"1") == 1, "image_interruption")
            observed = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if observed is not None:
                exited = True
                # Drain first: a fixed failure frame written just before exit decides.
                while True:
                    block = os.read(read_fd, 4096)
                    if not block:
                        break
                    raw.extend(block)
                    require(len(raw) <= 4096, "image_budget")
                consume()
                require(
                    observed.si_code == os.CLD_EXITED and observed.si_status == 0,
                    failure_code,
                )
                # consume() updates the nonlocal result; require a checked status.
                completed = cast(dict[str, Any] | None, result)
                if raw or completed is None:
                    raise ImageContractError("image_custody") from None
                return completed
            time.sleep(0.005)
        failed = True
    except BaseException as error:
        failed = True
        if type(error) is ImageContractError and failure_code == "image_interruption":
            failure_code = error.code  # e.g. a refused parent initializer
    finally:
        set_supervised(None)
        try:
            settled, unexpected = _settle_owned(pid, start, libc, admitted_initializers)
            require(settled and not unexpected, "image_interruption")
        finally:
            process.returncode = 0 if settled else -1  # reaped here, not by Popen
            os.close(read_fd)
            if permit_write >= 0:
                os.close(permit_write)
    require(settled and not failed, failure_code)
    raise ImageContractError(failure_code) from None
