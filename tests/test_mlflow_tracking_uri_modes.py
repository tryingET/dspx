from __future__ import annotations

import os
import sys
import types
from typing import Any

import pytest


class _FakeRun:
    def __init__(self, run_id: str) -> None:
        self.info = types.SimpleNamespace(run_id=run_id)


class _FakeMlflowBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self._active: _FakeRun | None = None

    def set_tracking_uri(self, uri: str) -> None:
        self.calls.append(("set_tracking_uri", uri))

    def set_experiment(self, name: str) -> None:
        self.calls.append(("set_experiment", name))

    def active_run(self):
        return self._active

    def start_run(self, run_name: str | None = None, nested: bool = False) -> _FakeRun:
        self.calls.append(("start_run", run_name, nested))
        self._active = _FakeRun(run_name or "run")
        return self._active

    def end_run(self) -> None:
        self.calls.append(("end_run",))
        self._active = None

    def set_tag(self, key: str, value: str) -> None:
        self.calls.append(("set_tag", key, value))

    def autolog(self, disable: bool = False) -> None:
        self.calls.append(("autolog", disable))

    def dspy_autolog(
        self,
        log_traces: bool = True,
        log_traces_from_compile: bool = False,
        log_traces_from_eval: bool = True,
        log_compiles: bool = False,
        log_evals: bool = False,
        disable: bool = False,
        silent: bool = False,
    ) -> None:
        self.calls.append(
            (
                "dspy.autolog",
                log_traces,
                log_traces_from_compile,
                log_traces_from_eval,
                log_compiles,
                log_evals,
                disable,
                silent,
            )
        )


def _install_fake_mlflow(monkeypatch: pytest.MonkeyPatch) -> _FakeMlflowBackend:
    backend = _FakeMlflowBackend()
    mod: Any = types.ModuleType("mlflow")
    setattr(mod, "set_tracking_uri", backend.set_tracking_uri)
    setattr(mod, "set_experiment", backend.set_experiment)
    setattr(mod, "active_run", backend.active_run)
    setattr(mod, "start_run", backend.start_run)
    setattr(mod, "end_run", backend.end_run)
    setattr(mod, "set_tag", backend.set_tag)
    setattr(mod, "autolog", backend.autolog)
    setattr(mod, "dspy", types.SimpleNamespace(autolog=backend.dspy_autolog))
    monkeypatch.setitem(sys.modules, "mlflow", mod)
    return backend


@pytest.mark.parametrize(
    "uri",
    [
        "sqlite:////tmp/dspx_mlflow_explicit.db",
        "http://127.0.0.1:5000",
    ],
)
def test_enable_mlflow_honors_explicit_tracking_uri(
    monkeypatch: pytest.MonkeyPatch, uri: str
) -> None:
    backend = _install_fake_mlflow(monkeypatch)
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("MLFLOW_EXPERIMENT", "DSPxTest")

    from dspx.tracing import enable_mlflow_from_env

    assert enable_mlflow_from_env() is True
    assert ("set_tracking_uri", uri) in backend.calls
    assert ("set_experiment", "DSPxTest") in backend.calls


@pytest.mark.parametrize(
    "uri",
    [
        "file:/tmp/dspx_mlruns_explicit",
        "/tmp/dspx_mlruns_explicit",
    ],
)
def test_enable_mlflow_rejects_filesystem_tracking_uri(
    monkeypatch: pytest.MonkeyPatch, uri: str
) -> None:
    backend = _install_fake_mlflow(monkeypatch)
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("MLFLOW_EXPERIMENT", "DSPxTest")

    from dspx.tracing import enable_mlflow_from_env, filesystem_tracking_uri_unsupported

    assert filesystem_tracking_uri_unsupported() is True
    assert enable_mlflow_from_env() is False
    assert not any(call[0] == "set_tracking_uri" for call in backend.calls)
    assert not any(call[0] == "set_experiment" for call in backend.calls)


def test_enable_mlflow_requires_explicit_tracking_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _install_fake_mlflow(monkeypatch)
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)

    from dspx.tracing import default_tracking_uri_from_env, enable_mlflow_from_env

    assert default_tracking_uri_from_env() == ""
    assert enable_mlflow_from_env() is False
    assert not any(call[0] == "set_tracking_uri" for call in backend.calls)
    assert "MLFLOW_TRACKING_URI" not in os.environ


def test_ensure_run_requires_explicit_run_name(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _install_fake_mlflow(monkeypatch)
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "sqlite:////tmp/dspx_mlflow_modes.db")

    from dspx.tracing import enable_mlflow_from_env, ensure_run_from_env

    assert enable_mlflow_from_env() is True

    assert ensure_run_from_env(tags={"service": "x"}) is False
    assert not any(call[0] == "start_run" for call in backend.calls)

    assert ensure_run_from_env(run_name="r1", tags={"service": "x"}) is True
    assert any(call[0] == "start_run" and call[1] == "r1" for call in backend.calls)

    assert ensure_run_from_env(tags={"service": "x", "phase": "next"}) is False
    assert ("set_tag", "phase", "next") in backend.calls


def test_standard_tags_include_dspx_correlation_fields() -> None:
    from dspx.tracing import standard_tags

    tags = standard_tags(
        "signature",
        template_version="Simple V1",
        run_kind="signature-gen",
        output_basename="generated/sig.py",
        cache_key="a" * 64,
        output_hash="b" * 64,
    )

    assert tags["service"] == "signature"
    assert tags["dspx.run_kind"] == "signature-gen"
    assert tags["dspx.template_version"] == "simple-v1"
    assert tags["dspx.output_basename"] == "sig.py"
    assert tags["dspx.cache_key"] == "a" * 64
    assert tags["dspx.output_hash_prefix"] == "b" * 12


def test_standard_tags_include_program_gen_run_kind() -> None:
    from dspx.tracing import standard_tags

    tags = standard_tags(
        "program",
        template_version="program-candidate-assembly-v1",
        run_kind="program-gen",
    )

    assert tags["service"] == "program"
    assert tags["dspx.run_kind"] == "program-gen"

    runtime_tags = standard_tags("program", run_kind="program-runtime")
    eval_tags = standard_tags("program", run_kind="program-eval")
    assert runtime_tags["dspx.run_kind"] == "program-runtime"
    assert eval_tags["dspx.run_kind"] == "program-eval"
