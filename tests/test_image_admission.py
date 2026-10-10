# summary: "Canonical admission bytes are immutable identity, not caller-selected digests; AK6756 admission red-matrix rows."
"""Admission rows of the Revision2 red matrix (AK6756; scenarios: AK6607 red-cases).

Parent rows run the real `validate_admission` and shipped parent entry; send-time drift
runs in the guarded clean worker, which publishes only fixed codes and counts.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from dataclasses import dataclass, fields
from typing import Any

import dspy
import httpx
import pytest

from dspx import image_execution, provider_registry
from dspx.image_admission import (
    CEILINGS,
    ImageAdmission,
    ImageContractError,
    LiveImageAuthority,
    SyntheticImageAuthority,
    canonical,
    digest,
    parse_json,
    require,
    sha,
    validate_admission,
    validate_source,
)
from dspx.image_custody import ImageCustodySession, parent_initializer
from dspx.image_effects import SyntheticTransportFixture, fixture_transport
from dspx.image_execution import (
    ImageExecutionRequest,
    ImagePreparation,
    _prepare,
    execute_image_program,
    prepare_image_execution,
)
from dspx.image_privacy import image_privacy, runtime_identity
from dspx.image_records import list_root, publish, read_record
from dspx.image_supervision import supervise_image_worker
from dspx.image_worker import worker_entry
from dspx.openai_compatible_provider import OpenAICompatibleProvider
from dspx.services import program_runtime_episode
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.stub_provider import StubProvider

_HERE = "test_image_admission"
_MODEL = "synthetic-vision-fixture"
_OTHER = "other-vision-fixture"
_ENDPOINT = "http://127.0.0.1:8000/v1"
_DRIFT_URL = "http://127.0.0.1:8001/v1"
_EXPECT = "3" * 64
_INVALID = "image_admission_invalid"
_ANSWER = "[[ ## answer ## ]]\nfixture result\n[[ ## completed ## ]]"
_GRANT = (6610, "ak://evidence/13666", "5" * 64)  # plausible, never authenticated
_APPROVAL = dict(
    zip(
        ("owning_ak_task", "operator_evidence_ref", "parent_confirmation_sha256"),
        _GRANT,
        strict=True,
    )
)


def test_admission_record_is_a_detached_view():
    raw = canonical({"limits": {"max_source_images": 1}})
    admission = ImageAdmission(
        raw, digest("admission-v2", {"limits": {"max_source_images": 1}})
    )
    admission.record["limits"]["max_source_images"] = 6
    assert admission.record["limits"]["max_source_images"] == 1


@pytest.mark.parametrize("raw", [b'{"x":1}', b'{ "x":1}', b'{"x":1,"x":2}', b"{}"])
def test_admission_rejects_forged_or_noncanonical_identity(raw):
    with pytest.raises(ImageContractError):
        ImageAdmission(raw, "0" * 64)


def test_admission_rejects_noncanonical_bytes_with_matching_semantic_digest():
    with pytest.raises(ImageContractError):
        ImageAdmission(b'{ "x":1}', digest("admission-v2", {"x": 1}))


def _refused(code: str, call) -> None:
    """Fixed public code only: no input repr, chained cause or formatted value."""
    with pytest.raises(ImageContractError) as caught:
        call()
    error = caught.value
    assert type(error) is ImageContractError
    assert (error.code, str(error), error.args) == (code, code, (code,))
    assert error.__cause__ is None and error.__suppress_context__


def _bytes(record: object) -> bytes:
    """Canonical layout without the integer-only guard, so laundered floats survive."""
    return json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _identity(raw: bytes) -> ImageAdmission:
    return ImageAdmission(raw, hashlib.sha256(b"admission-v2\0" + raw).hexdigest())


def _record(
    source: dict[str, Any],
    *,
    root: tuple[int, int],
    plan: list[dict[str, Any]],
    expectation: str = _EXPECT,
    limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    now = time.time_ns() // 1_000_000
    return {
        "schema_version": "dspx-image-admission-v2",
        "mode": "synthetic",
        "provider_kind": "openai-compatible",
        "model": _MODEL,
        "canonical_base_endpoint": _ENDPOINT,
        "source_package_sha256": digest("source-v1", source),
        "candidate_manifest_sha256": source["candidate_manifest_sha256"],
        "runtime_identity_sha256": runtime_identity(),
        "decoder_profile_sha256": source["decoder_profile_sha256"],
        "request_plan": plan,
        "limits": {**CEILINGS, "total_dispatch_allowance": len(plan), **(limits or {})},
        "deadlines": {
            "not_before_utc_ms": now - 1000,
            "expires_utc_ms": now + 60_000,
            "total_wall_ms": 30_000,
            "per_request_io_timeout_ms": 30_000,
        },
        "custody": {
            "custody_id": str(uuid.uuid4()),
            "caller_run_id": str(uuid.uuid4()),
            "caller_binding_sha256": "2" * 64,
            "root_dev": root[0],
            "root_ino": root[1],
            "caller_expectation_sha256": expectation,
        },
        "approval_binding": dict.fromkeys(_APPROVAL),
    }


def _no_effects(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Parent spies: worker spawn, custody init, provider/fallback/probe, client, send."""
    entries: list[str] = []

    def forbidden(name: str):
        def deny(*args, **kwargs):
            entries.append(name)
            raise AssertionError(f"admission refusal crossed {name}")

        return deny

    for owner, names in (
        (image_execution, ("supervise_image_worker", "parent_initializer")),
        (
            provider_registry,
            ("create", "create_configured", "create_from_env", "create_image_lm"),
        ),
        (program_runtime_episode, ("_configure_provider",)),
        (OpenAICompatibleProvider, ("__init__", "invoke")),
        (StubProvider, ("invoke",)),
        (httpx.Client, ("__init__", "send")),
        (subprocess, ("Popen",)),
    ):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden(name))
    return entries


