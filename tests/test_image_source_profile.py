"""Actual production root profiling before any private input materialization.

Each scenario is a declared entry executed inside the clean `-I -S` image worker.
"""

from __future__ import annotations

import base64
import contextlib
import functools
import importlib
import json
import logging
import os
from pathlib import Path
import struct
import sys
import zlib

import dspy
from dspy.adapters.base import Adapter
from dspy.clients.base_lm import GLOBAL_HISTORY
from dspy.core.types import LMMessage, LMRequest
from dspy.utils.callback import BaseCallback
import pytest

from dspx.image_admission import ImageContractError
from dspx.image_privacy import image_privacy
from dspx.image_records import list_root
from dspx.image_source_profile import ImageSourceProfile
from dspx.image_supervision import supervise_image_worker
from dspx.image_worker import worker_entry
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent


_HERE = "test_image_source_profile"


def _status():
    return {
        "status": "prepared",
        "commitment_sha256": "1" * 64,
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": None,
    }


@pytest.mark.parametrize("use_cot", [False, True])
def test_real_generated_kit_profile_builds_bound_native_predictors(
    tmp_path: Path, use_cot: bool
):
    root = tmp_path / "candidate"
    materialize_program_from_intent(
        ProgramIntent(
            name="ProfileProbe",
            objective="Inspect synthetic inputs.",
            inputs=["visual"],
            outputs=["answer"],
            options={"image_enabled": True},
        ),
        outdir=root,
    )
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert (
            supervise_image_worker(
                f"{_HERE}:_profile_entry",
                {"fd": fd, "use_cot": use_cot},
                fds=(fd,),
                wall_ms=30_000,
            )
            == _status()
        )
    finally:
        os.close(fd)


@worker_entry
def _profile_entry(params):
    use_cot = params["use_cot"]
    with image_privacy() as active:
        profile = ImageSourceProfile(params["fd"])
        program = profile.build(use_cot=use_cot)
        active.bind_graph(program, profile=profile)
        assert profile.owns(program)
        leaf = program.predict
        assert type(leaf) is (dspy.ChainOfThought if use_cot else dspy.Predict)
        if use_cot:
            assert type(leaf.predict) is dspy.Predict
            assert "reasoning" in leaf.predict.signature.output_fields
        assert profile.snapshot.inputs == ("visual",)
        assert profile.snapshot.outputs == ("answer",)
        assert not program.history
        return _status()


class _Wrapped(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.Predict("visual -> answer")

    def forward(self, visual):
        print(visual)
        return self.predict(visual=visual)


@worker_entry
def _root_type_entry(params):
    with image_privacy() as active:
        root = _Wrapped()
        with pytest.raises(ImageContractError, match="image_privacy"):
            active.bind_graph(root, root_types=(type(root),))
        return _status()


def test_callers_root_type_tuple_cannot_attest_custom_effects():
    assert (
        supervise_image_worker(f"{_HERE}:_root_type_entry", {}, wall_ms=30_000)
        == _status()
    )


@pytest.mark.parametrize(
    "drift", ["globals", "defaults", "instance_forward", "io", "signature", "predictor"]
)
def test_bound_root_rejects_executable_drift(tmp_path: Path, drift: str):
    root = tmp_path / "candidate"
    materialize_program_from_intent(
        ProgramIntent(
            name="DriftProbe",
            objective="Inspect synthetic inputs.",
            inputs=["visual"],
            outputs=["answer"],
            options={"image_enabled": True},
        ),
        outdir=root,
    )
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert (
            supervise_image_worker(
                f"{_HERE}:_drift_entry",
                {"fd": fd, "drift": drift},
                fds=(fd,),
                wall_ms=30_000,
            )
            == _status()
        )
    finally:
        os.close(fd)


@worker_entry
def _drift_entry(params):
    drift = params["drift"]
    with image_privacy() as active:
        profile = ImageSourceProfile(params["fd"])
        program = profile.build()
        active.bind_graph(program, profile=profile)
        calls = []

        def forbidden(*args, **kwargs):
            calls.append(True)
            raise AssertionError("drift executed")

        if drift == "globals":
            program.forward.__func__.__globals__["dspy"] = object()
        elif drift == "defaults":
            program.forward.__func__.__defaults__ = ("unexpected",)
        elif drift == "instance_forward":
            vars(program)["forward"] = forbidden
        elif drift == "io":
            program.forward.__func__.__globals__["io_spec"] = forbidden
        elif drift == "signature":
            vars(program)["predict"].signature = dspy.Predict(
                "visual -> other"
            ).signature
        else:
            vars(program)["predict"] = dspy.Predict("visual -> answer")
        with pytest.raises(ImageContractError, match="image_privacy"):
            active.check()
        assert not calls
        # Avoid asking the context to exit with a deliberately invalid root.
        active.root = None
        return _status()


# AK6756 red matrix (privacy): an observer configured before image execution makes the
# shipped preparation entry refuse before any input is read or materialized.

_LEAKS: list[str] = []  # worker-local: anything an armed observer or spy received
_MATERIALIZED: list[str] = []


def _png(rgb: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + data))
        return struct.pack(">I", len(data)) + kind + data + crc

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\0" + rgb))
        + chunk(b"IEND", b"")
    )


