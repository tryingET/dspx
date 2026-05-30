from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, cast

import pytest

from dspx.services import program_service, program_topology
from dspx.services.program_capabilities import build_program_capability_registry
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_module_surface import build_program_module_surfaces
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt


PIPELINE_TOPOLOGY = {
    "kind": "pipeline",
    "execution_status": "declared_not_materialized",
    "modules": [
        {
            "id": "classify_ticket",
            "primitive": "Predict",
            "signature": {
                "name": "ClassifyTicket",
                "inputs": ["ticket_text"],
                "outputs": ["route"],
            },
            "role": "Classify ticket route.",
        },
        {
            "id": "draft_response",
            "primitive": "chain_of_thought",
            "signature": {
                "name": "DraftResponse",
                "inputs": ["ticket_text", "route"],
                "outputs": ["response"],
            },
            "role": "Draft a response for the selected route.",
        },
    ],
    "edges": [
        {"from": "input", "to": "classify_ticket"},
        {"from": "classify_ticket", "to": "draft_response"},
        {"from": "draft_response", "to": "output"},
    ],
}


def _explicit_topology_intent() -> ProgramIntent:
    return ProgramIntent(
        name="SupportRouterProgram",
        objective="Route support tickets and draft a response.",
        inputs=["ticket_text"],
        outputs=["response"],
        metric="exact_match",
        constraints=["preserve the original ticket facts"],
        topology=PIPELINE_TOPOLOGY,
        examples=[
            {
                "inputs": {"ticket_text": "Billing invoice is wrong"},
                "outputs": {"response": "We will help review the billing invoice."},
            }
        ],
    )


def test_program_intent_rejects_stale_schema_version() -> None:
    with pytest.raises(ValueError, match="program-intent-v2"):
        ProgramIntent.model_validate(
            {"schema_version": "program-intent-v1", "objective": "x"}
        )

    with pytest.raises(ValueError, match="program-intent-v2"):
        ProgramIntent.model_validate(
            {"schema_version": "not-a-schema", "objective": "x"}
        )


def test_explicit_pipeline_topology_is_normalized_and_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    real_run = program_service.subprocess.run
    subprocess_calls: list[list[str]] = []

    def spy_run(
        command: list[str], *args: Any, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        command_text = [str(part) for part in command]
        command_names = [Path(part).name for part in command_text]
        assert "ak" not in command_names
        assert "oracle" not in command_names
        assert "program-refine" not in command_names
        assert "program-promote" not in command_names
        subprocess_calls.append(command_text)
        return cast(
            subprocess.CompletedProcess[str], real_run(command, *args, **kwargs)
        )

    monkeypatch.setattr(program_service.subprocess, "run", spy_run)

    intent = _explicit_topology_intent()
    assert intent.topology["modules"][1]["primitive"] == "ChainOfThought"

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)

    intent_payload = json.loads((root / "intent.json").read_text(encoding="utf-8"))
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    execution_episode = json.loads(
        (root / "execution_episode.json").read_text(encoding="utf-8")
    )
    receipt = json.loads((root / "manifest.json.meta.json").read_text(encoding="utf-8"))

    assert intent_payload["topology"]["kind"] == "pipeline"
    assert intent_payload["topology"]["execution_status"] == (
        "declared_not_materialized"
    )
    assert [module["id"] for module in intent_payload["topology"]["modules"]] == [
        "classify_ticket",
        "draft_response",
    ]
    assert intent_payload["topology"]["modules"][1]["primitive"] == ("ChainOfThought")

    assert plan["topology"] == intent_payload["topology"]
    assert plan["declared_topology"] == intent_payload["topology"]
    assert plan["topology"]["kind"] == "pipeline"
    assert plan["topology"]["execution_status"] == "declared_not_materialized"
    assert plan["topology_execution_status"] == "pipeline_materialized"
    assert plan["materialized_topology"]["kind"] == "pipeline"
    assert plan["materialized_topology"]["execution_status"] == "pipeline_materialized"
    assert [module["id"] for module in plan["materialized_topology"]["modules"]] == [
        "classify_ticket",
        "draft_response",
    ]
    assert plan["materialization_scope"]["topology_declared"] is True
    assert plan["materialization_scope"]["topology_materialized"] is True
    assert plan["materialization_scope"]["current_renderer"] == (
        "pipeline_topology_renderer"
    )

    assert manifest["intent"]["topology"] == intent_payload["topology"]
    assert manifest["program_plan"]["topology"] == plan["topology"]
    assert (
        manifest["program_plan"]["materialization_scope"]
        == (plan["materialization_scope"])
    )
    assert manifest["topology_execution"] == execution_episode["topology_execution"]
    assert manifest["topology_execution"] == {
        "declared_topology_present": True,
        "declared_topology_kind": "pipeline",
        "materialized": True,
        "status": "pipeline_materialized",
        "current_renderer": "pipeline_topology_renderer",
        "materialized_topology_kind": "pipeline",
        "notes": [
            "Explicit pipeline topology was rendered into signature.py, module.py, and program.py.",
            "Routing supports only simple when.field/equals clauses; no executable expressions are evaluated.",
        ],
    }
    assert (
        manifest["receipt_bundle"]["evidence"]["topology_execution"]
        == (manifest["topology_execution"])
    )
    assert (
        receipt["run_summary"]["topology_execution"] == manifest["topology_execution"]
    )
    assert receipt["program_topology_execution"] == manifest["topology_execution"]
    assert receipt["program_plan"]["topology"] == plan["topology"]
    assert receipt["program_intent"]["topology"] == intent_payload["topology"]

    signature_text = (root / "signature.py").read_text(encoding="utf-8")
    module_text = (root / "module.py").read_text(encoding="utf-8")
    program_text = (root / "program.py").read_text(encoding="utf-8")
    assert "class ClassifyTicket" in signature_text
    assert "class DraftResponse" in signature_text
    assert "class ClassifyTicketModule" in module_text
    assert "class DraftResponseModule" in module_text
    assert "DECLARED_TOPOLOGY" in program_text
    assert "pipeline_materialized" in program_text
    assert "pipeline_topology_renderer" in program_text
    assert "def build_program() -> dspy.Module:" in program_text
    assert "def build_student(*, use_cot: bool = False) -> dspy.Module:" in program_text
    assert "def configure_observability(" in program_text
    assert "def _receipt_manifest_hash() -> str:" in program_text
    assert "return _receipt_manifest_hash() or _current_manifest_hash()" in program_text
    assert "def run_with_observability(" in program_text
    assert (root / "eval_behavior.py").exists()
    assert (root / "behavior_episode.json").exists()
    assert subprocess_calls
    assert all(
        "oracle" not in [Path(part).name for part in call] for call in subprocess_calls
    )


