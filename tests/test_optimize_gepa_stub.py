# summary: "Offline tests for trusted GEPA program imports and loadable optimized artifacts."
# read_when:
#   - "Changing GEPA program trust roots or optimization output publication."

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
from typing import Any, cast

import dspy
import httpx
import pytest

import dspx.openai_compatible_provider as openai_provider
from dspx.dspy_typed_lm import DSPyTypedLMAdapter
from dspx.openai_compatible_provider import OpenAICompatibleProvider
from dspx.services.gepa_proposal_policy import GEPAProposalConfig
import dspx.services.optimize_service as optimize_service
from dspx.services.optimize_service import (
    GEPAResult,
    _import_program_module,
    _resolve_optimizer_provider,
    run_gepa_optimize,
)
from dspx.stub_provider import StubProvider


def test_import_program_module_rejects_untrusted_program_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DSPX_TRUSTED_PROGRAM_ROOTS", raising=False)

    with tempfile.TemporaryDirectory(dir=Path.home()) as outside_root:
        program = Path(outside_root) / "prog.py"
        program.write_text("X = 1\n", encoding="utf-8")

        with pytest.raises(ValueError, match="trusted root"):
            _import_program_module(program)


def test_import_program_module_rejects_default_temp_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DSPX_TRUSTED_PROGRAM_ROOTS", raising=False)
    program = tmp_path / "prog.py"
    program.write_text("X = 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="trusted root"):
        _import_program_module(program)


def test_import_program_module_rejects_temp_cwd_implicit_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DSPX_TRUSTED_PROGRAM_ROOTS", raising=False)
    monkeypatch.chdir(tempfile.gettempdir())
    with tempfile.TemporaryDirectory(dir=tempfile.gettempdir()) as temp_root:
        program = Path(temp_root) / "prog.py"
        program.write_text("X = 1\n", encoding="utf-8")

        with pytest.raises(ValueError, match="trusted root"):
            _import_program_module(program)


def test_import_program_module_allows_env_trusted_program_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as allowed_root:
        program = Path(allowed_root) / "prog.py"
        program.write_text("VALUE = 7\n", encoding="utf-8")

        monkeypatch.setenv("DSPX_TRUSTED_PROGRAM_ROOTS", allowed_root)

        mod = _import_program_module(program)
        assert getattr(mod, "VALUE") == 7


@pytest.mark.parametrize(
    ("proposal_config", "max_metric_calls"),
    [
        pytest.param(GEPAProposalConfig(), 2, id="single-default"),
        pytest.param(
            GEPAProposalConfig(
                sampling="same-parent",
                proposal_n=2,
                selection="top-k-improvements",
                top_k=2,
            ),
            8,
            id="same-parent-two-top-two",
        ),
    ],
)
def test_gepa_optimize_saves_loadable_program(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    proposal_config: GEPAProposalConfig,
    max_metric_calls: int,
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_TRUSTED_PROGRAM_ROOTS", str(tmp_path))

    from dspy.teleprompt.gepa.gepa import GEPA as RealGEPA

    gepa_kwargs: dict[str, object] = {}

    class RecordingGEPA:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            gepa_kwargs.update(kwargs)
            self._delegate = RealGEPA(*args, **kwargs)

        def compile(self, **kwargs: Any) -> object:
            return self._delegate.compile(**kwargs)

    monkeypatch.setattr("dspy.teleprompt.gepa.gepa.GEPA", RecordingGEPA)

    program = tmp_path / "prog.py"
    program.write_text(
        "\n".join(
            [
                "import dspy",
                "",
                "class Student(dspy.Module):",
                "    def __init__(self):",
                "        super().__init__()",
                "        self.predict = dspy.Predict('question -> answer')",
                "",
                "    def forward(self, question: str) -> dspy.Prediction:",
                "        return self.predict(question=question)",
                "",
                "def build_student() -> dspy.Module:",
                "    return Student()",
                "",
            ]
        ),
        encoding="utf-8",
    )

    train = tmp_path / "train.csv"
    with train.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["question", "answer"])
        w.writeheader()
        w.writerow({"question": "What is 2+2?", "answer": "4"})
        w.writerow({"question": "What is 3+3?", "answer": "6"})

    out_dir = tmp_path / "optimized"
    res = run_gepa_optimize(
        program_path=program,
        train_path=train,
        out_dir=out_dir,
        auto=None,
        max_metric_calls=max_metric_calls,
        seed=0,
        proposal_config=proposal_config,
    )

    assert set(gepa_kwargs) == {
        "auto",
        "max_full_evals",
        "max_metric_calls",
        "num_threads",
        "reflection_lm",
        "seed",
        "track_best_outputs",
        "track_stats",
        "gepa_kwargs",
    }
    assert gepa_kwargs["num_threads"] == 1
    assert gepa_kwargs["track_stats"] is True
    assert gepa_kwargs["track_best_outputs"] is False
    assert type(gepa_kwargs["reflection_lm"]).__name__ == "TerminalGEPAReflectionLM"
    advanced = cast(dict[str, object], gepa_kwargs["gepa_kwargs"])
    assert set(advanced) == {
        "acceptance_criterion",
        "callbacks",
        "sampling_strategy",
        "selection_strategy",
    }
    assert advanced["acceptance_criterion"] == "strict_improvement"
    callbacks = cast(list[object], advanced["callbacks"])
    assert len(callbacks) == 1
    assert type(callbacks[0]).__name__ == "GEPAReceiptCallback"
    assert (
        type(advanced["sampling_strategy"]).__name__
        == proposal_config.to_manifest()["upstream_sampling_type"]
    )
    assert (
        type(advanced["selection_strategy"]).__name__
        == proposal_config.to_manifest()["upstream_selection_type"]
    )

    assert res.out_dir.exists() and res.out_dir.is_dir()
    manifest = json.loads((res.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dspy_version"] == "3.3.1"
    assert manifest["gepa_version"] == "0.1.4"
    assert manifest["gepa"]["proposal_config"] == proposal_config.to_manifest()
    assert manifest["gepa"]["metric_budget_semantics"] == (
        "iteration_boundary_stop_threshold_not_hard_ceiling"
    )
    run_stats = manifest["gepa"]["run_stats"]
    assert run_stats == res.run_stats
    assert run_stats["candidate_count"] >= 1
    assert run_stats["total_metric_calls"] >= 1
    assert len(run_stats["candidate_component_sha256"]) == run_stats["candidate_count"]
    assert len(run_stats["parents"]) == run_stats["retained_candidate_count"]
    event_counts = run_stats["event_counts"]
    assert event_counts["event_payloads_retained"] is False
    if proposal_config.is_multi_proposal:
        assert event_counts["proposal_starts"] >= proposal_config.task_count
        assert event_counts["proposal_ends"] >= proposal_config.task_count
    assert run_stats["raw_detailed_result_candidates_or_outputs_retained"] is False
    payload = manifest["output_payload"]
    assert payload["hash_algorithm"] == "sha256"
    assert payload["tree_hash"]
    assert {item["path"] for item in payload["files"]}
    assert "manifest.json" not in {item["path"] for item in payload["files"]}

    loaded = dspy.load(str(res.out_dir), allow_pickle=True)
    assert not hasattr(loaded, "detailed_results")
    with dspy.context(lm=DSPyTypedLMAdapter(StubProvider())):
        pred = loaded(question="hello")
    assert isinstance(pred, dspy.Prediction)


def test_optimizer_explicit_openai_provider_uses_canonical_config_without_gepa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_OPENAI_COMPAT_MODEL", "local-model")
    monkeypatch.setenv("DSPX_OPENAI_COMPAT_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("DSPX_OPENAI_COMPAT_TIMEOUT", "4")
    monkeypatch.setattr(
        openai_provider,
        "_default_transport",
        lambda: httpx.MockTransport(
            lambda request: httpx.Response(500, request=request)
        ),
    )

    lm = _resolve_optimizer_provider("openai-compatible")

    assert type(lm.provider) is OpenAICompatibleProvider
    assert lm.model == "local-model"
    assert lm.provider.effective_timeout == 4.0
    assert lm.provider.provider_events == ()


@pytest.mark.parametrize("fails", [False, True])
def test_optimizer_restores_prior_global_lm_before_closing_owned_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fails: bool,
) -> None:
    original_lm = getattr(dspy.settings, "lm", None)
    prior_lm = DSPyTypedLMAdapter(StubProvider())
    dspy.configure(lm=prior_lm)
    owned_provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:8000/v1",
        model="local-model",
        _transport=httpx.MockTransport(
            lambda request: httpx.Response(500, request=request)
        ),
    )
    owned = DSPyTypedLMAdapter(owned_provider)

    def fake_impl(**kwargs: object) -> GEPAResult:
        owned_lms_value = kwargs["_owned_lms"]
        assert isinstance(owned_lms_value, list)
        owned_lms = cast(list[DSPyTypedLMAdapter], owned_lms_value)
        owned_lms.append(owned)
        dspy.configure(lm=owned)
        if fails:
            raise RuntimeError("optimizer failed")
        return GEPAResult(
            out_dir=tmp_path,
            input_keys=["question"],
            output_keys=["answer"],
            chosen_output_keys=["answer"],
            metric="exact",
            output_weights={},
            student_provider="openai-compatible",
            reflection_provider="openai-compatible",
        )

    monkeypatch.setattr(optimize_service, "_run_gepa_optimize_impl", fake_impl)
    try:
        if fails:
            with pytest.raises(RuntimeError, match="optimizer failed"):
                run_gepa_optimize(
                    program_path=tmp_path / "program.py",
                    train_path=tmp_path / "train.json",
                    out_dir=tmp_path / "out",
                )
        else:
            result = run_gepa_optimize(
                program_path=tmp_path / "program.py",
                train_path=tmp_path / "train.json",
                out_dir=tmp_path / "out",
            )
            assert result.student_provider == "openai-compatible"
        assert getattr(dspy.settings, "lm", None) is prior_lm
        assert owned_provider._client.is_closed
        assert getattr(dspy.settings, "lm", None) is not owned
    finally:
        dspy.configure(lm=original_lm)