def _image(rgb: bytes) -> dict[str, str]:
    data = base64.b64encode(_png(rgb)).decode("ascii")
    return {"type": "image_base64", "data": data, "media_type": "image/png"}


def _private(path: Path, document: dict[str, object] | None = None) -> int:
    path.mkdir(mode=0o700)
    if document is not None:
        (path / "inputs.json").write_text(json.dumps(document))
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY)


def _run(tmp_path: Path, entry: str, params: dict, document: dict, **fields) -> list:
    """Generate a real image candidate, run one declared entry, return prepared names."""
    root = tmp_path / "candidate"
    materialize_program_from_intent(
        ProgramIntent(
            name="PrivacyProbe",
            objective="Inspect synthetic inputs.",
            outputs=["answer"],
            options={"image_enabled": True},
            **fields,
        ),
        outdir=root,
    )
    fds = (
        os.open(root, os.O_RDONLY | os.O_DIRECTORY),
        _private(tmp_path / "inputs", document),
        _private(tmp_path / "preparation"),
    )
    try:
        names = ("candidate_fd", "input_fd", "preparation_fd")
        status = supervise_image_worker(
            f"{_HERE}:{entry}",
            {**params, **dict(zip(names, fds, strict=True))},
            fds=fds,
            wall_ms=30_000,
        )
        assert status == _status()
        return sorted(list_root(fds[2]))
    finally:
        for fd in fds:
            os.close(fd)


class _Observer(BaseCallback):
    """Independent spy: every DSPy callback handler invocation is recorded by name."""

    def __getattribute__(self, name: str):
        if name.startswith("on_"):
            return lambda **kwargs: _LEAKS.append("callback:" + name)
        return object.__getattribute__(self, name)


class _Sink(list):
    def append(self, item: object) -> None:
        _LEAKS.append("trace")
        super().append(item)


class _Stream:
    def __getattr__(self, name: str):
        _LEAKS.append("send_stream:" + name)
        raise AttributeError(name)


class _SpyLM(dspy.BaseLM):
    def __init__(self, callbacks: list | None = None) -> None:
        super().__init__("synthetic-vision-fixture", cache=False, callbacks=callbacks)

    def forward(self, *args, **kwargs):
        _LEAKS.append("lm.forward")
        raise AssertionError("an observed LM was invoked")


class _CustomAdapter(dspy.ChatAdapter):
    def __call__(self, *args, **kwargs):
        _LEAKS.append("adapter.__call__")
        return super().__call__(*args, **kwargs)

    def format(self, *args, **kwargs):
        _LEAKS.append("adapter.format")
        return super().format(*args, **kwargs)