def test_explicit_router_pipeline_materializes_three_modules_and_runs_harnesses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    topology = {
        "kind": "pipeline",
        "execution_status": "declared_not_materialized",
        "modules": [
            {
                "id": "classify_intent",
                "primitive": "Predict",
                "signature": {
                    "name": "ClassifyIntent",
                    "inputs": ["ticket_text"],
                    "outputs": ["intent"],
                },
            },
            {
                "id": "answer_billing",
                "primitive": "ChainOfThought",
                "signature": {
                    "name": "AnswerBillingQuestion",
                    "inputs": ["ticket_text"],
                    "outputs": ["answer"],
                },
            },
            {
                "id": "answer_technical",
                "primitive": "ChainOfThought",
                "signature": {
                    "name": "AnswerTechnicalQuestion",
                    "inputs": ["ticket_text"],
                    "outputs": ["answer"],
                },
            },
        ],
        "edges": [
            {"from": "input", "to": "classify_intent"},
            {
                "from": "classify_intent",
                "to": "answer_billing",
                "when": {"field": "intent", "equals": "billing"},
            },
            {
                "from": "classify_intent",
                "to": "answer_technical",
                "when": {"field": "intent", "equals": "technical"},
            },
            {"from": "answer_billing", "to": "output"},
            {"from": "answer_technical", "to": "output"},
        ],
    }
    intent = ProgramIntent(
        name="SupportRouterProgram",
        objective="Route a support ticket to a billing or technical answer path.",
        inputs=["ticket_text"],
        outputs=["answer"],
        metric="exact_match",
        constraints=["use only the supplied ticket text"],
        topology=topology,
        examples=[
            {
                "inputs": {"ticket_text": "My invoice is wrong"},
                "outputs": {"answer": "billing"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)

    signature_text = (root / "signature.py").read_text(encoding="utf-8")
    module_text = (root / "module.py").read_text(encoding="utf-8")
    program_text = (root / "program.py").read_text(encoding="utf-8")
    assert "class ClassifyIntent" in signature_text
    assert "class AnswerBillingQuestion" in signature_text
    assert "class AnswerTechnicalQuestion" in signature_text
    assert "class ClassifyIntentModule" in module_text
    assert "class AnswerBillingQuestionModule" in module_text
    assert "class AnswerTechnicalQuestionModule" in module_text
    assert "class SupportRouterProgramPipelineProgram" in program_text
    assert "def build_program() -> dspy.Module:" in program_text
    assert "def build_student(*, use_cot: bool = False) -> dspy.Module:" in program_text

    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert plan["topology"]["kind"] == "pipeline"
    assert [module["id"] for module in plan["topology"]["modules"]] == [
        "classify_intent",
        "answer_billing",
        "answer_technical",
    ]
    assert plan["topology"]["edges"][1]["when"] == {
        "field": "intent",
        "equals": "billing",
    }
    assert (
        plan["declared_topology"]
        == json.loads((root / "intent.json").read_text(encoding="utf-8"))["topology"]
    )
    assert plan["materialized_topology"]["kind"] == "pipeline"
    assert plan["materialization_scope"]["topology_materialized"] is True
    assert manifest["topology_execution"]["materialized"] is True
    assert manifest["topology_execution"]["status"] == "pipeline_materialized"
    assert manifest["program_promotion_review"]["promotion_state"] == "not_promoted"
    assert manifest["execution_episode"]["non_authority"]["oracle_ranking"] is False
    assert manifest["execution_episode"]["non_authority"]["external_mutation"] is False

    assert (root / "behavior_results.json").exists()
    assert (root / "oracle_evidence.json").exists()
    assert (root / "eval_behavior.py").exists()
    assert (root / "behavior_episode.json").exists()
    for filename in ("eval_smoke.py", "eval_examples.py"):
        result = subprocess.run(
            [sys.executable, filename],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"


@pytest.mark.parametrize(
    ("topology", "message"),
    [
        (
            {
                **PIPELINE_TOPOLOGY,
                "modules": [
                    PIPELINE_TOPOLOGY["modules"][0],
                    {**PIPELINE_TOPOLOGY["modules"][1], "id": "classify_ticket"},
                ],
            },
            "module ids must be unique",
        ),
        (
            {
                **PIPELINE_TOPOLOGY,
                "edges": [{"from": "classify_ticket", "to": "missing_module"}],
            },
            "edges must reference input, output, or declared module ids",
        ),
        (
            {
                **PIPELINE_TOPOLOGY,
                "modules": [
                    {
                        **PIPELINE_TOPOLOGY["modules"][0],
                        "signature": {
                            "name": "ClassifyTicket",
                            "inputs": ["ticket_text"],
                        },
                    }
                ],
                "edges": [{"from": "input", "to": "classify_ticket"}],
            },
            "signature.outputs must be a list",
        ),
        (
            {
                **PIPELINE_TOPOLOGY,
                "modules": [
                    {
                        **PIPELINE_TOPOLOGY["modules"][0],
                        "signature": {
                            "name": "ClassifyTicket",
                            "inputs": ["bad-field"],
                            "outputs": ["route"],
                        },
                    }
                ],
                "edges": [{"from": "input", "to": "classify_ticket"}],
            },
            "must be a valid Python identifier",
        ),
        (
            {
                **PIPELINE_TOPOLOGY,
                "edges": [
                    {"from": "input", "to": "classify_ticket"},
                    {
                        "from": "classify_ticket",
                        "to": "draft_response",
                        "when": "route == billing",
                    },
                ],
            },
            "when clauses must be objects",
        ),
    ],
)
def test_invalid_explicit_topology_fails_validation(
    topology: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ProgramIntent(
            name="BrokenTopologyProgram",
            objective="Reject invalid topology.",
            inputs=["ticket_text"],
            outputs=["response"],
            topology=topology,
        )


def test_pipeline_dag_scheduler_executes_out_of_order_fan_in_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    topology = {
        "kind": "pipeline",
        "execution_status": "declared_not_materialized",
        "modules": [
            {
                "id": "compose_answer",
                "primitive": "ChainOfThought",
                "signature": {
                    "name": "ComposeAnswer",
                    "inputs": ["facts", "risk"],
                    "outputs": ["answer"],
                },
            },
            {
                "id": "extract_facts",
                "primitive": "Predict",
                "signature": {
                    "name": "ExtractFacts",
                    "inputs": ["ticket_text"],
                    "outputs": ["facts"],
                },
            },
            {
                "id": "score_risk",
                "primitive": "Predict",
                "signature": {
                    "name": "ScoreRisk",
                    "inputs": ["ticket_text"],
                    "outputs": ["risk"],
                },
            },
        ],
        "edges": [
            {"from": "input", "to": "extract_facts"},
            {"from": "input", "to": "score_risk"},
            {"from": "extract_facts", "to": "compose_answer"},
            {"from": "score_risk", "to": "compose_answer"},
            {"from": "compose_answer", "to": "output"},
        ],
    }
    intent = ProgramIntent(
        name="OutOfOrderDagProgram",
        objective="Extract facts and score risk before composing an answer.",
        inputs=["ticket_text"],
        outputs=["answer"],
        topology=topology,
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)

    for module_name in ["program", "module", "signature"]:
        sys.modules.pop(module_name, None)
    sys.path.insert(0, str(root))
    try:
        spec = importlib.util.spec_from_file_location(
            "generated_out_of_order_dag_program", root / "program.py"
        )
        assert spec is not None and spec.loader is not None
        generated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generated)
        program = generated.build_program()
        calls: list[str] = []

        class StubModule:
            def __init__(self, module_id: str, outputs: dict[str, str]) -> None:
                self.module_id = module_id
                self.outputs = outputs

            def __call__(self, **kwargs: object) -> object:
                calls.append(self.module_id)
                return generated.dspy.Prediction(**self.outputs)

        program.extract_facts = StubModule("extract_facts", {"facts": "known facts"})
        program.score_risk = StubModule("score_risk", {"risk": "low"})
        program.compose_answer = StubModule(
            "compose_answer",
            {"answer": "known facts / low"},
        )
        prediction = program(ticket_text="billing ticket")
    finally:
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass
        for module_name in ["program", "module", "signature"]:
            sys.modules.pop(module_name, None)

    assert calls == ["extract_facts", "score_risk", "compose_answer"]
    assert prediction.answer == "known facts / low"
    assert program._last_runtime_trace["scheduler_events"] == [
        {"status": "completed", "missing_outputs": [], "pending": []}
    ]
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"


def test_pipeline_topology_rejects_cyclic_module_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    topology = {
        "kind": "pipeline",
        "execution_status": "declared_not_materialized",
        "modules": [
            {
                "id": "module_a",
                "primitive": "Predict",
                "signature": {"name": "ModuleA", "inputs": ["b"], "outputs": ["a"]},
            },
            {
                "id": "module_b",
                "primitive": "Predict",
                "signature": {"name": "ModuleB", "inputs": ["a"], "outputs": ["b"]},
            },
        ],
        "edges": [
            {"from": "module_a", "to": "module_b"},
            {"from": "module_b", "to": "module_a"},
            {"from": "module_a", "to": "output"},
        ],
    }
    intent = ProgramIntent(
        name="CyclicPipelineProgram",
        objective="Reject cyclic topology.",
        inputs=["question"],
        outputs=["a"],
        topology=topology,
    )

    with pytest.raises(ValueError, match="must be acyclic"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")
    assert not (tmp_path / "program" / "manifest.json").exists()


def test_pipeline_topology_rejects_missing_direct_data_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    topology = {
        "kind": "pipeline",
        "execution_status": "declared_not_materialized",
        "modules": [
            {
                "id": "extract_facts",
                "primitive": "Predict",
                "signature": {
                    "name": "ExtractFacts",
                    "inputs": ["ticket_text"],
                    "outputs": ["facts"],
                },
            },
            {
                "id": "compose_answer",
                "primitive": "ChainOfThought",
                "signature": {
                    "name": "ComposeAnswer",
                    "inputs": ["facts"],
                    "outputs": ["answer"],
                },
            },
        ],
        "edges": [
            {"from": "input", "to": "extract_facts"},
            {"from": "input", "to": "compose_answer"},
            {"from": "compose_answer", "to": "output"},
        ],
    }
    intent = ProgramIntent(
        name="MissingDependencyPipelineProgram",
        objective="Reject missing direct dependency edge.",
        inputs=["ticket_text"],
        outputs=["answer"],
        topology=topology,
    )

    with pytest.raises(ValueError, match="direct inbound module outputs"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")
    assert not (tmp_path / "program" / "manifest.json").exists()


def test_pipeline_scheduler_raises_when_no_branch_produces_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    topology = {
        "kind": "pipeline",
        "execution_status": "declared_not_materialized",
        "modules": [
            {
                "id": "classify_intent",
                "primitive": "Predict",
                "signature": {
                    "name": "ClassifyIntentForRuntimeStall",
                    "inputs": ["ticket_text"],
                    "outputs": ["intent"],
                },
            },
            {
                "id": "answer_billing",
                "primitive": "ChainOfThought",
                "signature": {
                    "name": "AnswerBillingRuntimeStall",
                    "inputs": ["ticket_text"],
                    "outputs": ["answer"],
                },
            },
        ],
        "edges": [
            {"from": "input", "to": "classify_intent"},
            {
                "from": "classify_intent",
                "to": "answer_billing",
                "when": {"field": "intent", "equals": "billing"},
            },
            {"from": "answer_billing", "to": "output"},
        ],
    }
    intent = ProgramIntent(
        name="RuntimeBranchMissProgram",
        objective="Raise when no route produces an answer.",
        inputs=["ticket_text"],
        outputs=["answer"],
        topology=topology,
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)

    for module_name in ["program", "module", "signature"]:
        sys.modules.pop(module_name, None)
    sys.path.insert(0, str(root))
    try:
        spec = importlib.util.spec_from_file_location(
            "generated_runtime_branch_miss_program", root / "program.py"
        )
        assert spec is not None and spec.loader is not None
        generated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generated)
        program = generated.build_program()

        class ClassifierStub:
            def __call__(self, **kwargs: object) -> object:
                return generated.dspy.Prediction(intent="technical")

        program.classify_intent = ClassifierStub()
        with pytest.raises(RuntimeError, match="scheduler stalled"):
            program(ticket_text="not billing")
        trace = program._last_runtime_trace
        assert trace["scheduler_events"] == [
            {
                "status": "scheduler_stalled",
                "missing_outputs": ["answer"],
                "pending": ["answer_billing"],
            }
        ]
        assert trace["module_calls"][0]["module_id"] == "classify_intent"
    finally:
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass
        for module_name in ["program", "module", "signature"]:
            sys.modules.pop(module_name, None)


def test_pipeline_scheduler_honors_conditional_output_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    topology = {
        "kind": "pipeline",
        "execution_status": "declared_not_materialized",
        "modules": [
            {
                "id": "answer_ticket",
                "primitive": "Predict",
                "signature": {
                    "name": "AnswerTicketConditionalOutput",
                    "inputs": ["ticket_text"],
                    "outputs": ["answer"],
                },
            },
        ],
        "edges": [
            {"from": "input", "to": "answer_ticket"},
            {
                "from": "answer_ticket",
                "to": "output",
                "when": {"field": "ticket_text", "equals": "ALLOW"},
            },
        ],
    }
    intent = ProgramIntent(
        name="ConditionalOutputProgram",
        objective="Return answer only when output edge condition permits it.",
        inputs=["ticket_text"],
        outputs=["answer"],
        topology=topology,
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)

    for module_name in ["program", "module", "signature"]:
        sys.modules.pop(module_name, None)
    sys.path.insert(0, str(root))
    try:
        spec = importlib.util.spec_from_file_location(
            "generated_conditional_output_program", root / "program.py"
        )
        assert spec is not None and spec.loader is not None
        generated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generated)
        program = generated.build_program()

        class AnswerStub:
            def __call__(self, **kwargs: object) -> object:
                return generated.dspy.Prediction(answer="allowed answer")

        program.answer_ticket = AnswerStub()
        with pytest.raises(RuntimeError, match="completed without declared outputs"):
            program(ticket_text="DENY")
        assert program(ticket_text="ALLOW").answer == "allowed answer"
    finally:
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass
        for module_name in ["program", "module", "signature"]:
            sys.modules.pop(module_name, None)


def test_pipeline_inline_retriever_materializes_bounded_local_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent = ProgramIntent(
        name="RetrieverPipelineProgram",
        objective="Retrieve local inline passages, then answer.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "retrieve_context",
                    "primitive": "Retriever",
                    "signature": {
                        "name": "RetrieveContext",
                        "inputs": ["question"],
                        "outputs": ["passages"],
                    },
                    "retriever": {
                        "mode": "inline_corpus",
                        "k": 1,
                        "documents": [
                            {
                                "id": "billing_doc",
                                "text": "Billing invoices can be corrected by the accounts team.",
                            },
                            {
                                "id": "technical_doc",
                                "text": "Technical crashes require logs and reproduction steps.",
                            },
                        ],
                    },
                },
                {
                    "id": "answer_question",
                    "primitive": "ChainOfThought",
                    "signature": {
                        "name": "AnswerQuestion",
                        "inputs": ["question", "passages"],
                        "outputs": ["answer"],
                    },
                },
            ],
            "edges": [
                {"from": "input", "to": "retrieve_context"},
                {"from": "retrieve_context", "to": "answer_question"},
                {"from": "answer_question", "to": "output"},
            ],
        },
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    module_text = (root / "module.py").read_text(encoding="utf-8")
    assert "_select_inline_documents" in module_text
    assert "generated_bounded_inline_retriever_adapter" not in module_text
    assert "dspy.Retrieve" not in module_text
    assert "dspy.settings.rm" not in module_text
    assert "importlib" not in module_text

    module_surfaces = json.loads(
        (root / "module_surfaces.json").read_text(encoding="utf-8")
    )
    registry = json.loads(
        (root / "program_capability_registry.json").read_text(encoding="utf-8")
    )
    retriever_surface = module_surfaces["module_surfaces"][0]
    assert retriever_surface["primitive"] == "Retriever"
    assert retriever_surface["capability_ref"] == {
        "schema_version": "program-capability-contract-v1",
        "capability_id": "dspy.primitive.Retriever",
        "primitive": "Retriever",
        "status": "materializable_with_bounded_inline_adapter",
        "materializable": True,
        "runtime_binding": "generated_bounded_inline_retriever_adapter",
    }
    assert retriever_surface["effects"]["provider_called"] is False
    assert retriever_surface["effects"]["tool_called"] is False
    assert retriever_surface["effects"]["filesystem_read"] is False
    assert retriever_surface["effects"]["network"] is False
    assert ("retrieve_context", "dspy.primitive.Retriever") in {
        (ref["module_id"], ref["capability_id"])
        for ref in registry["used_capability_refs"]
    }

    spec = importlib.util.spec_from_file_location(
        "generated_retriever_module", root / "module.py"
    )
    assert spec is not None and spec.loader is not None
    generated_module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(root))
    try:
        spec.loader.exec_module(generated_module)
        retriever = generated_module.RetrieveContextModule()
        prediction = retriever(question="How do I fix a billing invoice?")
    finally:
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass
        sys.modules.pop("signature", None)
        sys.modules.pop("generated_retriever_module", None)
    passages = json.loads(prediction.passages)
    assert passages[0]["id"] == "billing_doc"
    assert passages[0]["score"] > 0
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"


def test_pipeline_local_corpus_snapshot_retriever_materializes_bounded_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    corpus_path = tmp_path / "corpus.jsonl"
    corpus_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "doc_id": "billing_doc",
                        "body": "Billing invoices can be corrected by the accounts team.",
                    }
                ),
                json.dumps(
                    {
                        "doc_id": "technical_doc",
                        "body": "Technical crashes require logs and reproduction steps.",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    intent_source = tmp_path / "intent.json"
    intent_source.write_text(
        '{"schema_version":"program-intent-v2"}\n', encoding="utf-8"
    )
    intent = ProgramIntent(
        name="SnapshotRetrieverPipelineProgram",
        objective="Snapshot a local corpus, retrieve passages, then answer.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "retrieve_then_answer",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "retrieve_context",
                    "primitive": "Retriever",
                    "signature": {
                        "name": "RetrieveSnapshotContext",
                        "inputs": ["question"],
                        "outputs": ["passages"],
                    },
                    "retriever": {
                        "mode": "local_corpus_snapshot",
                        "path": "corpus.jsonl",
                        "id_field": "doc_id",
                        "text_field": "body",
                        "k": 1,
                    },
                },
                {
                    "id": "answer_question",
                    "primitive": "ChainOfThought",
                    "signature": {
                        "name": "AnswerSnapshotQuestion",
                        "inputs": ["question", "passages"],
                        "outputs": ["answer"],
                    },
                },
            ],
            "edges": [
                {"from": "input", "to": "retrieve_context"},
                {"from": "retrieve_context", "to": "answer_question"},
                {"from": "answer_question", "to": "output"},
            ],
        },
    )

    artifact = materialize_program_from_intent(
        intent, outdir=tmp_path / "program", intent_source=intent_source
    )
    root = Path(artifact.root_path)
    snapshot = json.loads(
        (root / "retriever_snapshots.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    module_text = (root / "module.py").read_text(encoding="utf-8")

    assert snapshot["schema_version"] == "program-retriever-snapshots-v1"
    assert snapshot["snapshot_count"] == 1
    assert snapshot["snapshots"][0]["module_id"] == "retrieve_context"
    assert snapshot["snapshots"][0]["document_count"] == 2
    assert snapshot["runtime_policy"] == {
        "generated_runtime_reads_source_corpus": False,
        "live_external_retriever_bound": False,
        "network_allowed": False,
        "tool_binding_allowed": False,
        "provider_call_allowed": False,
    }
    assert plan["retriever_snapshots"]["path"] == "retriever_snapshots.json"
    assert manifest["retriever_snapshots"] == snapshot
    assert (
        manifest["retriever_snapshots_artifact"]["content_hash"]
        == (
            manifest["receipt_bundle"]["evidence"]["surface_hashes"][
                "retriever_snapshots.json"
            ]
        )
    )
    assert {
        surface["kind"] for surface in manifest["candidate_assembly"]["surfaces"]
    } >= {"retriever_snapshots"}
    assert "dspy.Retrieve" not in module_text
    assert "importlib" not in module_text
    assert "corpus.jsonl" not in module_text
    assert "billing_doc" in module_text
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"


def test_local_corpus_snapshot_retriever_requires_intent_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="SnapshotRetrieverRequiresSourceProgram",
        objective="Reject source-less local corpus snapshots.",
        inputs=["question"],
        outputs=["passages"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "retrieve_context",
                    "primitive": "Retriever",
                    "signature": {
                        "name": "RetrieveRequiresSource",
                        "inputs": ["question"],
                        "outputs": ["passages"],
                    },
                    "retriever": {
                        "mode": "local_corpus_snapshot",
                        "path": "corpus.jsonl",
                        "k": 1,
                    },
                }
            ],
            "edges": [
                {"from": "input", "to": "retrieve_context"},
                {"from": "retrieve_context", "to": "output"},
            ],
        },
    )

    with pytest.raises(ValueError, match="requires intent_source"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")
    assert not (tmp_path / "program" / "manifest.json").exists()


def test_local_corpus_snapshot_retriever_rejects_parent_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent_dir = tmp_path / "intents"
    intent_dir.mkdir()
    intent_source = intent_dir / "intent.json"
    intent_source.write_text("{}\n", encoding="utf-8")
    (tmp_path / "corpus.jsonl").write_text(
        json.dumps({"id": "doc", "text": "text"}) + "\n",
        encoding="utf-8",
    )
    intent = ProgramIntent(
        name="SnapshotRetrieverTraversalProgram",
        objective="Reject path traversal for local corpus snapshots.",
        inputs=["question"],
        outputs=["passages"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "retrieve_context",
                    "primitive": "Retriever",
                    "signature": {
                        "name": "RetrieveTraversal",
                        "inputs": ["question"],
                        "outputs": ["passages"],
                    },
                    "retriever": {
                        "mode": "local_corpus_snapshot",
                        "path": "../corpus.jsonl",
                        "k": 1,
                    },
                }
            ],
            "edges": [
                {"from": "input", "to": "retrieve_context"},
                {"from": "retrieve_context", "to": "output"},
            ],
        },
    )

    with pytest.raises(ValueError, match="must stay under the intent file directory"):
        materialize_program_from_intent(
            intent, outdir=tmp_path / "program", intent_source=intent_source
        )
    assert not (tmp_path / "program" / "manifest.json").exists()


