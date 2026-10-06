"""Both actual production-generated shipped image routes: bounded PNG/JPEG fixtures.

Owner refinement 13975: payload work runs only in a clean `-I -S` worker. The parent
names an owner-defined synthetic fixture; the worker builds the exact MockTransport and
publishes only hashes, block kinds and order. Monkeypatches in this parent cannot reach it.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
from pathlib import Path
import time
import uuid
from io import BytesIO
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from PIL import Image

from dspx.dspy_typed_lm import DSPyTypedLMAdapter
from dspx.image_admission import (
    CEILINGS,
    SyntheticImageAuthority,
    canonical,
    digest,
    parse_json,
    sha,
    validate_admission,
)
from dspx.image_artifacts import ImageRunAnchor, verify_image_run
from dspx.image_execution import (
    ImageExecutionRequest,
    SyntheticTransportFixture,
    prepare_image_execution,
)
from dspx.image_privacy import runtime_identity
from dspx.image_records import list_root, read_record
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.program_runtime_episode import run_program_runtime_episode
from dspx.services.run_replay_service import check_run_receipt, execute_run_receipt

_PRIVATE_ROOTS = ("preparation", "custody", "artifacts", "wire")
_ANSWER = '[[ ## answer ## ]]\n[{"score":3.5,"other":null}]\n[[ ## completed ## ]]'


def _shipped_inputs(root: Path, *, media: str) -> bytes:
    """Materialize the generated candidate and one bounded synthetic image input."""
    materialize_program_from_intent(
        ProgramIntent(
            name="ShippedImageProbe",
            objective="Describe bounded synthetic pixels.",
            input_fields=[
                {"name": "visual", "type": "str"},
                {"name": "settings", "type": "dict[str, Optional[tuple[int, bool]]]"},
            ],
            output_fields=[
                {"name": "answer", "type": "list[dict[str, Optional[float]]]"}
            ],
            options={"image_enabled": True},
        ),
        outdir=root / "candidate",
    )
    image = Image.new("RGB", (2, 2), (12, 34, 56))
    buffer = BytesIO()
    image.save(buffer, format="PNG" if media == "image/png" else "JPEG")
    image.close()
    pixels = buffer.getvalue()
    inputs = root / "inputs"
    inputs.mkdir(mode=0o700)
    (inputs / "inputs.json").write_text(
        json.dumps(
            {
                "visual": [
                    "A",
                    {
                        "type": "image_base64",
                        "media_type": media,
                        "data": base64.b64encode(pixels).decode("ascii"),
                    },
                    "B",
                ],
                "settings": {"nullable": None, "tuple": [7, True]},
            }
        )
    )
    for name in _PRIVATE_ROOTS:
        (root / name).mkdir(mode=0o700)
    return pixels


@dataclass(frozen=True)
class _ShippedRun:
    verified: dict[str, Any]
    anchored_check: dict[str, Any]
    wire: list[dict[str, Any]]
    terminal: dict[str, Any]
    receipt: Path


def _run_shipped_route(
    root: Path, *, media: str, use_cot: bool, route: str
) -> _ShippedRun:
    """Run one shipped route; the caller-side parent never holds pixels."""
    fds = {
        name: os.open(root / name, os.O_RDONLY | os.O_DIRECTORY)
        for name in ("candidate", "inputs", *_PRIVATE_ROOTS)
    }
    try:
        prepared = prepare_image_execution(
            candidate_fd=fds["candidate"],
            input_fd=fds["inputs"],
            input_name="inputs.json",
            preparation_fd=fds["preparation"],
            model="synthetic-vision-fixture",
            use_cot=use_cot,
        )
        row = parse_json(prepared.raw)
        custody = os.fstat(fds["custody"])
        now = time.time_ns() // 1_000_000
        record = {
            "schema_version": "dspx-image-admission-v2",
            "mode": "synthetic",
            "provider_kind": "openai-compatible",
            "model": row["model"],
            "canonical_base_endpoint": "http://127.0.0.1:8000/v1",
            "source_package_sha256": digest("source-v1", row["source"]),
            "candidate_manifest_sha256": row["source"]["candidate_manifest_sha256"],
            "runtime_identity_sha256": row["runtime_identity_sha256"],
            "decoder_profile_sha256": row["source"]["decoder_profile_sha256"],
            "request_plan": row["plan"],
            "limits": {**CEILINGS, "total_dispatch_allowance": 1},
            "deadlines": {
                "not_before_utc_ms": now - 1000,
                "expires_utc_ms": now + 60_000,
                "total_wall_ms": 30_000,
                "per_request_io_timeout_ms": 30_000,
            },
            "custody": {
                "custody_id": str(uuid.uuid4()),
                "caller_run_id": str(uuid.uuid4()),
                "caller_binding_sha256": digest(
                    "caller-fixture-v1",
                    {
                        "route": route,
                        "source": row["source"],
                        "artifact_dev": os.fstat(fds["artifacts"]).st_dev,
                        "artifact_ino": os.fstat(fds["artifacts"]).st_ino,
                    },
                ),
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
        fixture = SyntheticTransportFixture(
            completion=("[[ ## reasoning ## ]]\nfixture reasoning\n" if use_cot else "")
            + _ANSWER,
            observation_fd=fds["wire"],
        )
        request = ImageExecutionRequest(
            fds["candidate"],
            fds["inputs"],
            "inputs.json",
            fds["artifacts"],
            fds["custody"],
            prepared,
            admission,
            authority,
            fixture,
        )
        if route == "episode":
            result = run_program_runtime_episode(
                manifest_path=root / "candidate" / "manifest.json",
                inputs_path=root / "inputs" / "inputs.json",
                outdir=root / "artifacts",
                image_execution=request,
            )
            assert result["status"] == "ok"
            anchor = result["image_anchor"]
        else:
            spec = importlib.util.spec_from_file_location(
                "fixture_direct_image", root / "candidate" / "direct_run.py"
            )
            assert spec is not None and spec.loader is not None
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
            anchor = runner.run_image(
                candidate_fd=fds["candidate"],
                input_fd=fds["inputs"],
                input_name="inputs.json",
                artifact_fd=fds["artifacts"],
                custody_fd=fds["custody"],
                preparation=prepared,
                admission=admission,
                authority=authority,
                fixture=fixture,
            )
        assert type(anchor) is ImageRunAnchor
        receipt = (
            root
            / "artifacts"
            / (
                "runtime_image_episode.json.meta.json"
                if route == "episode"
                else "direct_image_run_receipt.json"
            )
        )
        return _ShippedRun(
            verified=verify_image_run(anchor),
            anchored_check=check_run_receipt(receipt, image_anchor=anchor),
            wire=[
                parse_json(read_record(fds["wire"], name))
                for name in sorted(list_root(fds["wire"]))
            ],
            terminal=parse_json(read_record(fds["custody"], "terminal-1.json")),
            receipt=receipt,
        )
    finally:
        for fd in fds.values():
            os.close(fd)


@pytest.mark.parametrize("route", ["episode", "direct"])
@pytest.mark.parametrize("media", ["image/png", "image/jpeg"])
@pytest.mark.parametrize("use_cot", [False, True])
def test_shipped_production_image_route_artifacts_and_integrity_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    media: str,
    use_cot: bool,
):
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    pixels = _shipped_inputs(tmp_path, media=media)
    run = _run_shipped_route(tmp_path, media=media, use_cot=use_cot, route=route)
    assert run.verified["status"] == "ok" and run.verified["spent"] is True
    # Exactly one owner-fixture send carried the exact admitted pixels in order.
    wire = run.wire
    assert len(wire) == 1
    assert wire[0]["send_ordinal"] == 1
    assert wire[0]["message_block_kinds"][1] == ["text", "image_url", "text"]
    assert wire[0]["image_sha256"] == [sha(pixels)]
    assert wire[0]["image_media_types"] == [media]
    terminal = run.terminal
    assert (
        terminal["provider_disposition"] == "completed_success"
        and terminal["typed_finalization_completed"] is True
        and terminal["finalization_kind"] == "dspy_lm"
        and terminal["dispatch_count"] == 1
    )
    output = json.loads(
        (tmp_path / "artifacts" / "image_output_000000.json").read_bytes()
    )
    assert output["value"] == [{"score": 3.5, "other": None}]
    assert not (tmp_path / "artifacts" / "runtime_inputs.json").exists()
    assert not (tmp_path / "artifacts" / "runtime_replay_fixture.json").exists()
    for path in (tmp_path / "artifacts").iterdir():
        artifact = path.read_bytes()
        assert (
            base64.b64encode(pixels) not in artifact and b"data:image/" not in artifact
        )
    for path in (tmp_path / "custody").iterdir():
        assert base64.b64encode(pixels) not in path.read_bytes()
    # Receipt-domain migration (AK6710/AK6717) remains separate: an explicit anchor is
    # still denied before path access; unanchored legacy check/replay stay refused.
    assert run.anchored_check == {
        "status": "invalid",
        "error_codes": ["image_execution_unavailable"],
        "execution_reproduction": False,
        "dispatch_available": False,
    }
    receipt = run.receipt
    assert check_run_receipt(receipt)["status"] == "invalid"
    replay = execute_run_receipt(
        receipt, tmp_path / "artifacts" / "forbidden-replay.json"
    )
    assert (
        replay["error_codes"] == ["image_execution_replay_unsupported"]
        and replay["execution"]["attempted"] is False
    )
    assert not (tmp_path / "artifacts" / "forbidden-replay.json").exists()


# AK6692 containment, refined by owner decision 13975: payload boundaries refuse in
# every process that is not the guarded clean worker (this pytest parent included).
# Shipped parent entries now launch that worker, so poisoned arguments must be refused
# by fixed type checks before any work, spawn or record read.
def _fuzz_call(entry: Callable[..., object], *args: object, **kwargs: object) -> object:
    # Intentionally invalid nominal inputs: no cast declares poison to be valid data.
    return entry(*args, **kwargs)


class _RefusalPoison:
    def __getattribute__(self, name):
        raise AssertionError("refusal inspected an argument")

    def __repr__(self):
        raise AssertionError("refusal formatted an argument")

    def __bool__(self):
        raise AssertionError("refusal tested argument truthiness")

    def __iter__(self):
        raise AssertionError("refusal iterated an argument")

    def __enter__(self):
        raise AssertionError("refusal acquired an operation lock")


_PARENT_ENTRIES = {
    "prepare": "image_admission_invalid",
    "execute": "image_admission_invalid",
    "anchor-verify": "image_custody",
    "episode": "image_admission_invalid",
    "generated-prepare": "image_admission_invalid",
    "generated-execute": "image_admission_invalid",
    "request-execute": "image_admission_invalid",
}
_REFUSAL_BOUNDARIES = (
    "prepare",
    "execute",
    "materialize",
    "privacy-entry",
    "privacy-active",
    "provider-binding",
    "factory",
    "provider-constructor",
    "provider-invoke",
    "lm-call",
    "lm-forward",
    "artifact-binding",
    "anchor-verify",
    "episode",
    "generated-prepare",
    "generated-execute",
    "request-execute",
)


@pytest.mark.parametrize("boundary", _REFUSAL_BOUNDARIES)
def test_refusal_containment_precedes_payload_and_effect_work(
    boundary: str,
    monkeypatch: pytest.MonkeyPatch,
):
    from types import SimpleNamespace
    from dspx import image_admission, image_artifacts, image_execution
    from dspx import image_input_contract, image_privacy, provider_registry
    from dspx.image_admission import ImageContractError
    from dspx.openai_compatible_provider import OpenAICompatibleProvider
    from dspx.services import program_runtime_episode, program_surfaces

    poison = _RefusalPoison()
    runner = {}
    # Real production renderer; rendering itself has no supplied image payload.
    code = program_surfaces.render_direct_run_code(
        ProgramIntent(
            name="RefusalProbe",
            objective="Contain an unavailable image route.",
            input_fields=[{"name": "visual", "type": "str"}],
            output_fields=[{"name": "answer", "type": "str"}],
            options={"image_enabled": True},
        )
    )
    # ubs:ignore -- test executes the production-rendered runner source
    exec(compile(code, "<production-refusal-runner>", "exec"), runner)  # ubs:ignore
    preparation = dict(
        candidate_fd=poison,
        input_fd=poison,
        input_name=poison,
        preparation_fd=poison,
        model=poison,
    )
    execution = dict(
        candidate_fd=poison,
        input_fd=poison,
        input_name=poison,
        artifact_fd=poison,
        custody_fd=poison,
        preparation=poison,
        admission=poison,
        authority=poison,
        fixture=poison,
    )
    provider = object.__new__(OpenAICompatibleProvider)
    provider.image_session = poison
    provider._operation_lock = poison
    lm = object.__new__(DSPyTypedLMAdapter)
    lm.provider = SimpleNamespace(image_session=poison)
    lm._operation_lock = poison
    request = _fuzz_call(ImageExecutionRequest, **execution)
    assert type(request) is ImageExecutionRequest
    entries = []

    def forbidden(*args, **kwargs):
        entries.append(True)
        raise AssertionError("refusal crossed a work boundary")

    # Patch production owners AND local aliases; not just a mocked orchestrator.
    for module, names in (
        (
            image_execution,
            (
                "private_root",
                "list_root",
                "parse_json",
                "runtime_identity",
                "supervise_image_worker",
                "validate_admission",
                "_prepare",
                "parent_initializer",
            ),
        ),
        (
            image_input_contract,
            ("parse_json", "open_root", "read_relative", "image_bytes"),
        ),
        (image_artifacts, ("private_root", "read_record", "parse_json", "scan")),
        (image_privacy, ("worker_identity", "_ambient", "_observers")),
        (
            program_runtime_episode,
            ("_load_inputs", "_generated_program_module", "_configure_provider"),
        ),
    ):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    import subprocess

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setattr(Image, "open", forbidden)
    monkeypatch.setattr(provider_registry, "OpenAICompatibleProvider", forbidden)
    calls = {
        "prepare": lambda: _fuzz_call(
            image_execution.prepare_image_execution, **preparation
        ),
        "execute": lambda: _fuzz_call(
            image_execution.execute_image_program, route="direct", **execution
        ),
        "materialize": lambda: _fuzz_call(
            image_input_contract.materialize_image_inputs,
            poison,
            root_fd=poison,
            fields=poison,
            candidate_manifest_sha256=poison,
            candidate_source_sha256=poison,
            decoder=poison,
        ),
        "privacy-entry": lambda: image_privacy.image_privacy().__enter__(),
        "privacy-active": image_privacy.require_privacy,
        "provider-binding": lambda: _fuzz_call(
            image_admission.validate_image_provider_binding,
            poison,
            model=poison,
            base_url=poison,
            transport=poison,
        ),
        "factory": lambda: provider_registry.create_image_lm(poison, transport=poison),
        "provider-constructor": lambda: _fuzz_call(
            OpenAICompatibleProvider,
            model=poison,
            base_url=poison,
            _image_session=poison,
            _transport=poison,
        ),
        "provider-invoke": lambda: provider.invoke(poison),
        "lm-call": lambda: lm(request=poison),
        "lm-forward": lambda: lm.forward(poison),
        "artifact-binding": lambda: _fuzz_call(
            image_artifacts.verify_artifact_binding, poison, poison
        ),
        "anchor-verify": lambda: _fuzz_call(image_artifacts.verify_image_run, poison),
        "episode": lambda: _fuzz_call(
            program_runtime_episode.run_program_runtime_episode,
            manifest_path=poison,
            inputs_path=poison,
            outdir=poison,
            image_execution=poison,
        ),
        "generated-prepare": lambda: runner["prepare_image"](**preparation),
        "generated-execute": lambda: runner["run_image"](**execution),
        "request-execute": lambda: request.execute(route="direct"),
    }
    with pytest.raises(ImageContractError) as caught:
        calls[boundary]()
    expected = _PARENT_ENTRIES.get(boundary, "image_execution_unavailable")
    assert type(caught.value) is ImageContractError
    assert caught.value.code == expected
    assert str(caught.value) == expected
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert entries == []


@pytest.mark.parametrize(
    "session", [False, 0, {}, [], {"mode": "live", "approval_ref": "copied"}]
)
@pytest.mark.parametrize("boundary", ["constructor", "invoke", "lm-call", "lm-forward"])
def test_refusal_containment_non_none_sessions_cannot_enable_images(
    session: object,
    boundary: str,
    monkeypatch: pytest.MonkeyPatch,
):
    from types import SimpleNamespace
    from dspx.image_admission import ImageContractError
    from dspx.openai_compatible_provider import OpenAICompatibleProvider

    for name in (
        "DSPX_POLICY_ALLOW_NETWORK_MUTATE",
        "DSPX_IMAGE_ENABLED",
        "MLFLOW_ENABLE",
    ):
        monkeypatch.setenv(name, "1")
    monkeypatch.setenv("DSPX_IMAGE_APPROVAL_REF", "ak://evidence/13666")
    poison = _RefusalPoison()
    provider = object.__new__(OpenAICompatibleProvider)
    provider.image_session = session
    provider._operation_lock = poison
    lm = object.__new__(DSPyTypedLMAdapter)
    lm.provider = SimpleNamespace(image_session=session)
    lm._operation_lock = poison
    calls = {
        "constructor": lambda: _fuzz_call(
            OpenAICompatibleProvider,
            model=poison,
            base_url=poison,
            _image_session=session,
            _transport=poison,
        ),
        "invoke": lambda: provider.invoke(poison),
        "lm-call": lambda: lm(request=poison),
        "lm-forward": lambda: lm.forward(poison),
    }
    with pytest.raises(
        ImageContractError, match="^image_execution_unavailable$"
    ) as caught:
        calls[boundary]()
    assert type(caught.value) is ImageContractError
    assert caught.value.__suppress_context__ and caught.value.__cause__ is None


@pytest.mark.parametrize("session", [False, 0, {}, []])
@pytest.mark.parametrize("boundary", ["provider", "lm-call", "lm-forward"])
def test_refusal_containment_real_provider_session_mutation_has_zero_effects(
    session: object,
    boundary: str,
):
    from dspy.utils.callback import BaseCallback
    from dspx.image_admission import ImageContractError
    from dspx.openai_compatible_provider import OpenAICompatibleProvider

    sends = []
    callbacks = []

    class Callback(BaseCallback):
        def on_lm_start(self, call_id, instance, inputs):
            callbacks.append(True)

    def forbidden_send(request):
        sends.append(True)
        raise AssertionError("unavailable image route sent a request")

    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:8000/v1",
        model="refusal-fixture",
        _transport=httpx.MockTransport(forbidden_send),
    )
    lm = DSPyTypedLMAdapter(provider, cache=False, callbacks=[Callback()])
    # Actual text-capable instance, mutated after client/adapter construction.
    provider.image_session = session
    previous = (
        provider.provider_events,
        provider.attempt_total,
        provider.terminal_effect,
    )
    try:
        poison = _RefusalPoison()
        calls = {
            "provider": lambda: _fuzz_call(provider.invoke, poison),
            "lm-call": lambda: lm(request=poison),
            "lm-forward": lambda: _fuzz_call(lm.forward, poison),
        }
        with pytest.raises(ImageContractError, match="^image_execution_unavailable$"):
            calls[boundary]()
        assert sends == callbacks == []
        assert (
            provider.provider_events,
            provider.attempt_total,
            provider.terminal_effect,
        ) == previous
        assert lm._indeterminate_latched is False
    finally:
        provider._client.close()
