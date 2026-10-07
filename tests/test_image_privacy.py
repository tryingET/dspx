# summary: "Real generated Predict typed-image transport and early privacy falsifiers, synthetic only."
from __future__ import annotations

import base64
import importlib
import json
import os
from pathlib import Path
import struct
import sys
import time
import uuid
import zlib
from types import SimpleNamespace

import dspy
import httpx
import pytest
from dspy.core.types import LMImagePart, LMRequest, LMTextPart

from dspx.image_admission import (
    CEILINGS,
    ImageContractError,
    SyntheticImageAuthority,
    canonical,
    digest,
    parse_json,
    sha,
    validate_admission,
)
from dspx.dspy_typed_lm import DSPyTypedLMAdapter
from dspx.image_decoder import FrozenImageDecoder
from dspx.image_input_contract import materialize_image_inputs
from dspx.image_privacy import image_privacy, runtime_identity
from dspx.image_records import list_root, publish, read_record
from dspx.image_source_io import read_relative
from dspx.image_supervision import supervise_image_worker
from dspx.image_worker import worker_entry
from dspx.image_custody import ImageCustodySession, parent_initializer
from dspx.provider_contract import (
    ProviderImagePart,
    ProviderPartsMessage,
    ProviderRequest,
    ProviderTextPart,
    image_payload,
)
from dspx.provider_registry import create_image_lm
from dspx.services.program_service import ProgramIntent, materialize_program_from_intent
from dspx.image_source_profile import ImageSourceProfile


_HERE = "test_image_privacy"


def _png(color: bytes) -> bytes:
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\0" + color))
        + chunk(b"IEND", b"")
    )


def _status(kind: str, commitment: str):
    return {
        "status": kind,
        "commitment_sha256": commitment,
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": None,
    }


def _generated(tmp: Path):
    intent = ProgramIntent(
        name="ImageProbe",
        objective="Describe the bounded fixture.",
        inputs=["visual"],
        outputs=["answer"],
        options={"image_enabled": True},
    )
    materialize_program_from_intent(intent, outdir=tmp)
    return (tmp / "signature.py").read_text(), (tmp / "module.py").read_text()


def _load_generated(tmp: Path):
    fd = os.open(tmp, os.O_RDONLY | os.O_DIRECTORY)
    try:
        profile = ImageSourceProfile(fd)
        return profile, profile.build()
    finally:
        os.close(fd)