def test_local_corpus_snapshot_retriever_rejects_oversized_source_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    corpus_path = tmp_path / "corpus.jsonl"
    corpus_path.write_text("x" * 1_000_001, encoding="utf-8")
    intent_source = tmp_path / "intent.json"
    intent_source.write_text("{}\n", encoding="utf-8")
    intent = ProgramIntent(
        name="SnapshotRetrieverOversizedProgram",
        objective="Reject oversized local corpus snapshots.",
        inputs=["question"],
        outputs=["passages"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "retrieve_context",
                    "primitive": "Retriever",
                    "signature": {
                        "name": "RetrieveOversized",
                        "inputs": ["question"],
                        "outputs": ["passages"],
                    },
                    "retriever": {
                        "mode": "local_corpus_snapshot",
                        "path": "corpus.jsonl",
                        "k": 1,
                    },
                }
            ],
            "edges": [
                {"from": "input", "to": "retrieve_context"},
                {"from": "retrieve_context", "to": "output"},
            ],
        },
    )

    with pytest.raises(ValueError, match="source file exceeds byte limit"):
        materialize_program_from_intent(
            intent, outdir=tmp_path / "program", intent_source=intent_source
        )
    assert not (tmp_path / "program" / "manifest.json").exists()


def test_retrieve_then_answer_topology_materializes_bounded_inline_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent = ProgramIntent(
        name="RetrieveThenAnswerProgram",
        objective="Retrieve local inline passages, then answer.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "retrieve_then_answer",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "retrieve_context",
                    "primitive": "Retriever",
                    "signature": {
                        "name": "RetrieveContext",
                        "inputs": ["question"],
                        "outputs": ["passages"],
                    },
                    "retriever": {
                        "mode": "inline_corpus",
                        "k": 1,
                        "documents": [
                            {
                                "id": "billing_doc",
                                "text": "Billing invoices can be corrected by accounts.",
                            }
                        ],
                    },
                },
                {
                    "id": "answer_question",
                    "primitive": "ChainOfThought",
                    "signature": {
                        "name": "AnswerQuestion",
                        "inputs": ["question", "passages"],
                        "outputs": ["answer"],
                    },
                },
            ],
            "edges": [
                {"from": "input", "to": "retrieve_context"},
                {"from": "retrieve_context", "to": "answer_question"},
                {"from": "answer_question", "to": "output"},
            ],
        },
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    plan = manifest["program_plan"]
    assert plan["topology"]["kind"] == "retrieve_then_answer"
    assert plan["topology_execution_status"] == "retrieve_then_answer_materialized"
    assert (
        plan["materialization_scope"]["current_renderer"]
        == "retrieve_then_answer_topology_renderer"
    )
    assert (
        manifest["topology_execution"]["status"] == "retrieve_then_answer_materialized"
    )
    module_surfaces = json.loads(
        (root / "module_surfaces.json").read_text(encoding="utf-8")
    )
    assert {
        surface["source_kind"] for surface in module_surfaces["module_surfaces"]
    } == {"generated_topology_module"}
    program_text = (root / "program.py").read_text(encoding="utf-8")
    assert (
        "TOPOLOGY_EXECUTION_STATUS = 'retrieve_then_answer_materialized'"
        in program_text
    )
    assert "dspy.Retrieve" not in (root / "module.py").read_text(encoding="utf-8")
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"


