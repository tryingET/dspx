from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dspx.services.program_runtime_outcomes import build_program_runtime_outcomes
from dspx.services.program_service import ProgramIntent, materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt


def _surface(
    *,
    module_id: str,
    primitive: str,
    outputs: list[str] | None = None,
) -> dict[str, Any]:
    surface: dict[str, Any] = {
        "schema_version": "program-module-surface-v1",
        "module_id": module_id,
        "source_kind": "generated_topology_module",
        "primitive": primitive,
        "signature": {
            "name": f"{module_id.title().replace('_', '')}Signature",
            "inputs": ["question"],
            "outputs": outputs or ["answer"],
        },
        "effects": {
            "provider_called": False,
            "tool_called": False,
            "custom_import_loaded": False,
            "network": False,
            "filesystem_read": False,
            "filesystem_write": False,
            "subprocess": False,
            "external_authority": False,
        },
    }
    if primitive in {"ReAct", "ReActV2"}:
        surface["react"] = {
            "declared_tool_refs": [],
            "tool_binding_status": "declared_refs_only_not_bound",
            "tool_binding_allowed": False,
        }
    return surface


def _outcomes_for(*surfaces: dict[str, Any]) -> dict[str, Any]:
    return build_program_runtime_outcomes(
        SimpleNamespace(name="RuntimeOutcomeProgram", objective="Declare outcomes."),
        module_surfaces={"module_surfaces": list(surfaces)},
    )


def _by_module(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["module_id"]): item
        for item in payload["outcomes"]
        if isinstance(item, dict)
    }


def test_predict_runtime_outcome_contract_is_declared_not_trace() -> None:
    payload = _outcomes_for(_surface(module_id="answer", primitive="Predict"))
    outcome = _by_module(payload)["answer"]

    assert payload["schema_version"] == "program-runtime-outcomes-v1"
    assert payload["status"] == "outcome_contracts_declared"
    assert payload["module_outcome_count"] == 1
    assert payload["primitives"] == ["Predict"]
    assert outcome["status"] == "outcome_contract_declared_not_runtime_trace"
    assert outcome["final_outputs"] == ["answer"]
    assert outcome["trace_contract"] == {
        "kind": "prediction",
        "records_history": False,
        "records_tool_call_intents": False,
        "records_tool_call_results": False,
        "termination_reason": "prediction_returned_or_error",
    }
    assert all(value is False for value in outcome["effects"].values())
    assert outcome["non_authority"]["runtime_evidence_only"] is True
    assert outcome["non_authority"]["promotion_authority"] is False
    assert payload["runtime_policy"] == {
        "materialization_executed_modules": False,
        "records_actual_runtime_trace": False,
        "tool_binding_allowed": False,
        "live_external_retriever_allowed": False,
        "network_allowed": False,
        "filesystem_access_allowed": False,
        "react_v2_tools_require_program_tool_contracts": True,
    }


@pytest.mark.parametrize(
    ("primitive", "trace_kind", "extra"),
    [
        (
            "Retriever",
            "retrieval_selection",
            {
                "records_query": True,
                "records_selected_documents": True,
                "records_scores": True,
                "records_tool_calls": False,
                "termination_reason": "selection_completed",
            },
        ),
        (
            "ReAct",
            "bounded_react_trajectory",
            {
                "records_history": True,
                "records_reasoning": True,
                "records_tool_call_intents": False,
                "records_tool_call_results": False,
                "termination_reason": "finish_or_max_iters",
                "tool_policy": "tools_empty",
                "tool_refs": {
                    "declared_tool_refs": [],
                    "tool_binding_status": "declared_refs_only_not_bound",
                    "tool_binding_allowed": False,
                    "executable_tools": [],
                },
            },
        ),
        (
            "ReActV2",
            "react_v2_structured_trajectory",
            {
                "records_history": True,
                "records_reasoning": True,
                "records_tool_call_intents": True,
                "records_tool_call_results": True,
                "termination_reason": "submit_or_max_iters",
                "tool_policy": "tools_empty_until_program_tool_contracts_exists",
                "experimental": True,
                "tool_refs": {
                    "declared_tool_refs": [],
                    "tool_binding_status": "declared_refs_only_not_bound",
                    "tool_binding_allowed": False,
                    "executable_tools": [],
                },
            },
        ),
        (
            "ProgramOfThought",
            "sandboxed_code_reasoning",
            {
                "records_generated_code": True,
                "records_interpreter_result": True,
                "records_tool_call_intents": False,
                "records_tool_call_results": False,
                "termination_reason": "submit_or_error_or_max_iters",
                "sandbox_policy": "empty_python_interpreter_sandbox",
            },
        ),
    ],
)
def test_runtime_outcome_contracts_cover_bounded_primitives(
    primitive: str,
    trace_kind: str,
    extra: dict[str, Any],
) -> None:
    payload = _outcomes_for(_surface(module_id="module", primitive=primitive))
    outcome = _by_module(payload)["module"]

    assert outcome["primitive"] == primitive
    assert outcome["trace_contract"] == {"kind": trace_kind, **extra}
    assert all(value is False for value in outcome["effects"].values())
    assert outcome["non_authority"]["canonical_mutation"] is False
    assert outcome["non_authority"]["external_mutation"] is False