def _armed() -> tuple[object, ...]:
    """Observer state that a refusal must leave untouched (no cleanup or disable)."""
    config = importlib.import_module("dspy.dsp.utils.settings").main_thread_config
    mlflow = sys.modules.get("mlflow")
    return (
        list(GLOBAL_HISTORY),
        {
            key: list(value) if type(value) is list else value
            for key, value in config.items()
            if key not in {"lm", "adapter"} or value is not None
        },
        [
            vars(owner).get(name)
            for owner in (dspy.Module, dspy.Predict, dspy.ChainOfThought, Adapter)
            for name in ("__call__", "forward", "__getattribute__")
        ],
        None if mlflow is None else getattr(mlflow.active_run(), "info", None),
    )


def _mlflow(observer: str, patch: pytest.MonkeyPatch, tracking: str) -> None:
    """Arm MLflow offline inside the worker (the worker environment forces MLFLOW_ENABLE=0)."""
    for key, value in (
        ("MLFLOW_DISABLE_TELEMETRY", "true"),
        ("DO_NOT_TRACK", "true"),
        ("MLFLOW_TRACKING_URI", Path(tracking).as_uri()),
    ):
        patch.setenv(key, value)
    import mlflow
    from mlflow.utils.autologging_utils import AUTOLOGGING_INTEGRATIONS, safe_patch
    from mlflow.utils.autologging_utils.safety import _AUTOLOGGING_PATCHES

    if observer == "mlflow_imported":
        return  # importing MLflow registers integrations: refused without isolation
    if observer == "mlflow_autolog":
        import mlflow.dspy

        mlflow.dspy.autolog(silent=True)
        assert any(
            type(c).__name__ == "MlflowCallback" for c in dspy.settings.callbacks
        )
    elif observer == "mlflow_active_run":
        from mlflow.tracking.fluent import start_run

        start_run()
    elif observer in {"mlflow_disabled_patch", "mlflow_wrapped_only"}:

        def patched(original, self, **kwargs):
            _LEAKS.append("safe_patch")
            return original(self, **kwargs)

        safe_patch("dspy", dspy.Predict, "forward", patched)
        assert _AUTOLOGGING_PATCHES and hasattr(dspy.Predict.forward, "__wrapped__")
        if observer == "mlflow_wrapped_only":
            _AUTOLOGGING_PATCHES.clear()  # only the retained SDK __wrapped__ remains
    # Isolation: drop import-time registrations so only the armed observer remains.
    AUTOLOGGING_INTEGRATIONS.clear()


def _graph(observer: str):
    """Observers carried by the generated root graph itself (built inside the entry)."""
    callbacks = [_Observer()]
    demo = dspy.Example(visual="text-only demo", answer="secret-demo-answer")
    history = dspy.History(messages=[{"visual": "earlier", "answer": "secret-turn"}])
    return {
        "instance_callback": lambda root: root.callbacks.extend(callbacks),
        "nested_callback": lambda root: root.predict.predict.callbacks.extend(
            callbacks
        ),
        "module_history": lambda root: root.history.append({"prompt": "retained"}),
        "demos": lambda root: root.predict.predict.demos.append(demo),
        "history_demo": lambda root: root.predict.predict.demos.append(
            dspy.Example(history=history, visual="now", answer="secret-answer")
        ),
    }.get(observer)


def _wrap(owner: type, name: str, patch: pytest.MonkeyPatch) -> None:
    """Class-level instrumentation of the call path (an unknown wrapped Predict call)."""
    original = getattr(owner, name)

    @functools.wraps(original)
    def wrapper(self, *args, **kwargs):
        _LEAKS.append(f"{owner.__name__}.{name}")
        return original(self, *args, **kwargs)

    patch.setattr(owner, name, wrapper)


