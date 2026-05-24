from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from dspx.cache import sha256_text
from dspx.services.program_intent import ProgramIntent, load_program_intent
from dspx.services.program_module_surface import build_program_module_surfaces
from dspx.services.program_topology import (
    prompt_inferred_pipeline_topology,
    validate_materializable_pipeline_topology,
)

PROGRAM_ARCHITECTURE_CANDIDATES_SCHEMA = "program-architecture-candidates-v1"
_PROGRAM_INTENT_SCHEMA = "program-intent-v2"
_FORBIDDEN_OUTPUT_NAMES = {
    "manifest.json",
    "manifest.json.meta.json",
    "plan.json",
    "program.py",
    "module.py",
    "signature.py",
    "module_surfaces.json",
    "execution_episode.json",
    "oracle_evidence.json",
    "behavior_results.json",
}


class ProgramArchitectureError(ValueError):
    """Raised when architecture candidate planning cannot be written safely."""


def _json_text(payload: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _intent_payload(intent: ProgramIntent) -> dict[str, Any]:
    return intent.model_dump(mode="json", exclude_none=True)


def _intent_hash(payload: Mapping[str, Any]) -> str:
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _explicit_materializable_topology(topology: Mapping[str, Any]) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    for raw_module in topology.get("modules", []) or []:
        if not isinstance(raw_module, Mapping):
            continue
        module = dict(raw_module)
        signature = dict(module.get("signature") or {})
        normalized: dict[str, Any] = {
            "id": str(module.get("id") or ""),
            "primitive": str(module.get("primitive") or "Predict"),
            "signature": {
                "name": str(signature.get("name") or module.get("id") or "Module"),
                "inputs": [str(item) for item in signature.get("inputs", [])],
                "outputs": [str(item) for item in signature.get("outputs", [])],
            },
        }
        role = str(module.get("role") or "").strip()
        if role:
            normalized["role"] = role
        if normalized["primitive"] == "Retriever" and "retriever" in module:
            normalized["retriever"] = dict(module.get("retriever") or {})
        modules.append(normalized)
    edges = [
        dict(edge) for edge in topology.get("edges", []) if isinstance(edge, Mapping)
    ]
    return {
        "kind": "pipeline",
        "execution_status": "declared_not_materialized",
        "modules": modules,
        "edges": edges,
    }


def _candidate_intent_payload(
    intent: ProgramIntent,
    *,
    candidate_name: str,
    topology: Mapping[str, Any] | None,
    disable_inference: bool = False,
) -> dict[str, Any]:
    payload = _intent_payload(intent)
    payload["schema_version"] = _PROGRAM_INTENT_SCHEMA
    payload["name"] = candidate_name
    options = dict(payload.get("options") or {})
    if disable_inference:
        options["module_inference"] = False
    else:
        options.setdefault("module_inference", True)
    payload["options"] = options
    if topology is None:
        payload.pop("topology", None)
    else:
        payload["topology"] = _explicit_materializable_topology(topology)
    return payload


def _module_surface_preview(
    candidate_intent_payload: Mapping[str, Any],
) -> dict[str, Any]:
    candidate_intent = ProgramIntent.model_validate(dict(candidate_intent_payload))
    return build_program_module_surfaces(candidate_intent)


def _candidate(
    *,
    candidate_id: str,
    label: str,
    family: str,
    recommendation: str,
    candidate_intent: Mapping[str, Any],
    topology_source: str,
    materializable: bool,
    why: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    intent_text = _json_text(dict(candidate_intent))
    module_surfaces = (
        _module_surface_preview(candidate_intent) if materializable else None
    )
    return {
        "candidate_id": candidate_id,
        "label": label,
        "family": family,
        "status": "materializable"
        if materializable
        else "declared_only_not_materializable",
        "recommendation": recommendation,
        "topology_source": topology_source,
        "topology": dict(candidate_intent.get("topology") or {}),
        "intent_hash": sha256_text(intent_text),
        "intent_payload": dict(candidate_intent),
        "module_surface_preview": module_surfaces,
        "why": why,
        "limitations": limitations,
        "effect": {
            "candidate_materialized": False,
            "provider_called": False,
            "oracle_index_mutated": False,
            "ak_called": False,
            "governance_mutated": False,
            "external_authority_mutated": False,
        },
        "non_authority": _non_authority(),
    }


def _non_authority() -> dict[str, bool]:
    return {
        "planning_only": True,
        "winner_selection": False,
        "ranking_authority": False,
        "promotion_authority": False,
        "activation_authority": False,
        "oracle_authority": False,
        "governance_authority": False,
        "canonical_mutation": False,
        "external_mutation": False,
    }


def build_program_architecture_candidates(intent: ProgramIntent) -> dict[str, Any]:
    """Build a non-authoritative architecture candidate plan for one intent."""

    source_payload = _intent_payload(intent)
    source_hash = _intent_hash(source_payload)
    candidates: list[dict[str, Any]] = []

    baseline_payload = _candidate_intent_payload(
        intent,
        candidate_name=f"{intent.name}BaselinePredict",
        topology=None,
        disable_inference=True,
    )
    candidates.append(
        _candidate(
            candidate_id="baseline_single_predict",
            label="Baseline single Predict scaffold",
            family="single_module",
            recommendation="control_candidate",
            candidate_intent=baseline_payload,
            topology_source="baseline_default",
            materializable=True,
            why=[
                "Provides a low-complexity control candidate for empirical comparison.",
                "Keeps the historical single-module Predict scaffold available even when richer modules are inferred.",
            ],
            limitations=[
                "May underperform when the intent needs routing, evidence extraction, validation, or explicit reasoning.",
            ],
        )
    )

    declared_topology = dict(intent.topology or {})
    inferred_topology = prompt_inferred_pipeline_topology(intent)
    recommended_candidate_id = "baseline_single_predict"
    if declared_topology:
        materializable = declared_topology.get("kind") == "pipeline"
        limitations: list[str] = []
        if materializable:
            declared_payload = _candidate_intent_payload(
                intent,
                candidate_name=f"{intent.name}DeclaredTopology",
                topology=declared_topology,
                disable_inference=True,
            )
            candidate_intent = ProgramIntent.model_validate(dict(declared_payload))
            try:
                validate_materializable_pipeline_topology(candidate_intent)
            except Exception as exc:
                materializable = False
                recommendation = "declared_only"
                why = [
                    "Operator-declared pipeline topology is preserved as a planning candidate but is not materializable by the current renderer.",
                ]
                limitations.append(str(exc))
                limitations.append(
                    "Current execution renderer materializes only Predict/ChainOfThought pipeline modules and explicit Retriever:inline_corpus adapters."
                )
                declared_payload = deepcopy(source_payload)
            else:
                recommendation = "operator_declared_topology"
                recommended_candidate_id = "declared_pipeline"
                why = [
                    "Operator-declared executable pipeline topology takes precedence over prompt inference.",
                ]
        else:
            recommendation = "declared_only"
            why = [
                "Operator-declared topology is preserved as a planning candidate but is not materializable by the current renderer.",
            ]
            limitations.append(
                "Current execution renderer materializes only pipeline topologies over Predict/ChainOfThought and explicit Retriever:inline_corpus adapters."
            )
            declared_payload = deepcopy(source_payload)
        candidates.append(
            _candidate(
                candidate_id="declared_pipeline"
                if materializable
                else "declared_only_topology",
                label="Operator-declared topology",
                family=str(declared_topology.get("kind") or "declared"),
                recommendation=recommendation,
                candidate_intent=declared_payload,
                topology_source="declared",
                materializable=materializable,
                why=why,
                limitations=limitations,
            )
        )
    elif inferred_topology:
        inferred_payload = _candidate_intent_payload(
            intent,
            candidate_name=f"{intent.name}PromptInferred",
            topology=inferred_topology,
            disable_inference=False,
        )
        candidate_intent = ProgramIntent.model_validate(dict(inferred_payload))
        validate_materializable_pipeline_topology(candidate_intent)
        recommended_candidate_id = "prompt_inferred_pipeline"
        candidates.append(
            _candidate(
                candidate_id="prompt_inferred_pipeline",
                label="Prompt-inferred generated module pipeline",
                family="pipeline",
                recommendation="recommended_for_materialization",
                candidate_intent=inferred_payload,
                topology_source="prompt_inferred",
                materializable=True,
                why=[
                    str(
                        inferred_topology.get("inference_reason")
                        or "Prompt cues favor a richer generated module topology."
                    ),
                    "Materializes bounded generated Predict/ChainOfThought modules instead of only the default Predict scaffold.",
                ],
                limitations=[
                    "Inference is deterministic and local; it is not a provider-backed architecture search.",
                    "No arbitrary custom Python imports, tools, external retrievers, ReAct, or ProgramOfThought are executed; Retriever execution remains limited to explicit inline_corpus adapters.",
                ],
            )
        )

    return {
        "schema_version": PROGRAM_ARCHITECTURE_CANDIDATES_SCHEMA,
        "status": "planned_not_materialized",
        "lifecycle_state": "architecture_candidate_plan_ready",
        "intent_identity": {
            "schema_version": intent.schema_version,
            "name": intent.name,
            "objective": intent.objective,
            "inputs": list(intent.inputs),
            "outputs": list(intent.outputs),
            "intent_hash": source_hash,
        },
        "source_intent_payload": source_payload,
        "recommended_candidate_id": recommended_candidate_id,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "next_actions": [
            "Inspect this plan sidecar before materialization.",
            "Materialize a chosen candidate intent with `dspx program-gen --intent <candidate-intent.json> --outdir <candidate-dir>`.",
            "Run receipt replay on generated candidates before using behavior evidence downstream.",
        ],
        "effect": {
            "candidate_materialized": False,
            "portfolio_materialized": False,
            "provider_called": False,
            "oracle_index_mutated": False,
            "ak_called": False,
            "governance_mutated": False,
            "external_authority_mutated": False,
        },
        "non_authority": _non_authority(),
    }


def build_program_architecture_candidates_from_path(
    intent_path: Path,
) -> dict[str, Any]:
    return build_program_architecture_candidates(load_program_intent(intent_path))


def _safe_candidate_id(value: object) -> str:
    candidate_id = str(value or "").strip()
    if not candidate_id:
        raise ProgramArchitectureError("architecture candidate_id must not be blank")
    if candidate_id in {".", ".."} or "/" in candidate_id or "\\" in candidate_id:
        raise ProgramArchitectureError(
            f"architecture candidate_id is path-hostile: {candidate_id!r}"
        )
    return candidate_id


def _validate_output_path(path: Path) -> Path:
    target = path.expanduser().resolve()
    if target.name in _FORBIDDEN_OUTPUT_NAMES:
        raise ProgramArchitectureError(
            f"refusing to write architecture plan to generated candidate artifact path: {target.name}"
        )
    if target.exists() and target.is_dir():
        raise ProgramArchitectureError(
            f"architecture plan output path is a directory: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def write_program_architecture_candidates(
    payload: Mapping[str, Any], out: Path
) -> dict[str, Any]:
    target = _validate_output_path(out)
    payload_without_artifact = dict(payload)
    payload_without_artifact.pop("artifact", None)
    payload_hash = sha256_text(_json_text(payload_without_artifact))
    updated = dict(payload_without_artifact)
    updated["artifact"] = {
        "path": str(target),
        "payload_hash_excluding_artifact": payload_hash,
        "schema_version": PROGRAM_ARCHITECTURE_CANDIDATES_SCHEMA,
    }
    target.write_text(_json_text(updated), encoding="utf-8")
    return updated


def write_architecture_intent_portfolio(
    payload: Mapping[str, Any], portfolio_outdir: Path
) -> dict[str, Any]:
    root = portfolio_outdir.expanduser().resolve()
    if root.name in _FORBIDDEN_OUTPUT_NAMES:
        raise ProgramArchitectureError(
            f"refusing to write portfolio to generated candidate artifact path: {root.name}"
        )
    root.mkdir(parents=True, exist_ok=True)
    intents_dir = root / "candidate_intents"
    intents_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ProgramArchitectureError("architecture plan candidates must be a list")
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, Mapping):
            continue
        if raw_candidate.get("status") != "materializable":
            continue
        candidate_id = _safe_candidate_id(raw_candidate.get("candidate_id"))
        intent_payload = raw_candidate.get("intent_payload")
        if not isinstance(intent_payload, Mapping):
            continue
        path = intents_dir / f"{candidate_id}.json"
        text = _json_text(dict(intent_payload))
        path.write_text(text, encoding="utf-8")
        records.append(
            {
                "candidate_id": candidate_id,
                "intent_path": str(path),
                "intent_hash": sha256_text(text),
                "materialize_command": f"dspx program-gen --intent {path} --outdir <outdir>/{candidate_id}",
            }
        )
    index = {
        "schema_version": "program-architecture-intent-portfolio-v1",
        "status": "materialized_intent_drafts_only",
        "architecture_plan_schema": payload.get("schema_version"),
        "recommended_candidate_id": payload.get("recommended_candidate_id"),
        "candidate_intent_count": len(records),
        "candidate_intents": records,
        "effect": {
            "candidate_program_materialized": False,
            "provider_called": False,
            "oracle_index_mutated": False,
            "ak_called": False,
            "governance_mutated": False,
            "external_authority_mutated": False,
        },
        "non_authority": _non_authority(),
    }
    index_text = _json_text(index)
    index["artifact"] = {
        "path": str(root / "portfolio_index.json"),
        "payload_hash_excluding_artifact": sha256_text(index_text),
        "schema_version": index["schema_version"],
    }
    (root / "portfolio_index.json").write_text(_json_text(index), encoding="utf-8")
    return index