@pytest.mark.parametrize(
    "admission_view",
    [
        "original",
        "limits",
        "plan",
        "deadlines",
        "binding",
        "replacement",
        "wall_drift",
        "validation_interrupt",
        "cleanup_interrupt",
        "typed_interrupt",
        "presend_budget",
        "register_after_ready",
        "register_in_send",
        "forged_worker_pid",
        "forged_worker_start_identity",
        "forged_worker_deadline_ns",
        "forged_grant_sha256",
        "unparsable",
    ],
)
def test_actual_generated_predict_typed_image_to_ordered_fake_http(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    admission_view: str,
) -> None:
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    source = tmp_path / "candidate"
    _generated(source)
    candidate_manifest_sha = sha((source / "manifest.json").read_bytes())
    images = (_png(b"\xff\0\0"), _png(b"\0\0\xff"))
    encoded = [base64.b64encode(item).decode("ascii") for item in images]
    inputs = tmp_path / "inputs"
    inputs.mkdir(mode=0o700)
    (inputs / "inputs.json").write_text(
        json.dumps(
            {
                "visual": [
                    "A",
                    {
                        "type": "image_base64",
                        "data": encoded[0],
                        "media_type": "image/png",
                    },
                    "B",
                    {
                        "type": "image_base64",
                        "data": encoded[1],
                        "media_type": "image/png",
                    },
                    "C",
                ]
            }
        )
    )
    prep = tmp_path / "prep"
    custody = tmp_path / "custody"
    prep.mkdir(mode=0o700)
    custody.mkdir(mode=0o700)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(mode=0o700)
    artifact_fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
    prep_fd = os.open(prep, os.O_RDONLY | os.O_DIRECTORY)
    root_fd = os.open(custody, os.O_RDONLY | os.O_DIRECTORY)
    input_fd = os.open(inputs, os.O_RDONLY | os.O_DIRECTORY)
    model = "synthetic-vision-fixture"
    try:
        result = supervise_image_worker(
            f"{_HERE}:_privacy_prepare_entry",
            {
                "source": str(source),
                "input_fd": input_fd,
                "prep_fd": prep_fd,
                "model": model,
            },
            fds=(input_fd, prep_fd),
            wall_ms=30_000,
        )
        prepared_raw = read_record(prep_fd, "preparation.json")
        assert result["commitment_sha256"] == sha(prepared_raw)
        prepared = parse_json(prepared_raw)
        stat = os.fstat(root_fd)
        now = time.time_ns() // 1_000_000
        record = {
            "schema_version": "dspx-image-admission-v2",
            "mode": "synthetic",
            "provider_kind": "openai-compatible",
            "model": model,
            "canonical_base_endpoint": "http://127.0.0.1:8000/v1",
            "source_package_sha256": digest("source-v1", prepared["source"]),
            "candidate_manifest_sha256": candidate_manifest_sha,
            "runtime_identity_sha256": runtime_identity(),
            "decoder_profile_sha256": prepared["source"]["decoder_profile_sha256"],
            "request_plan": prepared["plan"],
            "limits": {**CEILINGS, "total_dispatch_allowance": 1},
            "deadlines": {
                "not_before_utc_ms": now - 1000,
                "expires_utc_ms": now + 60_000,
                "total_wall_ms": 29_999 if admission_view == "wall_drift" else 30_000,
                "per_request_io_timeout_ms": 29_999
                if admission_view == "wall_drift"
                else 30_000,
            },
            "custody": {
                "custody_id": str(uuid.uuid4()),
                "caller_run_id": str(uuid.uuid4()),
                "caller_binding_sha256": "2" * 64,
                "root_dev": stat.st_dev,
                "root_ino": stat.st_ino,
                "caller_expectation_sha256": "3" * 64,
            },
            "approval_binding": {
                "owning_ak_task": None,
                "operator_evidence_ref": None,
                "parent_confirmation_sha256": None,
            },
        }
        admission_raw = canonical(record)
        authority = SyntheticImageAuthority(
            admission_raw, "3" * 64, stat.st_dev, stat.st_ino
        )
        admission = validate_admission(
            admission_raw,
            source=prepared["source"],
            authority=authority,
            runtime_identity_sha256=runtime_identity(),
        )
        manifest = {
            "schema_version": "dspx-image-input-manifest-v2",
            "source_package_sha256": record["source_package_sha256"],
            "admission_sha256": admission.sha256,
            "marker_entries": prepared["markers"],
        }
        initialize = parent_initializer(
            root_fd,
            authority,
            admission,
            source_sha256=record["source_package_sha256"],
            manifest_sha256=digest("manifest-v2", manifest),
        )
        params = {
            "source": str(source),
            "input_fd": input_fd,
            "root_fd": root_fd,
            "artifact_fd": artifact_fd,
            "admission": admission_raw.decode("ascii"),
            "prepared": prepared_raw.decode("ascii"),
            "admission_view": admission_view,
            "model": model,
        }
        if admission_view.startswith("forged_"):
            # A worker misreporting any binding field gets no ready.json, lock or permit:
            # the parent initializer refuses, which surfaces as image_durability.
            with pytest.raises(ImageContractError, match="^image_durability$"):
                supervise_image_worker(
                    f"{_HERE}:_privacy_execute_entry",
                    params,
                    fds=(input_fd, root_fd, artifact_fd),
                    wall_ms=30_000,
                    parent_action=initialize,
                )
            assert list_root(root_fd) == []
            return
        if admission_view.startswith("register_"):
            # An observer registered after ready/permit or during the send ends the
            # worker; the spent root keeps its intent without terminal, never retried.
            with pytest.raises(ImageContractError, match="^image_privacy$"):
                supervise_image_worker(
                    f"{_HERE}:_privacy_execute_entry",
                    params,
                    fds=(input_fd, root_fd, artifact_fd),
                    wall_ms=30_000,
                    parent_action=initialize,
                )
            expected = {"ready.json", "lock"}
            if admission_view == "register_in_send":
                expected.add("intent-1.json")
            assert set(list_root(root_fd)) == expected
            again = SyntheticImageAuthority(
                admission_raw, "3" * 64, stat.st_dev, stat.st_ino
            )
            with pytest.raises(ImageContractError, match="^image_spent$"):
                parent_initializer(
                    root_fd,
                    again,
                    admission,
                    source_sha256=record["source_package_sha256"],
                    manifest_sha256=digest("manifest-v2", manifest),
                )
            return
        try:
            result = supervise_image_worker(
                f"{_HERE}:_privacy_execute_entry",
                params,
                fds=(input_fd, root_fd, artifact_fd),
                wall_ms=30_000,
                parent_action=initialize,
            )
        except Exception:
            pytest.fail(
                "supervised image invocation rejected; inspect safe custody records",
                pytrace=False,
            )
        if admission_view in {
            "validation_interrupt",
            "cleanup_interrupt",
            "typed_interrupt",
            "presend_budget",
        }:
            assert result == _status(
                "failed", sha(read_record(root_fd, "terminal-1.json"))
            )
            terminal = parse_json(read_record(root_fd, "terminal-1.json"))
            assert terminal["provider_disposition"] == (
                "preflight_rejected"
                if admission_view == "presend_budget"
                else "effect_indeterminate"
            )
            assert not (custody / "closure.json").exists()
            return
        if admission_view == "unparsable":
            terminal_raw = read_record(root_fd, "terminal-1.json")
            assert result == _status("failed", sha(terminal_raw))
            assert set(list_root(root_fd)) == {
                "ready.json",
                "lock",
                "intent-1.json",
                "terminal-1.json",
            }
            return
        if admission_view == "wall_drift":
            assert result == _status("failed", sha(admission.raw))
            assert os.listdir(root_fd) == []
            return
        assert (
            result["status"] == "completed"
            and result["fixture_evidence"]
            and not result["live_authorized"]
        )
        terminal = parse_json(read_record(root_fd, "terminal-1.json"))
        assert terminal["dispatch_count"] == 1
        assert (
            terminal["result_finalization_completed"]
            and terminal["typed_finalization_completed"]
        )
        assert terminal["finalization_kind"] == "dspy_lm"
    finally:
        for fd in (prep_fd, root_fd, input_fd, artifact_fd):
            os.close(fd)


