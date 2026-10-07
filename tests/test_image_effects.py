# summary: "AK6756 HTTP-effects red matrix (AK6607-S19..S23, S45) on the image path, synthetic only."
# read_when:
#   - "Changing image HTTP effect classification, latching, custody terminals or receipts."
"""Image-path HTTP effects inside the guarded clean worker.

Every scenario dispatches through a real `ImageCustodySession`, `create_image_lm` and an
exact `httpx.MockTransport` in the `-I -S` worker. The worker asserts nothing the parent
cannot re-check: it publishes one closed, payload-free observation record, and the
parent asserts on that record and on the durable custody records themselves.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import time
import uuid
from collections.abc import Callable

import dspy
from dspy.core.types import LMTextPart
import httpx
import pytest
from PIL import Image

from dspx.dspy_typed_lm import DSPyTypedLMAdapter
from dspx.image_admission import (
    CEILINGS,
    ImageAdmission,
    ImageContractError,
    SyntheticImageAuthority,
    canonical,
    closed,
    digest,
    parse_json,
    sha,
    validate_admission,
)
from dspx.image_artifacts import (
    ImageRunAnchor,
    _ReadOnlyCustody,
    _ReadOnlySource,
    _entry,
    publish_image_run,
    verify_image_run,
)
from dspx.image_custody import ImageCustodySession, parent_initializer
from dspx.image_effects import image_effect_envelope
from dspx.image_execution import (
    ImagePreparation,
    SyntheticTransportFixture,
    _prepare,
    execute_image_program,
    prepare_image_execution,
)
from dspx.image_privacy import image_privacy, runtime_identity
from dspx.image_records import list_root, publish, read_record, scan
from dspx.image_supervision import supervise_image_worker
from dspx.image_worker import worker_entry
from dspx.provider_contract import (
    EffectDisposition,
    ProviderImagePart,
    ProviderPartsMessage,
    ProviderRequest,
    ProviderResult,
    ProviderTextPart,
)
from dspx.provider_registry import create_image_lm
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent

_HERE = "test_image_effects"
_MODEL = "synthetic-vision-fixture"
_ENDPOINT_PATH = "/v1/chat/completions"
_ANSWER = "[[ ## answer ## ]]\nfixture result\n[[ ## completed ## ]]"
_REDIRECT = "http://127.0.0.1:8000/v1/redirected-elsewhere?token=redirect-secret"
_REDIRECT_BODY = b"redirect-secret-body"
_PRIVATE = ("preparation", "custody", "artifacts", "spy")
_PARAMS = "candidate_fd input_fd custody_fd artifact_fd spy_fd preparation admission authority scenario"
_RECEIPT = "direct_image_run_receipt.json"
_SPENT_ROOT = ["intent-1.json", "lock", "ready.json", "terminal-1.json"]


# ---------------------------------------------------------------------------
# Parent side: production preparation and admission, then one supervised worker.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Admitted:
    fds: dict[str, int]
    pixels: bytes
    prepared: ImagePreparation
    admission: ImageAdmission
    authority: SyntheticImageAuthority
    manifest: dict[str, object]

    @property
    def source(self) -> dict[str, object]:
        return parse_json(self.prepared.raw)["source"]

    def anchor(self, closure_sha256: str) -> ImageRunAnchor:
        return ImageRunAnchor(
            self.fds["custody"],
            self.fds["artifacts"],
            closure_sha256,
            self.admission.raw,
            canonical(self.source),
            canonical(self.manifest),
            1,
        )


def _pixels() -> bytes:
    image = Image.new("RGB", (2, 2), (12, 34, 56))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    image.close()
    return buffer.getvalue()


def _admit(root: Path, opened: list[int], *, slots: int, repeat: bool) -> _Admitted:
    """Production candidate and `prepare_image_execution`; `slots` dispatch allowance."""
    materialize_program_from_intent(
        ProgramIntent(
            name="EffectsProbe",
            objective="Describe bounded synthetic pixels.",
            input_fields=[{"name": "visual", "type": "str"}],
            output_fields=[{"name": "answer", "type": "str"}],
            options={"image_enabled": True},
        ),
        outdir=root / "candidate",
    )
    pixels = _pixels()
    image = {
        "type": "image_base64",
        "media_type": "image/png",
        "data": base64.b64encode(pixels).decode("ascii"),
    }
    visual: list[object] = ["A", image, "B"] + (["C", image] if repeat else [])
    (root / "inputs").mkdir(mode=0o700)
    (root / "inputs" / "inputs.json").write_text(json.dumps({"visual": visual}))
    for name in _PRIVATE:
        (root / name).mkdir(mode=0o700)
    fds = {}
    for name in ("candidate", "inputs", *_PRIVATE):
        fds[name] = os.open(root / name, os.O_RDONLY | os.O_DIRECTORY)
        opened.append(fds[name])
    prepared = prepare_image_execution(
        candidate_fd=fds["candidate"],
        input_fd=fds["inputs"],
        input_name="inputs.json",
        preparation_fd=fds["preparation"],
        model=_MODEL,
    )
    row = parse_json(prepared.raw)
    custody = os.fstat(fds["custody"])
    now = time.time_ns() // 1_000_000
    record = {
        "schema_version": "dspx-image-admission-v2",
        "mode": "synthetic",
        "provider_kind": "openai-compatible",
        "model": _MODEL,
        "canonical_base_endpoint": "http://127.0.0.1:8000/v1",
        "source_package_sha256": digest("source-v1", row["source"]),
        "candidate_manifest_sha256": row["source"]["candidate_manifest_sha256"],
        "runtime_identity_sha256": row["runtime_identity_sha256"],
        "decoder_profile_sha256": row["source"]["decoder_profile_sha256"],
        # Separately authorized slots: identical request shape, distinct ordinals.
        "request_plan": [
            {**row["plan"][0], "plan_ordinal": ordinal}
            for ordinal in range(1, slots + 1)
        ],
        "limits": {**CEILINGS, "total_dispatch_allowance": slots},
        "deadlines": {
            "not_before_utc_ms": now - 1000,
            "expires_utc_ms": now + 120_000,
            "total_wall_ms": 30_000,
            "per_request_io_timeout_ms": 30_000,
        },
        "custody": {
            "custody_id": str(uuid.uuid4()),
            "caller_run_id": str(uuid.uuid4()),
            "caller_binding_sha256": "2" * 64,
            "root_dev": custody.st_dev,
            "root_ino": custody.st_ino,
            "caller_expectation_sha256": sha(prepared.raw),
        },
        "approval_binding": {
            "owning_ak_task": None,
            "operator_evidence_ref": None,
            "parent_confirmation_sha256": None,
        },
    }
    raw = canonical(record)
    authority = SyntheticImageAuthority(
        raw, sha(prepared.raw), custody.st_dev, custody.st_ino
    )
    admission = validate_admission(
        raw,
        source=row["source"],
        authority=authority,
        runtime_identity_sha256=runtime_identity(),
    )
    manifest = {
        "schema_version": "dspx-image-input-manifest-v2",
        "source_package_sha256": record["source_package_sha256"],
        "admission_sha256": admission.sha256,
        "marker_entries": row["markers"],
    }
    return _Admitted(fds, pixels, prepared, admission, authority, manifest)


@pytest.fixture
def admit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    opened: list[int] = []
    yield lambda slots=1, repeat=False: _admit(
        tmp_path, opened, slots=slots, repeat=repeat
    )
    for fd in opened:
        os.close(fd)


def _effects(run: _Admitted, scenario: str) -> dict[str, object]:
    """One supervised `_effects_entry` run; the parent independently initializes."""
    initialize = parent_initializer(
        run.fds["custody"],
        run.authority,
        run.admission,
        source_sha256=run.admission.record["source_package_sha256"],
        manifest_sha256=digest("manifest-v2", run.manifest),
    )
    names = ("candidate", "inputs", "custody", "artifacts", "spy")
    params: dict[str, object] = {
        "candidate_fd": run.fds["candidate"],
        "input_fd": run.fds["inputs"],
        "custody_fd": run.fds["custody"],
        "artifact_fd": run.fds["artifacts"],
        "spy_fd": run.fds["spy"],
        "preparation": run.prepared.raw.decode("ascii"),
        "admission": run.admission.raw.decode("ascii"),
        "authority": {
            "caller_expectation_sha256": run.authority.caller_expectation_sha256,
            "root_dev": run.authority.root_dev,
            "root_ino": run.authority.root_ino,
        },
        "scenario": scenario,
    }
    return supervise_image_worker(
        f"{_HERE}:_effects_entry",
        params,
        fds=tuple(run.fds[name] for name in names),
        wall_ms=30_000,
        parent_action=initialize,
    )


def _load(fd: int, name: str) -> dict:
    return parse_json(read_record(fd, name))


def _put(fd: int, name: str, row: dict | None) -> None:
    """Replace one private record (a producer rewriting its own projection)."""
    os.unlink(name, dir_fd=fd)
    if row is not None:
        publish(fd, name, row)


def _status(status: str, commitment: object, failure: object = None) -> dict:
    return {
        "status": status,
        "commitment_sha256": commitment,
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": failure,
    }


def _execute(run: _Admitted, completion: str) -> ImageRunAnchor:
    """The shipped production direct route with the owner fixture (no test entry)."""
    return execute_image_program(
        candidate_fd=run.fds["candidate"],
        input_fd=run.fds["inputs"],
        input_name="inputs.json",
        artifact_fd=run.fds["artifacts"],
        custody_fd=run.fds["custody"],
        preparation=run.prepared,
        admission=run.admission,
        authority=run.authority,
        fixture=SyntheticTransportFixture(completion, run.fds["spy"]),
        route="direct",
    )


def _observation(run: _Admitted, result: dict[str, object]) -> dict:
    raw = read_record(run.fds["spy"], "observation.json")
    assert result["commitment_sha256"] == sha(raw)
    return parse_json(raw)


def _assert_spent_root(run: _Admitted) -> None:
    """A spent custody root never reconstructs a fresh dispatch allowance."""
    again = SyntheticImageAuthority(
        run.admission.raw,
        run.authority.caller_expectation_sha256,
        run.authority.root_dev,
        run.authority.root_ino,
    )
    with pytest.raises(ImageContractError, match="^image_spent$"):
        parent_initializer(
            run.fds["custody"],
            again,
            run.admission,
            source_sha256=run.admission.record["source_package_sha256"],
            manifest_sha256=digest("manifest-v2", run.manifest),
        )


# ---------------------------------------------------------------------------
# Worker side: one declared entry, closed integer-only params, payload-free output.
# ---------------------------------------------------------------------------


class _FaultStream(httpx.SyncByteStream):
    def __init__(self, fault: type[BaseException]) -> None:
        self.fault = fault

    def __iter__(self):
        raise self.fault("synthetic-read-fault")
        yield b""  # pragma: no cover


class _LogCapture(logging.Handler):
    def __init__(self, sink: list[str]) -> None:
        super().__init__(logging.DEBUG)
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self.sink.append(logging.Formatter().format(record))


def _transport(scenario: str, sends: list[list[str]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        sends.append([request.url.path, sha(request.content)])
        if scenario == "send_error":
            raise httpx.ConnectError("synthetic-send-fault")
        if scenario == "send_interrupt":
            raise KeyboardInterrupt("synthetic-send-fault")
        if scenario == "redirect":
            return httpx.Response(
                302,
                headers={"Location": _REDIRECT},
                content=_REDIRECT_BODY,
                request=request,
            )
        if scenario in {"read_error", "read_exit"}:
            fault = httpx.ReadError if scenario == "read_error" else SystemExit
            return httpx.Response(200, stream=_FaultStream(fault), request=request)
        message = {"role": "assistant", "content": _ANSWER}
        return httpx.Response(
            200,
            json={"model": _MODEL, "choices": [{"message": message}]},
            request=request,
        )

    return httpx.MockTransport(handler)


def _code(call: Callable[[], object]) -> str:
    try:
        call()
    except ImageContractError as error:
        return error.code
    except BaseException as error:  # recorded by type name only, never by text
        return type(error).__name__
    return "none"


def _direct_request(active, program, context, session) -> ProviderRequest:
    """The exact admitted ports, built without DSPy typed execution."""
    signature = vars(program)["predict"].signature
    ports, cursor = [], 0
    for message in active.formatter.format(signature, [], context.materialized()):
        parts: list[ProviderTextPart | ProviderImagePart] = []
        for part in message.parts:
            if type(part) is LMTextPart:
                parts.append(ProviderTextPart(part.text))
                continue
            item = context.occurrences[cursor]
            cursor += 1
            parts.append(
                ProviderImagePart(
                    item.media_type,
                    item.data,
                    sha(item.data),
                    len(item.data),
                    item.width,
                    item.height,
                    item.occurrence_id,
                )
            )
        ports.append(ProviderPartsMessage(message.role, tuple(parts)))
    return ProviderRequest(session.record["model"], tuple(ports), session)


@worker_entry
def _effects_entry(params):
    row = closed(params, _PARAMS)
    scenario, custody_fd = row["scenario"], row["custody_fd"]
    preparation = ImagePreparation(row["preparation"].encode("ascii"))
    raw = row["admission"].encode("ascii")
    admission = ImageAdmission(raw, digest("admission-v2", parse_json(raw)))
    bound = closed(row["authority"], "caller_expectation_sha256 root_dev root_ino")

    def mirror() -> SyntheticImageAuthority:
        # Worker-local mirror; usable only through the parent's bound handshake.
        return SyntheticImageAuthority(
            raw,
            bound["caller_expectation_sha256"],
            bound["root_dev"],
            bound["root_ino"],
            _used=[False],
        )

    sends: list[list[str]] = []
    logs: list[str] = []
    observation: dict[str, object] = {"scenario": scenario}
    with image_privacy() as active:
        program, context, rederived = _prepare(
            active,
            candidate_fd=row["candidate_fd"],
            input_fd=row["input_fd"],
            input_name="inputs.json",
            model=admission.record["model"],
            use_cot=False,
            limits=admission.record["limits"],
        )
        assert canonical(rederived) == preparation.raw
        session = ImageCustodySession(
            root_fd=custody_fd, admission=admission, authority=mirror(), context=context
        )
        active.session = session
        lm = create_image_lm(session, transport=_transport(scenario, sends))

        def call_program():
            with dspy.context(lm=lm):
                return program(**context.materialized())

        def direct():
            return lm.provider.invoke(
                _direct_request(active, program, context, session)
            )

        def lm_call():
            # A queued typed LM call that bypasses the formatter's plan check.
            signature = vars(program)["predict"].signature
            messages = active.formatter.format(signature, [], context.materialized())
            return lm(request=dspy.LMRequest(model=lm.model, messages=messages))

        def raises(*args, **kwargs):
            raise RuntimeError("synthetic-finalization-fault")

        if scenario == "direct_then_typed":
            typed: list[bool] = []
            forward = DSPyTypedLMAdapter._forward_locked

            def typed_spy(adapter, request):
                typed.append(True)
                return forward(adapter, request)

            with pytest.MonkeyPatch.context() as spy:
                spy.setattr(DSPyTypedLMAdapter, "_forward_locked", typed_spy)
                result = direct()
                observation["typed_calls_after_direct"] = len(typed)
                observation["history_after_direct"] = len(lm.history)
                answer = call_program().answer
                observation["typed_calls_after_program"] = len(typed)
            observation["direct_result"] = (
                type(result) is ProviderResult
                and result.effect_disposition is EffectDisposition.COMPLETED_SUCCESS
                and result.text == _ANSWER
            )
            observation["answer_ok"] = answer == "fixture result"
            observation["third_direct"] = _code(direct)
            observation["third_program"] = _code(call_program)
            observation["third_lm"] = _code(lm_call)
            status = ("completed", None)
        elif scenario == "two_attempts":
            first = call_program().answer
            observation["terminal_1_after_first"] = sha(
                read_record(custody_fd, "terminal-1.json")
            )
            second = call_program().answer
            observation["answers_ok"] = first == second == "fixture result"
            observation["third_program"] = _code(call_program)
            observation["third_lm"] = _code(lm_call)
            binding = publish_image_run(
                session,
                artifact_fd=row["artifact_fd"],
                outputs={"answer": second},
                route="direct",
            )
            session.close_run(binding, outcome="completed")
            status = ("completed", None)
        else:
            assert scenario in {*_UNCERTAIN, "redirect"}
            root = logging.getLogger()
            capture, level = _LogCapture(logs), root.level
            root.addHandler(capture)
            root.setLevel(logging.DEBUG)
            try:
                with pytest.MonkeyPatch.context() as fault:
                    if scenario == "typed_error":
                        fault.setattr(lm, "_typed_response", raises)
                    elif scenario == "finalize_error":
                        fault.setattr(lm, "_finalize_lm_response", raises)
                    observation["first"] = _code(call_program)
            finally:
                root.removeHandler(capture)
                root.setLevel(level)
            terminal = read_record(custody_fd, "terminal-1.json")
            # Queued typed calls, direct calls, a new factory, a reconstructed
            # session and an effect envelope over the same custody root.
            observation["again"] = _code(call_program)
            observation["lm_again"] = _code(lm_call)
            observation["direct"] = _code(direct)
            observation["factory"] = _code(
                lambda: create_image_lm(session, transport=_transport("ok", sends))
            )
            observation["rebuilt"] = _code(
                lambda: ImageCustodySession(
                    root_fd=custody_fd,
                    admission=admission,
                    authority=mirror(),
                    context=context,
                )
            )
            try:  # the receipt's effect projection, or its fixed refusal
                observation["envelope"] = image_effect_envelope(session)[
                    "terminal_effect"
                ]
            except ImageContractError as error:
                observation["envelope"] = error.code
            observation["terminal_unchanged"] = terminal == read_record(
                custody_fd, "terminal-1.json"
            )
            observation["latched"] = [
                lm._indeterminate_latched,
                lm.provider._indeterminate_latched,
                session.poisoned,
            ]
            observation["log_lines"] = len(logs)
            observation["log_leaks"] = [
                index
                for index, line in enumerate(logs)
                if _REDIRECT in line
                or "redirected-elsewhere" in line
                or _REDIRECT_BODY.decode("ascii") in line
            ]
            status = ("failed", parse_json(terminal)["failure_code"])
        observation["sends"] = sends
        commitment = publish(row["spy_fd"], "observation.json", observation)
        return _status(status[0], commitment, status[1])


# ---------------------------------------------------------------------------
# AK6607-S19: an echoing completion is a completed privacy failure, nothing written.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("echo", ["base64", "data_uri", "marker"])
def test_s19_echoing_completion_is_completed_privacy_failure_with_nothing_written(
    admit, echo: str
) -> None:
    run = admit()
    encoded = base64.b64encode(run.pixels).decode("ascii")
    echoed = {
        "base64": encoded,
        "data_uri": f"data:image/png;base64,{encoded}",
        "marker": "<<CUSTOM-TYPE-START-IDENTIFIER>>",
    }[echo]
    with pytest.raises(ImageContractError) as caught:
        _execute(run, f"[[ ## answer ## ]]\n{echoed}\n[[ ## completed ## ]]")
    # Fixed safe metadata reports the privacy failure; no provider text crosses.
    assert caught.value.code == "image_privacy"
    assert str(caught.value) == "image_privacy" and caught.value.__cause__ is None
    custody = run.fds["custody"]
    assert sorted(list_root(custody)) == _SPENT_ROOT
    terminal = _load(custody, "terminal-1.json")
    # An observed completion: never relabelled preflight_rejected or no-effect.
    assert terminal["provider_disposition"] == "completed_failure"
    assert terminal["failure_code"] == "privacy"
    assert terminal["dispatch_count"] == 1 and terminal["observed_model"] == _MODEL
    assert terminal["response_sha256"] is not None
    assert terminal["response_byte_count"] > 0
    assert terminal["result_finalization_completed"] is False
    assert terminal["typed_finalization_completed"] is False
    assert terminal["attempt_id"] == _load(custody, "intent-1.json")["attempt_id"]
    # Exactly the one observed send; no output, Oracle, receipt or closure record.
    assert list_root(run.fds["spy"]) == ["wire-1.json"]
    assert list_root(run.fds["artifacts"]) == []
    for name in list_root(custody):
        if name != "lock":
            raw = read_record(custody, name)
            assert encoded.encode() not in raw and echoed.encode() not in raw
    _assert_spent_root(run)


# ---------------------------------------------------------------------------
# AK6607-S20: identical request bytes, distinct attempt identities, no overwrite.
# ---------------------------------------------------------------------------


def test_s20_identical_requests_get_distinct_attempts_and_reject_duplicates(
    admit,
) -> None:
    run = admit(slots=2, repeat=True)
    result = _effects(run, "two_attempts")
    seen = _observation(run, result)
    assert result == _status("completed", result["commitment_sha256"])
    custody = run.fds["custody"]
    closure_sha = sha(read_record(custody, "closure.json"))
    # Plan exhaustion refuses before the LM; a queued typed call hits the ledger.
    assert seen["answers_ok"] is True and seen["third_lm"] == "image_budget"
    assert seen["third_program"] == "image_admission_invalid"
    # Identical request bytes on the wire: equal digests, exactly two sends.
    assert [path for path, _ in seen["sends"]] == [_ENDPOINT_PATH] * 2
    assert seen["sends"][0][1] == seen["sends"][1][1]
    intents = [_load(custody, f"intent-{n}.json") for n in (1, 2)]
    terminals = [_load(custody, f"terminal-{n}.json") for n in (1, 2)]
    # Fresh provider-issued attempt identity per consumed slot.
    assert intents[0]["attempt_id"] != intents[1]["attempt_id"]
    assert [row["attempt_ordinal"] for row in intents] == [1, 2]
    assert [row["attempt_id"] for row in terminals] == [
        row["attempt_id"] for row in intents
    ]
    assert intents[0]["request_shape_sha256"] == intents[1]["request_shape_sha256"]
    # Repeated identical images: distinct occurrence IDs, equal byte hashes.
    sequence = intents[0]["image_occurrence_sequence"]
    assert len(sequence) == len(set(sequence)) == 2
    hashes = {
        row["occurrence_id"]: row["content_sha256"]
        for row in run.source["source_occurrences"]
    }
    assert hashes[sequence[0]] == hashes[sequence[1]] == sha(run.pixels)
    # The first terminal is immutable across the second attempt.
    assert seen["terminal_1_after_first"] == sha(
        read_record(custody, "terminal-1.json")
    )
    anchor = run.anchor(closure_sha)
    assert verify_image_run(anchor)["status"] == "ok"
    view = _ReadOnlyCustody(
        custody,
        run.admission,
        _ReadOnlySource(run.source),
        digest("manifest-v2", run.manifest),
        read_record(custody, "ready.json"),
    )
    originals = {
        name: read_record(custody, name)
        for name in ("intent-2.json", "terminal-2.json")
    }

    def rewrite(intent_edit: dict, terminal_edit: dict) -> None:
        intent = {**parse_json(originals["intent-2.json"]), **intent_edit}
        _put(custody, "intent-2.json", intent)
        terminal = {
            **parse_json(originals["terminal-2.json"]),
            "attempt_id": intent["attempt_id"],
            "custody_id": intent["custody_id"],
            "intent_sha256": sha(read_record(custody, "intent-2.json")),
            **terminal_edit,
        }
        _put(custody, "terminal-2.json", terminal)

    foreign = str(uuid.uuid4())
    cases = {
        # Control: a self-consistent fresh identity passes the record scan, so the
        # rejections below are the duplicate/foreign rules, not a broken rewrite.
        "fresh": ({"attempt_id": foreign}, {}),
        "duplicate": ({"attempt_id": intents[0]["attempt_id"]}, {}),
        "foreign_terminal": ({}, {"attempt_id": foreign}),
        "foreign_custody": ({"custody_id": foreign}, {}),
    }
    for case, (intent_edit, terminal_edit) in cases.items():
        rewrite(intent_edit, terminal_edit)
        if case == "fresh":
            assert [row["attempt_id"] for row, _ in scan(view, allow_closure=True)] == [
                intents[0]["attempt_id"],
                foreign,
            ]
        else:
            with pytest.raises(ImageContractError, match="^image_custody$"):
                scan(view, allow_closure=True)
        # The caller-held closure binds the issued identities: every case rejects.
        with pytest.raises(ImageContractError, match="^image_custody$"):
            verify_image_run(anchor)
        for name, raw in originals.items():
            _put(custody, name, parse_json(raw))
    assert verify_image_run(anchor)["status"] == "ok"
    # No-replace publication: the first terminal can never be overwritten.
    first = read_record(custody, "terminal-1.json")
    with pytest.raises(ImageContractError, match="^image_durability$"):
        publish(custody, "terminal-1.json", {**terminals[0], "dispatch_count": 0})
    assert read_record(custody, "terminal-1.json") == first


# ---------------------------------------------------------------------------
# AK6607-S21: a redirect is one completed failure, never a second request.
# ---------------------------------------------------------------------------


def test_s21_redirect_is_one_completed_failure_without_location_logging(
    admit,
) -> None:
    run = admit()
    result = _effects(run, "redirect")
    seen = _observation(run, result)
    assert result == _status("failed", result["commitment_sha256"], "response")
    # Exactly one send to the admitted endpoint; the Location was never followed.
    assert [path for path, _ in seen["sends"]] == [_ENDPOINT_PATH]
    assert seen["first"] == "image_finalization"
    custody = run.fds["custody"]
    terminal = _load(custody, "terminal-1.json")
    assert terminal["provider_disposition"] == "completed_failure"
    assert terminal["failure_code"] == "response" and terminal["dispatch_count"] == 1
    # The complete response was classified: digest/length only, never the body.
    assert terminal["response_sha256"] == sha(_REDIRECT_BODY)
    assert terminal["response_byte_count"] == len(_REDIRECT_BODY)
    assert terminal["observed_model"] is None
    # A completed failure consumes the slot without latching an unknown effect.
    assert seen["latched"] == [False, False, False]
    assert seen["again"] == "image_admission_invalid"
    assert seen["lm_again"] == seen["direct"] == "image_spent"
    # The effect projection reports the observed failure, never success/no-effect.
    assert seen["envelope"] == "completed_failure"
    assert seen["rebuilt"] == "image_spent" and seen["terminal_unchanged"] is True
    # DEBUG-level capture of every log record during the call: no URL or body.
    assert seen["log_lines"] >= 1 and seen["log_leaks"] == []
    assert sorted(list_root(custody)) == _SPENT_ROOT
    for name in ("intent-1.json", "terminal-1.json", "ready.json"):
        raw = read_record(custody, name)
        assert b"redirected-elsewhere" not in raw and _REDIRECT_BODY not in raw
    assert list_root(run.fds["artifacts"]) == []
    _assert_spent_root(run)


# ---------------------------------------------------------------------------
# AK6607-S22-E01..E06: an uncertain effect terminalizes custody and latches.
# (E07, absent-terminal reconciliation, belongs to the custody slice.)
# ---------------------------------------------------------------------------

# failure -> whether the complete response was observed before the fault
_UNCERTAIN = {
    "send_error": False,  # E01 send exception
    "read_error": False,  # E02 response read exception
    "send_interrupt": False,  # E03 KeyboardInterrupt during send
    "read_exit": False,  # E04 SystemExit during read
    "typed_error": True,  # E05 unexpected typed construction error
    "finalize_error": True,  # E06 unexpected finalization error
}


@pytest.mark.parametrize("failure", list(_UNCERTAIN))
def test_s22_uncertain_image_effect_terminalizes_and_latches(
    admit, failure: str
) -> None:
    run = admit()
    result = _effects(run, failure)
    seen = _observation(run, result)
    custody = run.fds["custody"]
    terminal = _load(custody, "terminal-1.json")
    intent = _load(custody, "intent-1.json")
    assert result == _status(
        "failed", result["commitment_sha256"], terminal["failure_code"]
    )
    # The same reserved attempt, effect_indeterminate with dispatch_count one.
    assert sorted(list_root(custody)) == _SPENT_ROOT
    assert terminal["attempt_id"] == intent["attempt_id"]
    assert terminal["provider_disposition"] == "effect_indeterminate"
    assert terminal["dispatch_count"] == 1
    assert terminal["failure_code"] in {"io", "interruption", "finalization"}
    assert terminal["finalization_kind"] == "dspy_lm"
    assert terminal["typed_finalization_completed"] is False
    observed = _UNCERTAIN[failure]
    assert terminal["result_finalization_completed"] is observed
    assert (terminal["response_sha256"] is not None) is observed
    # Fixed safe failure code; one send, never retried, no fallback request.
    assert seen["first"] in {"image_finalization", "image_interruption"}
    assert [path for path, _ in seen["sends"]] == [_ENDPOINT_PATH]
    # Provider, typed adapter and session all latch.
    assert seen["latched"] == [True, True, True]
    # Queued typed calls, direct calls, new factories and reconstructed sessions
    # are denied without a send; no effect envelope (score input) is produced.
    assert seen["again"] == "image_admission_invalid"
    assert seen["lm_again"] == seen["direct"] == "image_spent"
    assert seen["factory"] == "image_admission_invalid"
    assert seen["rebuilt"] == seen["envelope"] == "image_spent"
    assert seen["terminal_unchanged"] is True and seen["log_leaks"] == []
    assert list_root(run.fds["artifacts"]) == []
    _assert_spent_root(run)


# ---------------------------------------------------------------------------
# AK6607-S23: projection tampering cannot create no-effect or success evidence.
# ---------------------------------------------------------------------------


def _reseal(anchor: ImageRunAnchor, edits) -> ImageRunAnchor:
    """A producer rewriting its projection AND every hash link it controls."""
    art, custody = anchor.artifact_fd, anchor.custody_fd
    for fd, name, edit in edits:
        _put(fd, name, edit(_load(fd, name)))
    content = _load(art, "image_content_artifacts.json")
    content["artifacts"] = [_entry(art, item["name"]) for item in content["artifacts"]]
    _put(art, "image_content_artifacts.json", content)
    content_sha = sha(read_record(art, "image_content_artifacts.json"))
    for name, key in (
        ("image_oracle_evidence.json", "artifact_manifest_sha256"),
        (_RECEIPT, "content_artifact_manifest_sha256"),
    ):
        _put(art, name, {**_load(art, name), key: content_sha})
    published = _load(art, "image_published_artifacts.json")
    published["artifacts"] = [
        _entry(art, item["name"]) for item in published["artifacts"]
    ]
    _put(art, "image_published_artifacts.json", published)
    closure = _load(custody, "closure.json")
    present = set(list_root(custody))
    closure["terminal_commitments"] = [
        {**item, "terminal_sha256": sha(read_record(custody, name))}
        for item in closure["terminal_commitments"]
        if (name := f"terminal-{item['ordinal']}.json") in present
    ]
    closure["artifact_manifest_sha256"] = sha(
        read_record(art, "image_published_artifacts.json")
    )
    _put(custody, "closure.json", closure)
    return replace(anchor, closure_sha256=sha(read_record(custody, "closure.json")))


def _attempt(edit: Callable[[dict], None]) -> Callable[[dict], dict]:
    def apply(receipt: dict) -> dict:
        edit(receipt["effect_evidence"])
        return receipt

    return apply


def _set(row: dict, **values: object) -> dict:
    row.update(values)
    return row


_TRACES = "image_program_runtime_traces.json"
# tamper -> (root, record, producer edit, fixed refusal)
_TAMPER: dict[str, tuple[str, str, Callable[[dict], dict | None], str]] = {
    "receipt_attempt_id": (
        "artifacts",
        _RECEIPT,
        _attempt(lambda ev: ev["attempts"][0].update(attempt_id=str(uuid.uuid4()))),
        "image_custody",
    ),
    "receipt_terminal_sha256": (
        "artifacts",
        _RECEIPT,
        _attempt(lambda ev: ev["attempts"][0].update(terminal_sha256="0" * 64)),
        "image_custody",
    ),
    "receipt_no_effect_count": (
        "artifacts",
        _RECEIPT,
        _attempt(lambda ev: ev["attempts"][0].update(dispatch_count=0)),
        "image_custody",
    ),
    "receipt_truncated_history": (
        "artifacts",
        _RECEIPT,
        _attempt(lambda ev: ev.update(attempts=[], attempts_truncated=True)),
        "image_custody",
    ),
    "traces_attempt_id": (
        "artifacts",
        _TRACES,
        lambda row: _set(row, attempt_ids=[str(uuid.uuid4())]),
        "image_custody",
    ),
    "custody_unknown_effect": (
        "custody",
        "terminal-1.json",
        # A self-consistent unknown effect: the scan accepts it, success does not.
        lambda row: _set(
            row, provider_disposition="effect_indeterminate", failure_code="io"
        ),
        "image_custody",
    ),
    "custody_missing_terminal": (
        "custody",
        "terminal-1.json",
        lambda row: None,
        "image_spent",
    ),
}


@pytest.mark.parametrize("tamper", list(_TAMPER))
def test_s23_projection_tampering_cannot_create_success_or_no_effect(
    admit, tamper: str
) -> None:
    run = admit()
    anchor = _execute(run, _ANSWER)
    assert verify_image_run(anchor)["status"] == "ok"
    # The independent synthetic send observation agrees with retained custody.
    wire = _load(run.fds["spy"], "wire-1.json")
    terminal = _load(run.fds["custody"], "terminal-1.json")
    receipt = _load(run.fds["artifacts"], _RECEIPT)["effect_evidence"]
    assert list_root(run.fds["spy"]) == ["wire-1.json"]
    assert wire["send_ordinal"] == terminal["dispatch_count"] == 1
    assert wire["image_sha256"] == [sha(run.pixels)]
    assert receipt["attempts"][0]["validated_image_count"] == len(wire["image_sha256"])
    assert receipt["attempt_total"] == 1 and receipt["attempts_truncated"] is False
    # Control: resealing every hash link without an edit still verifies, so each
    # rejection below is the retained semantic check, not a stale digest.
    anchor = _reseal(anchor, [])
    assert verify_image_run(anchor)["status"] == "ok"
    where, name, edit, code = _TAMPER[tamper]
    forged = _reseal(anchor, [(run.fds[where], name, edit)])
    with pytest.raises(ImageContractError, match=f"^{code}$"):
        verify_image_run(forged)


# ---------------------------------------------------------------------------
# AK6607-S45: direct provider finalization is distinct from DSPy finalization.
# ---------------------------------------------------------------------------


def test_s45_direct_provider_invoke_records_direct_provider_finalization(
    admit,
) -> None:
    run = admit(slots=2)
    result = _effects(run, "direct_then_typed")
    seen = _observation(run, result)
    assert result == _status("completed", result["commitment_sha256"])
    assert seen["direct_result"] is True and seen["answer_ok"] is True
    # The direct invoke ran no DSPy typed call and left no LM history.
    assert seen["typed_calls_after_direct"] == 0
    assert seen["history_after_direct"] == 0
    assert seen["typed_calls_after_program"] == 1
    custody = run.fds["custody"]
    direct, typed = (_load(custody, f"terminal-{n}.json") for n in (1, 2))
    assert direct["finalization_kind"] == "direct_provider"
    assert direct["provider_disposition"] == "completed_success"
    assert direct["result_finalization_completed"] is True
    assert direct["typed_finalization_completed"] is False
    assert direct["dispatch_count"] == 1 and direct["failure_code"] is None
    assert typed["finalization_kind"] == "dspy_lm"
    assert typed["typed_finalization_completed"] is True
    # One consumed ledger: contiguous ordinals, distinct identities, no third slot.
    intents = [_load(custody, f"intent-{n}.json") for n in (1, 2)]
    assert [row["attempt_ordinal"] for row in intents] == [1, 2]
    assert intents[0]["attempt_id"] != intents[1]["attempt_id"]
    assert seen["third_direct"] == seen["third_lm"] == "image_budget"
    assert seen["third_program"] == "image_admission_invalid"
    assert [path for path, _ in seen["sends"]] == [_ENDPOINT_PATH] * 2
    assert "closure.json" not in list_root(custody)
    _assert_spent_root(run)