def _source(count: int = 2) -> dict[str, Any]:
    names = ("candidate_manifest", "candidate_source", "raw_input_file", "input_shape")
    row = {"field_slot": 0, "media_type": "image/png", "byte_count": 96}
    return {
        "schema_version": "dspx-image-source-package-v2",
        **{f"{name}_sha256": char * 64 for name, char in zip(names, "abcd")},
        "decoder_profile_sha256": "e" * 64,
        "source_occurrences": [
            {
                **row,
                "occurrence_id": f"s{index:06d}",
                "list_ordinal": 2 * index - 1,
                "content_sha256": sha(b"synthetic-%d" % index),
                "width": 4,
                "height": 3,
            }
            for index in range(1, count + 1)
        ],
        "plain_text_slots": [
            {"field_slot": 0, "text_sha256": "f" * 64, "char_count": 1}
        ],
    }


def _plan(source: dict[str, Any]) -> list[dict[str, Any]]:
    sequence = [row["occurrence_id"] for row in source["source_occurrences"]]
    return [
        {
            "plan_ordinal": 1,
            "predictor_slot": 0,
            "request_shape_sha256": "4" * 64,
            "image_occurrence_sequence": sequence,
        }
    ]


def _preparation(source: dict[str, Any], plan: list[dict[str, Any]]):
    markers = [
        {"occurrence_id": row["occurrence_id"], "marker_sha256": "6" * 64}
        for row in source["source_occurrences"]
    ]
    record = {
        "schema_version": "dspx-image-preparation-v1",
        "source": source,
        "markers": markers,
        "plan": plan,
        "model": _MODEL,
        "use_cot": False,
        "runtime_identity_sha256": runtime_identity(),
        "output_slots": 1,
    }
    return ImagePreparation(canonical(record))


def _execution(fds: dict[str, int], preparation, *, wire: int | None = None):
    """Held fds and preparation for the shipped parent entry (no admission yet)."""
    return {
        "candidate_fd": fds["candidate"],
        "input_fd": fds["inputs"],
        "input_name": "inputs.json",
        "artifact_fd": fds["artifacts"],
        "custody_fd": fds["custody"],
        "preparation": preparation,
        "fixture": SyntheticTransportFixture(_ANSWER, observation_fd=wire),
    }


@dataclass
class _World:
    tmp: Path
    fds: dict[str, int]
    root: tuple[int, int]
    source: dict[str, Any]
    record: dict[str, Any]

    @property
    def raw(self) -> bytes:
        return canonical(self.record)

    def held(self, raw: bytes | None = None) -> SyntheticImageAuthority:
        """The trusted parent's independently expected bytes and bindings."""
        return SyntheticImageAuthority(
            self.raw if raw is None else raw, _EXPECT, *self.root
        )

    def validate(self, raw: bytes, authority, source=None) -> ImageAdmission:
        return validate_admission(
            raw,
            source=self.source if source is None else source,
            authority=authority,
            runtime_identity_sha256=runtime_identity(),
        )

    def kwargs(self, preparation=None) -> dict[str, Any]:
        plan = self.record["request_plan"]
        return _execution(self.fds, preparation or _preparation(self.source, plan))

    def shipped(self, admission, authority, *, preparation=None, route="direct"):
        return execute_image_program(
            **self.kwargs(preparation),
            admission=admission,
            authority=authority,
            route=route,
        )

    def done(self, entries: list[str]) -> None:
        assert entries == [], "a refused admission crossed a spied effect boundary"
        assert not list_root(self.fds["custody"]) and not list_root(
            self.fds["artifacts"]
        ), "a refused admission wrote custody or artifact state"


