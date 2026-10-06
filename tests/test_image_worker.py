# summary: "Owner refinement 13975: clean `-I -S` worker, earliest registration guard, native closure."
# read_when:
#   - "Changing the image worker bootstrap, its guard events or the hooked-parent exclusion."

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import zlib

import pytest

from dspx.image_admission import ImageContractError, parse_json, sha
from dspx.image_records import publish, read_record
from dspx.image_supervision import supervise_image_worker
from dspx.image_worker import (
    GUARD_EVENTS,
    OBSERVER_SYMBOLS,
    native_registration_closure,
    require_clean_boundary,
    worker_entry,
)

_HERE = "test_image_worker"
_ALLOWED_ENV = {
    "LC_CTYPE",  # set by the interpreter's own PEP 538 locale coercion
    "MLFLOW_ENABLE",
    "DSPX_PROVIDER",
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
    "HOME",
    "TMPDIR",
    "DSPY_CACHEDIR",
}


def _status(commitment: str) -> dict[str, object]:
    return {
        "status": "prepared",
        "commitment_sha256": commitment,
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": None,
    }


def _png(rgb: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\0" + rgb))
        + chunk(b"IEND", b"")
    )


def _private(path: Path) -> int:
    path.mkdir(mode=0o700)
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY)


def _dumpable() -> int:
    import ctypes

    return ctypes.CDLL(None).prctl(3, 0, 0, 0, 0)  # PR_GET_DUMPABLE


@worker_entry
def _facts(params):
    require_clean_boundary()
    rows = [
        row.split(maxsplit=5)
        for row in Path("/proc/self/maps").read_bytes().splitlines()
    ]
    native = {fields[5] for fields in rows if len(fields) == 6}
    facts = {
        "isolated": sys.flags.isolated,
        "no_site": sys.flags.no_site,
        "cwd_on_path": "" in sys.path or os.getcwd() in sys.path,
        "startup_modules": sorted(
            name
            for name in (
                "site",
                "sitecustomize",
                "usercustomize",
                "_virtualenv",
                "coverage",
            )
            if name in sys.modules
        ),
        "env": sorted(os.environ),
        "observers_absent": sys.gettrace() is None and sys.getprofile() is None,
        "parent_pid": os.getppid(),
        "native_libraries": len([name for name in native if b".so" in name]),
        "dumpable": _dumpable(),
    }
    return _status(publish(params["observation_fd"], "facts.json", facts))


def test_worker_is_isolated_site_free_scrubbed_and_native_closed(tmp_path: Path):
    """Given the owner refinement; When the worker boots; Then no startup code ran."""
    fd = _private(tmp_path / "observation")
    try:
        result = supervise_image_worker(
            f"{_HERE}:_facts", {"observation_fd": fd}, fds=(fd,), wall_ms=30_000
        )
        raw = read_record(fd, "facts.json")
        assert result["commitment_sha256"] == sha(raw)
        facts = parse_json(raw)
        assert facts["isolated"] == 1 and facts["no_site"] == 1
        assert facts["cwd_on_path"] is False and facts["startup_modules"] == []
        assert set(facts["env"]) <= _ALLOWED_ENV | {
            name for name in facts["env"] if name.startswith("DSPX_POLICY_")
        }
        assert facts["observers_absent"] is True
        assert facts["parent_pid"] == os.getpid()
        assert facts["native_libraries"] > 0
        assert facts["dumpable"] == 0
    finally:
        os.close(fd)


def _candidate(tmp_path: Path) -> tuple[Path, Path, bytes]:
    from dspx.services.program_intent import ProgramIntent
    from dspx.services.program_service import materialize_program_from_intent

    candidate = tmp_path / "candidate"
    materialize_program_from_intent(
        ProgramIntent(
            name="WorkerBoundary",
            objective="Inspect synthetic inputs.",
            inputs=["visual"],
            outputs=["answer"],
            options={"image_enabled": True},
        ),
        outdir=candidate,
    )
    pixels = _png(b"\x07\x08\x09")
    inputs = tmp_path / "inputs"
    inputs.mkdir(mode=0o700)
    (inputs / "inputs.json").write_text(
        json.dumps(
            {
                "visual": {
                    "type": "image_base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(pixels).decode("ascii"),
                }
            }
        )
    )
    return candidate, inputs, pixels


