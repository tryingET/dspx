# summary: "Tests prompt-driven topology inference, richer module selection, opt-out behavior, and single-module fallback."
# read_when:
#   - "Changing prompt-to-topology inference cues, inferred module primitives, renderer selection, or default topology behavior."

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt


@pytest.mark.slow
def test_prompt_inferred_modules_choose_richer_pipeline_when_prompt_cues_are_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent = ProgramIntent(
        name="PromptInferredSupportProgram",
        objective=(
            "Route support tickets by classifying billing versus technical issues, "
            "then draft a helpful response with rationale."
        ),
        inputs=["ticket_text"],
        outputs=["response"],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    intent_payload = json.loads((root / "intent.json").read_text(encoding="utf-8"))
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    module_surfaces = json.loads(
        (root / "module_surfaces.json").read_text(encoding="utf-8")
    )

    assert intent_payload["topology"] == {}
    assert plan["declared_topology"] is None
    assert plan["inferred_topology"]["origin"] == "prompt_inferred"
    assert plan["inferred_topology"]["kind"] == "pipeline"
    assert plan["materialization_scope"]["topology_declared"] is False
    assert plan["materialization_scope"]["topology_inferred"] is True
    assert plan["materialization_scope"]["topology_materialized"] is True
    assert plan["materialization_scope"]["current_renderer"] == (
        "prompt_inferred_pipeline_renderer"
    )
    assert [module["id"] for module in plan["materialized_topology"]["modules"]] == [
        "classify_route",
        "produce_response",
    ]
    assert [
        module["primitive"] for module in plan["materialized_topology"]["modules"]
    ] == ["Predict", "ChainOfThought"]

    assert manifest["topology_execution"]["declared_topology_present"] is False
    assert manifest["topology_execution"]["inferred_topology_present"] is True
    assert manifest["topology_execution"]["materialized"] is True
    assert manifest["topology_execution"]["status"] == "pipeline_materialized"
    assert manifest["topology_execution"]["current_renderer"] == (
        "prompt_inferred_pipeline_renderer"
    )
    assert module_surfaces["module_surface_count"] == 2
    assert [
        surface["source_kind"] for surface in module_surfaces["module_surfaces"]
    ] == [
        "generated_prompt_inferred_module",
        "generated_prompt_inferred_module",
    ]
    assert [surface["primitive"] for surface in module_surfaces["module_surfaces"]] == [
        "Predict",
        "ChainOfThought",
    ]

    signature_text = (root / "signature.py").read_text(encoding="utf-8")
    module_text = (root / "module.py").read_text(encoding="utf-8")
    program_text = (root / "program.py").read_text(encoding="utf-8")
    assert "class ClassifyRoute" in signature_text
    assert "class ProduceResponse" in signature_text
    assert "class ClassifyRouteModule" in module_text
    assert "class ProduceResponseModule" in module_text
    assert "dspy.ChainOfThought(ProduceResponse)" in module_text
    assert "INFERRED_TOPOLOGY" in program_text
    assert "prompt_inferred_pipeline_renderer" in program_text

    replay = check_run_receipt(root / "manifest.json.meta.json")
    assert replay["status"] == "ok"


@pytest.mark.slow
def test_prompt_inferred_reasoning_intent_uses_chain_of_thought_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent = ProgramIntent(
        name="ReviewFindingsProgram",
        objective="Review the evidence and explain the strongest recommendation.",
        inputs=["evidence"],
        outputs=["recommendation"],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    module_surfaces = json.loads(
        (root / "module_surfaces.json").read_text(encoding="utf-8")
    )

    assert plan["declared_topology"] is None
    assert plan["inferred_topology"]["execution_status"] == (
        "prompt_inferred_not_materialized"
    )
    assert plan["materialization_scope"]["topology_inferred"] is True
    assert [module["id"] for module in plan["materialized_topology"]["modules"]] == [
        "reason_recommendation"
    ]
    assert [
        module["primitive"] for module in plan["materialized_topology"]["modules"]
    ] == ["ChainOfThought"]
    assert module_surfaces["module_surfaces"][0]["source_kind"] == (
        "generated_prompt_inferred_module"
    )
    assert module_surfaces["module_surfaces"][0]["primitive"] == "ChainOfThought"
    assert "dspy.ChainOfThought(ReasonRecommendation)" in (
        root / "module.py"
    ).read_text(encoding="utf-8")


@pytest.mark.slow
def test_prompt_module_inference_can_be_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="InferenceDisabledProgram",
        objective=(
            "Route support tickets by classifying billing versus technical issues, "
            "then draft a helpful response with rationale."
        ),
        inputs=["ticket_text"],
        outputs=["response"],
        options={"module_inference": False},
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    module_surfaces = json.loads(
        (root / "module_surfaces.json").read_text(encoding="utf-8")
    )

    assert plan["inferred_topology"] is None
    assert plan["topology"]["kind"] == "single_module"
    assert plan["materialization_scope"]["current_renderer"] == (
        "single_module_scaffold"
    )
    assert module_surfaces["module_surface_count"] == 1
    assert module_surfaces["module_surfaces"][0]["primitive"] == "Predict"


@pytest.mark.slow
def test_classification_only_prompt_does_not_infer_generation_pipeline_from_output_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ClassifyOnlyProgram",
        objective="Classify sentiment for a support ticket.",
        inputs=["ticket_text"],
        outputs=["answer"],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))

    assert plan["inferred_topology"] is None
    assert plan["topology"]["kind"] == "single_module"


@pytest.mark.slow
def test_default_single_module_intent_keeps_current_materialization_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="DefaultTopologyProgram",
        objective="Answer a question.",
        inputs=["question"],
        outputs=["answer"],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    intent_payload = json.loads((root / "intent.json").read_text(encoding="utf-8"))
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    assert intent_payload["topology"] == {}
    assert plan["topology"]["kind"] == "single_module"
    assert plan["declared_topology"] is None
    assert plan["materialization_scope"]["topology_declared"] is False
    assert plan["materialization_scope"]["topology_materialized"] is True
    assert manifest["topology_execution"]["declared_topology_present"] is False
    assert manifest["topology_execution"]["materialized"] is True
    assert manifest["topology_execution"]["status"] == (
        "single_module_scaffold_materialized"
    )
    assert (root / "program.py").exists()
    assert not (root / "eval_behavior.py").exists()
