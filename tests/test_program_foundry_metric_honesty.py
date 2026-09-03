# summary: "Tests AK-5362 metric honesty: concept_coverage GEPA binding, exact-metric refusal, and non-blocking differs signals for non-exact intents."
# read_when:
#   - "Changing program_foundry_gepa_proposal._metric_plan, program_refinement_gepa concept-coverage wrapping, or refinement comparison signals."

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from dspx.services.program_foundry_gepa_proposal import (
    ProgramFoundryGepaProposalError,
    _metric_plan,
)
from dspx.services.program_foundry_gepa_execution_contract import (
    _SUPPORTED_METRICS as EXECUTOR_METRICS,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_refinement import (
    _bounded_refinement,
    _failure_signals_from_behavior,
    _target_surface_for_status,
    comparison_signal_kind,
    metric_is_exact,
)
from dspx.services.program_refinement_gepa import (
    CONCEPT_COVERAGE_PROGRAM_NAME,
    build_program_refinement_gepa_result,
)
from dspx.services.program_service import materialize_program_from_intent
from test_program_refinement_gepa import _fake_gepa, _setup_env

_CRITERIA = [
    {
        "id": "recipe_fidelity",
        "output_field": "answer",
        "evaluator": "concept_coverage",
        "required_concept_groups": [["espresso"], ["170 c", "170 °c"]],
        "forbidden_concepts": [],
        "min_score": 1.0,
    }
]


def _candidate(metric: str | None, criteria: list[dict[str, Any]] | None) -> dict:
    intent: dict[str, Any] = {"metric": metric}
    if criteria is not None:
        intent["quality_criteria"] = criteria
    return {"manifest": {"intent": intent}}


# --- proposal metric plan -------------------------------------------------------


def test_metric_plan_binds_concept_coverage_to_intent_criteria() -> None:
    plan = _metric_plan(_candidate("concept_coverage", _CRITERIA), metric_override=None)
    assert plan["optimizer_metric"] == "concept_coverage"
    assert plan["operator_metric_required"] is False
    assert plan["blockers"] == []
    binding = plan["concept_coverage_binding"]
    assert binding["criterion_ids"] == ["recipe_fidelity"]
    assert len(binding["criteria_sha256"]) == 64
    assert binding["optimizer_backend_metric"] == "exact"

    explicit = _metric_plan(
        _candidate("concept_coverage", _CRITERIA), metric_override="concept_coverage"
    )
    assert explicit["operator_metric_override"] == "concept_coverage"
    assert explicit["optimizer_metric"] == "concept_coverage"
    assert explicit["concept_coverage_binding"] == binding
    assert "concept_coverage" in EXECUTOR_METRICS


@pytest.mark.parametrize("override", ["exact", "exact_match"])
def test_metric_plan_refuses_exact_over_concept_coverage_intent(override: str) -> None:
    with pytest.raises(ProgramFoundryGepaProposalError, match="dishonest"):
        _metric_plan(
            _candidate("concept_coverage", _CRITERIA), metric_override=override
        )


def test_metric_plan_refuses_concept_coverage_without_matching_intent() -> None:
    with pytest.raises(ProgramFoundryGepaProposalError, match="requires an intent"):
        _metric_plan(
            _candidate("exact_match", None), metric_override="concept_coverage"
        )
    with pytest.raises(ProgramFoundryGepaProposalError, match="quality_criteria"):
        _metric_plan(_candidate("concept_coverage", []), metric_override=None)
    with pytest.raises(ProgramFoundryGepaProposalError, match="must be"):
        _metric_plan(_candidate("concept_coverage", _CRITERIA), metric_override="bogus")
    exact = _metric_plan(_candidate("exact_match", None), metric_override="exact")
    assert exact["optimizer_metric"] == "exact"
    assert "concept_coverage_binding" not in exact


# --- refinement comparison signals ----------------------------------------------


def _behavior() -> dict[str, Any]:
    return {
        "examples": [
            {
                "status": "failed",
                "expected_outputs": {"answer": "Espresso brownies bake at 170 °C."},
                "observed_outputs": {"answer": "Bake the espresso brownies at 170 C."},
                "notes": ["output mismatch for answer"],
            }
        ]
    }


def test_non_exact_metric_downgrades_mismatch_to_non_blocking_differs() -> None:
    assert metric_is_exact(None) and metric_is_exact("exact") and metric_is_exact("")
    assert not metric_is_exact("concept_coverage") and not metric_is_exact("f1")
    assert comparison_signal_kind("exact_match") == "mismatch"
    assert comparison_signal_kind("concept_coverage") == "differs"

    exact = _failure_signals_from_behavior(_behavior(), output_fields=["answer"])
    assert exact == ["mismatch:answer"]
    relaxed = _failure_signals_from_behavior(
        _behavior(), output_fields=["answer"], exact_metric=False
    )
    assert relaxed == ["differs:answer"]
    assert not any(signal.startswith("mismatch:") for signal in relaxed)

    surface, reason = _target_surface_for_status("failed", relaxed)
    assert surface == "module"
    assert "non-blocking" in reason and "mismatch" not in reason.split(";")[0]
    exact_surface, exact_reason = _target_surface_for_status("failed", exact)
    assert exact_surface == "module" and "output mismatch for answer" in exact_reason

    bounded = _bounded_refinement(
        behavior_status="failed", proposal_status="proposed", signals=relaxed
    )
    change = bounded["proposed_changes"][0]
    assert change["change_type"] == "improve_declared_quality_coverage"
    assert "not exact" in change["rationale"]
    assert "exact_match" not in change["rationale"]
    strict = _bounded_refinement(
        behavior_status="failed", proposal_status="proposed", signals=exact
    )
    assert strict["proposed_changes"][0]["change_type"] == "tighten_output_mapping"


# --- GEPA concept-coverage wrapper ----------------------------------------------


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("dspx_test_cc_wrapper", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    modules_before = dict(sys.modules)
    path_before = list(sys.path)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.clear()
        sys.modules.update(modules_before)
        sys.path[:] = path_before
    # The wrapper must not leak the candidate's modules into the process.
    assert "program" not in sys.modules or sys.modules["program"] is modules_before.get(
        "program"
    )
    assert "module" not in sys.modules or sys.modules["module"] is modules_before.get(
        "module"
    )
    return module


def test_gepa_concept_coverage_binds_wrapper_program_and_exact_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "DSPX_REPLAY_FIXTURE_JSON",
        json.dumps({"reasoning": "bounded", "answer": "Espresso brownies at 170 C."}),
    )
    calls = _fake_gepa(monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="RecipeFidelityProgram",
            objective="Assess a recipe evidence package.",
            inputs=["evidence"],
            outputs=["answer"],
            metric="concept_coverage",
            quality_criteria=_CRITERIA,
            examples=[
                {
                    "inputs": {"evidence": "espresso brownies bake at 170 C"},
                    "outputs": {"answer": "Espresso brownies bake at 170 °C."},
                }
            ],
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    outdir = tmp_path / "program-gepa"

    result = build_program_refinement_gepa_result(
        manifest_path=program_root / "manifest.json",
        outdir=outdir,
        metric="concept_coverage",
        max_metric_calls=2,
    )

    assert len(calls) == 1
    wrapper = outdir / "_gepa_inputs" / CONCEPT_COVERAGE_PROGRAM_NAME
    assert Path(calls[0]["program_path"]) == wrapper
    assert calls[0]["metric"] == "exact"
    gepa = result["gepa"]
    assert gepa["metric"] == "concept_coverage"
    assert gepa["optimizer_metric"] == "concept_coverage"
    assert gepa["metric_honesty"] == {
        "intent_metric": "concept_coverage",
        "optimizer_metric": "concept_coverage",
        "aligned": True,
    }
    binding = gepa["concept_coverage_binding"]
    assert binding["criterion_ids"] == ["recipe_fidelity"]
    assert binding["optimizer_backend_metric"] == "exact"
    assert Path(binding["candidate_program_path"]) == program_root / "program.py"
    assert Path(binding["wrapper_program_path"]) == wrapper
    assert len(binding["wrapper_program_sha256"]) == 64
    assert "dspx_version" not in wrapper.read_text(encoding="utf-8")
    assert not (program_root / CONCEPT_COVERAGE_PROGRAM_NAME).exists()

    module = _load_module(wrapper)
    assert module.io_spec()["outputs"] == ["answer"]
    passed = module.normalize_output(
        "answer", "irrelevant gold", "Espresso brownies, bake at 170 °C for 35 min."
    )
    assert passed[0] == passed[1] == "concept_coverage[recipe_fidelity]:passed"
    failed = module.normalize_output("answer", "irrelevant gold", "Bake at 350 F.")
    assert failed[0] == "concept_coverage[recipe_fidelity]:passed"
    assert failed[1].startswith("concept_coverage[recipe_fidelity]:failed (")
    assert "matched 0/2 groups" in failed[1]
    assert "missing group indexes [0, 1]" in failed[1]
    # Keys without criteria fall back to the candidate's own normalizer.
    assert module.normalize_output("other", '{"a":1}', '{ "a" : 1 }') == (
        '{"a":1}',
        '{"a":1}',
    )
    assert callable(module.build_student)


def test_gepa_result_records_metric_misalignment_for_exact_over_concept_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    calls = _fake_gepa(monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="RecipeFidelityProgram",
            objective="Assess a recipe evidence package.",
            inputs=["evidence"],
            outputs=["answer"],
            metric="concept_coverage",
            quality_criteria=_CRITERIA,
            examples=[
                {
                    "inputs": {"evidence": "espresso brownies bake at 170 C"},
                    "outputs": {"answer": "Espresso brownies bake at 170 °C."},
                }
            ],
        ),
        outdir=tmp_path / "program",
    )
    result = build_program_refinement_gepa_result(
        manifest_path=Path(artifact.root_path) / "manifest.json",
        outdir=tmp_path / "program-gepa",
        metric="exact",
        max_metric_calls=2,
    )
    assert calls[0]["metric"] == "exact"
    assert result["gepa"]["metric_honesty"]["aligned"] is False
    assert "concept_coverage_binding" not in result["gepa"]
