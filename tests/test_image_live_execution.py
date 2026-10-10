# summary: "AK6918 live image execution against a test-owned loopback server: worker LiveImageAuthority mirror, approval binding, refusals before send and the IO window."
# read_when:
#   - "Changing live image execution, the worker authority mirror, approval binding or the live transport."
"""AK6918 live mode end to end, with no real provider (owner decision AK14880).

The server is test-owned: a canned-completion HTTP/1.1 loop on 127.0.0.1 at an
ephemeral port that records each request's controls and body digest, never pixels.
`supervise_image_worker` requires a single-threaded, childless parent and settles
every process it owns, so a server thread or child would refuse with `image_custody`
or be killed at settlement. The server is therefore double-forked into its own session
before the run; the clean worker, a separate process, reaches it over loopback through
the real `HTTPTransport(trust_env=False, retries=0)`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import base64
import ctypes
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import time
from typing import Any, NoReturn

import pytest

from dspx import image_execution
from dspx.image_admission import (
    ImageAdmission,
    ImageContractError,
    LiveImageAuthority,
    SyntheticImageAuthority,
    canonical,
    digest,
    parse_json,
    sha,
    validate_admission,
)
from dspx.image_artifacts import verify_image_run
from dspx.image_execution import ImageExecutionRequest, ImagePreparation
from dspx.image_privacy import runtime_identity
from dspx.image_records import list_root, read_record
from test_image_execution import _ANSWER, _admitted_request, _execute_route
from test_image_execution import _prepare_route, _route_fds, _shipped_inputs
from test_image_live_admission import _confirmation
from test_image_response_controls import IGNORED, response_body

_INVALID = "image_admission_invalid"
_TASK_REF = (6918, "ak://evidence/14880")  # the confirmation is computed per admission
_FIELDS = ("owning_ak_task", "operator_evidence_ref", "parent_confirmation_sha256")
_CAP = 512  # the admitted max_output_tokens of every live admission here
_CONTROLS = {"max_output_tokens": _CAP, "thinking": "off"}
_SWITCH_OFF = {"enable_thinking": False}
_EXECUTE = "dspx.image_execution:_execute_entry"


# ---------------------------------------------------------------------------
# The test-owned loopback server (a daemon, never this parent's child).
# ---------------------------------------------------------------------------


def _completion(model: str, behaviour: str, cap: int) -> bytes:
    """A controlled completion, or the one response variant the behaviour names."""
    variant = behaviour if behaviour in IGNORED else "valid_null_reasoning"
    return response_body(model, variant, cap, _ANSWER)


def _record(log: Path, ordinal: int, head: str, body: bytes) -> dict[str, Any]:
    lines = head.split("\r\n")
    method, path, _ = lines[0].split(" ", 2)
    headers = {
        name.strip().lower(): value.strip()
        for name, _, value in (line.partition(":") for line in lines[1:])
    }
    packet = json.loads(body)
    images = sum(
        block.get("type") == "image_url"
        for message in packet.get("messages", [])
        if type(message.get("content")) is list
        for block in message["content"]
    )
    row = {
        "method": method,
        "path": path,
        "accept_encoding": headers.get("accept-encoding"),
        "content_type": headers.get("content-type"),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "model": packet.get("model"),
        "controls": {k: v for k, v in packet.items() if k not in {"model", "messages"}},
        "image_blocks": images,
    }
    pending = log / f".request-{ordinal}"
    pending.write_text(json.dumps(row))
    pending.rename(log / f"request-{ordinal}.json")
    return row


def _answer(connection: socket.socket, log: Path, ordinal: int, behaviour: str) -> None:
    connection.settimeout(30)
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = connection.recv(65_536)
        if not chunk:
            return
        data += chunk
    head, _, body = data.partition(b"\r\n\r\n")
    length = 0
    for line in head.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            length = int(value)
    while len(body) < length:
        chunk = connection.recv(65_536)
        if not chunk:
            return
        body += chunk
    row = _record(log, ordinal, head.decode("latin-1"), body)
    payload = _completion(row["model"], behaviour, row["controls"]["max_tokens"])
    status = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
        b"Content-Length: %d\r\nConnection: close\r\n\r\n" % len(payload)
    )
    if behaviour == "trickle":  # every byte beats the per-read timeout, not the window
        connection.sendall(status)
        for index in range(len(payload)):
            time.sleep(0.2)
            connection.sendall(payload[index : index + 1])
    else:
        connection.sendall(status + payload)


def _serve(listener: socket.socket, log: Path, behaviour: str) -> NoReturn:
    try:
        os.setsid()  # its own session: never a member the worker supervisor owns
        signal.alarm(120)  # a lost test can never leave it running
        ordinal = 0
        while True:
            connection, _ = listener.accept()
            ordinal += 1
            with connection:
                try:
                    _answer(connection, log, ordinal, behaviour)
                except OSError:
                    pass  # the client closed its end (the IO window case)
    finally:
        os._exit(0)


@dataclass(frozen=True)
class _Server:
    port: int
    log: Path

    def requests(self) -> list[dict[str, Any]]:
        names = sorted(p.name for p in self.log.iterdir() if p.name.endswith(".json"))
        return [json.loads((self.log / name).read_text()) for name in names]


@contextmanager
def _server(tmp: Path, behaviour: str = "ok") -> Iterator[_Server]:
    log = tmp / "server-log"
    log.mkdir(mode=0o700)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    port = listener.getsockname()[1]
    read_end, write_end = os.pipe()
    child = os.fork()
    if child == 0:  # the intermediate exits at once; the daemon is re-parented
        try:
            os.close(read_end)
            if os.fork() == 0:
                os.write(write_end, str(os.getpid()).encode())
                os.close(write_end)
                _serve(listener, log, behaviour)
        finally:
            os._exit(0)
    listener.close()
    os.close(write_end)
    os.waitpid(child, 0)
    daemon = int(os.read(read_end, 32))
    os.close(read_end)
    libc = ctypes.CDLL(None, use_errno=True)  # this Python build lacks os.pidfd_open
    libc.pidfd_open.argtypes = [ctypes.c_int, ctypes.c_uint]
    libc.pidfd_send_signal.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    handle = libc.pidfd_open(daemon, 0)  # pins the daemon: its PID cannot be reused
    assert handle >= 0
    try:
        yield _Server(port, log)
    finally:
        libc.pidfd_send_signal(handle, int(signal.SIGKILL), None, 0)
        os.close(handle)


# ---------------------------------------------------------------------------
# Owner admissions: the caller-held synthetic admission, re-bound as live.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _live_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")


def _live_record(
    request: ImageExecutionRequest,
    endpoint: str,
    binding: tuple[object, ...] | None = None,
    **edits: Any,
) -> dict[str, Any]:
    """A live admission; without `binding`, its own confirmed approval binding."""
    record = {
        **request.admission.record,
        "mode": "live",
        "canonical_base_endpoint": endpoint,
        "request_controls": dict(_CONTROLS),
        "approval_binding": dict(zip(_FIELDS, (*_TASK_REF, None), strict=True)),
        **edits,
    }
    own = _confirmation(record)
    grant = (*_TASK_REF, own) if binding is None else binding
    record["approval_binding"] = dict(zip(_FIELDS, grant, strict=True))
    return record


def _grant(raw: bytes) -> tuple[Any, ...]:
    return tuple(parse_json(raw)["approval_binding"][key] for key in _FIELDS)


def _authority(
    request: ImageExecutionRequest, raw: bytes, grant: tuple[Any, ...] | None = None
) -> LiveImageAuthority:
    held = request.authority
    assert type(held) is SyntheticImageAuthority
    bound = (held.caller_expectation_sha256, held.root_dev, held.root_ino)
    return LiveImageAuthority(raw, *bound, *(_grant(raw) if grant is None else grant))


def _live(
    fds: dict[str, int],
    prepared: ImagePreparation,
    port: int,
    *,
    route: str = "direct",
    **edits: Any,
) -> ImageExecutionRequest:
    """An owner live admission with its exact parent authority; no fixture."""
    synthetic = _admitted_request(fds, prepared, route=route, completion=_ANSWER)
    raw = canonical(_live_record(synthetic, f"http://127.0.0.1:{port}/v1", **edits))
    authority = _authority(synthetic, raw)
    admission = validate_admission(
        raw,
        source=parse_json(prepared.raw)["source"],
        authority=authority,
        runtime_identity_sha256=runtime_identity(),
    )
    return replace(synthetic, admission=admission, authority=authority, fixture=None)


def _unchecked(raw: bytes) -> ImageAdmission:
    return ImageAdmission(raw, digest("admission-v3", parse_json(raw)))


def _executions(monkeypatch: pytest.MonkeyPatch, tamper=None) -> list[dict[str, Any]]:
    """Spy on (and optionally tamper with) the parent's execute-worker params."""
    seen: list[dict[str, Any]] = []
    real = image_execution.supervise_image_worker

    def spy(entry: str, params: dict[str, object], **kwargs: Any):
        if entry == _EXECUTE and tamper is not None:
            params = tamper(json.loads(json.dumps(params)))
        row: dict[str, Any] = {"entry": entry, "params": params}
        seen.append(row)
        row["result"] = real(entry, params, **kwargs)
        return row["result"]

    monkeypatch.setattr(image_execution, "supervise_image_worker", spy)
    return seen


