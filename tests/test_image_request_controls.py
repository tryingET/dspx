# summary: "AK6918 admission-bound image request controls: the v3 closed schema, the wire body and send-time drift."
# read_when:
#   - "Changing image admission request controls, the image request body or its send-time checks."
"""AK6918 (owner decisions AK14879/AK14880): bounded output, thinking off.

Every image admission (`dspx-image-admission-v3`, synthetic and live) carries closed,
owner-bound request controls: `max_output_tokens` (1..8192) and `thinking: "off"`. The
image request body sends exactly `max_tokens` and the vLLM chat-template switch
`chat_template_kwargs: {"enable_thinking": false}` from the admission, never from a
caller. Synthetic only: the worker builds the exact `httpx.MockTransport`.
"""

from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import dspy
from dspy.core.types import LMConfig
import pytest

import test_image_admission as admission_tests
import test_image_effects as effects
from dspx.image_admission import (
    ImageAdmission,
    SyntheticImageAuthority,
    canonical,
    closed,
    digest,
    parse_json,
    sha,
    validate_admission,
)
from dspx.image_artifacts import verify_image_run
from dspx.image_custody import ImageCustodySession, parent_initializer
from dspx.image_effects import fixture_transport
from dspx.image_execution import ImageExecutionRequest, ImagePreparation, _prepare
from dspx.image_privacy import image_privacy, runtime_identity
from dspx.image_records import list_root, publish, read_record
from dspx.image_supervision import supervise_image_worker
from dspx.image_worker import worker_entry
from dspx.provider_registry import create_image_lm
from test_image_admission import _World, _bytes, _identity, _no_effects, _refused
from test_image_live_admission import _held, _live
from test_image_execution import _ANSWER, _admitted_request, _execute_route
from test_image_execution import _prepare_route, _records, _route_fds, _shipped_inputs

_HERE = "test_image_request_controls"
_INVALID = "image_admission_invalid"
_CEILING = 8192
_SWITCH_OFF = {"enable_thinking": False}
world, admit = admission_tests.world, effects.admit  # shared prepared fixtures


def _controls(tokens: object = 256, thinking: object = "off") -> dict[str, object]:
    return {"max_output_tokens": tokens, "thinking": thinking}


# ---------------------------------------------------------------------------
# (a) The v3 admission: closed request controls, required in every mode.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tokens", [1, 512, _CEILING])
def test_v3_admission_accepts_owner_bound_request_controls(
    world: _World, tokens: int
) -> None:
    """Given an owner admission v3 whose controls are an output cap 1 <= N <= 8192 and
    thinking "off"; When the trusted parent validates it; Then it is admitted and its
    commitment (domain admission-v3) covers the controls."""
    record = {**world.record, "request_controls": _controls(tokens)}
    assert record["schema_version"] == "dspx-image-admission-v3"
    raw = canonical(record)
    admission = world.validate(raw, world.held(raw))
    assert admission.record["request_controls"] == _controls(tokens)
    # ubs:ignore -- public sha256 admission commitment, not a secret
    assert admission.sha256 == digest("admission-v3", record)
    other = canonical({**record, "request_controls": _controls(tokens % _CEILING + 1)})
    # ubs:ignore -- public sha256 admission commitment, not a secret
    assert world.validate(other, world.held(other)).sha256 != admission.sha256


_OMIT = object()
# case -> (request_controls value, or _OMIT for an absent key; expected fixed code)
_CONTROL_REFUSALS: dict[str, tuple[object, str]] = {
    "section_omitted": (_OMIT, _INVALID),
    "section_null": (None, _INVALID),
    "section_list": ([256, "off"], _INVALID),
    "section_string": ("off", _INVALID),
    "unknown_key": ({**_controls(), "temperature": 0}, _INVALID),
    "cap_omitted": ({"thinking": "off"}, _INVALID),
    "thinking_omitted": ({"max_output_tokens": 256}, _INVALID),
    "cap_zero": (_controls(0), _INVALID),
    "cap_negative": (_controls(-1), _INVALID),
    "cap_above_ceiling": (_controls(_CEILING + 1), _INVALID),
    "cap_boolean": (_controls(True), _INVALID),
    "cap_string": (_controls("256"), _INVALID),
    "cap_null": (_controls(None), _INVALID),
    "cap_float": (_controls(256.0), "image_input_invalid"),
    "cap_fraction": (_controls(255.5), "image_input_invalid"),
    "thinking_on": (_controls(thinking="on"), _INVALID),
    "thinking_upper": (_controls(thinking="OFF"), _INVALID),
    "thinking_false": (_controls(thinking=False), _INVALID),
    "thinking_true": (_controls(thinking=True), _INVALID),
    "thinking_null": (_controls(thinking=None), _INVALID),
    "thinking_zero": (_controls(thinking=0), _INVALID),
    "thinking_empty": (_controls(thinking=""), _INVALID),
    "thinking_switch": (_controls(thinking=_SWITCH_OFF), _INVALID),
}