def _arm(observer: str, patch: pytest.MonkeyPatch, tracking: str):
    """Configure the observer before image execution; return the masking override."""
    hidden: contextlib.AbstractContextManager = contextlib.nullcontext()
    if observer.startswith("mlflow"):
        _mlflow(observer, patch, tracking)
    elif observer == "global_callback":
        dspy.configure(callbacks=[_Observer()])
    elif observer == "hidden_callback":
        dspy.configure(callbacks=[_Observer()])
        hidden = dspy.context(callbacks=[])
    elif observer == "hidden_adapter_callback":
        dspy.configure(adapter=dspy.ChatAdapter(callbacks=[_Observer()]))
        hidden = dspy.context(adapter=None)
    elif observer == "hidden_lm_callback":
        dspy.configure(lm=_SpyLM(callbacks=[_Observer()]))
        hidden = dspy.context(lm=None)
    elif observer == "custom_adapter":
        dspy.configure(adapter=_CustomAdapter())
    elif observer == "hidden_custom_adapter":
        dspy.configure(adapter=_CustomAdapter())
        hidden = dspy.context(adapter=None)
    elif observer == "trace_sink":
        dspy.configure(trace=_Sink())
    elif observer == "trace_override":
        hidden = dspy.context(trace=_Sink())
    elif observer == "global_history":
        GLOBAL_HISTORY.append({"prompt": "retained"})
    elif observer == "send_stream":
        dspy.configure(send_stream=_Stream())
    elif observer == "stream_listener":
        listener = dspy.streaming.StreamListener(signature_field_name="answer")
        dspy.configure(stream_listeners=[listener])
    elif observer in _CLASS_WRAPS:
        owner, name = _CLASS_WRAPS[observer]
        _wrap(owner, name, patch)
    elif observer == "type_mismatch":
        predict_owner = importlib.import_module("dspy.predict.predict")
        name = "_is_value_compatible_with_type"
        patch.setattr(
            predict_owner, name, _counting(name, getattr(predict_owner, name))
        )
    graph = _graph(observer)
    if graph is not None:
        build = ImageSourceProfile.build

        def built(self, *, use_cot: bool = False):
            root = build(self, use_cot=use_cot)
            graph(root)
            return root

        patch.setattr(ImageSourceProfile, "build", built)
    return hidden


_CLASS_WRAPS: dict[str, tuple[type, str]] = {
    "predict_call": (dspy.Predict, "__call__"),
    "cot_call": (dspy.ChainOfThought, "__call__"),
    "cot_forward": (dspy.ChainOfThought, "forward"),
    "adapter_call": (Adapter, "__call__"),
    "predict_getattr": (dspy.Predict, "__getattribute__"),
}


class _Records(logging.Handler):
    """Independent logger spy: installed DSPy value warnings or any payload text."""

    def emit(self, record: logging.LogRecord) -> None:
        text = record.getMessage()
        if record.name.startswith("dspy.predict") or any(
            needle in text
            for needle in ("data:image", "CUSTOM-TYPE", "iVBOR", "secret-")
        ):
            _LEAKS.append("log:" + record.name)


@worker_entry
def _observer_entry(params):
    import dspx.image_execution as shipped

    observer = params["observer"]
    logging.getLogger().addHandler(_Records())
    with pytest.MonkeyPatch.context() as patch:
        for owner, name in (
            (shipped, "read_relative"),
            (shipped, "materialize_image_inputs"),
        ):
            original = getattr(owner, name)

            def spy(*args, _name=name, _original=original, **kwargs):
                warn = dspy.settings.warn_on_type_mismatch
                _MATERIALIZED.append(f"{_name}:warn={warn}")
                return _original(*args, **kwargs)

            patch.setattr(owner, name, spy)
        for kind in (LMRequest, LMMessage):  # S16: no request repr or model_dump
            for name in ("__repr__", "model_dump", "model_dump_json"):
                label = f"{kind.__name__}.{name}"
                patch.setattr(kind, name, _counting(label, getattr(kind, name)))
        hidden = _arm(observer, patch, params["tracking"])
        armed = _armed()
        request = {
            key: params[key] for key in ("candidate_fd", "input_fd", "preparation_fd")
        }
        request.update(
            input_name="inputs.json", model="synthetic-vision-fixture", use_cot=True
        )
        code = None
        with hidden:
            try:
                shipped._prepare_entry(request)
            except ImageContractError as error:
                code = error.code
        expected = {
            "none": None,
            "mlflow_isolated": None,
            "type_mismatch": "signature_input_shape",
        }.get(observer, "image_privacy")
        assert code == expected
        # Refusal precedes any input read; the controls prove the spies observe reads.
        read = ["read_relative:warn=False", "materialize_image_inputs:warn=False"]
        assert _MATERIALIZED == ([] if expected == "image_privacy" else read)
        assert _LEAKS == []  # no callback, wrapper, LM, logger or sink saw anything
        assert _armed() == armed  # no autolog disable, history reset or unpatching
    return _status()