def _no_spawn(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    entries: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        entries.append("spawn")
        raise AssertionError("a refused live run reached the worker or custody")

    monkeypatch.setattr(image_execution, "supervise_image_worker", forbidden)
    monkeypatch.setattr(image_execution, "parent_initializer", forbidden)
    return entries


def _refused(code: str, call) -> None:
    with pytest.raises(ImageContractError) as caught:
        call()
    assert (caught.value.code, str(caught.value)) == (code, code)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def _quiet(server: _Server, fds: dict[str, int]) -> None:
    time.sleep(0.2)  # nothing in flight could still arrive
    assert server.requests() == []
    assert [list_root(fds[name]) for name in ("custody", "artifacts", "wire")] == [
        [],
        [],
        [],
    ]


# ---------------------------------------------------------------------------
# (c) A live run reaches the loopback server once, through the real transport.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", ["direct", "episode"])
def test_live_run_sends_once_through_the_real_transport_with_admitted_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """Given an owner live admission (loopback endpoint, approval binding, output cap
    512, thinking off) and its exact LiveImageAuthority, no fixture; When the shipped
    route runs; Then the clean worker mirrors the live authority, sends exactly once to
    the loopback server with max_tokens 512 and enable_thinking false, writes custody
    intent, terminal and closure, reports live_authorized and no fixture evidence, and
    the run verifies."""
    pixels = _shipped_inputs(tmp_path, media="image/png")
    executions = _executions(monkeypatch)
    with _route_fds(tmp_path) as fds, _server(tmp_path) as server:
        prepared = _prepare_route(fds, use_cot=False)
        request = _live(fds, prepared, server.port, route=route)
        anchor = _execute_route(tmp_path, request, route=route)
        verified = verify_image_run(anchor)
        custody = sorted(list_root(fds["custody"]))
        closure = read_record(fds["custody"], "closure.json")
        terminal = parse_json(read_record(fds["custody"], "terminal-1.json"))
        wire = list_root(fds["wire"])
        requests = server.requests()
    assert verified["status"] == "ok" and verified["spent"] is True
    (run,) = [row for row in executions if row["entry"] == _EXECUTE]
    assert run["params"]["fixture"] is None
    bound = run["params"]["authority"]
    assert bound["mode"] == "live"
    assert tuple(bound[key] for key in _FIELDS) == _grant(request.admission.raw)
    assert bound["owning_ak_task"] == 6918 and bound["parent_confirmation_sha256"] == (
        _confirmation(request.admission.record)
    )
    assert run["result"] == {
        "status": "completed",
        "commitment_sha256": sha(closure),
        "fixture_evidence": False,
        "live_authorized": True,
        "failure_code": None,
    }
    assert custody == [
        "closure.json",
        "intent-1.json",
        "lock",
        "ready.json",
        "terminal-1.json",
    ]
    assert terminal["provider_disposition"] == "completed_success"
    assert terminal["dispatch_count"] == 1 and terminal["failure_code"] is None
    assert terminal["typed_finalization_completed"] is True
    assert terminal["observed_model"] == prepared.record["model"]
    assert wire == []  # no fixture observation exists in live mode
    (sent,) = requests
    assert (sent["method"], sent["path"]) == ("POST", "/v1/chat/completions")
    assert sent["accept_encoding"] == "identity"
    assert sent["content_type"] == "application/json"
    assert sent["model"] == prepared.record["model"] and sent["image_blocks"] == 1
    assert sent["controls"] == {"max_tokens": 512, "chat_template_kwargs": _SWITCH_OFF}
    for path in (tmp_path / "artifacts").iterdir():
        artifact = path.read_bytes()
        assert base64.b64encode(pixels) not in artifact
        assert b"data:image/" not in artifact


# ---------------------------------------------------------------------------
# (d) Refusals before any send.
# ---------------------------------------------------------------------------

_Edit = Callable[[tuple[Any, ...]], tuple[Any, ...]]
_SAME: _Edit = lambda grant: grant  # noqa: E731
_FOREIGN_REF: _Edit = lambda g: (g[0], "https://e/14880", g[2])  # noqa: E731
_BOOLEAN_TASK: _Edit = lambda g: (True, *g[1:])  # noqa: E731
# case -> (edit of the admitted confirmed binding, edit giving the parent's fields)
_APPROVALS: dict[str, tuple[_Edit, _Edit]] = {
    "approval_absent": (lambda g: (None,) * 3, lambda g: (None,) * 3),
    "task_mismatch": (_SAME, lambda g: (6610, *g[1:])),
    "evidence_mismatch": (_SAME, lambda g: (g[0], "ak://evidence/14879", g[2])),
    "confirmation_mismatch": (_SAME, lambda g: (*g[:2], "5" * 64)),
    "unconfirmed_bytes": (lambda g: (*g[:2], "5" * 64), lambda g: (*g[:2], "5" * 64)),
    "evidence_not_ak": (_FOREIGN_REF, _FOREIGN_REF),
    "task_boolean": (_BOOLEAN_TASK, _BOOLEAN_TASK),
}


@pytest.mark.parametrize("case", list(_APPROVALS))
def test_live_without_exact_approval_binding_refuses_in_the_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """Given a live admission whose approval binding is absent, malformed or differs
    from the parent's LiveImageAuthority; When the shipped entry runs; Then it refuses
    before the worker, custody or any request reaches the server."""
    admit_edit, held_edit = _APPROVALS[case]
    _shipped_inputs(tmp_path, media="image/png")
    with _route_fds(tmp_path) as fds, _server(tmp_path) as server:
        prepared = _prepare_route(fds, use_cot=False)
        synthetic = _admitted_request(fds, prepared, route="direct", completion=_ANSWER)
        endpoint = f"http://127.0.0.1:{server.port}/v1"
        confirmed = _grant(canonical(_live_record(synthetic, endpoint)))
        raw = canonical(_live_record(synthetic, endpoint, admit_edit(confirmed)))
        authority = _authority(synthetic, raw, held_edit(confirmed))
        entries = _no_spawn(monkeypatch)
        live = replace(
            synthetic, admission=_unchecked(raw), authority=authority, fixture=None
        )
        _refused(_INVALID, lambda: live.execute(route="direct"))
        assert entries == []
        _quiet(server, fds)


# The worker-side mirror: params the parent sends are tampered in transit.
_MIRROR = {
    "approval_field_missing": lambda p: {
        **p,
        "authority": {
            k: v for k, v in p["authority"].items() if k != "parent_confirmation_sha256"
        },
    },
    "task_mismatch": lambda p: {
        **p,
        "authority": {**p["authority"], "owning_ak_task": 6610},
    },
    "evidence_mismatch": lambda p: {
        **p,
        "authority": {**p["authority"], "operator_evidence_ref": "ak://evidence/1"},
    },
    "confirmation_mismatch": lambda p: {
        **p,
        "authority": {**p["authority"], "parent_confirmation_sha256": "5" * 64},
    },
    "mirrored_as_synthetic": lambda p: {
        **p,
        "authority": {**p["authority"], "mode": "synthetic", **dict.fromkeys(_FIELDS)},
    },
    "unknown_binding": lambda p: {
        **p,
        "authority": {**p["authority"], "approved": True},
    },
    "fixture_injected": lambda p: {
        **p,
        "fixture": {"completion": _ANSWER, "observation_fd": None},
    },
}


@pytest.mark.parametrize("case", list(_MIRROR))
def test_worker_mirror_refuses_unless_every_approval_field_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """Given an exact live admission and authority in the parent; When the closed
    worker params lose, alter or add an approval field, claim synthetic mode or carry
    a fixture; Then the worker mirror (or its session's validate_admission) refuses
    with image_admission_invalid before ready.json, intent or send."""
    _shipped_inputs(tmp_path, media="image/png")
    executions = _executions(monkeypatch, tamper=_MIRROR[case])
    with _route_fds(tmp_path) as fds, _server(tmp_path) as server:
        prepared = _prepare_route(fds, use_cot=False)
        request = _live(fds, prepared, server.port)
        _refused(_INVALID, lambda: request.execute(route="direct"))
        assert [row["entry"] for row in executions][-1] == _EXECUTE
        _quiet(server, fds)


def test_live_and_synthetic_authorities_never_cross_modes_or_take_a_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a live admission with a fixture, a synthetic admission under a live
    authority (with or without a fixture), or a live admission under a synthetic
    authority; When the shipped entry runs; Then each refuses before spawn or send."""
    from dspx.image_effects import SyntheticTransportFixture

    _shipped_inputs(tmp_path, media="image/png")
    with _route_fds(tmp_path) as fds, _server(tmp_path) as server:
        prepared = _prepare_route(fds, use_cot=False)
        live = _live(fds, prepared, server.port)
        synthetic = _admitted_request(fds, prepared, route="direct", completion=_ANSWER)
        assert synthetic.fixture is not None
        fixture = SyntheticTransportFixture(_ANSWER, observation_fd=fds["wire"])
        crossed_live = _authority(synthetic, synthetic.admission.raw)
        held = synthetic.authority
        assert type(held) is SyntheticImageAuthority
        crossed_synthetic = SyntheticImageAuthority(
            live.admission.raw,
            held.caller_expectation_sha256,
            held.root_dev,
            held.root_ino,
        )
        entries = _no_spawn(monkeypatch)
        for case in (
            replace(live, fixture=fixture),
            replace(synthetic, authority=crossed_live, fixture=None),
            replace(synthetic, authority=crossed_live),
            replace(live, authority=crossed_synthetic),
            replace(live, authority=crossed_synthetic, fixture=fixture),
        ):
            _refused(_INVALID, lambda c=case: c.execute(route="direct"))
        assert entries == []
        _quiet(server, fds)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:{port}/v1",
        "http://0.0.0.0:{port}/v1",
        "http://10.0.0.8:{port}/v1",
        "https://127.0.0.1:{port}/v1",
        "http://127.0.0.1:{port}/v1/chat/completions",
        "http://user@127.0.0.1:{port}/v1",
    ],
)
def test_live_endpoint_must_be_a_loopback_ip_literal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    """Given a live admission whose endpoint is a hostname (even one resolving to the
    running server), a non-loopback address or a non-canonical URL; When the parent
    validates or runs it under an exact live authority; Then it refuses before send."""
    _shipped_inputs(tmp_path, media="image/png")
    with _route_fds(tmp_path) as fds, _server(tmp_path) as server:
        prepared = _prepare_route(fds, use_cot=False)
        synthetic = _admitted_request(fds, prepared, route="direct", completion=_ANSWER)
        raw = canonical(_live_record(synthetic, endpoint.format(port=server.port)))
        authority = _authority(synthetic, raw)
        _refused(
            _INVALID,
            lambda: validate_admission(
                raw,
                source=parse_json(prepared.raw)["source"],
                authority=authority,
                runtime_identity_sha256=runtime_identity(),
            ),
        )
        entries = _no_spawn(monkeypatch)
        live = replace(
            synthetic, admission=_unchecked(raw), authority=authority, fixture=None
        )
        _refused(_INVALID, lambda: live.execute(route="direct"))
        assert entries == []
        _quiet(server, fds)


@pytest.mark.parametrize("layer", ["parent", "worker"])
def test_live_run_needs_the_network_mutate_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layer: str
) -> None:
    """Given an exact live admission and authority but DSPX_POLICY_ALLOW_NETWORK_MUTATE
    off; When the shipped entry runs; Then the parent refuses before spawn, and a worker
    that inherits the policy (parent check bypassed) refuses before reservation/send."""
    _shipped_inputs(tmp_path, media="image/png")
    with _route_fds(tmp_path) as fds, _server(tmp_path) as server:
        prepared = _prepare_route(fds, use_cot=False)
        request = _live(fds, prepared, server.port)
        monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "0")
        if layer == "parent":
            entries = _no_spawn(monkeypatch)
            _refused(_INVALID, lambda: request.execute(route="direct"))
            assert entries == []
            _quiet(server, fds)
            return
        monkeypatch.setattr(image_execution, "allow_network_mutate", lambda: True)
        _refused(_INVALID, lambda: request.execute(route="direct"))
        time.sleep(0.2)
        assert server.requests() == []
        assert sorted(list_root(fds["custody"])) == ["lock", "ready.json"]
        assert list_root(fds["artifacts"]) == []


# ---------------------------------------------------------------------------
# (e) A trickling server: the IO window closes once; no retry or repeat.
# ---------------------------------------------------------------------------


def test_live_trickle_ends_at_the_io_window_without_retry_or_repeat(
    tmp_path: Path,
) -> None:
    """Given a live admission with a 1000 ms per-request IO window and a server that
    sends one byte every 200 ms; When the shipped route runs; Then the worker writes
    one effect_indeterminate terminal (io) at the window, the parent gets the fixed
    image_finalization, the server saw exactly one request, and the spent root never
    dispatches again under a fresh authority."""
    _shipped_inputs(tmp_path, media="image/png")
    with _route_fds(tmp_path) as fds, _server(tmp_path, "trickle") as server:
        prepared = _prepare_route(fds, use_cot=False)
        synthetic = _admitted_request(fds, prepared, route="direct", completion=_ANSWER)
        deadlines = {
            **synthetic.admission.record["deadlines"],
            "total_wall_ms": 20_000,
            "per_request_io_timeout_ms": 1_000,
        }
        request = _live(fds, prepared, server.port, deadlines=deadlines)
        _refused("image_finalization", lambda: request.execute(route="direct"))
        names = sorted(list_root(fds["custody"]))
        intent = parse_json(read_record(fds["custody"], "intent-1.json"))
        terminal = parse_json(read_record(fds["custody"], "terminal-1.json"))
        fresh = _authority(synthetic, request.admission.raw)
        again = replace(request, authority=fresh)
        _refused("image_spent", lambda: again.execute(route="direct"))
        time.sleep(0.5)
        requests = server.requests()
        artifacts = list_root(fds["artifacts"])
    assert names == ["intent-1.json", "lock", "ready.json", "terminal-1.json"]
    assert terminal["provider_disposition"] == "effect_indeterminate"
    assert terminal["failure_code"] == "io" and terminal["dispatch_count"] == 1
    assert terminal["response_sha256"] is None
    elapsed = terminal["terminal_utc_ms"] - intent["reserved_utc_ms"]
    assert 1_000 <= elapsed < 1_000 + 2_000  # the IO window, not the wall budget
    assert len(requests) == 1 and artifacts == []
    assert requests[0]["controls"] == {
        "max_tokens": 512,
        "chat_template_kwargs": _SWITCH_OFF,
    }


# ---------------------------------------------------------------------------
# AK6918 review: the live response must show the admitted controls took effect.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("variant", IGNORED)
def test_live_response_that_ignored_the_controls_is_a_completed_failure(
    tmp_path: Path, variant: str
) -> None:
    """Given an exact live admission (output cap 512, thinking off) and a server whose
    completion <variant> (reasoning, no usage, tokens over the cap, or a finish reason
    other than stop/length); When the shipped route runs; Then the one send is a
    completed failure `response`, never success, with no artifact or closure."""
    _shipped_inputs(tmp_path, media="image/png")
    with _route_fds(tmp_path) as fds, _server(tmp_path, variant) as server:
        prepared = _prepare_route(fds, use_cot=False)
        request = _live(fds, prepared, server.port)
        _refused("image_finalization", lambda: request.execute(route="direct"))
        names = sorted(list_root(fds["custody"]))
        terminal = parse_json(read_record(fds["custody"], "terminal-1.json"))
        artifacts = list_root(fds["artifacts"])
        requests = server.requests()
    model = parse_json(prepared.raw)["model"]
    body = response_body(model, variant, _CAP, _ANSWER)
    assert names == ["intent-1.json", "lock", "ready.json", "terminal-1.json"]
    assert terminal["provider_disposition"] == "completed_failure"
    assert terminal["failure_code"] == "response" and terminal["dispatch_count"] == 1
    assert (
        terminal["response_sha256"] == sha(body) and terminal["observed_model"] == model
    )
    assert artifacts == [] and len(requests) == 1