@pytest.mark.parametrize("kind", ["router"])
def test_named_bounded_topologies_materialize_as_declared_dags(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent = ProgramIntent(
        name="NamedTopologyProgram",
        objective=f"Run the declared {kind} DAG.",
        inputs=["text"],
        outputs=["answer"],
        topology={
            "kind": kind,
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "prepare",
                    "primitive": "Predict",
                    "signature": {
                        "name": "Prepare",
                        "inputs": ["text"],
                        "outputs": ["draft"],
                    },
                },
                {
                    "id": "answer",
                    "primitive": "ChainOfThought",
                    "signature": {
                        "name": "Answer",
                        "inputs": ["text", "draft"],
                        "outputs": ["answer"],
                    },
                },
            ],
            "edges": [
                {"from": "input", "to": "prepare"},
                {"from": "prepare", "to": "answer"},
                {"from": "answer", "to": "output"},
            ],
        },
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["program_plan"]["topology"]["kind"] == kind
    assert (
        manifest["program_plan"]["topology_execution_status"] == f"{kind}_materialized"
    )
    assert manifest["topology_execution"]["status"] == f"{kind}_materialized"
    assert (
        manifest["topology_execution"]["current_renderer"]
        == f"{kind}_topology_renderer"
    )
    module_surfaces = json.loads(
        (root / "module_surfaces.json").read_text(encoding="utf-8")
    )
    assert {
        surface["source_kind"] for surface in module_surfaces["module_surfaces"]
    } == {"generated_topology_module"}
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"


