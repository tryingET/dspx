from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dspx.services import program_service
from dspx.services.program_intent import ProgramIntent
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
        command: list[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        command_text = [str(part) for part in command]
        command_names = [Path(part).name for part in command_text]
        assert "ak" not in command_names
        assert "oracle" not in command_names
        assert "program-refine" not in command_names
        assert "program-promote" not in command_names
        assert "eval_behavior.py" not in command_names
        subprocess_calls.append(command_text)
        return real_run(command, *args, **kwargs)

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
    assert not (root / "eval_behavior.py").exists()
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
    assert not (root / "eval_behavior.py").exists()
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
                {**PIPELINE_TOPOLOGY["modules"][1], "primitive": "ReAct"},
            ],
        },
    )

    with pytest.raises(ValueError, match="supports only module primitives"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")
    assert not (tmp_path / "program" / "manifest.json").exists()


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
