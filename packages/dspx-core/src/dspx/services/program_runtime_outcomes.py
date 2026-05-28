from __future__ import annotations

from importlib import metadata
from typing import Any, Mapping

PROGRAM_RUNTIME_OUTCOMES_SCHEMA = "program-runtime-outcomes-v1"

_EFFECT_KEYS = {
    "provider_called",
    "tool_called",
    "custom_import_loaded",
    "network",
    "filesystem_read",
    "filesystem_write",
    "subprocess",
    "external_authority",
}

_NON_AUTHORITY = {
    "runtime_evidence_only": True,
    "oracle_authority": False,
    "ranking_authority": False,
    "promotion_authority": False,
    "activation_authority": False,
    "governance_authority": False,
    "canonical_mutation": False,
    "external_mutation": False,
}


def _dspy_runtime_metadata() -> dict[str, Any]:
    for distribution in ("dspy", "dspy-ai"):
        try:
            version = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            continue
        return {
            "distribution": distribution,
            "version": version,
            "prerelease": any(marker in version for marker in ("a", "b", "rc")),
        }
    return {"distribution": None, "version": None, "prerelease": False}


def _effects(surface: Mapping[str, Any]) -> dict[str, bool]:
    raw = surface.get("effects")
    payload = dict(raw) if isinstance(raw, Mapping) else {}
    return {key: bool(payload.get(key, False)) for key in sorted(_EFFECT_KEYS)}


def _trace_contract_for_primitive(primitive: str) -> dict[str, Any]:
    if primitive == "Retriever":
        return {
            "kind": "retrieval_selection",
            "records_query": True,
            "records_selected_documents": True,
            "records_scores": True,
            "records_tool_calls": False,
            "termination_reason": "selection_completed",
        }
    if primitive == "ReAct":
        return {
            "kind": "bounded_react_trajectory",
            "records_history": True,
            "records_reasoning": True,
            "records_tool_call_intents": False,
            "records_tool_call_results": False,
            "termination_reason": "finish_or_max_iters",
            "tool_policy": "tools_empty",
        }
    if primitive == "ReActV2":
        return {
            "kind": "react_v2_structured_trajectory",
            "records_history": True,
            "records_reasoning": True,
            "records_tool_call_intents": True,
            "records_tool_call_results": True,
            "termination_reason": "submit_or_max_iters",
            "tool_policy": "tools_empty_until_program_tool_contracts_exists",
            "experimental": True,
        }
    if primitive == "ProgramOfThought":
        return {
            "kind": "sandboxed_code_reasoning",
            "records_generated_code": True,
            "records_interpreter_result": True,
            "records_tool_call_intents": False,
            "records_tool_call_results": False,
            "termination_reason": "submit_or_error_or_max_iters",
            "sandbox_policy": "empty_python_interpreter_sandbox",
        }
    return {
        "kind": "prediction",
        "records_history": False,
        "records_tool_call_intents": False,
        "records_tool_call_results": False,
        "termination_reason": "prediction_returned_or_error",
    }


def _outcome_contract(surface: Mapping[str, Any]) -> dict[str, Any]:
    primitive = str(surface.get("primitive") or "Predict")
    signature = dict(surface.get("signature") or {})
    return {
        "module_id": str(surface.get("module_id") or ""),
        "primitive": primitive,
        "source_kind": str(surface.get("source_kind") or ""),
        "signature": {
            "name": str(signature.get("name") or ""),
            "inputs": [str(item) for item in signature.get("inputs", [])],
            "outputs": [str(item) for item in signature.get("outputs", [])],
        },
        "status": "outcome_contract_declared_not_runtime_trace",
        "final_outputs": [str(item) for item in signature.get("outputs", [])],
        "trace_contract": _trace_contract_for_primitive(primitive),
        "effects": _effects(surface),
        "non_authority": dict(_NON_AUTHORITY),
    }


def build_program_runtime_outcomes(
    intent: Any,
    *,
    module_surfaces: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the normalized runtime outcome/trajectory contract sidecar.

    This artifact deliberately records the shape of runtime outcomes that a
    generated candidate may emit. It is not a claim that module calls happened
    during materialization, and it does not grant ranking, promotion, activation,
    governance, or external authority.
    """

    raw_surfaces = module_surfaces.get("module_surfaces")
    surfaces = (
        [dict(item) for item in raw_surfaces if isinstance(item, Mapping)]
        if isinstance(raw_surfaces, list)
        else []
    )
    contracts = [_outcome_contract(surface) for surface in surfaces]
    primitives = sorted({contract["primitive"] for contract in contracts})
    return {
        "schema_version": PROGRAM_RUNTIME_OUTCOMES_SCHEMA,
        "status": "outcome_contracts_declared",
        "intent": {
            "name": str(getattr(intent, "name", "")),
            "objective": str(getattr(intent, "objective", "")),
        },
        "dspy_runtime": _dspy_runtime_metadata(),
        "module_outcome_count": len(contracts),
        "primitives": primitives,
        "outcomes": contracts,
        "runtime_policy": {
            "materialization_executed_modules": False,
            "records_actual_runtime_trace": False,
            "tool_binding_allowed": False,
            "live_external_retriever_allowed": False,
            "network_allowed": False,
            "filesystem_access_allowed": False,
            "react_v2_tools_require_program_tool_contracts": True,
        },
        "non_authority": dict(_NON_AUTHORITY),
        "notes": [
            "This sidecar normalizes the expected runtime outcome/trajectory shape for generated modules.",
            "It is inspired by DSPy ReActV2-style structured history/tool-call/final-submit outcomes, but it does not enable tools or live external retrievers by itself.",
            "Actual behavior evidence remains in behavior_results.json, dataset split behavior results, behavior_episode.json, and later explicit runtime traces when such traces exist.",
        ],
    }