_KINDS = [
    "addaudithook",
    "settrace",
    "setprofile",
    "monitoring",
    "dlsym",
    "gc_objects",
    "current_frames",
    "signal",
    "gc_callback",
    "rebaseline",
]


def _attempt(kind: str, observer) -> None:
    """One observer channel; the guard or the next boundary probe ends the worker."""
    if kind == "addaudithook":
        sys.addaudithook(observer)
    elif kind == "settrace":
        sys.settrace(lambda frame, event, arg: observer(event, (frame,)))
    elif kind == "setprofile":
        sys.setprofile(lambda frame, event, arg: observer(event, (frame,)))
    elif kind == "monitoring":
        tool = sys.monitoring.PROFILER_ID
        sys.monitoring.use_tool_id(tool, "falsifier")
        sys.monitoring.register_callback(
            tool, sys.monitoring.events.PY_START, lambda *args: observer("m", ())
        )
        sys.monitoring.set_events(tool, sys.monitoring.events.PY_START)
    elif kind == "dlsym":
        import ctypes

        # A GIL-releasing CDLL call would register without notification (B2).
        native = ctypes.CDLL(None).PySys_AddAuditHook
        native(ctypes.CFUNCTYPE(ctypes.c_int)(lambda: 0), None)
    elif kind == "gc_objects":
        import gc

        gc.get_objects()  # the only route to the guard object (B1)
    elif kind == "current_frames":
        sys._current_frames()
    elif kind == "signal":
        import signal

        signal.signal(signal.SIGALRM, lambda number, frame: observer("signal", ()))
        signal.setitimer(signal.ITIMER_REAL, 0.001, 0.001)
    elif kind == "gc_callback":
        import gc

        gc.callbacks.append(lambda phase, info: observer("gc", ()))
    elif kind == "rebaseline":
        import signal

        # The guard holds the one baseline; a second one cannot launder a change.
        signal.signal(signal.SIGALRM, lambda number, frame: observer("signal", ()))
        sys.audit("dspx.image.baseline", "0" * 64)


@worker_entry
def _register(params):
    from dspx.image_decoder import FrozenImageDecoder
    from dspx.image_input_contract import materialize_image_inputs
    from dspx.image_privacy import image_privacy
    from dspx.image_source_io import read_relative
    from dspx.image_source_profile import ImageSourceProfile

    input_fd, candidate_fd = params["input_fd"], params["candidate_fd"]
    marker = params["marker_fd"]
    raw = read_relative(input_fd, "inputs.json", limit=1 << 20)
    pixels = base64.b64decode(json.loads(raw)["visual"]["data"])

    def observer(event, args):
        os.write(marker, b"e")
        frame = sys._getframe(1)
        while frame is not None:
            values = list(frame.f_locals.values())
            if any(type(value) is bytes and pixels in value for value in values):
                os.write(marker, b"p")
            frame = frame.f_back

    kind, phase = params["kind"], params["phase"]
    if kind not in {"none", "control"} and phase == "before_privacy":
        _attempt(kind, observer)
    with pytest.MonkeyPatch.context() as spies:
        if kind == "control":
            real = FrozenImageDecoder.decode

            def decode(self, data, media):
                observer("control", ())  # called directly: not a registration
                return real(self, data, media)

            spies.setattr(FrozenImageDecoder, "decode", decode)
        with image_privacy():
            if kind not in {"none", "control"} and phase == "inside_privacy":
                _attempt(kind, observer)
            profile = ImageSourceProfile(candidate_fd)
            materialize_image_inputs(
                raw,
                root_fd=input_fd,
                fields=profile.snapshot.inputs,
                candidate_manifest_sha256=profile.snapshot.manifest_sha256,
                candidate_source_sha256=profile.snapshot.sha256,
                decoder=FrozenImageDecoder(),
            )
    return _status("1" * 64)


