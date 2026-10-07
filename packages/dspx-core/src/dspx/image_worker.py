# summary: "Clean `-I -S` image worker: earliest registration guard, native closure, declared entries."
# read_when:
#   - "Changing how image payload work is born, guarded or bound to its supervising parent."

"""Owner refinement 13975 (docket 2026-10-06, dspx-image-privacy-boundary = A).

Payload-reading image work runs only in a fresh isolated interpreter whose FIRST
statement registers a guard. A later audit-hook, trace, profile or monitoring
registration, a ctypes lookup of a native observer API or frame/gc introspection ends
the worker inside the audit call with a fixed ``image_privacy`` frame. Unaudited
observer channels (signal handlers, gc callbacks, hooks, threads) must be pristine
when the entry starts and are re-checked at every boundary probe: a change is detected
and ends the worker at the next probe, not prevented at the moment it is made.

A parent that is hooked or otherwise instrumented (trace, profile, MLflow, DSPy
callbacks, LM history) is outside the boundary (owner decisions 13975 and 14132): exec
inherits none of it, and the parent never reads, formats or sends pixels.

Threat model: observers installed by admitted, non-adversarial code, configuration or
startup. Startup is trusted (``-I -S``: no site, ``.pth``, sitecustomize or
``PYTHON*``-selected code). Native ``PySys_AddAuditHook`` skips notification with a NULL
thread state; no mapped executable image other than the interpreter itself may
reference it or the other observer APIs. Deliberately hostile code executing inside
the worker (raw function pointers from parsed ELF symbols, memory or module-state
tampering) is NOT contained: it could read the pixels directly.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import sys
import sysconfig
from typing import Any, Callable, Iterable, Never, TypeVar, cast

from .image_admission import (
    ImageContractError,
    bounded_tree,
    canonical,
    closed,
    require,
)

GUARD_EVENTS = (
    "sys.addaudithook",
    "sys.settrace",
    "sys.setprofile",
    "sys.monitoring.register_callback",
    "sys._current_frames",
    "gc.get_objects",
    "gc.get_referrers",
    "gc.get_referents",
)
# Native observer/registration APIs. A ctypes lookup of any of them poisons the worker
# (a GIL-releasing CDLL call reaches the unnotified NULL-thread-state path), and no
# mapped executable image may reference them.
OBSERVER_SYMBOLS = (
    "PySys_AddAuditHook",
    "PyEval_SetTrace",
    "PyEval_SetProfile",
    "PyRefTracer_SetTracer",
    "SetEvalFrameFunc",
    "_AddWatcher",
)
_PROBE = "dspx.image.guard"
_BASELINE_EVENT = "dspx.image.baseline"
_ENTRY = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*\Z")
_CONTROL = "entry params paths deadline_ns started_utc_ms wall_ms parent_pid"
_PASSTHROUGH = ("HOME", "TMPDIR", "DSPY_CACHEDIR")
_CONTROL_LIMIT = 60_000
_POISON = b'F{"failure_code":"image_privacy"}\n'

# Executed with ``-c`` before any import. The guard must be the first registration.
# Poison is irreversible: the first hostile event writes one fixed failure frame and
# terminates the worker inside the audit call, so no later code can clear any state.
# The observer-state baseline is set once and held in the closure, not module state.
BOOT = (
    "import sys\n"
    "import posix\n"
    "def _dspx_image_guard_factory(status_fd):\n"
    "    hostile, symbols = frozenset(%r), %r\n"
    "    write, leave, kind, size, text, box, scan = (\n"
    "        posix.write, posix._exit, type, len, str, list, any)\n"
    "    held = []\n"
    "    def guard(event, args):\n"
    "        if event == %r:\n"
    "            if size(args) == 2 and kind(args[0]) is box and kind(args[1]) is text:\n"
    "                if not held or held[0] == args[1]:\n"
    "                    args[0].append(0)\n"
    "                    return\n"
    "        elif event == %r:\n"
    "            if not held and size(args) == 1 and kind(args[0]) is text:\n"
    "                held.append(args[0])\n"
    "                return\n"
    "        elif event in hostile:\n"
    "            pass\n"
    "        elif event[:12] == 'ctypes.dlsym' and size(args) == 2:\n"
    "            name = args[1]\n"
    "            if kind(name) is text and not scan(item in name for item in symbols):\n"
    "                return\n"
    "        elif event == 'object.__setattr__' and size(args) and args[0] is guard:\n"
    "            pass\n"
    "        else:\n"
    "            return\n"
    "        try:\n"
    "            write(status_fd, %r)\n"
    "        finally:\n"
    "            leave(1)\n"
    "    return guard\n"
    "sys.addaudithook(_dspx_image_guard_factory(int(sys.argv[2])))\n"
    "del _dspx_image_guard_factory\n"
    "import os\n"
    "try:\n"
    "    import json\n"
    "    _fds = tuple(int(value) for value in sys.argv[1:])\n"
    "    if len(_fds) != 3:\n"
    "        raise ValueError\n"
    "    _raw = b''\n"
    "    while len(_raw) <= %d:\n"
    "        _block = os.read(_fds[0], 65536)\n"
    "        if not _block:\n"
    "            break\n"
    "        _raw += _block\n"
    "    os.close(_fds[0])\n"
    "    if len(_raw) > %d:\n"
    "        raise ValueError\n"
    "    _control = json.loads(_raw)\n"
    "    _paths = _control['paths']\n"
    "    if type(_paths) is not list or not all(\n"
    "        type(path) is str and path.startswith('/') for path in _paths\n"
    "    ):\n"
    "        raise ValueError\n"
    "    sys.path.extend(_paths)\n"
    "    from dspx.image_worker import run_clean_worker\n"
    "except BaseException:\n"
    "    os._exit(1)\n"
    "run_clean_worker(_control, _fds[1], _fds[2])\n"
) % (
    GUARD_EVENTS,
    OBSERVER_SYMBOLS,
    _PROBE,
    _BASELINE_EVENT,
    _POISON,
    _CONTROL_LIMIT,
    _CONTROL_LIMIT,
)

_F = TypeVar("_F", bound=Callable[..., Any])


def worker_entry(function: _F) -> _F:
    """Declare installed code as runnable in the clean worker; nothing else is."""
    vars(function)["__dspx_image_entry__"] = True
    return function


def poison() -> Never:
    """Irreversible: one fixed failure frame, then immediate worker termination."""
    from .image_supervision import worker_status_fd

    fd = worker_status_fd()
    if fd is None:
        raise ImageContractError("image_privacy") from None
    try:
        os.write(fd, _POISON)
    finally:
        os._exit(1)


def observer_digest() -> str:
    """Unaudited observer channels: signal handlers, gc callbacks, hooks, threads."""
    import _thread
    import gc
    import hashlib
    import signal
    import threading

    handlers = []
    for number in range(1, signal.NSIG):
        try:
            handlers.append(signal.getsignal(number))
        except (OSError, ValueError):
            handlers.append(None)
    state = (
        tuple(handlers),
        tuple(gc.callbacks),
        sys.excepthook,
        sys.unraisablehook,
        sys.breakpointhook,
        sys.displayhook,
        threading.excepthook,
        threading.gettrace(),
        threading.getprofile(),
        sys.gettrace(),
        sys.getprofile(),
        tuple(sys.monitoring.get_tool(tool) for tool in range(6)),
        _thread._count(),
    )
    return hashlib.sha256(repr(state).encode("utf-8", "replace")).hexdigest()


def pristine_observers() -> bool:
    """Interpreter defaults only: nothing imported may have armed an observer channel."""
    import _thread
    import gc
    import signal
    import threading

    defaults = {signal.SIG_DFL, signal.SIG_IGN, signal.default_int_handler, None}
    for number in range(1, signal.NSIG):
        try:
            if signal.getsignal(number) not in defaults:
                return False
        except (OSError, ValueError):
            continue
    return (
        gc.callbacks == []
        and sys.excepthook is sys.__excepthook__
        and sys.unraisablehook is sys.__unraisablehook__
        and sys.breakpointhook is sys.__breakpointhook__
        and sys.displayhook is sys.__displayhook__
        and threading.excepthook is threading.__excepthook__
        and threading.gettrace() is None
        and threading.getprofile() is None
        and sys.gettrace() is None
        and sys.getprofile() is None
        and all(sys.monitoring.get_tool(tool) is None for tool in range(6))
        and _thread._count() == 0
    )


def require_clean_boundary() -> None:
    """Admit payload work only in a live guarded worker with unchanged observers.

    The guard itself compares this digest with the baseline it holds; a mismatch or a
    malformed probe ends the worker inside the audit call.
    """
    box: list[object] = []
    sys.audit(_PROBE, box, observer_digest())
    if not box:
        raise ImageContractError("image_execution_unavailable") from None
    if box != [0]:
        poison()
    try:
        native_registration_closure()
    except ImageContractError:
        poison()


_NATIVE_CLEAN: set[tuple[bytes, bytes]] = set()
_SYMBOLS = tuple(name.encode("ascii") for name in OBSERVER_SYMBOLS)


def _own_images() -> set[bytes]:
    """The trusted interpreter image itself defines these APIs; it is the boundary."""
    own = {os.fsencode(os.path.realpath(sys.executable))}
    if sysconfig.get_config_var("Py_ENABLE_SHARED"):
        name = sysconfig.get_config_var("INSTSONAME") or ""
        libdir = sysconfig.get_config_var("LIBDIR") or ""
        own.add(os.fsencode(os.path.realpath(os.path.join(libdir, name))))
    return own


def native_registration_closure(paths: Iterable[bytes] | None = None) -> None:
    """Fail closed if any executable mapping can call an observer registration API."""
    if paths is None:
        with open("/proc/self/maps", "rb") as handle:
            rows = handle.read(4 << 20)
        require(len(rows) < 4 << 20, "image_privacy")
        own = _own_images()
        mapped: set[tuple[bytes, bytes]] = set()
        for row in rows.splitlines():
            fields = row.split(maxsplit=5)
            if len(fields) == 6 and b"x" in fields[1] and fields[5][:1] == b"/":
                if os.path.realpath(fields[5]) not in own:
                    mapped.add((fields[5], fields[4]))
    else:
        mapped = {(path, b"") for path in paths}
    for key in mapped:
        if key in _NATIVE_CLEAN:
            continue
        path = key[0]
        require(not path.endswith(b" (deleted)"), "image_privacy")
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            raise ImageContractError("image_privacy") from None
        require(not any(symbol in data for symbol in _SYMBOLS), "image_privacy")
        _NATIVE_CLEAN.add(key)


_SUPERVISED: dict[str, object] | None = None


def set_supervised(binding: dict[str, object] | None) -> None:
    """Parent side: the identity of the one worker currently being supervised."""
    global _SUPERVISED
    _SUPERVISED = binding


def supervised_worker() -> dict[str, object]:
    """Parent-held truth about the spawned child: PID, start, deadline, grant hash."""
    require(type(_SUPERVISED) is dict, "image_custody")
    return dict(cast(dict[str, object], _SUPERVISED))


def worker_binding() -> dict[str, object]:
    """Worker claim for the ready handshake; the parent publishes only on equality."""
    from . import image_supervision as supervision

    identity = supervision.worker_identity()
    grant = getattr(supervision._LOCAL, "grant_sha256", None)
    require(type(grant) is str and len(grant) == 64, "image_custody")
    return {
        "worker_pid": identity.pid,
        "worker_start_identity": identity.start_identity,
        "worker_deadline_ns": identity.deadline_ns,
        "grant_sha256": grant,
    }


def validate_entry(entry: object, params: object) -> bytes:
    """Closed bounded control data naming a declared entry; never code or pickle."""
    require(type(entry) is str and _ENTRY.fullmatch(entry) is not None, "image_custody")
    require(type(params) is dict, "image_custody")
    try:
        bounded_tree(params, max_depth=16, max_nodes=4096)
        raw = canonical(params)
    except (ImageContractError, TypeError, ValueError):
        raise ImageContractError("image_custody") from None
    require(len(raw) <= _CONTROL_LIMIT // 2, "image_budget")
    return raw


def worker_paths() -> list[str]:
    """The parent's already-resolved absolute import roots; .pth code is not rerun."""
    paths: list[str] = []
    for path in sys.path:
        if type(path) is str and os.path.isabs(path) and os.path.isdir(path):
            if path not in paths:
                paths.append(path)
    return paths