def test_react_v2_runtime_outcome_preserves_declared_tool_refs_not_bound() -> None:
    surface = _surface(module_id="agent", primitive="ReActV2")
    surface["react"] = {
        "declared_tool_refs": ["lookup_policy"],
        "tool_binding_status": "declared_refs_only_not_bound",
        "tool_binding_allowed": False,
    }

    payload = _outcomes_for(surface)
    outcome = _by_module(payload)["agent"]

    assert outcome["trace_contract"]["tool_refs"] == {
        "declared_tool_refs": ["lookup_policy"],
        "tool_binding_status": "declared_refs_only_not_bound",
        "tool_binding_allowed": False,
        "executable_tools": [],
    }
    assert outcome["effects"]["tool_called"] is False


def test_runtime_outcomes_preserve_explicit_effect_flags_without_authority() -> None:
    surface = _surface(module_id="retriever", primitive="Retriever")
    surface["effects"] = {
        "provider_called": False,
        "tool_called": False,
        "custom_import_loaded": False,
        "network": False,
        "filesystem_read": True,
        "filesystem_write": False,
        "subprocess": False,
        "external_authority": False,
    }

    payload = _outcomes_for(surface)
    outcome = _by_module(payload)["retriever"]

    assert outcome["effects"]["filesystem_read"] is True
    assert outcome["effects"]["network"] is False
    assert outcome["non_authority"]["runtime_evidence_only"] is True
    assert outcome["non_authority"]["oracle_authority"] is False
    assert payload["non_authority"]["governance_authority"] is False


def test_program_replay_detects_runtime_outcomes_artifact_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayRuntimeOutcomesProgram",
        objective="Answer a question from context.",
        inputs=["context", "question"],
        outputs=["answer"],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    replay = check_run_receipt(root / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert replay["checks"]["program_runtime_outcomes_hash_match"] is True
    assert replay["checks"]["program_runtime_outcomes_semantic_valid"] is True

    outcomes_path = root / "program_runtime_outcomes.json"
    outcomes_payload = json.loads(outcomes_path.read_text(encoding="utf-8"))
    outcomes_payload["status"] = "drifted"
    outcomes_path.write_text(
        json.dumps(outcomes_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    drift = check_run_receipt(root / "manifest.json.meta.json")

    assert drift["status"] == "failed"
    assert drift["checks"]["output_hash_match"] is True
    assert drift["checks"]["program_runtime_outcomes_exists"] is True
    assert drift["checks"]["program_runtime_outcomes_hash_match"] is False
    assert drift["checks"]["program_runtime_outcomes_semantic_valid"] is False
    assert "program_evidence_hash_mismatch" in drift["error_codes"]
    assert "program_evidence_declaration_mismatch" in drift["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_hash_mismatch"
        and detail.get("check") == "program_runtime_outcomes_hash_match"
        for detail in drift["error_details"]
    )
    assert any(
        detail.get("code") == "program_evidence_declaration_mismatch"
        and detail.get("check") == "program_runtime_outcomes_semantic_valid"
        for detail in drift["error_details"]
    )