def test_generate_critique_revise_named_topology_requires_semantic_stage_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="BrokenGenerateCritiqueReviseProgram",
        objective="Draft, critique, and revise an answer.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "generate_critique_revise",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "generate_draft",
                    "primitive": "ChainOfThought",
                    "role": "generate_draft",
                    "signature": {
                        "name": "GenerateDraftBroken",
                        "inputs": ["question"],
                        "outputs": ["draft"],
                    },
                },
                {
                    "id": "critique_draft",
                    "primitive": "ChainOfThought",
                    "role": "critique_draft",
                    "signature": {
                        "name": "CritiqueDraftBroken",
                        "inputs": ["question", "draft"],
                        "outputs": ["critique"],
                    },
                },
                {
                    "id": "revise_final",
                    "primitive": "ChainOfThought",
                    "role": "revise_final",
                    "signature": {
                        "name": "ReviseFinalBroken",
                        "inputs": ["question", "critique"],
                        "outputs": ["answer"],
                    },
                },
            ],
            "edges": [
                {"from": "input", "to": "generate_draft"},
                {"from": "generate_draft", "to": "critique_draft"},
                {"from": "critique_draft", "to": "revise_final"},
                {"from": "revise_final", "to": "output"},
            ],
        },
    )

    with pytest.raises(ValueError, match="generate_draft outputs to feed revise_final"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")


def test_extract_transform_validate_named_topology_requires_semantic_stage_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="BrokenExtractTransformValidateProgram",
        objective="Extract, transform, and validate an answer.",
        inputs=["text"],
        outputs=["answer"],
        topology={
            "kind": "extract_transform_validate",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "extract_evidence",
                    "primitive": "Predict",
                    "role": "extract",
                    "signature": {
                        "name": "ExtractEvidenceBroken",
                        "inputs": ["text"],
                        "outputs": ["evidence"],
                    },
                },
                {
                    "id": "validate_final",
                    "primitive": "ChainOfThought",
                    "role": "validate",
                    "signature": {
                        "name": "ValidateFinalBroken",
                        "inputs": ["text", "evidence"],
                        "outputs": ["answer"],
                    },
                },
            ],
            "edges": [
                {"from": "input", "to": "extract_evidence"},
                {"from": "extract_evidence", "to": "validate_final"},
                {"from": "validate_final", "to": "output"},
            ],
        },
    )

    with pytest.raises(ValueError, match=r"missing roles: \['transform'\]"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")


def test_retrieve_then_answer_fails_closed_when_retriever_does_not_feed_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent = ProgramIntent(
        name="DisconnectedRetrieveThenAnswerProgram",
        objective="Retrieve local inline passages, then answer.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "retrieve_then_answer",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "retrieve_context",
                    "primitive": "Retriever",
                    "signature": {
                        "name": "RetrieveContext",
                        "inputs": ["question"],
                        "outputs": ["passages"],
                    },
                    "retriever": {
                        "mode": "inline_corpus",
                        "k": 1,
                        "documents": [
                            {"id": "billing_doc", "text": "Billing invoices."}
                        ],
                    },
                },
                {
                    "id": "answer_question",
                    "primitive": "ChainOfThought",
                    "signature": {
                        "name": "AnswerQuestion",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                },
            ],
            "edges": [
                {"from": "input", "to": "retrieve_context"},
                {"from": "input", "to": "answer_question"},
                {"from": "answer_question", "to": "output"},
            ],
        },
    )

    with pytest.raises(ValueError, match="Retriever output to feed"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")

    assert not (tmp_path / "program" / "intent_normalization.json").exists()


def test_pipeline_retriever_fails_closed_without_bounded_inline_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="InvalidRetrieverProgram",
        objective="Reject unbounded retriever modules.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "retrieve_context",
                    "primitive": "Retriever",
                    "signature": {
                        "name": "RetrieveContext",
                        "inputs": ["question"],
                        "outputs": ["passages"],
                    },
                }
            ],
            "edges": [{"from": "input", "to": "retrieve_context"}],
        },
    )

    with pytest.raises(ValueError, match="supports only module primitives"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")
    assert not (tmp_path / "program" / "manifest.json").exists()


@pytest.mark.parametrize(
    "retriever",
    [
        {"mode": "remote", "k": 1, "documents": [{"id": "doc", "text": "text"}]},
        {
            "mode": "inline_corpus",
            "k": 99,
            "documents": [{"id": "doc", "text": "text"}],
        },
        {"mode": "inline_corpus", "k": 1, "documents": []},
        {
            "mode": "local_corpus_snapshot",
            "k": 99,
            "path": "corpus.jsonl",
        },
        {
            "mode": "local_corpus_snapshot",
            "k": 1,
        },
        {
            "mode": "inline_corpus",
            "k": 1,
            "documents": [{"id": "doc", "text": "text", "path": "secret.md"}],
        },
    ],
)
def test_pipeline_retriever_contract_validation_rejects_unsafe_shapes(
    retriever: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        ProgramIntent(
            name="InvalidRetrieverContractProgram",
            objective="Reject unsafe retriever contracts.",
            inputs=["question"],
            outputs=["answer"],
            topology={
                "kind": "pipeline",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "retrieve_context",
                        "primitive": "Retriever",
                        "signature": {
                            "name": "RetrieveContext",
                            "inputs": ["question"],
                            "outputs": ["passages"],
                        },
                        "retriever": retriever,
                    }
                ],
                "edges": [{"from": "input", "to": "retrieve_context"}],
            },
        )