@pytest.mark.parametrize("case", list(_CONTROL_REFUSALS))
def test_v3_admission_refuses_every_invalid_request_control(
    world: _World, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """Given a v3 admission whose request controls are <case>; When the parent
    validates it, even with an authority re-minted over those bytes, or the shipped
    entry is called; Then it refuses with one fixed code before worker, custody,
    provider or send."""
    value, code = _CONTROL_REFUSALS[case]
    record = copy.deepcopy(world.record)
    if value is _OMIT:
        del record["request_controls"]
    else:
        record["request_controls"] = value
    raw = _bytes(record)  # floats survive into the bytes
    _refused(_INVALID, lambda: world.validate(raw, world.held()))
    reminted = world.held(raw)
    _refused(code, lambda: world.validate(raw, reminted))
    entries = _no_effects(monkeypatch)
    _refused(code, lambda: world.shipped(_identity(raw), reminted))
    world.done(entries)


def test_v3_controls_are_required_in_live_mode_and_v2_is_refused(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a live admission without controls, or a v2-labelled admission with valid
    controls; When the parent validates; Then both refuse with the fixed code."""
    live = _live(world)  # confirmed over its own bytes
    assert world.validate(canonical(live), _held(world, live))
    del live["request_controls"]
    raw = canonical(live)
    _refused(_INVALID, lambda: world.validate(raw, _held(world, live)))
    labelled = canonical({**world.record, "schema_version": "dspx-image-admission-v2"})
    _refused(_INVALID, lambda: world.validate(labelled, world.held(labelled)))
    entries = _no_effects(monkeypatch)
    _refused(_INVALID, lambda: world.shipped(_identity(labelled), world.held(labelled)))
    world.done(entries)


# ---------------------------------------------------------------------------
# (b) The shipped synthetic route sends exactly the admitted controls.
# ---------------------------------------------------------------------------


_V2 = "dspx-image-admission-v2"


def _worker_statuses(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """The statuses the shipped parent entries receive from their clean workers."""
    from dspx import image_execution

    seen: list[dict[str, Any]] = []
    real = image_execution.supervise_image_worker

    def spy(*args: Any, **kwargs: Any) -> dict[str, object]:
        result = real(*args, **kwargs)
        seen.append(result)
        return result

    monkeypatch.setattr(image_execution, "supervise_image_worker", spy)
    return seen


def _with_controls(
    request: ImageExecutionRequest, prepared: ImagePreparation, tokens: int
) -> ImageExecutionRequest:
    """The same caller-held admission with other owner-bound controls, re-admitted."""
    record = {**request.admission.record, "request_controls": _controls(tokens)}
    raw = canonical(record)
    held = request.authority
    assert type(held) is SyntheticImageAuthority
    authority = SyntheticImageAuthority(
        raw, held.caller_expectation_sha256, held.root_dev, held.root_ino
    )
    admission = validate_admission(
        raw,
        source=parse_json(prepared.raw)["source"],
        authority=authority,
        runtime_identity_sha256=runtime_identity(),
    )
    return replace(request, admission=admission, authority=authority)


@pytest.mark.parametrize(("route", "tokens"), [("direct", 1), ("episode", _CEILING)])
def test_synthetic_worker_route_sends_the_admitted_output_cap_and_thinking_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str, tokens: int
) -> None:
    """Given a synthetic admission with max_output_tokens N and thinking off; When the
    shipped route runs in the clean worker; Then the one MockTransport send carries
    max_tokens N and enable_thinking false, and the run verifies."""
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    _shipped_inputs(tmp_path, media="image/png")
    statuses = _worker_statuses(monkeypatch)
    with _route_fds(tmp_path) as fds:
        prepared = _prepare_route(fds, use_cot=False)
        request = _admitted_request(fds, prepared, route=route, completion=_ANSWER)
        request = _with_controls(request, prepared, tokens)
        anchor = _execute_route(tmp_path, request, route=route)
        assert verify_image_run(anchor)["status"] == "ok"
        (wire,) = _records(fds["wire"])
        # AK6918 review: read-only custody names a non-v3 admission precisely.
        relabelled = {**request.admission.record, "schema_version": _V2}
        stale = replace(anchor, admission_raw=canonical(relabelled))
        _refused(_INVALID, lambda: verify_image_run(stale))
    # AK6918 review: preparation is mode-free (no fixture, no live authority); the
    # synthetic run reports fixture evidence only.
    assert [
        (row["status"], row["fixture_evidence"], row["live_authorized"])
        for row in statuses
    ] == [
        ("prepared", False, False),
        ("completed", True, False),
    ]
    assert wire["schema_version"] == "dspx-image-wire-observation-v2"
    assert wire["send_ordinal"] == 1 and len(wire["request_sha256"]) == 64
    # Every body key besides model and messages: exactly the two admitted controls.
    assert wire["controls"] == {
        "max_tokens": tokens,
        "chat_template_kwargs": _SWITCH_OFF,
    }
    assert type(wire["controls"]["max_tokens"]) is int
    assert wire["controls"]["chat_template_kwargs"]["enable_thinking"] is False


# ---------------------------------------------------------------------------
# (d) Send-time drift: a body whose controls differ from the admission, or a
# caller-supplied control, is refused before send; the admitted call then sends.
# ---------------------------------------------------------------------------


def _drift(body: bytes, scenario: str) -> bytes:
    """The controlled wire bytes with one drift; the duplicate keeps the last value."""
    if scenario == "drift_duplicate_key":
        return b'{"max_tokens":1,' + body[1:]
    wire = json.loads(body)
    if scenario == "drift_max_tokens":
        wire["max_tokens"] += 1
    elif scenario == "drift_cap_boolean":
        wire["max_tokens"] = True
    elif scenario == "drift_thinking_on":
        wire["chat_template_kwargs"] = {"enable_thinking": True}
    elif scenario == "drift_thinking_zero":
        wire["chat_template_kwargs"] = {"enable_thinking": 0}
    elif scenario == "drift_switch_missing":
        del wire["chat_template_kwargs"]
    elif scenario == "drift_cap_missing":
        del wire["max_tokens"]
    else:
        assert scenario == "drift_extra_control"
        wire["temperature"] = 0
    return json.dumps(wire, ensure_ascii=False, separators=(",", ":")).encode()


_DRIFTS = (
    "drift_max_tokens",
    "drift_cap_boolean",
    "drift_cap_missing",
    "drift_thinking_on",
    "drift_thinking_zero",
    "drift_switch_missing",
    "drift_extra_control",
    "drift_duplicate_key",
)
_CALLERS = (
    "caller_body_max_tokens",
    "caller_config_max_tokens",
    "caller_config_thinking",
    "caller_kwargs_max_tokens",
)
_PARAMS = "candidate_fd input_fd custody_fd spy_fd report_fd preparation admission expectation"


@worker_entry
def _drift_entry(params: dict[str, Any]) -> dict[str, object]:
    from dspx import image_effects

    row = closed(params, _PARAMS)
    preparation = ImagePreparation(row["preparation"].encode("ascii"))
    raw = row["admission"].encode("ascii")
    admission = ImageAdmission(raw, digest("admission-v3", parse_json(raw)))
    record = admission.record
    root = (record["custody"]["root_dev"], record["custody"]["root_ino"])
    held = SyntheticImageAuthority(raw, row["expectation"], *root, _used=[False])
    spy_fd, custody_fd = row["spy_fd"], row["custody_fd"]
    probes: dict[str, dict[str, object]] = {}
    real_body, real_payload = image_effects.controlled_body, image_effects.image_payload

    def probe(name: str, call) -> None:
        sends = len(list_root(spy_fd))
        try:
            call()
            code = None
        except Exception as error:
            code = getattr(error, "code", "unexpected:" + type(error).__name__)
        probes[name] = {
            "code": code,
            "sends": len(list_root(spy_fd)) - sends,
            "intents": [n for n in list_root(custody_fd) if n.startswith("intent")],
        }

    with image_privacy() as active:
        program, context, rederived = _prepare(
            active,
            candidate_fd=row["candidate_fd"],
            input_fd=row["input_fd"],
            input_name="inputs.json",
            model=record["model"],
            use_cot=False,
            limits=record["limits"],
        )
        assert canonical(rederived) == preparation.raw
        session = ImageCustodySession(
            root_fd=custody_fd, admission=admission, authority=held, context=context
        )
        active.session = session
        fixture = {"completion": effects._ANSWER, "observation_fd": spy_fd}
        model = record["model"]
        lm = create_image_lm(session, transport=fixture_transport(fixture, model))
        signature = vars(program)["predict"].signature

        def run() -> None:
            with dspy.context(lm=lm):
                program(**context.materialized())

        def typed(**config: Any):
            messages = active.formatter.format(signature, [], context.materialized())
            request = dspy.LMRequest(
                model=model, messages=messages, config=LMConfig(**config)
            )
            return lambda: lm(request=request)

        with pytest.MonkeyPatch.context() as patch:
            for scenario in _DRIFTS:
                patch.setattr(
                    image_effects,
                    "controlled_body",
                    lambda body, admitted, s=scenario: _drift(
                        real_body(body, admitted), s
                    ),
                )
                probe(scenario, run)
            patch.setattr(image_effects, "controlled_body", real_body)

            def caller_payload(request, bound):
                body, shape, sequence = real_payload(request, bound)
                return {**body, "max_tokens": 99}, shape, sequence

            patch.setattr(image_effects, "image_payload", caller_payload)
            probe("caller_body_max_tokens", run)
        probe("caller_config_max_tokens", typed(max_tokens=99))
        thinking = {"chat_template_kwargs": {"enable_thinking": True}}
        probe("caller_config_thinking", typed(extensions=thinking))
        messages = active.formatter.format(signature, [], context.materialized())
        baseline = dspy.LMRequest(model=model, messages=messages)
        probe("caller_kwargs_max_tokens", lambda: lm(request=baseline, max_tokens=99))
        probe("control", run)
        report = {"probes": probes, "poisoned": session.poisoned}
        commitment = publish(row["report_fd"], "report.json", report)
    return effects._status("completed", commitment)


def test_send_time_drift_of_request_controls_is_refused_before_send(admit) -> None:
    """Given a synthetic admission with max_output_tokens 256 and thinking off; When the
    wire body's controls drift from it (changed, missing, boolean, extra, duplicated)
    or a caller supplies max_tokens or a thinking switch; Then each call is refused
    with image_admission_invalid before reservation or send, and the admitted call
    then sends exactly the admitted controls once."""
    run = admit()
    report_dir = run.fds["artifacts"]
    initialize = parent_initializer(
        run.fds["custody"],
        run.authority,
        run.admission,
        source_sha256=run.admission.record["source_package_sha256"],
        manifest_sha256=digest("manifest-v2", run.manifest),
    )
    result = supervise_image_worker(
        f"{_HERE}:_drift_entry",
        {
            "candidate_fd": run.fds["candidate"],
            "input_fd": run.fds["inputs"],
            "custody_fd": run.fds["custody"],
            "spy_fd": run.fds["spy"],
            "report_fd": report_dir,
            "preparation": run.prepared.raw.decode("ascii"),
            "admission": run.admission.raw.decode("ascii"),
            "expectation": run.authority.caller_expectation_sha256,
        },
        fds=tuple(
            run.fds[name]
            for name in ("candidate", "inputs", "custody", "spy", "artifacts")
        ),
        wall_ms=30_000,
        parent_action=initialize,
    )
    raw = read_record(report_dir, "report.json")
    assert result == effects._status("completed", sha(raw))
    report = parse_json(raw)
    probes = report["probes"]
    refused = {"code": _INVALID, "sends": 0, "intents": []}
    assert probes == {
        **{name: refused for name in (*_DRIFTS, *_CALLERS)},
        "control": {"code": None, "sends": 1, "intents": ["intent-1.json"]},
    }
    assert report["poisoned"] is False
    assert sorted(list_root(run.fds["custody"])) == [
        "intent-1.json",
        "lock",
        "ready.json",
        "terminal-1.json",
    ]
    terminal = parse_json(read_record(run.fds["custody"], "terminal-1.json"))
    assert terminal["provider_disposition"] == "completed_success"
    (wire,) = [
        parse_json(read_record(run.fds["spy"], n)) for n in list_root(run.fds["spy"])
    ]
    assert wire["controls"] == {"max_tokens": 256, "chat_template_kwargs": _SWITCH_OFF}