@pytest.fixture
def world(tmp_path: Path):
    fds: dict[str, int] = {}
    try:
        for name in ("candidate", "inputs", "artifacts", "custody"):
            (tmp_path / name).mkdir(mode=0o700)
            fds[name] = os.open(tmp_path / name, os.O_RDONLY | os.O_DIRECTORY)
        stat = os.fstat(fds["custody"])
        root = (stat.st_dev, stat.st_ino)
        source = _source()
        built = _World(
            tmp_path, fds, root, source, _record(source, root=root, plan=_plan(source))
        )
        built.validate(built.raw, built.held())  # the unaltered admission is valid
        yield built
    finally:
        for fd in fds.values():
            os.close(fd)


_S27 = {  # case: (bound path, laundered alterations); plus omit/unknown/bool/float
    "AK6607-S27-E01": ("source_package_sha256", ("hash",)),
    "AK6607-S27-E02": ("request_plan", ("shape", "extra_request")),
    "AK6607-S27-E03": (
        "request_plan.0.image_occurrence_sequence",
        ("reordered", "repeated", "dropped"),
    ),
    "AK6607-S27-E04": ("limits.max_response_bytes", ("above_ceiling", "zero")),
    "AK6607-S27-E05": (
        "limits.max_output_artifact_bytes",
        ("above_ceiling", "negative"),
    ),
    "AK6607-S27-E06": (
        "limits.total_dispatch_allowance",
        ("beyond_plan", "above_ceiling"),
    ),
    "AK6607-S27-E07": ("deadlines.not_before_utc_ms", ("future", "after_expiry")),
    "AK6607-S27-E08": ("deadlines.expires_utc_ms", ("expired", "inverted")),
    "AK6607-S27-E09": (
        "deadlines.total_wall_ms",
        ("above_ceiling", "below_request_io"),
    ),
    "AK6607-S27-E10": ("custody.caller_expectation_sha256", ("hash",)),
    "AK6607-S27-E11": ("custody.root_ino", ("other_inode",)),
    "AK6607-S27-E12": ("runtime_identity_sha256", ("hash",)),
    "AK6607-S27-E13": ("decoder_profile_sha256", ("hash",)),
}
_LAUNDERING = ("omit", "unknown_key", "boolean", "noninteger")
# Plan alterations that stay internally consistent are rejected by the binding to the
# independently held preparation (the shipped parent entry), not by the bare record.
_PREPARATION_BOUND = {("AK6607-S27-E02", "shape"), ("AK6607-S27-E03", "repeated")}


def _laundered(record: dict[str, Any], key: str, label: str) -> object:
    plan, times = record["request_plan"], record["deadlines"]
    return {
        "hash": "9" * 64,
        "shape": [{**plan[0], "request_shape_sha256": "5" * 64}],
        "extra_request": [*plan, {**plan[0], "plan_ordinal": 2}],
        "reordered": ["s000002", "s000001"],
        "repeated": ["s000001", "s000001", "s000002"],
        "dropped": ["s000001"],
        "above_ceiling": CEILINGS.get(key, 180_000) + 1,
        "zero": 0,
        "negative": -1,
        "beyond_plan": 2,
        "future": times["expires_utc_ms"] - 1,
        "after_expiry": times["expires_utc_ms"] + 1,
        "expired": times["not_before_utc_ms"] + 1,
        "inverted": times["not_before_utc_ms"],
        "below_request_io": 29_999,
        "other_inode": record["custody"]["root_ino"] + 1,
    }[label]


def _holder(record: dict[str, Any], path: str) -> tuple[Any, Any]:
    parts: list[Any] = [int(p) if p.isdigit() else p for p in path.split(".")]
    holder: Any = record
    for part in parts[:-1]:
        holder = holder[part]
    return holder, parts[-1]


def _put(record: dict[str, Any], path: str, value: object) -> dict[str, Any]:
    altered = copy.deepcopy(record)
    holder, key = _holder(altered, path)
    holder[key] = value
    return altered


def _mutated(record: dict[str, Any], case: str, mutation: str) -> dict[str, Any]:
    mutated = copy.deepcopy(record)
    holder, key = _holder(mutated, _S27[case][0])
    if mutation == "omit":
        del holder[key]
    elif mutation == "unknown_key" and key == "image_occurrence_sequence":
        holder[key].append("s999999")
    elif mutation == "unknown_key":
        (holder[key][0] if key == "request_plan" else holder)["unexpected_bound"] = 1
    elif mutation == "boolean":
        holder[key] = True
    elif mutation == "noninteger":
        holder[key] = holder[key] + 0.5 if type(holder[key]) is int else 1.5
    else:
        holder[key] = _laundered(record, key, mutation)
    return mutated