@pytest.mark.parametrize(
    "extra_key",
    ["provider", "endpoint", "tool", "import"],
)
def test_pipeline_retriever_rejects_external_module_level_keys(extra_key: str) -> None:
    with pytest.raises(ValueError, match="unsupported keys"):
        ProgramIntent(
            name="ExternalRetrieverRejectedProgram",
            objective="Reject external retriever hints on materialized retriever module.",
            inputs=["question"],
            outputs=["answer"],
            topology={
                "kind": "pipeline",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "retrieve_context",
                        "primitive": "Retriever",
                        "signature": {
                            "name": "RetrieveContext",
                            "inputs": ["question"],
                            "outputs": ["passages"],
                        },
                        "retriever": {
                            "mode": "inline_corpus",
                            "k": 1,
                            "documents": [{"id": "doc", "text": "text"}],
                        },
                        extra_key: "external",
                    }
                ],
                "edges": [{"from": "input", "to": "retrieve_context"}],
            },
        )


@pytest.mark.parametrize(
    ("primitive", "expected_call", "config"),
    [
        ("ReAct", "dspy.ReAct", {"tools": [], "max_iters": 1}),
        ("ProgramOfThought", "dspy.ProgramOfThought", {"max_iters": 1}),
    ],
)
def test_bounded_reasoning_primitives_materialize_without_external_tools(
    primitive: str,
    expected_call: str,
    config: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    module = {
        "id": "reason_answer",
        "primitive": primitive,
        "signature": {
            "name": "ReasonAnswer",
            "inputs": ["question"],
            "outputs": ["answer"],
        },
        **config,
    }
    intent = ProgramIntent(
        name=f"{primitive}PipelineProgram",
        objective=f"Use bounded {primitive} reasoning to answer.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [module],
            "edges": [
                {"from": "input", "to": "reason_answer"},
                {"from": "reason_answer", "to": "output"},
            ],
        },
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    module_text = (root / "module.py").read_text(encoding="utf-8")
    assert expected_call in module_text
    assert "dspy.Tool" not in module_text
    assert "importlib" not in module_text
    if primitive == "ReAct":
        assert "tools=[]" in module_text
    else:
        assert "dspy.PythonInterpreter" in module_text
        assert "enable_network_access=[]" in module_text
        assert "sync_files=False" in module_text

    policy = json.loads(
        (root / "generated_module_policy.json").read_text(encoding="utf-8")
    )
    assert policy["status"] == "passed"
    registry = json.loads(
        (root / "program_capability_registry.json").read_text(encoding="utf-8")
    )
    used = {ref["primitive"]: ref for ref in registry["used_capability_refs"]}
    assert used[primitive]["materializable"] is True
    module_surfaces = json.loads(
        (root / "module_surfaces.json").read_text(encoding="utf-8")
    )
    surface = module_surfaces["module_surfaces"][0]
    assert surface["capability_ref"]["materializable"] is True
    if primitive == "ReAct":
        assert surface["capability_ref"]["runtime_binding"] == (
            "generated_bounded_react_no_tools"
        )
    else:
        assert surface["capability_ref"]["runtime_binding"] == (
            "generated_sandboxed_program_of_thought"
        )
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"


def _react_v2_intent(*, opt_in: bool = False) -> ProgramIntent:
    return ProgramIntent(
        name="ReActV2PipelineProgram",
        objective="Use explicitly enabled experimental ReActV2 reasoning to answer.",
        inputs=["question"],
        outputs=["answer"],
        options={"enable_react_v2_materialization": opt_in},
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "reason_answer",
                    "primitive": "react_v2",
                    "signature": {
                        "name": "ReasonAnswer",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                    "tools": [],
                    "max_iters": 2,
                }
            ],
            "edges": [
                {"from": "input", "to": "reason_answer"},
                {"from": "reason_answer", "to": "output"},
            ],
        },
    )


