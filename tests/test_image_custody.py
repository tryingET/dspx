# summary: "Custody red matrix in the clean worker: publication faults, post-send failures, contention, trickle and absent-terminal reconciliation."
# read_when:
#   - "Changing image custody publication, settlement, root claiming or read-only reconciliation."
"""AK6756 custody rows of the Revision2 red matrix (AK6607 red-cases.feature).

Every case runs the production custody path inside the guarded clean worker. Faults are
injected there with pytest.MonkeyPatch around the exact custody publication; the parent
asserts on durable records, the wire-observation root and the read-only reconciliation.
The worker reports its in-memory latch state only through the status commitment.
"""

from __future__ import annotations

import base64
import errno
import json
import os
import signal
import struct
import time
import uuid
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dspy
import httpx
import pytest

from dspx.image_admission import (
    CEILINGS,
    ImageAdmission,
    ImageContractError,
    SyntheticImageAuthority,
    canonical,
    digest,
    parse_json,
    sha,
    validate_admission,
)
from dspx.image_artifacts import ImageRunAnchor, verify_image_run
from dspx.image_custody import ImageCustodySession, parent_initializer
from dspx.image_execution import prepare_image_execution
from dspx.image_privacy import image_privacy, runtime_identity
from dspx.image_records import list_root, read_record
from dspx.image_supervision import supervise_image_worker
from dspx.image_worker import worker_entry
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent

_HERE = "test_image_custody"
_MODEL = "synthetic-vision-fixture"
_ANSWER = "[[ ## answer ## ]]\nfixture result\n[[ ## completed ## ]]"
_RECORDS = {"lock", "ready.json", "intent-1.json", "terminal-1.json", "closure.json"}
_ARTIFACTS = {
    "image_source_package.json",
    "image_input_manifest.json",
    "runtime_image_inputs.json",
    "image_output_000000.json",
    "image_behavior_results.json",
    "image_program_runtime_traces.json",
    "image_content_artifacts.json",
    "image_oracle_evidence.json",
    "runtime_image_episode.json.meta.json",
    "runtime_image_episode.json",
    "image_published_artifacts.json",
}


def _png(color: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + data))
        return struct.pack(">I", len(data)) + kind + data + crc

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\0" + color))
        + chunk(b"IEND", b"")
    )


def _status(kind: str, commitment: str) -> dict[str, object]:
    return {
        "status": kind,
        "commitment_sha256": commitment,
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": None,
    }


def _commitment(names, *, poisoned: bool, latched: bool, sends: int) -> str:
    """Worker-side latch facts, bound to the exact durable listing it observed."""
    state = {"names": sorted(names), "poisoned": poisoned, "latched": latched}
    return digest("custody-case-v1", {**state, "sends": sends})


@dataclass(frozen=True)
class _Case:
    base: Path
    preparation: bytes


@pytest.fixture(scope="module")
def case(tmp_path_factory: pytest.TempPathFactory) -> _Case:
    """One prepared candidate and input; every test binds its own fresh roots."""
    base = tmp_path_factory.mktemp("custody-case")
    materialize_program_from_intent(
        ProgramIntent(
            name="CustodyProbe",
            objective="Describe bounded synthetic pixels.",
            input_fields=[{"name": "visual", "type": "str"}],
            output_fields=[{"name": "answer", "type": "str"}],
            options={"image_enabled": True},
        ),
        outdir=base / "candidate",
    )
    inputs = base / "inputs"
    inputs.mkdir(mode=0o700)
    image = base64.b64encode(_png(b"\x0c\x22\x38")).decode("ascii")
    block = {"type": "image_base64", "media_type": "image/png", "data": image}
    (inputs / "inputs.json").write_text(json.dumps({"visual": ["A", block, "B"]}))
    (base / "preparation").mkdir(mode=0o700)
    names = ("candidate", "inputs", "preparation")
    fds = [os.open(base / name, os.O_RDONLY | os.O_DIRECTORY) for name in names]
    try:
        prepared = prepare_image_execution(
            candidate_fd=fds[0],
            input_fd=fds[1],
            input_name="inputs.json",
            preparation_fd=fds[2],
            model=_MODEL,
        )
    finally:
        for fd in fds:
            os.close(fd)
    return _Case(base, prepared.raw)