_OBSERVERS = [
    pytest.param("none", id="control"),
    pytest.param("mlflow_isolated", id="control-mlflow-imported-isolated"),
    pytest.param("global_callback", id="S16-global-callback"),
    pytest.param("instance_callback", id="S16-instance-callback"),
    pytest.param("trace_sink", id="S16-S31E06-substituted-trace-list"),
    pytest.param("global_history", id="S16-S31E04-global-lm-history"),
    pytest.param("nested_callback", id="S29-nested-predict-instance-callback"),
    pytest.param("hidden_callback", id="S30-base-callback-hidden-by-override"),
    pytest.param("hidden_adapter_callback", id="S30-base-adapter-callback-hidden"),
    pytest.param("hidden_lm_callback", id="S30-base-lm-callback-hidden"),
    pytest.param("mlflow_imported", id="S31E01-mlflow-imported"),
    pytest.param("mlflow_autolog", id="S31E01-mlflow-autolog"),
    pytest.param("mlflow_disabled_patch", id="S31E02-disabled-retained-safe-patch"),
    pytest.param("mlflow_wrapped_only", id="S31E02-retained-sdk-wrapper"),
    pytest.param("mlflow_active_run", id="S31E03-active-mlflow-run"),
    pytest.param("module_history", id="S31E05-module-history"),
    pytest.param("trace_override", id="S31E06-substituted-trace-override"),
    pytest.param("send_stream", id="S31E07-send-stream"),
    pytest.param("stream_listener", id="S31E08-stream-listener"),
    pytest.param("custom_adapter", id="S31E09-custom-adapter"),
    pytest.param("hidden_custom_adapter", id="S31E09-custom-adapter-hidden"),
    pytest.param("predict_call", id="S31E10-class-predict-call"),
    pytest.param("cot_call", id="S31E10-class-chain-of-thought-call"),
    pytest.param("cot_forward", id="S31E10-class-chain-of-thought-forward"),
    pytest.param("adapter_call", id="S31E10-class-adapter-call"),
    pytest.param("predict_getattr", id="S31E10-class-predict-getattribute"),
    pytest.param("demos", id="S36-text-only-demos"),
    pytest.param("history_demo", id="S36-conversation-history-demo"),
]


@pytest.mark.parametrize("observer", _OBSERVERS)
def test_configured_observer_refuses_before_materialization(
    tmp_path: Path, observer: str
) -> None:
    """Given an observer configured before image execution (AK6607 S16/S29-S31/S36);
    When the shipped preparation entry starts; Then it refuses before any input read,
    the observer received nothing and its configuration was left as found."""
    document = {"visual": ["A", _image(b"\xff\0\0"), "B"]}
    params = {"observer": observer, "tracking": str(tmp_path / "mlruns")}
    prepared = _run(tmp_path, "_observer_entry", params, document, inputs=["visual"])
    assert prepared == (
        [] if observer not in {"none", "mlflow_isolated"} else ["preparation.json"]
    )