def worker_environment() -> dict[str, str]:
    environment = {
        "MLFLOW_ENABLE": "0",
        "DSPX_PROVIDER": "stub",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    for key, value in os.environ.items():
        if key.startswith("DSPX_POLICY_") or key in _PASSTHROUGH:
            environment[key] = value
    return environment


def worker_command(control_fd: int, status_fd: int, permit_fd: int) -> list[str]:
    return [
        sys.executable,
        "-I",
        "-S",
        "-c",
        BOOT,
        str(control_fd),
        str(status_fd),
        str(permit_fd),
    ]


def _not_dumpable() -> None:
    """No core dump, same-uid ptrace attach or /proc/<pid>/mem read of pixels."""
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(4, 0, 0, 0, 0) == 0, "image_privacy")  # PR_SET_DUMPABLE


def bind_worker(identity: object, *, status_fd: int, permit_fd: int) -> None:
    """Clean worker only: take the parent's permit and one-use grant, bind the budget."""
    from . import image_supervision as supervision

    local = supervision._LOCAL
    require(getattr(local, "identity", None) is None, "image_custody")
    for fd in (status_fd, permit_fd):
        os.set_inheritable(fd, False)  # no exec'd descendant inherits the handshake
    permit = os.read(permit_fd, 33)  # b"1" + the parent's one-use 32-byte grant
    require(len(permit) == 33 and permit[:1] == b"1", "image_interruption")
    local.grant_sha256 = hashlib.sha256(permit[1:]).hexdigest()
    local.identity = identity
    local.write_fd, local.permit_fd = status_fd, permit_fd
    local.ready_sent = False
    supervision.worker_identity()