def test_react_v2_pipeline_requires_explicit_opt_in_for_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setattr(program_topology, "_dspy_react_v2_available", lambda: True)

    with pytest.raises(
        ValueError,
        match="unsupported primitives: \\['ReActV2'\\]",
    ):
        materialize_program_from_intent(
            _react_v2_intent(opt_in=False), outdir=tmp_path / "program"
        )


def test_react_v2_pipeline_fails_closed_when_dspy_lacks_react_v2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setattr(program_topology, "_dspy_react_v2_available", lambda: False)

    with pytest.raises(
        ValueError, match="requires installed DSPy with public dspy.ReActV2"
    ):
        materialize_program_from_intent(
            _react_v2_intent(opt_in=True), outdir=tmp_path / "program"
        )


def test_react_v2_explicit_opt_in_renders_declared_tool_refs_not_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(program_topology, "_dspy_react_v2_available", lambda: True)
    intent = ProgramIntent(
        name="ReActV2ToolRefProgram",
        objective="Use explicitly enabled experimental ReActV2 reasoning with a future tool ref.",
        inputs=["question"],
        outputs=["answer"],
        options={"enable_react_v2_materialization": True},
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "reason_answer",
                    "primitive": "react_v2",
                    "signature": {
                        "name": "ReasonAnswer",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                    "tools": [],
                    "tool_refs": ["lookup_policy"],
                    "max_iters": 2,
                }
            ],
            "edges": [
                {"from": "input", "to": "reason_answer"},
                {"from": "reason_answer", "to": "output"},
            ],
        },
        capabilities={
            "declarations": [
                {"id": "lookup_policy", "kind": "tool", "effect_class": "pure"}
            ]
        },
    )

    module_text, _metadata = program_topology.render_pipeline_module_surface(intent)
    module_surfaces = build_program_module_surfaces(intent)

    assert "_DECLARED_TOOL_REFS = ['lookup_policy']" in module_text
    assert "_TOOL_BINDING_STATUS = 'declared_refs_only_not_bound'" in module_text
    assert "dspy.ReActV2(ReasonAnswer, tools=[], max_iters=2)" in module_text
    assert "dspy.Tool" not in module_text
    surface = module_surfaces["module_surfaces"][0]
    assert surface["react"]["declared_tool_refs"] == ["lookup_policy"]
    assert surface["react"]["tool_binding_allowed"] is False