@pytest.mark.parametrize(
    ("case", "mutation"),
    [
        (case, name)
        for case, (_, alters) in _S27.items()
        for name in alters + _LAUNDERING
    ],
)
def test_s27_closed_admission_rejects_altered_or_omitted_bound(
    world: _World, monkeypatch: pytest.MonkeyPatch, case: str, mutation: str
):
    """AK6607-S27: Given admission-v2 and held caller expectations; When a bound is
    altered or omitted; Then admission rejects before provider construction and send."""
    raw = _bytes(_mutated(world.record, case, mutation))
    assert raw != world.raw
    code = "image_input_invalid" if mutation == "noninteger" else _INVALID
    # The trusted parent still holds the exact original bytes.
    _refused(_INVALID, lambda: world.validate(raw, world.held()))
    # Even a parent object minted over the altered bytes keeps the independently held
    # caller expectation, root identity, runtime identity and source commitments.
    reminted = world.held(raw)
    if (case, mutation) not in _PREPARATION_BOUND:
        _refused(code, lambda: world.validate(raw, reminted))
    entries = _no_effects(monkeypatch)
    _refused(code, lambda: world.shipped(_identity(raw), reminted))
    world.done(entries)


@pytest.mark.parametrize(
    "flag", ["live", "live_without_approval", "synthetic_with_approval", "authority"]
)
def test_s28_e05_synthetic_to_live_flag_is_refused_before_provider_factory(
    world: _World, monkeypatch: pytest.MonkeyPatch, flag: str
):
    """AK6607-S28-E05 (parent half): a live flag never rides a synthetic authority."""
    record = copy.deepcopy(world.record)
    if flag != "authority":
        record["mode"] = "synthetic" if flag == "synthetic_with_approval" else "live"
        if flag != "live_without_approval":
            record["approval_binding"] = dict(_APPROVAL)
    raw = canonical(record)
    authority = (
        LiveImageAuthority(raw, _EXPECT, *world.root, *_GRANT)
        if flag == "authority"
        else world.held(raw)
    )
    _refused(_INVALID, lambda: world.validate(raw, authority))
    entries = _no_effects(monkeypatch)
    _refused(_INVALID, lambda: world.shipped(_identity(raw), authority))
    world.done(entries)


def test_s02_copied_live_admission_file_is_not_operator_authority(
    world: _World, monkeypatch: pytest.MonkeyPatch
):
    """AK6607-S02: a schema-valid copied live admission never authorizes execution."""
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    monkeypatch.setenv("DSPX_IMAGE_APPROVAL_REF", "ak://evidence/13666")
    copied = world.tmp / "copied-admission.json"
    copied.write_bytes(
        canonical({**world.record, "mode": "live", "approval_binding": _APPROVAL})
    )
    raw = copied.read_bytes()

    def live(
        *,
        root: tuple[int, int] = world.root,
        expectation: str = _EXPECT,
        grant: tuple[int, str, str] = _GRANT,
    ) -> LiveImageAuthority:
        return LiveImageAuthority(raw, expectation, root[0], root[1], *grant)

    # The trusted parent has not established exact approval and custody.
    for authority in (
        world.held(raw),
        live(grant=(6610, "ak://evidence/13666", "6" * 64)),
        live(grant=(6611, "ak://evidence/13666", "5" * 64)),
        live(grant=(6610, "ak://evidence/1", "5" * 64)),
        live(expectation="9" * 64),
        live(root=(world.root[0], world.root[1] + 1)),
    ):
        _refused(_INVALID, lambda a=authority: world.validate(raw, a))
    # Even an exact parent object yields only a commitment: no approval is reported.
    admission = world.validate(raw, live())
    assert type(admission) is ImageAdmission
    assert [item.name for item in fields(ImageAdmission)] == ["raw", "sha256"]
    # ubs:ignore -- public sha256 admission commitment, not a secret
    assert admission.sha256 == digest("admission-v2", parse_json(raw))
    entries = _no_effects(monkeypatch)
    request = ImageExecutionRequest(
        **world.kwargs(), admission=admission, authority=live()
    )
    for call in (
        lambda: world.shipped(admission, live()),
        lambda: world.shipped(admission, live(), route="episode"),
        lambda: request.execute(route="direct"),
        lambda: program_runtime_episode.run_program_runtime_episode(
            manifest_path=world.tmp / "candidate" / "manifest.json",
            inputs_path=world.tmp / "inputs" / "inputs.json",
            outdir=world.tmp / "artifacts",
            image_execution=request,
        ),
    ):
        _refused(_INVALID, call)
    world.done(entries)