@pytest.mark.parametrize("phase", ["before_privacy", "inside_privacy"])
@pytest.mark.parametrize("kind", ["none", "control", *_KINDS])
def test_observer_registration_inside_worker_poisons_before_materialization(
    tmp_path: Path, kind: str, phase: str
):
    """Original audit red 13513 under the refinement: refusal INSIDE the worker.

    The frame-inspecting observer is the falsifier that saw 34 pixel frames in the
    forked worker. Every registration, native lookup, introspection or unaudited
    observer channel now ends the worker with image_privacy before any pixel exists;
    the observer logs each invocation to an append-only file the parent reads after.
    The control proves the same observer does see pixels inside the worker.
    """
    candidate, inputs, _ = _candidate(tmp_path)
    marker = tmp_path / "observer.log"
    fds = {
        "candidate_fd": os.open(candidate, os.O_RDONLY | os.O_DIRECTORY),
        "input_fd": os.open(inputs, os.O_RDONLY | os.O_DIRECTORY),
        "marker_fd": os.open(marker, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600),
    }
    try:
        params = {**fds, "kind": kind, "phase": phase}
        if kind in {"none", "control"}:
            result = supervise_image_worker(
                f"{_HERE}:_register", params, fds=tuple(fds.values()), wall_ms=30_000
            )
            assert result == _status("1" * 64)
        else:
            with pytest.raises(ImageContractError, match="^image_privacy$"):
                supervise_image_worker(
                    f"{_HERE}:_register",
                    params,
                    fds=tuple(fds.values()),
                    wall_ms=30_000,
                )
        log = marker.read_bytes()
        if kind == "control":
            assert log.count(b"p") > 0, log
        elif kind in {"signal", "gc_callback", "rebaseline"}:
            assert b"p" not in log, log  # may fire, but never with pixels in reach
        else:
            assert log == b"", log
    finally:
        for fd in fds.values():
            os.close(fd)


_IMPORT_TIME_OBSERVER = """
import signal
import sys

from dspx.image_worker import worker_entry

if sys.flags.isolated:  # arm only inside the worker, never in the test parent
    signal.signal(signal.SIGALRM, lambda number, frame: None)


@worker_entry
def entry(params):
    raise AssertionError("an import-time observer must end the worker first")
"""


def test_observer_armed_at_import_time_never_becomes_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Non-adversarial import-time observers are not absorbed into the clean state."""
    (tmp_path / "import_time_observer.py").write_text(_IMPORT_TIME_OBSERVER)
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ImageContractError, match="^image_privacy$"):
        supervise_image_worker("import_time_observer:entry", {}, wall_ms=30_000)


def test_unguarded_process_is_outside_the_boundary():
    """This pytest parent has no guard; a fork of it inherits that state."""
    with pytest.raises(ImageContractError, match="^image_execution_unavailable$"):
        require_clean_boundary()
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            require_clean_boundary()
            os.write(write_fd, b"admitted")
        except ImageContractError as error:
            os.write(write_fd, error.code.encode())
        os._exit(0)
    os.close(write_fd)
    try:
        assert os.read(read_fd, 64) == b"image_execution_unavailable"
    finally:
        os.close(read_fd)
        os.waitpid(pid, 0)


def test_native_registration_closure_fails_closed(tmp_path: Path):
    clean = tmp_path / "libclean.so"
    hostile = tmp_path / "libhostile.so.1"
    clean.write_bytes(b"\x7fELF ordinary native library")
    hostile.write_bytes(b"\x7fELF ... PySys_AddAuditHook ...")
    native_registration_closure([os.fsencode(clean)])
    with pytest.raises(ImageContractError, match="^image_privacy$"):
        native_registration_closure([os.fsencode(hostile)])
    with pytest.raises(ImageContractError, match="^image_privacy$"):
        native_registration_closure([os.fsencode(clean) + b" (deleted)"])
    with pytest.raises(ImageContractError, match="^image_privacy$"):
        native_registration_closure([b"/memfd:payload (deleted)"])
    for symbol in OBSERVER_SYMBOLS:
        other = tmp_path / f"lib{symbol}.so"
        other.write_bytes(b"\x7fELF " + symbol.encode())
        with pytest.raises(ImageContractError, match="^image_privacy$"):
            native_registration_closure([os.fsencode(other)])


def test_admitted_native_roots_cannot_register_unnotified_hooks():
    """Static tripwire for refinement B: no admitted extension imports the native API.

    PySys_AddAuditHook skips notification with a NULL thread state. No library under
    the worker's native roots references it, so admitted native code cannot take that
    path; Python-level ctypes lookups of observer APIs end the worker (dlsym veto), and
    the runtime check repeats this over every executable mapping. Deliberately hostile
    code calling a raw function pointer derived from parsed ELF symbols is outside the
    threat model (it could read the pixels directly).
    """
    import sysconfig

    roots = {
        Path(sysconfig.get_paths()["platlib"]),
        Path(sysconfig.get_paths()["purelib"]),
        Path(sysconfig.get_config_var("DESTSHARED")),
    }
    scanned = []
    observer_capable = set()
    for root in roots:
        for path in root.rglob("*.so*"):
            if path.is_file() and not path.is_symlink():
                data = path.read_bytes()
                assert b"PySys_AddAuditHook" not in data, path.name
                if any(symbol.encode() in data for symbol in OBSERVER_SYMBOLS):
                    observer_capable.add(path.parent.name + "/" + path.name)
                scanned.append(path)
    assert scanned
    # Only coverage's tracer can set a trace natively; the worker never maps it
    # (isolation test), and the runtime closure would refuse it if it were mapped.
    assert all(name.startswith("coverage/tracer") for name in observer_capable)
    assert set(GUARD_EVENTS) >= {
        "sys.addaudithook",
        "sys.settrace",
        "sys.setprofile",
        "sys.monitoring.register_callback",
    }


_HOOKED_PARENT = r"""
import base64, json, os, sys
from pathlib import Path
case = json.loads(sys.argv[1])
import test_image_execution as fixture
def _needles():
    raw = Path(case["pixels_path"]).read_bytes()
    return raw, base64.b64encode(raw).decode("ascii")