def test_react_v2_explicit_opt_in_renders_no_tool_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(program_topology, "_dspy_react_v2_available", lambda: True)
    intent = _react_v2_intent(opt_in=True)

    module_text, metadata = program_topology.render_pipeline_module_surface(intent)
    module_surfaces = build_program_module_surfaces(intent)
    registry = build_program_capability_registry(intent)

    assert metadata["module_classes"] == ["ReasonAnswerModule"]
    assert "dspy.ReActV2(ReasonAnswer, tools=[], max_iters=2)" in module_text
    assert "dspy.Tool" not in module_text
    assert "_TOOL_BINDING_ALLOWED = False" in module_text
    surface = module_surfaces["module_surfaces"][0]
    assert surface["primitive"] == "ReActV2"
    assert surface["capability_ref"] == {
        "schema_version": "program-capability-contract-v1",
        "capability_id": "dspy.primitive.ReActV2",
        "primitive": "ReActV2",
        "status": "experimental_materializable_with_empty_tools_explicit_opt_in",
        "materializable": True,
        "runtime_binding": "generated_experimental_react_v2_no_tools",
    }
    used = registry["used_capability_refs"][0]
    assert used["primitive"] == "ReActV2"
    assert used["materializable"] is True
    assert used["runtime_binding"] == "generated_experimental_react_v2_no_tools"


@pytest.mark.parametrize(
    ("module_patch", "match"),
    [
        ({"primitive": "ReAct", "tools": ["external_search"]}, "empty tools list"),
        ({"primitive": "ReAct", "max_iters": 99}, "max_iters"),
        ({"primitive": "ProgramOfThought", "max_iters": 99}, "max_iters"),
        ({"primitive": "ProgramOfThought", "tools": []}, "unsupported keys"),
    ],
)
def test_bounded_reasoning_primitives_reject_unsafe_shapes(
    module_patch: dict[str, object], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        ProgramIntent(
            name="UnsafeReasoningPrimitiveProgram",
            objective="Reject unsafe reasoning primitive config.",
            inputs=["question"],
            outputs=["answer"],
            topology={
                "kind": "pipeline",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "reason_answer",
                        "signature": {
                            "name": "ReasonAnswer",
                            "inputs": ["question"],
                            "outputs": ["answer"],
                        },
                        **module_patch,
                    }
                ],
                "edges": [
                    {"from": "input", "to": "reason_answer"},
                    {"from": "reason_answer", "to": "output"},
                ],
            },
        )


def test_unsupported_pipeline_primitive_fails_when_materializing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="UnsupportedPipelineProgram",
        objective="Reject unsupported executable topology primitives.",
        inputs=["ticket_text"],
        outputs=["answer"],
        topology={
            **PIPELINE_TOPOLOGY,
            "modules": [
                PIPELINE_TOPOLOGY["modules"][0],
                {
                    **cast(Mapping[str, object], PIPELINE_TOPOLOGY["modules"][1]),
                    "primitive": "Custom",
                },
            ],
        },
    )

    with pytest.raises(ValueError, match="supports only module primitives"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")
    assert not (tmp_path / "program" / "manifest.json").exists()


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