@pytest.fixture(autouse=True)
def _synthetic_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")


class _Run:
    """Fresh artifact/wire roots (and by default custody) with independent descriptions."""

    def __init__(
        self,
        case: _Case,
        home: Path,
        *,
        custody: Path | None = None,
        admission_raw: bytes | None = None,
        wall_ms: int = 30_000,
        io_ms: int = 30_000,
    ) -> None:
        self.case, self.wall_ms = case, wall_ms
        custody = home / "custody" if custody is None else custody
        for path in (home / "artifacts", home / "wire", custody):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        paths = {
            "candidate": case.base / "candidate",
            "inputs": case.base / "inputs",
            "custody": custody,
            "artifacts": home / "artifacts",
            "wire": home / "wire",
        }
        self.fds = {
            name: os.open(path, os.O_RDONLY | os.O_DIRECTORY)
            for name, path in paths.items()
        }
        self.prepared = parse_json(case.preparation)
        root = os.fstat(self.fds["custody"])
        self.root = (root.st_dev, root.st_ino)
        now = time.time_ns() // 1_000_000
        record = {
            "schema_version": "dspx-image-admission-v2",
            "mode": "synthetic",
            "provider_kind": "openai-compatible",
            "model": _MODEL,
            "canonical_base_endpoint": "http://127.0.0.1:8000/v1",
            "source_package_sha256": digest("source-v1", self.prepared["source"]),
            "candidate_manifest_sha256": self.prepared["source"][
                "candidate_manifest_sha256"
            ],
            "runtime_identity_sha256": self.prepared["runtime_identity_sha256"],
            "decoder_profile_sha256": self.prepared["source"]["decoder_profile_sha256"],
            "request_plan": self.prepared["plan"],
            "limits": {**CEILINGS, "total_dispatch_allowance": 1},
            "deadlines": {
                "not_before_utc_ms": now - 1000,
                "expires_utc_ms": now + 120_000,
                "total_wall_ms": wall_ms,
                "per_request_io_timeout_ms": io_ms,
            },
            "custody": {
                "custody_id": str(uuid.uuid4()),
                "caller_run_id": str(uuid.uuid4()),
                "caller_binding_sha256": "2" * 64,
                "root_dev": root.st_dev,
                "root_ino": root.st_ino,
                "caller_expectation_sha256": sha(case.preparation),
            },
            "approval_binding": {
                "owning_ak_task": None,
                "operator_evidence_ref": None,
                "parent_confirmation_sha256": None,
            },
        }
        self.admission_raw = (
            canonical(record) if admission_raw is None else admission_raw
        )
        self.manifest = {
            "schema_version": "dspx-image-input-manifest-v2",
            "source_package_sha256": record["source_package_sha256"],
            "admission_sha256": digest("admission-v2", parse_json(self.admission_raw)),
            "marker_entries": self.prepared["markers"],
        }

    def close(self) -> None:
        for fd in self.fds.values():
            os.close(fd)

    def initializer(self):
        """A copied admission with a fresh nominal authority, as any later caller holds."""
        authority = SyntheticImageAuthority(
            self.admission_raw, sha(self.case.preparation), self.root[0], self.root[1]
        )
        admission = validate_admission(
            self.admission_raw,
            source=self.prepared["source"],
            authority=authority,
            runtime_identity_sha256=runtime_identity(),
        )
        return parent_initializer(
            self.fds["custody"],
            authority,
            admission,
            source_sha256=self.manifest["source_package_sha256"],
            manifest_sha256=digest("manifest-v2", self.manifest),
        )

    def execute(self, fault: str = "none", *, barrier: str = "", initialize=True):
        params = {
            "candidate_fd": self.fds["candidate"],
            "input_fd": self.fds["inputs"],
            "input_name": "inputs.json",
            "artifact_fd": self.fds["artifacts"],
            "custody_fd": self.fds["custody"],
            "preparation": self.case.preparation.decode("ascii"),
            "admission": self.admission_raw.decode("ascii"),
            "authority": {
                "caller_expectation_sha256": sha(self.case.preparation),
                "root_dev": self.root[0],
                "root_ino": self.root[1],
            },
            "fixture": {"completion": _ANSWER, "observation_fd": self.fds["wire"]},
            "fault": fault,
            "barrier": barrier,
        }
        try:
            return supervise_image_worker(
                f"{_HERE}:_custody_entry",
                params,
                fds=tuple(fd for name, fd in self.fds.items()),
                wall_ms=self.wall_ms,
                parent_action=self.initializer() if initialize else None,
            )
        except ImageContractError as error:
            return error.code

    def names(self, root: str = "custody") -> list[str]:
        return sorted(list_root(self.fds[root]))

    def record(self, name: str) -> dict[str, Any]:
        return parse_json(read_record(self.fds["custody"], name))

    def snapshot(self) -> dict[str, object]:
        rows: dict[str, object] = {"wire": self.names("wire")}
        for name in self.names():
            row = os.stat(name, dir_fd=self.fds["custody"], follow_symlinks=False)
            rows[name] = (row.st_ino, row.st_size, row.st_mtime_ns, row.st_mode)
        return rows

    def anchor(self) -> ImageRunAnchor:
        closure = "0" * 64
        if "closure.json" in self.names():
            closure = sha(read_record(self.fds["custody"], "closure.json"))
        return ImageRunAnchor(
            self.fds["custody"],
            self.fds["artifacts"],
            closure,
            self.admission_raw,
            canonical(self.prepared["source"]),
            canonical(self.manifest),
            self.prepared["output_slots"],
        )

    def reconcile(self) -> dict[str, Any]:
        from dspx.image_record_validation import reconcile_image_custody

        return reconcile_image_custody(
            self.fds["custody"],
            admission_raw=self.admission_raw,
            source_raw=canonical(self.prepared["source"]),
            manifest_raw=canonical(self.manifest),
        )