_REPAIR = (
    ("json_repair", "loads"),
    ("json_repair", "repair_json"),
    ("dspy.adapters.base", "_expand_legacy_custom_type_markers_in_lm_message"),
    ("dspy.adapters.base", "_expand_legacy_custom_type_markers_in_chat_message"),
    ("dspy.adapters._legacy_type_markers", "_parse_legacy_payload"),
    ("dspy.adapters.types.base_type", "split_message_content_for_custom_types"),
    ("dspy.adapters.types.image", "encode_image"),
    ("dspy.adapters.json_adapter:JSONAdapter", "__call__"),
    ("dspy.adapters.json_adapter:JSONAdapter", "format"),
    ("dspy.adapters.json_adapter:JSONAdapter", "parse"),
)


def _spy_repairs(patch: pytest.MonkeyPatch, calls: list[str]) -> None:
    """Independent spies on installed legacy marker repair and the JSONAdapter path."""
    for path, name in _REPAIR:
        module, _, member = path.partition(":")
        owner = importlib.import_module(module)
        owner = getattr(owner, member) if member else owner
        original = getattr(owner, name)

        def spy(*args, _name=f"{path}.{name}", _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)

        patch.setattr(owner, name, spy)


def _context(active, profile: ImageSourceProfile, input_fd: int):
    raw = read_relative(input_fd, "inputs.json", limit=1 << 20)
    ctx = materialize_image_inputs(
        raw,
        root_fd=input_fd,
        fields=("visual",),
        candidate_manifest_sha256=profile.snapshot.manifest_sha256,
        candidate_source_sha256=profile.snapshot.sha256,
        decoder=FrozenImageDecoder(),
    )
    active.context = ctx
    return ctx


