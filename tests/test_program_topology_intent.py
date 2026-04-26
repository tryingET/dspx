from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dspx.services import program_service
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent


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
    assert plan["topology_execution_status"] == "declared_not_materialized"
    assert plan["materialized_topology"]["kind"] == "single_module"
    assert plan["materialized_topology"]["execution_status"] == (
        "single_module_scaffold_materialized"
    )
    assert plan["materialization_scope"] == {
        "topology_declared": True,
        "topology_materialized": False,
        "current_renderer": "single_module_scaffold",
        "notes": [
            "Explicit topology is preserved as a planning contract.",
            "This slice does not render or execute multi-module topology yet.",
            "The generated Python remains the current single-module scaffold.",
        ],
    }

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
        "materialized": False,
        "status": "declared_not_materialized",
        "current_renderer": "single_module_scaffold",
        "materialized_topology_kind": "single_module",
        "notes": [
            "Explicit topology is declared-only unless materialized is true.",
            "program.py currently delegates to the generated single module scaffold.",
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

    program_text = (root / "program.py").read_text(encoding="utf-8")
    assert "DECLARED_TOPOLOGY" in program_text
    assert "declared_not_materialized" in program_text
    assert "single_module_scaffold" in program_text
    assert not (root / "eval_behavior.py").exists()
    assert subprocess_calls
    assert all(
        "oracle" not in [Path(part).name for part in call] for call in subprocess_calls
    )


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