@pytest.mark.parametrize("annotation", ["int", "list[int]"])
def test_incompatible_image_annotation_never_reaches_value_warning(
    tmp_path: Path, annotation: str
) -> None:
    """Given a real generated Predict whose image field is annotated incompatibly
    (AK6607-S32); Then signature_input_shape refuses before any Predict call, with
    warn_on_type_mismatch already off and the installed logger seeing nothing."""
    document = {"visual": ["A", _image(b"\0\xff\0"), "B"]}
    params = {"observer": "type_mismatch", "tracking": str(tmp_path / "mlruns")}
    field = {"name": "visual", "type": annotation, "desc": "visual input"}
    assert (
        _run(tmp_path, "_observer_entry", params, document, input_fields=[field]) == []
    )


# S34 marker defects and S17 settled formatting state: a newly generated Predict inside
# the strict image context, called with helper-issued markers that were then tampered.

_START, _END = "<<CUSTOM-TYPE-START-IDENTIFIER>>", "<<CUSTOM-TYPE-END-IDENTIFIER>>"
_REPAIR = (
    ("json_repair", "loads"),
    ("json_repair", "repair_json"),
    ("dspy.adapters.base", "_expand_legacy_custom_type_markers_in_lm_message"),
    ("dspy.adapters.base", "_expand_legacy_custom_type_markers_in_chat_message"),
    ("dspy.adapters._legacy_type_markers", "_parse_legacy_payload"),
    ("dspy.adapters.types.base_type", "split_message_content_for_custom_types"),
    ("dspy.adapters.types.image", "encode_image"),
    ("dspy.adapters.types.image:Image", "__init__"),
    ("dspx.image_privacy", "LMTextPart"),
    ("dspx.image_privacy", "LMImagePart"),
    ("dspx.image_privacy", "LMRequest"),
)


def _counting(name: str, original):
    def spy(*args, **kwargs):
        _LEAKS.append(name)
        return original(*args, **kwargs)

    return spy


def _tamper(defect: str, values: dict[str, object], marker: str) -> dict[str, object]:
    visual, note = values["visual"], values["note"]
    assert type(visual) is str and type(note) is str and marker in visual
    body = marker[len(_START) : -len(_END)]
    other = base64.b64encode(_png(b"\0\0\xff")).decode("ascii")
    edits = {
        "missing_quote": body.replace('"type":', 'type":', 1),
        "doubly_quoted": json.dumps(body),
        "added_key": body.replace('{"type":"image_url",', '{"type":"image_url","x":1,'),
        "dropped_field": body.replace('"type":"image_url",', "", 1),
        "multiple_blocks": "[" + body[1:-1] + "," + body[1:-1] + "]",
        "changed_bytes": body.replace('","image_url":', '", "image_url":', 1),
    }
    if defect in edits:
        assert edits[defect] != body
        visual = visual.replace(marker, _START + edits[defect] + _END)
    elif defect == "orphan_start":
        visual += "\n" + _START + " tail"
    elif defect == "orphan_end":
        visual = _END + visual
    elif defect == "nested":
        visual = visual.replace(marker, _START + marker + _END)
    elif defect == "unregistered":
        uri = "data:image/png;base64," + other
        block = [{"type": "image_url", "image_url": {"url": uri}}]
        note += " " + _START + json.dumps(block, separators=(",", ":")) + _END
    elif defect == "moved_slot":
        visual, note = visual.replace(marker, ""), note + marker
    elif defect == "repeated":
        visual += "\n" + marker
    else:
        assert defect in {"none", "interrupt"}
    return {**values, "visual": visual, "note": note}


def _interrupt(self, text, *, slot=None):
    raise KeyboardInterrupt("synthetic interruption while scanning markers")