@worker_entry
def _privacy_prepare_entry(params):
    model, input_fd = params["model"], params["input_fd"]
    with image_privacy() as active:
        profile, program = _load_generated(Path(params["source"]))
        active.bind_graph(program, profile=profile)
        ctx = _context(active, profile, input_fd)
        signature = program.predict.signature
        messages = active.formatter.format(signature, [], ctx.materialized())
        pseudo = SimpleNamespace(
            record={"model": model, "limits": dict(CEILINGS)}, context=ctx
        )
        ports = []
        cursor = 0
        for message in messages:
            parts = []
            for part in message.parts:
                if type(part) is LMTextPart:
                    parts.append(ProviderTextPart(part.text))
                elif type(part) is LMImagePart:
                    item = ctx.occurrences[cursor]
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
                    cursor += 1
            ports.append(ProviderPartsMessage(message.role, tuple(parts)))
        _, shape, sequence = image_payload(
            ProviderRequest(model, tuple(ports), pseudo), pseudo
        )
        record = {
            "source": ctx.source,
            "markers": ctx.manifest("0" * 64)["marker_entries"],
            "plan": [
                {
                    "plan_ordinal": 1,
                    "predictor_slot": 0,
                    "request_shape_sha256": shape,
                    "image_occurrence_sequence": sequence,
                }
            ],
        }
        commitment = publish(params["prep_fd"], "preparation.json", record)
        return _status("prepared", commitment)