def _contains(value, needles, depth=0):
    if type(value) in (bytes, bytearray):
        return needles[0] in value
    if type(value) is str:
        return needles[1] in value
    if depth < 3 and type(value) in (list, tuple, set, frozenset):
        return any(_contains(item, needles, depth + 1) for item in list(value)[:1000])
    if depth < 3 and type(value) is dict:
        items = list(value.items())[:1000]
        return any(_contains(k, needles, depth + 1) or _contains(v, needles, depth + 1) for k, v in items)
    return False
hits, events, active = [], [], []
def observer(event, args, _needles=_needles()):
    if active:
        return  # frame introspection raises its own audit events
    active.append(True)
    try:
        events.append(event)
        frame = sys._getframe(1)
        while frame is not None:
            if any(_contains(v, _needles) for v in list(frame.f_locals.values())):
                hits.append(event)
            frame = frame.f_back
    finally:
        active.pop()
sys.addaudithook(observer)
control = Path(case["inputs"]).read_text()
open(os.devnull).close()
sensitive = len(hits)
del control
hits.clear()
fixture._run_shipped_route(
    Path(case["root"]), media="image/png", use_cot=False, route=case["route"]
)
print(json.dumps({"sensitive": sensitive, "hits": len(hits), "events": len(events)}))
"""


@pytest.mark.parametrize("route", ["episode", "direct"])
def test_hooked_parent_is_outside_boundary_and_never_sees_pixels(
    tmp_path: Path, route: str
):
    """Given an audit-hooked caller; When it runs a shipped route; Then no pixel frame.

    The refinement excludes an already-hooked parent from the boundary: its hooks are
    not inherited across exec and the parent never decodes, formats or sends pixels.
    The control proves the same observer does see pixels the parent itself reads.
    """
    import test_image_execution as fixture

    pixels = fixture._shipped_inputs(tmp_path, media="image/png")
    (tmp_path / "pixels.bin").write_bytes(pixels)
    env = {
        **{
            name: value
            for name, value in os.environ.items()
            if not name.startswith("PYTHON")
        },
        "PYTHONPATH": os.pathsep.join(entry for entry in sys.path if entry),
        "MLFLOW_ENABLE": "0",
        "DSPX_POLICY_ALLOW_NETWORK_MUTATE": "1",
    }
    case = {
        "pixels_path": str(tmp_path / "pixels.bin"),
        "inputs": str(tmp_path / "inputs" / "inputs.json"),
        "root": str(tmp_path),
        "route": route,
    }
    completed = subprocess.run(
        [sys.executable, "-c", _HOOKED_PARENT, json.dumps(case)],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode()[-2000:]
    facts = json.loads(completed.stdout.decode().strip().splitlines()[-1])
    assert facts["sensitive"] > 0, facts
    assert facts["hits"] == 0 and facts["events"] > 0, facts