def run_clean_worker(control: object, status_fd: int, permit_fd: int) -> Never:
    """Worker side of the supervised handshake. Never returns; no raw error output."""
    from . import image_supervision as supervision

    try:
        _not_dumpable()
        row = closed(control, _CONTROL)
        validate_entry(row["entry"], row["params"])
        require(
            all(
                type(row[key]) is int and row[key] > 0
                for key in ("deadline_ns", "started_utc_ms", "wall_ms", "parent_pid")
            ),
            "image_custody",
        )
        bind_worker(
            supervision.WorkerIdentity(
                os.getpid(),
                row["parent_pid"],
                supervision.start_identity(os.getpid()),
                row["deadline_ns"] / 1_000_000_000,
                row["started_utc_ms"],
                row["wall_ms"],
                row["deadline_ns"],
            ),
            status_fd=status_fd,
            permit_fd=permit_fd,
        )
        module, _, name = row["entry"].partition(":")
        work = getattr(importlib.import_module(module), name, None)
        if (
            not callable(work)
            or getattr(work, "__dspx_image_entry__", False) is not True
        ):
            raise ImageContractError("image_custody") from None
        if not pristine_observers():
            poison()  # an import armed an observer before the baseline (R3)
        sys.audit(_BASELINE_EVENT, observer_digest())  # once; held by the guard
        supervision.worker_identity()
        raw = b"S" + canonical(supervision.safe_status(work(row["params"]))) + b"\n"
        require(
            len(raw) < 4096 and os.write(status_fd, raw) == len(raw), "image_custody"
        )
        os.close(status_fd)
        os._exit(0)
    except BaseException as error:
        if type(error) is ImageContractError:
            try:
                os.write(
                    status_fd, b"F" + canonical({"failure_code": error.code}) + b"\n"
                )
            except BaseException:
                pass
        os._exit(1)  # no traceback, repr, arbitrary output or raw exception IPC