@worker_entry
def _privacy_execute_entry(params):
    admission_view, model = params["admission_view"], params["model"]
    input_fd, root_fd = params["input_fd"], params["root_fd"]
    artifact_fd = params["artifact_fd"]
    prepared = parse_json(params["prepared"].encode("ascii"))
    admission_raw = params["admission"].encode("ascii")
    record = parse_json(admission_raw)
    # Worker-local mirror of the parent's reserved nominal authority. It is usable
    # only through the parent handshake that checks ready.json independently.
    authority = SyntheticImageAuthority(
        admission_raw,
        "3" * 64,
        record["custody"]["root_dev"],
        record["custody"]["root_ino"],
        _used=[False],
    )
    admission = validate_admission(
        admission_raw,
        source=prepared["source"],
        authority=authority,
        runtime_identity_sha256=runtime_identity(),
    )
    images = tuple(
        base64.b64decode(item["data"])
        for item in json.loads(read_relative(input_fd, "inputs.json", limit=1 << 20))[
            "visual"
        ]
        if type(item) is dict
    )
    with image_privacy() as active:
        profile, program = _load_generated(Path(params["source"]))
        active.bind_graph(program, profile=profile)
        ctx = _context(active, profile, input_fd)
        if admission_view == "wall_drift":
            with pytest.raises(ImageContractError, match="image_budget"):
                ImageCustodySession(
                    root_fd=root_fd,
                    admission=admission,
                    authority=authority,
                    context=ctx,
                )
            assert os.listdir(root_fd) == []
            return _status("failed", sha(admission.raw))
        if admission_view.startswith("forged_"):
            import dspx.image_worker as handshake

            field = admission_view.removeprefix("forged_")
            real = handshake.worker_binding()
            pid, deadline_ns = real["worker_pid"], real["worker_deadline_ns"]
            assert type(pid) is int and type(deadline_ns) is int
            lie_value = {
                "worker_pid": pid + 1,
                "worker_start_identity": "0",
                "worker_deadline_ns": deadline_ns + 1,
                "grant_sha256": "f" * 64,
            }[field]
            forged = {**real, field: lie_value}
            with pytest.MonkeyPatch.context() as lie:
                lie.setattr("dspx.image_custody.worker_binding", lambda: forged)
                ImageCustodySession(
                    root_fd=root_fd,
                    admission=admission,
                    authority=authority,
                    context=ctx,
                )
            raise AssertionError("a forged worker binding was admitted")
        session = ImageCustodySession(
            root_fd=root_fd,
            admission=admission,
            authority=authority,
            context=ctx,
        )
        active.session = session
        if admission_view == "register_after_ready":
            sys.addaudithook(lambda event, args: None)
        # Assertions execute inside the worker; safe successful status is
        # mandatory below, so a swallowed fork assertion cannot pass.
        if admission_view == "limits":
            session.record["limits"]["total_dispatch_allowance"] = 64
        elif admission_view == "plan":
            session.record["request_plan"][0]["image_occurrence_sequence"].reverse()
        elif admission_view == "deadlines":
            session.record["deadlines"]["expires_utc_ms"] += 180_000
        elif admission_view == "binding":
            session.binding["caller_binding_sha256"] = "9" * 64
        elif admission_view == "replacement":
            for name, replacement in (
                ("record", {}),
                ("binding", {}),
                ("admission", admission),
                ("manifest", {}),
                ("manifest_sha256", "9" * 64),
                ("ready_raw", b"{}"),
            ):
                with pytest.raises(AttributeError):
                    setattr(session, name, replacement)
        assert session.record == parse_json(admission.raw)
        assert session.binding == record["custody"]
        assert session._scan() == []
        observed = []

        def handler(request):
            if admission_view == "register_in_send":
                sys.addaudithook(lambda event, args: None)
            packet = json.loads(request.content)
            blocks = packet["messages"][1]["content"]
            assert [item["type"] for item in blocks] == [
                "text",
                "image_url",
                "text",
                "image_url",
                "text",
            ]
            assert [
                base64.b64decode(item["image_url"]["url"].split(",", 1)[1])
                for item in blocks
                if item["type"] == "image_url"
            ] == list(images)
            observed.append(True)
            response_type = httpx.Response
            if admission_view == "cleanup_interrupt":

                class CleanupFault(httpx.Response):
                    def close(self) -> None:
                        super().close()
                        raise KeyboardInterrupt("synthetic-cleanup")

                response_type = CleanupFault
            content = "[[ ## answer ## ]]\nfixture result\n[[ ## completed ## ]]"
            if admission_view == "unparsable":
                content = "unstructured fixture text without any field section"
            return response_type(
                200,
                json={
                    "model": model,
                    "choices": [{"message": {"role": "assistant", "content": content}}],
                },
                request=request,
            )

        # Characterize exact synthetic transport separation before the
        # admitted positive; no client/default transport may be created.
        import dspx.openai_compatible_provider as provider_owner

        denied_entries = []

        def forbidden_client(*args, **kwargs):
            denied_entries.append(True)
            raise AssertionError("invalid image binding constructed a client")

        class MockSubclass(httpx.MockTransport):
            pass

        with pytest.MonkeyPatch.context() as guard_spies:
            guard_spies.setattr(httpx.Client, "__init__", forbidden_client)
            guard_spies.setattr(provider_owner, "_default_transport", forbidden_client)
            for bad_transport in (
                None,
                httpx.BaseTransport(),
                MockSubclass(handler),
                httpx.HTTPTransport.__new__(httpx.HTTPTransport),
            ):
                with pytest.raises(ImageContractError):
                    provider_owner.OpenAICompatibleProvider(
                        base_url="http://127.0.0.1:8000/v1",
                        model=model,
                        _image_session=session,
                        _transport=bad_transport,
                    )
            assert not denied_entries and session._scan() == []
        lm = create_image_lm(session, transport=httpx.MockTransport(handler))
        assert type(lm) is DSPyTypedLMAdapter  # no additional LM subclass
        repaired: list[str] = []
        if admission_view == "unparsable":
            # AK6607-S37: the installed parser fails once; there is no JSONAdapter
            # fallback, the one terminal stays and no later request is dispatched.
            assert active.formatter.use_json_adapter_fallback is False
            with pytest.MonkeyPatch.context() as spies:
                _spy_repairs(spies, repaired)
                spies.setattr(
                    active.formatter,
                    "_make_json_adapter_fallback",
                    lambda: repaired.append("_make_json_adapter_fallback"),
                )
                with (
                    dspy.context(lm=lm),
                    pytest.raises(ImageContractError, match="^image_finalization$"),
                ):
                    program(**ctx.materialized())
                with (
                    dspy.context(lm=lm),
                    pytest.raises(
                        ImageContractError, match="^image_admission_invalid$"
                    ),
                ):
                    program(**ctx.materialized())
            assert repaired == [] and observed == [True]
            assert len(session._scan()) == 1 and not session.poisoned
            terminal = parse_json(read_record(root_fd, "terminal-1.json"))
            assert terminal["dispatch_count"] == 1
            assert terminal["provider_disposition"] == "completed_success"
            assert not lm.history and not program.history
            return _status("failed", sha(read_record(root_fd, "terminal-1.json")))
        faults = {
            "validation_interrupt",
            "cleanup_interrupt",
            "typed_interrupt",
            "presend_budget",
        }
        if admission_view in faults:
            from dspx.image_custody import ImageAttemptTransaction

            def interrupted(*args, **kwargs):
                raise KeyboardInterrupt("synthetic-finalization")

            with pytest.MonkeyPatch.context() as fault:
                if admission_view == "validation_interrupt":
                    fault.setattr(lm.provider, "_validated_response", interrupted)
                elif admission_view == "typed_interrupt":
                    fault.setattr(lm, "_typed_response", interrupted)
                elif admission_view == "presend_budget":
                    reserve = ImageAttemptTransaction.reserve
                    check = active.check
                    once = []

                    def budget_once():
                        if not once:
                            once.append(True)
                            raise ImageContractError("image_budget")
                        check()

                    def reserve_and_expire(tx, shape, sequence):
                        attempt = reserve(tx, shape, sequence)
                        fault.setattr(active, "check", budget_once)
                        return attempt

                    fault.setattr(
                        ImageAttemptTransaction, "reserve", reserve_and_expire
                    )
                with dspy.context(lm=lm), pytest.raises(ImageContractError):
                    program(**ctx.materialized())
            terminal = parse_json(read_record(root_fd, "terminal-1.json"))
            expected = (
                "preflight_rejected"
                if admission_view == "presend_budget"
                else "effect_indeterminate"
            )
            assert terminal["provider_disposition"] == expected
            assert terminal["dispatch_count"] == (
                0 if admission_view == "presend_budget" else 1
            )
            if admission_view == "presend_budget":
                assert not observed
                assert (
                    not lm.provider._indeterminate_latched
                    and not lm._indeterminate_latched
                )
            else:
                assert observed == [True]
                assert (
                    lm.provider._indeterminate_latched
                    and lm._indeterminate_latched
                    and session.poisoned
                )
            assert not terminal["typed_finalization_completed"]
            return _status("failed", sha(read_record(root_fd, "terminal-1.json")))
        typed = []
        forward = DSPyTypedLMAdapter._forward_locked

        def typed_spy(adapter, request):
            # The sole typed adapter receives ordered LMImagePart values with the
            # exact pixels before any send (restores the pre-exec shipped-route spy).
            assert type(request) is LMRequest and observed == []
            parts = request.messages[1].parts
            assert [type(part) for part in parts] == [
                LMTextPart,
                LMImagePart,
                LMTextPart,
                LMImagePart,
                LMTextPart,
            ]
            assert [
                (part.media_type, base64.b64decode(part.data))
                for part in parts
                if type(part) is LMImagePart
            ] == [("image/png", item) for item in images]
            typed.append(True)
            return forward(adapter, request)

        with pytest.MonkeyPatch.context() as spy:
            spy.setattr(DSPyTypedLMAdapter, "_forward_locked", typed_spy)
            _spy_repairs(spy, repaired)  # AK6607-S35: no upstream marker expansion
            with dspy.context(lm=lm):
                answer = program(**ctx.materialized())
        assert answer.answer == "fixture result" and repaired == []
        assert observed == [True] and typed == [True]
        assert not lm.history and not program.history and not dspy.settings.trace
        from dspx.image_artifacts import publish_image_run

        with pytest.raises(ImageContractError, match="image_custody"):
            session.close_run("4" * 64, outcome="completed")
        bound_artifacts = publish_image_run(
            session,
            artifact_fd=artifact_fd,
            outputs={"answer": answer.answer},
            route="episode",
        )
        session.close_run(bound_artifacts, outcome="completed")
        lm.provider.close()
        return _status("completed", sha(read_record(root_fd, "closure.json")))