@worker_entry
def _marker_entry(params):
    import dspx.image_privacy as privacy
    from dspx.image_decoder import FrozenImageDecoder
    from dspx.image_input_contract import ImageContext, materialize_image_inputs
    from dspx.image_source_io import read_relative

    defect, input_fd = params["defect"], params["input_fd"]
    lm = _SpyLM()
    image_format = dspy.Image.format
    caches = (
        image_format.cache_info().currsize,
        len(dspy.cache.memory_cache),
        len(dspy.cache.disk_cache),
    )
    code = active = program = None
    with pytest.MonkeyPatch.context() as patch:
        for path, name in _REPAIR:
            module, _, member = path.partition(":")
            owner = importlib.import_module(module)
            owner = getattr(owner, member) if member else owner
            patch.setattr(
                owner, name, _counting(f"{path}.{name}", getattr(owner, name))
            )
        try:
            with image_privacy() as active:
                profile = ImageSourceProfile(params["candidate_fd"])
                program = profile.build()
                active.bind_graph(program, profile=profile)
                context = materialize_image_inputs(
                    read_relative(input_fd, "inputs.json", limit=1 << 20),
                    root_fd=input_fd,
                    fields=profile.snapshot.inputs,
                    candidate_manifest_sha256=profile.snapshot.manifest_sha256,
                    candidate_source_sha256=profile.snapshot.sha256,
                    decoder=FrozenImageDecoder(),
                )
                active.context, active.lm = context, lm
                marker = context.occurrences[0].marker
                values = _tamper(defect, context.materialized(), marker)
                if defect == "interrupt":
                    patch.setattr(ImageContext, "split", _interrupt)
                with dspy.context(lm=lm):
                    program(**values)
        except ImageContractError as error:
            code = error.code
    expected = {"none": "image_custody", "interrupt": "image_privacy"}
    assert code == expected.get(defect, "image_marker_invalid")
    # No repair, expansion, dspy.Image, typed part, request or LM call ever ran.
    assert _LEAKS == []
    assert caches == (
        image_format.cache_info().currsize,
        len(dspy.cache.memory_cache),
        len(dspy.cache.disk_cache),
    )
    # Context restoration ran and the privacy state dropped its payload references.
    assert privacy._ACTIVE.get() is None and active is not None
    assert (active.context, active.session, active.lm, active.root) == (None,) * 4
    assert dspy.settings.adapter is None and dspy.settings.lm is None
    assert program is not None and not program.history and not lm.history
    assert not GLOBAL_HISTORY
    return _status()


_DEFECTS = [
    pytest.param("none", id="control-untampered-passes-marker-check"),
    pytest.param("missing_quote", id="S34E01-json-repair-recoverable-missing-quote"),
    pytest.param("doubly_quoted", id="S34E02-doubly-quoted-payload"),
    pytest.param("orphan_start", id="S34E03-orphan-start"),
    pytest.param("orphan_end", id="S34E04-orphan-end"),
    pytest.param("nested", id="S34E05-nested-marker"),
    pytest.param("added_key", id="S34E06-added-image-block-key"),
    pytest.param("dropped_field", id="S34E07-dropped-field"),
    pytest.param("multiple_blocks", id="S34E08-multiple-blocks-in-one-marker"),
    pytest.param("unregistered", id="S34E09-unregistered-marker-in-plain-text"),
    pytest.param("moved_slot", id="S34E10-registered-marker-moved-to-other-slot"),
    pytest.param("repeated", id="S34E11-repeated-marker-outside-request-plan"),
    pytest.param("changed_bytes", id="S34E12-changed-canonical-marker-bytes"),
    pytest.param("interrupt", id="S17-interrupted-marker-scan"),
]


@pytest.mark.parametrize("defect", _DEFECTS)
def test_marker_defect_rejects_before_repair_or_lm(tmp_path: Path, defect: str) -> None:
    """Given helper-issued markers in a generated Predict call (AK6607 S34, S17);
    When a marker is defective or the scan is interrupted; Then the strict helper
    refuses before any repair, expansion, dspy.Image, typed part or LM call, and the
    formatting caches, settings and privacy references are settled afterwards."""
    document = {"visual": ["A", _image(b"\xff\0\0"), "B"], "note": "plain note"}
    params = {"defect": defect}
    assert (
        _run(tmp_path, "_marker_entry", params, document, inputs=["visual", "note"])
        == []
    )