_S03_BOUNDS = {  # subject: self-consistent re-minted admissions beyond a code bound
    "AK6607-S03-E01": [
        ("canonical_base_endpoint", url)
        for url in (
            "http://localhost:8000/v1",
            "https://127.0.0.1:8000/v1",
            "http://10.0.0.8:8000/v1",
            "http://127.0.0.1:8000/v1/chat/completions",
            "http://user:pw@127.0.0.1:8000/v1",
        )
    ],
    "AK6607-S03-E02": [("model", " " + _MODEL), ("model", "x" * 300)],
    "AK6607-S03-E03": [
        ("limits.max_request_images", 1),
        ("limits.max_source_images", 1),
        ("limits.max_source_images", 7),
        ("request_plan.0.image_occurrence_sequence", ["s000001"] * 4 + ["s000002"] * 3),
    ],
    "AK6607-S03-E04": [
        ("deadlines.per_request_io_timeout_ms", 30_001),
        ("deadlines.total_wall_ms", 10_000),
    ],
    "AK6607-S03-E05": [
        ("limits.max_image_bytes", 95),
        ("limits.max_image_bytes", 8_388_609),
        ("limits.max_source_image_bytes", 191),
    ],
    "AK6607-S03-E06": [
        ("limits.max_request_body_bytes", 41_943_041),
        ("limits.max_request_body_bytes", 0),
    ],
}


@pytest.mark.parametrize("case", sorted(_S03_BOUNDS))
def test_s03_parent_refuses_bounds_outside_the_admission(
    world: _World, monkeypatch: pytest.MonkeyPatch, case: str
):
    """AK6607-S03 (parent half): Given an approved synthetic admission; When <subject>
    exceeds its bound; Then rejected before worker, provider or send (fixed code)."""
    entries = _no_effects(monkeypatch)
    for path, value in _S03_BOUNDS[case]:
        raw = canonical(_put(world.record, path, value))
        for authority in (world.held(), world.held(raw)):
            _refused(_INVALID, lambda: world.validate(raw, authority))
            _refused(_INVALID, lambda: world.shipped(_identity(raw), authority))
    world.done(entries)


@pytest.mark.parametrize("case", ["E01", "E02", "E03", "E05", "E07", "E08"])
def test_s03_parent_refuses_drift_against_held_expectations(
    world: _World, monkeypatch: pytest.MonkeyPatch, case: str
):
    """AK6607-S03 drift only the held expectations reveal: foreign endpoint, unprepared
    model, ceiling-breaking source, repeated bytes, changed source, foreign binding."""
    record, source = world.record, world.source
    entries = _no_effects(monkeypatch)
    if case == "E01":  # a different canonical endpoint is a different admission
        raw = canonical(_put(record, "canonical_base_endpoint", "http://[::1]:8000/v1"))
        _refused(_INVALID, lambda: world.validate(raw, world.held()))
        _refused(_INVALID, lambda: world.shipped(_identity(raw), world.held()))
    elif case == "E02":  # the held preparation names the requested model
        raw = canonical(_put(record, "model", _OTHER))
        world.validate(raw, world.held(raw))
        _refused(_INVALID, lambda: world.shipped(_identity(raw), world.held(raw)))
    elif case == "E03":  # seven images exceed the code count ceiling at the source
        many = _source(7)
        changed = {"source_package_sha256": digest("source-v1", many)}
        raw = canonical({**record, **changed, "request_plan": _plan(many)})
        _refused(_INVALID, lambda: world.validate(raw, world.held(raw), many))
    elif case == "E05":  # explicit repetition is counted again per request
        altered = _put(record, "limits.max_request_image_bytes", 200)
        world.validate(canonical(altered), world.held(canonical(altered)))
        sequence = ["s000001", "s000001", "s000002"]
        raw = canonical(
            _put(altered, "request_plan.0.image_occurrence_sequence", sequence)
        )
        _refused(_INVALID, lambda: world.validate(raw, world.held(raw)))
    elif case == "E07":  # source commitments changed after admission/preparation
        for path, value in (
            ("source_occurrences.0.content_sha256", "0" * 64),
            ("source_occurrences.1.byte_count", 97),
            ("raw_input_file_sha256", "1" * 64),
            ("candidate_manifest_sha256", "2" * 64),
            ("plain_text_slots.0.char_count", 2),
        ):
            changed = _put(source, path, value)
            prepared = _preparation(changed, record["request_plan"])
            _refused(_INVALID, lambda: world.validate(world.raw, world.held(), changed))
            _refused(
                _INVALID,
                lambda: world.shipped(
                    _identity(world.raw), world.held(), preparation=prepared
                ),
            )
    else:  # E08: a parent object bound to a foreign caller attempt binding
        other = _put(record, "custody.caller_binding_sha256", "9" * 64)
        foreign = world.held(canonical(other))
        _refused(_INVALID, lambda: world.validate(world.raw, foreign))
        _refused(_INVALID, lambda: world.shipped(_identity(world.raw), foreign))
    world.done(entries)