@pytest.fixture
def run(case: _Case, tmp_path: Path):
    current = _Run(case, tmp_path)
    try:
        yield current
    finally:
        current.close()


def _assert_spent(run: _Run, *, sends: int) -> dict[str, Any]:
    """Reconstruction is read-only: no initializer, verification, allowance or write."""
    before = run.snapshot()
    with pytest.raises(ImageContractError, match="^image_spent$"):
        run.initializer()
    with pytest.raises(ImageContractError, match="^image_spent$"):
        verify_image_run(run.anchor())
    state = run.reconcile()
    assert state["status"] == "spent" and state["dispatch_available"] is False
    assert state["consumed_dispatches"] == len(state["attempts"])
    assert state["publication_residue"] == sum(
        name.startswith(".pending-") for name in run.names()
    )
    assert run.snapshot() == before and len(run.names("wire")) == sends
    return state


def _durable(run: _Run) -> set[str]:
    names = set(run.names())
    residue = {name for name in names if name.startswith(".pending-")}
    assert names - residue <= _RECORDS  # no diagnostic or foreign record is written
    return names - residue


def _reconciled(
    state: dict[str, Any], disposition: str, *, terminal: bool, contradicted=False
) -> None:
    (attempt,) = state["attempts"]
    assert attempt["attempt_ordinal"] == 1
    assert attempt["provider_disposition"] == disposition
    assert (attempt["terminal_sha256"] is not None) is terminal
    assert attempt["terminal_contradicted"] is contradicted
    if not terminal:  # never mints a send outcome that nothing durable recorded
        assert attempt["dispatch_count"] is None
    assert state["terminal_effect"] == disposition


# ---------------------------------------------------------------- worker side


def _eio(*args: object, **kwargs: object):
    raise OSError(errno.EIO, "synthetic-fault")


def _interrupt(*args: object, **kwargs: object):
    raise KeyboardInterrupt("synthetic-fault")


