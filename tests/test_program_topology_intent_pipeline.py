# summary: "Tests explicit, inferred-name, routed, retriever, and bounded-reasoning topology materialization and runtime behavior."
# read_when:
#   - "Changing pipeline DAG rendering, scheduling, retriever adapters, named topology execution, or bounded reasoning primitives."

from __future__ import annotations

import importlib.util
from importlib.metadata import version
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from dspx.services import program_service
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.program_surfaces import render_program_code
from dspx.services.program_topology import (
    render_pipeline_module_surface,
    render_pipeline_signature_surface,
)
from dspx.services.run_replay_service import check_run_receipt
from program_topology_intent_helpers import (
    _explicit_topology_intent,
)


def test_protected_snapshot_profile_renders_policy_compatible_static_program() -> None:
    intent = _explicit_topology_intent().model_copy(
        update={"runtime": {"generated_source_profile": "protected_snapshot"}}
    )

    program_code = render_program_code(intent)
    module_code, _ = render_pipeline_module_surface(intent)
    signature_code, _ = render_pipeline_signature_surface(intent)

    from dspx.services.program_runtime_episode import (
        validate_generated_program_snapshot_sources,
    )

    validate_generated_program_snapshot_sources(
        {
            "program": program_code,
            "module": module_code,
            "signature": signature_code,
        }
    )
    assert "dspx.tracing" not in program_code
    assert "getattr(" not in program_code
    assert "hasattr(" not in program_code
    assert "prediction = self.classify_ticket(**kwargs)" in program_code
    assert "prediction = self.draft_response(**kwargs)" in program_code
    assert "def configure_observability(" in program_code
    assert "    return False" in program_code


def test_default_profile_preserves_prediction_mapping_compatibility(
    tmp_path: Path,
) -> None:
    intent = _explicit_topology_intent()
    program_code = render_program_code(intent)
    module_code, _ = render_pipeline_module_surface(intent)
    signature_code, _ = render_pipeline_signature_surface(intent)
    (tmp_path / "program.py").write_text(program_code, encoding="utf-8")
    (tmp_path / "module.py").write_text(module_code, encoding="utf-8")
    (tmp_path / "signature.py").write_text(signature_code, encoding="utf-8")

    class LegacyPrediction:
        def to_dict(self) -> dict[str, str]:
            return {"response": "legacy-compatible"}

    sys.path.insert(0, str(tmp_path))
    try:
        spec = importlib.util.spec_from_file_location(
            "generated_default_profile_program", tmp_path / "program.py"
        )
        assert spec is not None and spec.loader is not None
        generated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generated)
        assert generated._prediction_mapping(LegacyPrediction()) == {
            "response": "legacy-compatible"
        }
    finally:
        sys.path.remove(str(tmp_path))
        for name in ("module", "signature", "generated_default_profile_program"):
            sys.modules.pop(name, None)

    assert "elif hasattr(prediction, output_name):" in program_code
    assert "getattr(prediction, output_name)" in program_code


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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
@pytest.mark.slow
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


def test_program_of_thought_renderer_uses_exact_reviewed_interpreter_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    intent = ProgramIntent(
        name="ProgramOfThoughtLifecycleProgram",
        objective="Use bounded ProgramOfThought reasoning.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "reason_answer",
                    "primitive": "ProgramOfThought",
                    "signature": {
                        "name": "ReasonAnswer",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                    "max_iters": 1,
                }
            ],
            "edges": [
                {"from": "input", "to": "reason_answer"},
                {"from": "reason_answer", "to": "output"},
            ],
        },
    )
    module_code, _ = render_pipeline_module_surface(intent)
    assert "excluded_lm_generated_runtime_code" in module_code

    (tmp_path / "signature.py").write_text(
        "import dspy\n"
        "class ReasonAnswer(dspy.Signature):\n"
        "    question: str = dspy.InputField()\n"
        "    answer: str = dspy.OutputField()\n",
        encoding="utf-8",
    )
    module_path = tmp_path / "module.py"
    module_path.write_text(module_code, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "signature", raising=False)
    spec = importlib.util.spec_from_file_location(
        "generated_program_of_thought_lifecycle", module_path
    )
    assert spec is not None and spec.loader is not None
    generated = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generated)

    instance = generated.ReasonAnswerModule()
    assert instance._TRUSTED_LOCAL_CORE_PRODUCTION_STATUS == (
        "excluded_lm_generated_runtime_code"
    )
    dspy_version = version("dspy")
    if dspy_version in {"3.3.0", "3.3.1"}:
        assert "interpreter_factory=lambda:" in module_code
        assert "interpreter=dspy.PythonInterpreter" not in module_code
        first = instance.predict._interpreter_factory()
        second = instance.predict._interpreter_factory()
        assert first is not second
        interpreters = [first, second]
    elif dspy_version == "3.1.3":
        assert "interpreter=dspy.PythonInterpreter" in module_code
        assert "interpreter_factory=" not in module_code
        interpreters = [instance.predict.interpreter]
    else:  # pragma: no cover - renderer fails closed before this branch
        pytest.fail(f"unexpected reviewed DSPy version: {dspy_version}")

    for interpreter in interpreters:
        assert interpreter.enable_read_paths == []
        assert interpreter.enable_write_paths == []
        assert interpreter.enable_env_vars == []
        assert interpreter.enable_network_access == []
        assert interpreter.tools == {}
        assert interpreter.sync_files is False


@pytest.mark.parametrize(
    ("primitive", "expected_call", "config"),
    [
        ("ReAct", "dspy.ReAct", {"tools": [], "max_iters": 1}),
        ("ProgramOfThought", "dspy.ProgramOfThought", {"max_iters": 1}),
    ],
)
@pytest.mark.slow
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
        assert "excluded_lm_generated_runtime_code" in module_text

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
