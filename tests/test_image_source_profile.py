"""Actual production root profiling before any private input materialization.

Each scenario is a declared entry executed inside the clean `-I -S` image worker.
"""

from __future__ import annotations

import os
from pathlib import Path

import dspy
import pytest

from dspx.image_admission import ImageContractError
from dspx.image_privacy import image_privacy
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