def _png(color: tuple[int, int, int]) -> bytes:
    from PIL import Image  # parent-only fixture encoder; the worker decodes

    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _write_inputs(root: Path, images: list[bytes]) -> None:
    visual: list[object] = ["A"]
    for index, pixels in enumerate(images):
        data = base64.b64encode(pixels).decode("ascii")
        visual.append({"type": "image_base64", "media_type": "image/png", "data": data})
        visual.append(f"T{index}")
    (root / "inputs" / "inputs.json").write_text(json.dumps({"visual": visual}))


@pytest.fixture
def materialized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Factory: one generated image candidate, N synthetic screenshots, private fds."""
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    opened: dict[str, int] = {}

    def build(images: int) -> dict[str, int]:
        materialize_program_from_intent(
            ProgramIntent(
                name="AdmissionProbe",
                objective="Describe bounded synthetic screenshots.",
                input_fields=[{"name": "visual", "type": "str"}],
                output_fields=[{"name": "answer", "type": "str"}],
                options={"image_enabled": True},
            ),
            outdir=tmp_path / "candidate",
        )
        names = ("inputs", "preparation", "custody", "artifacts", "wire", "report")
        for name in names:
            (tmp_path / name).mkdir(mode=0o700)
        _write_inputs(
            tmp_path, [_png((40 * i, 90, 255 - 40 * i)) for i in range(images)]
        )
        for name in ("candidate", *names):
            opened[name] = os.open(tmp_path / name, os.O_RDONLY | os.O_DIRECTORY)
        return opened

    try:
        yield build
    finally:
        for fd in opened.values():
            os.close(fd)


def _prepare_and_admit(fds: dict[str, int], **limits: int):
    prepared = prepare_image_execution(
        candidate_fd=fds["candidate"],
        input_fd=fds["inputs"],
        input_name="inputs.json",
        preparation_fd=fds["preparation"],
        model=_MODEL,
    )
    row = parse_json(prepared.raw)
    stat = os.fstat(fds["custody"])
    root, expectation = (stat.st_dev, stat.st_ino), sha(prepared.raw)
    record = _record(
        row["source"],
        root=root,
        plan=row["plan"],
        expectation=expectation,
        limits=limits,
    )
    raw = canonical(record)
    authority = SyntheticImageAuthority(raw, expectation, *root)
    admission = validate_admission(
        raw,
        source=row["source"],
        authority=authority,
        runtime_identity_sha256=runtime_identity(),
    )
    return prepared, authority, admission


def _status(commitment: str) -> dict[str, object]:
    return {
        "status": "completed",
        "commitment_sha256": commitment,
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": None,
    }


class _ForgedAuthority(SyntheticImageAuthority):
    pass


def test_s01_code_defaults_without_owner_bound_admission_refuse_before_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, materialized
):
    """AK6607-S01: six valid screenshots at the count ceiling, network.mutate on, no
    owner-bound admission: refused before invoke/send/probe/fallback; no success."""
    from dspx.policy import allow_network_mutate, check_capability

    fds = materialized(6)
    assert allow_network_mutate()
    check_capability("network.mutate")
    prepared, authority, admission = _prepare_and_admit(fds)
    row = parse_json(prepared.raw)
    assert validate_source(row["source"]) == row["source"]
    assert len(row["source"]["source_occurrences"]) == CEILINGS["max_source_images"]
    assert row["plan"][0]["image_occurrence_sequence"] == [
        f"s{index:06d}" for index in range(1, 7)
    ]
    spec = importlib.util.spec_from_file_location(
        "admission_direct_run", tmp_path / "candidate" / "direct_run.py"
    )
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    raw, record = admission.raw, admission.record
    bound = (sha(prepared.raw), authority.root_dev, authority.root_ino)
    foreign = canonical({**record, "model": _OTHER})
    entries = _no_effects(monkeypatch)
    execution = _execution(fds, prepared, wire=fds["wire"])
    for unbound_admission, held in (
        (None, None),
        (raw, authority),
        (admission, None),
        (admission, {"expected_admission": raw, "caller_expectation_sha256": _EXPECT}),
        (admission, _ForgedAuthority(raw, *bound)),
        (admission, SyntheticImageAuthority(foreign, *bound)),
    ):
        pair = {"admission": unbound_admission, "authority": held}
        for call in (
            lambda: execute_image_program(**execution, **pair, route="direct"),
            lambda: execute_image_program(**execution, **pair, route="episode"),
            lambda: runner.run_image(**execution, **pair),
            lambda: ImageExecutionRequest(**execution, **pair).execute(route="direct"),
        ):
            _refused(_INVALID, call)
    _refused(
        _INVALID,
        lambda: program_runtime_episode.run_program_runtime_episode(
            manifest_path=tmp_path / "candidate" / "manifest.json",
            inputs_path=tmp_path / "inputs" / "inputs.json",
            outdir=tmp_path / "episode",
        ),
    )
    assert entries == []
    for name in ("custody", "artifacts", "wire"):
        assert list_root(fds[name]) == []
    assert not (tmp_path / "episode").exists()


@worker_entry
def _drift_entry(params: dict[str, Any]) -> dict[str, object]:
    import dspx.openai_compatible_provider as provider_owner

    preparation = ImagePreparation(params["preparation"].encode("ascii"))
    raw = params["admission"].encode("ascii")
    admission = ImageAdmission(raw, digest("admission-v2", parse_json(raw)))
    record = admission.record
    root = (record["custody"]["root_dev"], record["custody"]["root_ino"])
    expectation = params["expectation"]
    # Worker-local mirror of the parent's reserved nominal authority (as shipped).
    authority = SyntheticImageAuthority(raw, expectation, *root, _used=[False])
    wire_fd = params["wire_fd"]
    probes: dict[str, dict[str, object]] = {}

    def probe(name: str, call) -> None:
        before = len(list_root(wire_fd))
        code, fixed = None, False
        try:
            call()
        except ImageContractError as error:
            code = error.code
            fixed = (
                str(error) == error.code
                and error.args == (error.code,)
                and error.__cause__ is None
                and error.__suppress_context__
            )
        except Exception as error:
            code = "unexpected:" + type(error).__name__
        sends = len(list_root(wire_fd)) - before
        probes[name] = {"code": code, "fixed": fixed, "sends": sends}

    with image_privacy() as active:
        program, context, rederived = _prepare(
            active,
            candidate_fd=params["candidate_fd"],
            input_fd=params["input_fd"],
            input_name="inputs.json",
            model=record["model"],
            use_cot=False,
            limits=record["limits"],
        )
        require(canonical(rederived) == preparation.raw, _INVALID)

        def session_for(bound: ImageAdmission, held: object) -> ImageCustodySession:
            return ImageCustodySession(
                root_fd=params["custody_fd"],
                admission=bound,
                authority=held,
                context=context,
            )

        live = {**record, "mode": "live", "approval_binding": _APPROVAL}
        live_raw = canonical(live)
        live_admission = ImageAdmission(live_raw, digest("admission-v2", live))
        flagged = SyntheticImageAuthority(live_raw, expectation, *root, _used=[False])
        probe("s28_live_record_session", lambda: session_for(live_admission, flagged))
        session = session_for(admission, authority)
        active.session = session
        fixture = {"completion": _ANSWER, "observation_fd": wire_fd}
        transport = fixture_transport(fixture, record["model"])
        lm = provider_registry.create_image_lm(session, transport=transport)
        provider = lm.provider
        clients: list[bool] = []

        def no_client(*args, **kwargs):
            clients.append(True)
            raise AssertionError("client construction")

        with pytest.MonkeyPatch.context() as spies:
            spies.setattr(httpx.Client, "__init__", no_client)
            spies.setattr(provider_owner, "_default_transport", no_client)
            for name, url, model in (
                ("e01_constructor_endpoint", _DRIFT_URL, _MODEL),
                ("e02_constructor_model", _ENDPOINT, _OTHER),
            ):
                probe(
                    name,
                    lambda u=url, m=model: provider_owner.OpenAICompatibleProvider(
                        base_url=u,
                        model=m,
                        _image_session=session,
                        _transport=httpx.MockTransport(no_client),
                    ),
                )
            # A synthetic session whose authority is flipped to live selects no client.
            session._authority = LiveImageAuthority(raw, expectation, *root, *_GRANT)
            try:
                probe(
                    "s28_live_authority_factory",
                    lambda: provider_registry.create_image_lm(session, transport=None),
                )
            finally:
                session._authority = authority

        def run() -> None:
            with dspy.context(lm=lm):
                program(**context.materialized())

        def drifted(owner: object, attribute: str, value: object):
            def call() -> None:
                original = getattr(owner, attribute)
                setattr(owner, attribute, value)
                try:
                    run()
                finally:
                    setattr(owner, attribute, original)

            return call

        probe("e01_send_endpoint", drifted(provider, "_base_url", _DRIFT_URL))
        probe("e02_send_provider_model", drifted(provider, "_model", _OTHER))
        probe("e02_send_requested_model", drifted(lm, "model", _OTHER))
        probe("e04_send_timeout", drifted(provider, "_effective_timeout", 30.001))
        foreign = object.__new__(ImageCustodySession)
        probe("e08_foreign_session", drifted(provider, "image_session", foreign))
        probe("control", run)
        probe("e08_reused_attempt", run)
        probe("e08_reused_authority", lambda: session_for(admission, authority))
        report = {"probes": probes, "client_constructions": len(clients)}
        commitment = publish(params["report_fd"], "report.json", report)
    return _status(commitment)


_DRIFT_CODES = {
    "s28_live_record_session": _INVALID,
    "e01_constructor_endpoint": _INVALID,
    "e02_constructor_model": _INVALID,
    "s28_live_authority_factory": _INVALID,
    "e01_send_endpoint": _INVALID,
    "e02_send_provider_model": _INVALID,
    "e02_send_requested_model": _INVALID,
    "e04_send_timeout": "image_budget",
    "e08_foreign_session": _INVALID,
    "control": None,
    "e08_reused_attempt": _INVALID,
    "e08_reused_authority": "image_spent",
}


def test_s03_send_time_drift_outside_the_admission_is_refused_before_send(materialized):
    """AK6607-S03-E01/E02/E04/E08 and S28-E05 in the clean worker: each drift refused
    before HTTP send with a fixed code; exactly one admitted send follows."""
    fds = materialized(2)
    prepared, authority, admission = _prepare_and_admit(fds)
    record = admission.record
    manifest = {
        "schema_version": "dspx-image-input-manifest-v2",
        "source_package_sha256": record["source_package_sha256"],
        "admission_sha256": admission.sha256,
        "marker_entries": parse_json(prepared.raw)["markers"],
    }
    bind = {
        "source_sha256": record["source_package_sha256"],
        "manifest_sha256": digest("manifest-v2", manifest),
    }
    initialize = parent_initializer(fds["custody"], authority, admission, **bind)
    names = ("candidate", "inputs", "custody", "wire", "report")
    result = supervise_image_worker(
        f"{_HERE}:_drift_entry",
        {
            "candidate_fd": fds["candidate"],
            "input_fd": fds["inputs"],
            "custody_fd": fds["custody"],
            "wire_fd": fds["wire"],
            "report_fd": fds["report"],
            "preparation": prepared.raw.decode("ascii"),
            "admission": admission.raw.decode("ascii"),
            "expectation": sha(prepared.raw),
        },
        fds=tuple(fds[name] for name in names),
        wall_ms=30_000,
        parent_action=initialize,
    )
    report_raw = read_record(fds["report"], "report.json")
    assert result == _status(sha(report_raw))
    report = parse_json(report_raw)
    probes = report["probes"]
    assert {name: row["code"] for name, row in probes.items()} == _DRIFT_CODES
    assert all(row["fixed"] for name, row in probes.items() if name != "control")
    sends = {name: row["sends"] for name, row in probes.items()}
    assert sends == {name: int(name == "control") for name in _DRIFT_CODES}
    assert report["client_constructions"] == 0
    assert list_root(fds["wire"]) == ["wire-1.json"]
    custody = sorted(list_root(fds["custody"]))
    assert custody == ["intent-1.json", "lock", "ready.json", "terminal-1.json"]
    terminal = parse_json(read_record(fds["custody"], "terminal-1.json"))
    assert terminal["provider_disposition"] == "completed_success"
    assert terminal["dispatch_count"] == 1
    # E08 in the parent: the reserved authority and the spent root never rebind.
    _refused(
        "image_custody",
        lambda: parent_initializer(fds["custody"], authority, admission, **bind),
    )
    fresh = SyntheticImageAuthority(
        admission.raw, sha(prepared.raw), authority.root_dev, authority.root_ino
    )
    _refused(
        "image_spent",
        lambda: parent_initializer(fds["custody"], fresh, admission, **bind),
    )


@pytest.mark.parametrize("case", ["AK6607-S03-E06", "AK6607-S03-E07"])
def test_s03_shipped_route_refuses_body_or_source_drift_before_send(
    tmp_path: Path, materialized, case: str
):
    """AK6607-S03-E06: the actual body exceeds the admitted body ceiling. E07: the
    source input changed after preparation and admission. Refused before ready/send."""
    fds = materialized(1)
    body = case.endswith("E06")
    limits = {"max_request_body_bytes": 64} if body else {}
    prepared, authority, admission = _prepare_and_admit(fds, **limits)
    if not body:
        _write_inputs(tmp_path, [_png((1, 2, 3))])
    _refused(
        "image_budget" if body else _INVALID,
        lambda: execute_image_program(
            **_execution(fds, prepared, wire=fds["wire"]),
            admission=admission,
            authority=authority,
            route="direct",
        ),
    )
    # The worker rederives the request under the admitted limits (E06) or from the
    # changed source (E07) and refuses before ready.json, intent or send.
    for name in ("wire", "artifacts", "custody"):
        assert list_root(fds[name]) == []