def _io_fault(io: pytest.MonkeyPatch, kind: str, root_fd: int, name: str, real, record):
    import dspx.image_records as records

    if kind == "create":  # the pending file exists, the open's response is lost
        opened = os.open

        def lost(path, flags, *args, **kwargs):
            fd = opened(path, flags, *args, **kwargs)
            if type(path) is str and path.startswith(".pending-"):
                os.close(fd)
                _eio()
            return fd

        io.setattr(os, "open", lost)
    elif kind == "partial":
        written = os.write

        def partial(fd, data):
            io.setattr(os, "write", _eio)
            return written(fd, bytes(data[: max(1, len(data) // 2)]))

        io.setattr(os, "write", partial)
    elif kind in {"fsync_file", "fsync_dir"}:
        synced = os.fsync

        def failing(fd):
            if (fd == root_fd) is (kind == "fsync_dir"):
                _eio()
            synced(fd)

        io.setattr(os, "fsync", failing)
    elif kind == "exists":  # a different same-slot record is already linked
        real(root_fd, name, {**record, "attempt_id": str(uuid.uuid4())})
    else:
        assert kind == "readback"
        read = records.read_record
        io.setattr(
            records,
            "read_record",
            lambda fd, target: read(fd, target) + (b" " if target == name else b""),
        )


def _fail_publication(patch, owner, prefix: str, kind: str, *, once: bool) -> None:
    real, fired = owner.publish, []

    def faulty(root_fd, name, record):
        if not name.startswith(prefix) or (once and fired):
            return real(root_fd, name, record)
        fired.append(name)
        with pytest.MonkeyPatch.context() as io:
            _io_fault(io, kind, root_fd, name, real, record)
            return real(root_fd, name, record)

    patch.setattr(owner, "publish", faulty)


def _arm(patch: pytest.MonkeyPatch, fault: str, barrier: str) -> None:
    import dspx.image_artifacts as artifacts
    import dspx.image_custody as custody
    from dspx.dspy_typed_lm import DSPyTypedLMAdapter
    from dspx.openai_compatible_provider import OpenAICompatibleProvider

    if fault.startswith("intent_"):
        kind = fault.removeprefix("intent_")
        _fail_publication(patch, custody, "intent-", kind, once=False)
    elif fault in {"terminal_write", "terminal_dir_fsync", "terminal_missing"}:
        kind = "fsync_dir" if fault == "terminal_dir_fsync" else "partial"
        once = fault != "terminal_missing"
        _fail_publication(patch, custody, "terminal-", kind, once=once)
    elif fault == "closure":
        _fail_publication(patch, custody, "closure.json", "fsync_file", once=True)
    elif fault == "artifact":
        name = "image_behavior_results.json"
        _fail_publication(patch, artifacts, name, "partial", once=True)
    elif fault == "provider_interrupt":
        patch.setattr(OpenAICompatibleProvider, "_validated_response", _interrupt)
    elif fault == "typed_interrupt":
        patch.setattr(DSPyTypedLMAdapter, "_typed_response", _interrupt)
    elif fault == "finalization":  # BaseLM's own post-forward finalization step
        patch.setattr(DSPyTypedLMAdapter, "_finalize_lm_response", _eio)
    elif fault == "contend":
        listed = custody.list_root

        def gated(fd: int) -> list[str]:
            names = listed(fd)
            if not names:  # both contenders observe the empty root before either claims
                Path(barrier, str(os.getpid())).write_bytes(b"")
                until = time.monotonic() + 20
                while len(os.listdir(barrier)) < 2:
                    assert time.monotonic() < until, "contender barrier"
                    time.sleep(0.002)
            return names

        patch.setattr(custody, "list_root", gated)


class _Trickle(httpx.SyncByteStream):
    """Every chunk arrives well within the per-read timeout; the body never ends."""

    def __iter__(self):
        while True:
            time.sleep(0.1)
            yield b" "


def _transport(params: dict[str, Any], fault: str) -> httpx.MockTransport:
    from dspx.image_effects import fixture_transport

    owner = fixture_transport(params["fixture"], _MODEL)
    if fault not in {"killed", "trickle", "http_500"}:
        return owner

    def handler(request: httpx.Request) -> httpx.Response:
        owner.handler(request)  # the owner fixture records exactly this send
        if fault == "killed":
            os.kill(os.getpid(), signal.SIGKILL)
        if fault == "http_500":  # a fully observed, classified completed_failure
            return httpx.Response(500, json={"error": "fixture"}, request=request)
        return httpx.Response(200, stream=_Trickle(), request=request)

    return httpx.MockTransport(handler)


def _forked_contender(session: ImageCustodySession, params: dict[str, Any]) -> None:
    """A second process sharing the session and root gets no provider and no slot."""
    from dspx.provider_registry import create_image_lm

    pid = os.fork()
    if pid == 0:
        codes = []
        for attempt in (
            lambda: create_image_lm(session, transport=_transport(params, "none")),
            lambda: session.transaction("dspy_lm").__enter__(),
        ):
            try:
                attempt()
                codes.append("entered")
            except ImageContractError as error:
                codes.append(error.code)
            except BaseException:
                codes.append("other")
        os._exit(0 if codes == ["image_custody", "image_custody"] else 1)
    _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


def _denied_after(active, session, lm, program, context, params) -> dict[str, object]:
    """Inside the live privacy context: retries, new providers and fallbacks get no send."""
    from dspx.image_artifacts import publish_image_run
    from dspx.provider_registry import create_image_lm

    custody_fd, wire_fd = params["custody_fd"], params["fixture"]["observation_fd"]
    names, sends = list_root(custody_fd), list_root(wire_fd)
    poisoned = session.poisoned
    latched = lm._indeterminate_latched and lm.provider._indeterminate_latched
    callers = [lm]
    if not poisoned:  # a new provider object over the same session and root
        callers.append(create_image_lm(session, transport=_transport(params, "none")))
    for caller in callers:
        with pytest.raises(ImageContractError), dspy.context(lm=caller):
            program(**context.materialized())
    with pytest.raises(ImageContractError, match="^image_(spent|budget)$"):
        with session.transaction("direct_provider"):
            raise AssertionError("a direct-provider fallback reserved a slot")
    artifact_fd = params["artifact_fd"]
    if not list_root(artifact_fd):  # failed before publication: nothing may follow
        with pytest.raises(ImageContractError, match="^image_(spent|custody)$"):
            publish_image_run(
                session,
                artifact_fd=artifact_fd,
                outputs={"answer": "fixture result"},
                route="episode",
            )
        assert list_root(artifact_fd) == []  # refused before any artifact write
    assert active.session is session
    assert list_root(wire_fd) == sends and list_root(custody_fd) == names
    commitment = _commitment(
        names, poisoned=poisoned, latched=latched, sends=len(sends)
    )
    return _status("failed", commitment)


@worker_entry
def _custody_entry(params: dict[str, Any]) -> dict[str, object]:
    fault, barrier = params.pop("fault"), params.pop("barrier")
    with pytest.MonkeyPatch.context() as patch:
        _arm(patch, fault, barrier)
        return _flow(params, fault)


def _flow(params: dict[str, Any], fault: str) -> dict[str, object]:
    """The shipped `_execute_entry` sequence, with failures inspected in place."""
    from dspx.image_artifacts import publish_image_run
    from dspx.image_execution import ImagePreparation, _prepare
    from dspx.provider_registry import create_image_lm

    preparation = ImagePreparation(params["preparation"].encode("ascii"))
    raw = params["admission"].encode("ascii")
    admission = ImageAdmission(raw, digest("admission-v2", parse_json(raw)))
    bound = params["authority"]
    # Worker-local mirror, usable only through the parent's bound ready handshake.
    authority = SyntheticImageAuthority(
        raw,
        bound["caller_expectation_sha256"],
        bound["root_dev"],
        bound["root_ino"],
        _used=[False],
    )
    record, custody_fd = admission.record, params["custody_fd"]
    with image_privacy() as active:
        program, context, rederived = _prepare(
            active,
            candidate_fd=params["candidate_fd"],
            input_fd=params["input_fd"],
            input_name=params["input_name"],
            model=record["model"],
            use_cot=preparation.record["use_cot"] is True,
            limits=record["limits"],
        )
        assert canonical(rederived) == preparation.raw
        session = ImageCustodySession(
            root_fd=custody_fd,
            admission=admission,
            authority=authority,
            context=context,
        )
        active.session = session
        if fault == "contend":
            _forked_contender(session, params)
        lm = create_image_lm(session, transport=_transport(params, fault))
        try:
            with dspy.context(lm=lm):
                prediction = program(**context.materialized())
            outputs = {"answer": prediction.toDict()["answer"]}
            active.check()
            binding = publish_image_run(
                session,
                artifact_fd=params["artifact_fd"],
                outputs=outputs,
                route="episode",
            )
            session.close_run(binding, outcome="completed")
        except ImageContractError:
            return _denied_after(active, session, lm, program, context, params)
        return _status("completed", sha(read_record(custody_fd, "closure.json")))


# ---------------------------------------------------------------------- cases


@pytest.mark.parametrize(
    "fault",
    [
        "intent_create",  # AK6607-S43-E01 temp create response missing
        "intent_partial",  # AK6607-S43-E02 partial intent write
        "intent_fsync_file",  # AK6607-S43-E03 intent file fsync failure
        "intent_exists",  # AK6607-S43-E04 target already exists
        "intent_fsync_dir",  # AK6607-S43-E05 directory fsync failure
        "intent_readback",  # AK6607-S43-E06 final intent readback mismatch
    ],
)
def test_presend_publication_fault_inside_real_reservation_prohibits_send(
    run: _Run, fault: str
) -> None:
    result = run.execute(fault)
    names = run.names()
    assert run.names("wire") == []  # no HTTP send occurred
    assert result == _status(
        "failed", _commitment(names, poisoned=True, latched=True, sends=0)
    )
    linked = fault in {"intent_exists", "intent_fsync_dir", "intent_readback"}
    assert _durable(run) == {"lock", "ready.json"} | (
        {"intent-1.json"} if linked else set()
    )
    residue = [name for name in names if name.startswith(".pending-")]
    assert len(residue) == (
        0 if fault in {"intent_fsync_dir", "intent_readback"} else 1
    )
    state = _assert_spent(run, sends=0)
    if linked:  # an unconfirmed reservation is never read back as "nothing happened"
        _reconciled(state, "effect_indeterminate", terminal=False)
    else:
        assert state["attempts"] == [] and state["terminal_effect"] == "none"


@pytest.mark.parametrize(
    ("fault", "durable_terminal", "residue"),
    [
        ("provider_interrupt", "effect_indeterminate", 0),  # AK6607-S44-E01
        ("typed_interrupt", "effect_indeterminate", 0),  # AK6607-S44-E02
        ("finalization", "effect_indeterminate", 0),  # AK6607-S44-E03
        ("terminal_write", "effect_indeterminate", 1),  # AK6607-S44-E04
        ("terminal_dir_fsync", "completed_success", 2),  # AK6607-S44-E05
        ("terminal_missing", None, 3),  # AK6607-S22-E07 missing durable terminal
    ],
)
def test_post_send_failure_latches_and_never_publishes_early_success(
    run: _Run, fault: str, durable_terminal: str | None, residue: int
) -> None:
    result = run.execute(fault)
    names = run.names()
    assert len(run.names("wire")) == 1  # exactly one send entered
    assert result == _status(
        "failed", _commitment(names, poisoned=True, latched=True, sends=1)
    )
    durable = _durable(run)
    assert sum(name.startswith(".pending-") for name in names) == residue
    assert "closure.json" not in durable  # no later case, artifact or acceptance score
    assert run.names("artifacts") == []
    if durable_terminal is None:
        assert durable == {"lock", "ready.json", "intent-1.json"}
    else:
        terminal = run.record("terminal-1.json")
        assert terminal["provider_disposition"] == durable_terminal
        assert terminal["dispatch_count"] == 1
        intent = run.record("intent-1.json")
        assert terminal["attempt_id"] == intent["attempt_id"]  # the same UUID and slot
    state = _assert_spent(run, sends=1)
    # Every post-send failure reconciles to indeterminate, never to success: a linked
    # success terminal whose own worker then recorded indeterminate is contradicted.
    _reconciled(
        state,
        "effect_indeterminate",
        terminal=durable_terminal is not None,
        contradicted=fault == "terminal_dir_fsync",
    )


def test_completed_failure_is_spent_and_publishes_no_artifact(run: _Run) -> None:
    """Extra row (effects-slice finding): no artifact after a classified failure."""
    result = run.execute("http_500")
    names = run.names()
    assert result == _status(
        "failed", _commitment(names, poisoned=False, latched=False, sends=1)
    )
    assert len(run.names("wire")) == 1 and run.names("artifacts") == []
    assert _durable(run) == {"lock", "ready.json", "intent-1.json", "terminal-1.json"}
    terminal = run.record("terminal-1.json")
    assert terminal["provider_disposition"] == "completed_failure"
    assert terminal["dispatch_count"] == 1 and terminal["failure_code"] == "response"
    state = _assert_spent(run, sends=1)
    _reconciled(state, "completed_failure", terminal=True)


def test_worker_killed_after_send_is_reconciled_indeterminate(run: _Run) -> None:
    """AK6607-S44-E06: durable intent, a send entered, no terminal ever written."""
    assert run.execute("killed") == "image_interruption"
    assert len(run.names("wire")) == 1
    assert _durable(run) == {"lock", "ready.json", "intent-1.json"}
    assert run.names() == ["intent-1.json", "lock", "ready.json"]
    state = _assert_spent(run, sends=1)
    _reconciled(state, "effect_indeterminate", terminal=False)
    assert (
        state["attempts"][0]["attempt_id"] == run.record("intent-1.json")["attempt_id"]
    )


@pytest.mark.parametrize("fault", ["artifact", "closure"])
def test_artifact_or_closure_fault_burns_the_run(run: _Run, fault: str) -> None:
    """AK6607-S46: the completed provider terminal is neither relabeled nor retried."""
    result = run.execute(fault)
    names = run.names()
    assert result == _status(
        "failed", _commitment(names, poisoned=False, latched=False, sends=1)
    )
    assert len(run.names("wire")) == 1
    assert _durable(run) == {"lock", "ready.json", "intent-1.json", "terminal-1.json"}
    terminal = run.record("terminal-1.json")
    assert terminal["provider_disposition"] == "completed_success"
    artifacts = set(run.names("artifacts"))
    pending = {name for name in artifacts if name.startswith(".pending-")}
    assert artifacts - pending <= _ARTIFACTS and len(pending) == (fault == "artifact")
    # An artifact fault stops the chain; a closure fault follows a complete chain.
    assert ("image_published_artifacts.json" in artifacts) is (fault == "closure")
    state = _assert_spent(run, sends=1)
    _reconciled(state, "completed_success", terminal=True)
    assert state["closure_present"] is False
    assert state["publication_residue"] == (fault == "closure")


def test_trickling_response_cannot_extend_the_original_wall_deadline(
    case: _Case, tmp_path: Path
) -> None:
    """AK6607-S47: per-read progress never refreshes the parent's absolute deadline."""
    run = _Run(case, tmp_path, wall_ms=6_000, io_ms=1_000)
    try:
        started = time.monotonic()
        outcome = run.execute("trickle")
        assert type(outcome) is str and outcome.startswith("image_")
        assert time.monotonic() - started < 6.0 + 2.5
        worker = run.record("ready.json")["worker_pid"]
        with pytest.raises(ProcessLookupError):
            os.kill(worker, 0)  # the owned worker group is terminated and reaped
        assert len(run.names("wire")) == 1  # no second worker or provider attempt
        durable = _durable(run)
        assert {"lock", "ready.json", "intent-1.json"} <= durable
        assert durable <= {"lock", "ready.json", "intent-1.json", "terminal-1.json"}
        if "terminal-1.json" in durable:  # the worker observed the deadline first
            terminal = run.record("terminal-1.json")
            assert terminal["provider_disposition"] == "effect_indeterminate"
        settled = run.snapshot()
        time.sleep(0.3)
        assert run.snapshot() == settled  # nothing survives to send or publish later
        state = _assert_spent(run, sends=1)
        _reconciled(
            state, "effect_indeterminate", terminal="terminal-1.json" in durable
        )
    finally:
        run.close()


def test_spent_completed_root_admits_only_read_only_verification(run: _Run) -> None:
    """AK6607-S48: a closed run reconstructs to integrity checks, never a dispatch."""
    result = run.execute()
    assert type(result) is dict and result["status"] == "completed"
    before = run.snapshot()
    verified = verify_image_run(run.anchor())
    assert verified["spent"] is True and verified["dispatch_available"] is False
    with pytest.raises(ImageContractError, match="^image_spent$"):
        run.initializer()
    # A fresh clean worker with a fresh authority mirror cannot open a session either.
    assert run.execute(initialize=False) == "image_spent"
    state = run.reconcile()
    assert state["terminal_effect"] == "completed_success"
    assert state["closure_present"] is True and state["publication_residue"] == 0
    assert state["dispatch_available"] is False and state["consumed_dispatches"] == 1
    assert run.snapshot() == before and len(run.names("wire")) == 1


def _contend(case: _Case, home: Path, custody: Path, raw: bytes, barrier: Path) -> str:
    """One independent contender: its own parent, descriptions, authority and worker."""
    contender = _Run(case, home, custody=custody, admission_raw=raw)
    try:
        result = contender.execute("contend", barrier=str(barrier))
    finally:
        contender.close()
    return result if type(result) is str else str(result["status"])


def test_two_contending_workers_cannot_both_claim_one_custody_root(
    case: _Case, tmp_path: Path
) -> None:
    """AK6607-S42: real processes race for one root; exactly one wins, no residue."""
    first = _Run(case, tmp_path / "a")
    raw, custody = first.admission_raw, tmp_path / "a" / "custody"
    first.close()
    (tmp_path / "barrier").mkdir()
    helpers = {}
    for name in ("a", "b"):
        pid = os.fork()
        if pid == 0:  # a separate supervising parent; never returns into pytest
            code = 1
            try:
                outcome = _contend(
                    case, tmp_path / name, custody, raw, tmp_path / "barrier"
                )
                (tmp_path / f"outcome-{name}").write_text(outcome)
                code = 0
            finally:
                os._exit(code)
        helpers[name] = pid
    until = time.monotonic() + 90
    while helpers and time.monotonic() < until:
        for name, pid in tuple(helpers.items()):
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
                del helpers[name]
        time.sleep(0.01)
    for pid in helpers.values():  # red cleanup: only this test's own helpers
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    assert not helpers
    outcomes = sorted((tmp_path / f"outcome-{name}").read_text() for name in "ab")
    assert outcomes == ["completed", "image_durability"]
    winner = "a" if (tmp_path / "outcome-a").read_text() == "completed" else "b"
    view = _Run(case, tmp_path / winner, custody=custody, admission_raw=raw)
    try:
        assert view.names() == sorted(_RECORDS)  # no loser residue or second record
        sends = sum(len(list_root(fd)) for fd in _wire_fds(tmp_path))
        assert sends == 1 and view.record("intent-1.json")["attempt_ordinal"] == 1
        assert verify_image_run(view.anchor())["status"] == "ok"
    finally:
        view.close()


def _wire_fds(tmp_path: Path):
    for name in "ab":
        fd = os.open(tmp_path / name / "wire", os.O_RDONLY | os.O_DIRECTORY)
        try:
            yield fd
        finally:
            os.close(fd)
