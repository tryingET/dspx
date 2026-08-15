# summary: "Plans, verifies, and materializes non-authoritative program architecture candidate intents."
# read_when:
#   - "Changing architecture candidate planning, contract verification, or intent portfolios."

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from dspx.cache import sha256_text
from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES
from dspx.services.program_generation_preview import (
    build_generation_assumption_preview,
    preview_tokens,
)
from dspx.services.program_intent import ProgramIntent, load_program_intent
from dspx.services.program_module_surface import build_program_module_surfaces
from dspx.services.program_tool_contracts import build_program_tool_contracts
from dspx.services.program_topology import (
    MATERIALIZABLE_DECLARED_TOPOLOGY_KINDS,
    prompt_inferred_pipeline_topology,
    validate_materializable_pipeline_topology,
)

PROGRAM_ARCHITECTURE_CANDIDATES_SCHEMA = "program-architecture-candidates-v1"
_PROGRAM_INTENT_SCHEMA = "program-intent-v2"
_FORBIDDEN_OUTPUT_NAMES = set(PROTECTED_PROGRAM_ARTIFACT_NAMES)


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
        if normalized["primitive"] == "ReAct" and "react" in module:
            normalized["react"] = dict(module.get("react") or {})
        if (
            normalized["primitive"] == "ProgramOfThought"
            and "program_of_thought" in module
        ):
            normalized["program_of_thought"] = dict(
                module.get("program_of_thought") or {}
            )
        modules.append(normalized)
    edges = [
        dict(edge) for edge in topology.get("edges", []) if isinstance(edge, Mapping)
    ]
    return {
        "kind": str(topology.get("kind") or "pipeline"),
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
    topology_preview: Mapping[str, Any] | None = None,
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
        "topology_preview": dict(topology_preview or {}),
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


def _preview_advisory_candidates(
    *,
    intent: ProgramIntent,
    source_payload: Mapping[str, Any],
    preview: Mapping[str, Any],
    existing_families: set[str],
) -> list[dict[str, Any]]:
    advisory: list[dict[str, Any]] = []
    preview_candidates = preview.get("topology_candidates")
    if not isinstance(preview_candidates, list):
        return advisory
    advisory_kinds = {
        "router",
        "retrieve_then_answer",
        "extract_transform_validate",
        "generate_critique_revise",
        "ReAct",
        "ReActV2",
        "ProgramOfThought",
        "custom",
    }
    for raw_candidate in preview_candidates:
        if not isinstance(raw_candidate, Mapping):
            continue
        kind = str(raw_candidate.get("kind") or "")
        if kind not in advisory_kinds or kind in existing_families:
            continue
        if (
            kind in {"router", "extract_transform_validate"}
            and "pipeline" in existing_families
        ):
            continue
        candidate_id = f"preview_{kind.lower()}_declared_only".replace(" ", "_")
        advisory.append(
            _candidate(
                candidate_id=candidate_id,
                label=f"Preview-only {kind} architecture",
                family=kind,
                recommendation="declare_explicit_contract_before_materialization",
                candidate_intent=deepcopy(dict(source_payload)),
                topology_source="generation_assumptions_preview",
                materializable=False,
                why=[
                    str(
                        raw_candidate.get("reason")
                        or "Preview detected this topology candidate."
                    )
                ],
                limitations=[
                    str(
                        raw_candidate.get("safety_boundary")
                        or "Preview-only candidate requires an explicit safe contract before materialization."
                    ),
                    "This architecture-plan row is advisory only until the required_explicit_contract is accepted and validated as a real intent patch.",
                ],
                topology_preview=raw_candidate,
            )
        )
    return advisory


def build_program_architecture_candidates(intent: ProgramIntent) -> dict[str, Any]:
    """Build a non-authoritative architecture candidate plan for one intent."""

    source_payload = _intent_payload(intent)
    source_hash = _intent_hash(source_payload)
    token_set = preview_tokens(
        " ".join([intent.objective, intent.task_type, " ".join(intent.constraints)])
    )
    generation_assumptions_preview = build_generation_assumption_preview(
        token_set, intent
    )
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
        materializable = (
            declared_topology.get("kind") in MATERIALIZABLE_DECLARED_TOPOLOGY_KINDS
        )
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
                    "Operator-declared topology is preserved as a planning candidate but is not materializable by the current renderer.",
                ]
                limitations.append(str(exc))
                limitations.append(
                    "Current execution renderer materializes only bounded pipeline/router/retrieve_then_answer/extract_transform_validate/generate_critique_revise modules over Predict/ChainOfThought/ReAct/ProgramOfThought and explicit Retriever:inline_corpus adapters."
                )
                declared_payload = deepcopy(source_payload)
            else:
                recommendation = "operator_declared_topology"
                recommended_candidate_id = "declared_pipeline"
                why = [
                    "Operator-declared executable topology takes precedence over prompt inference.",
                ]
        else:
            recommendation = "declared_only"
            why = [
                "Operator-declared topology is preserved as a planning candidate but is not materializable by the current renderer.",
            ]
            limitations.append(
                "Current execution renderer materializes only bounded pipeline/router/retrieve_then_answer/extract_transform_validate/generate_critique_revise topologies over Predict/ChainOfThought/ReAct/ProgramOfThought and explicit Retriever:inline_corpus adapters."
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
                    "No arbitrary custom Python imports, tools, or external retrievers are executed; ReAct uses an empty tools list, ProgramOfThought uses an empty sandbox, and Retriever execution remains limited to explicit inline_corpus adapters.",
                ],
            )
        )

    existing_families = {str(candidate.get("family") or "") for candidate in candidates}
    candidates.extend(
        _preview_advisory_candidates(
            intent=intent,
            source_payload=source_payload,
            preview=generation_assumptions_preview,
            existing_families=existing_families,
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
        "generation_assumptions_preview": generation_assumptions_preview,
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


def _merge_intent_patch(
    source_payload: Mapping[str, Any], patch: Mapping[str, Any], *, candidate_id: str
) -> dict[str, Any]:
    draft = deepcopy(dict(source_payload))
    draft["schema_version"] = _PROGRAM_INTENT_SCHEMA
    draft["name"] = (
        f"{draft.get('name') or 'Program'}{candidate_id.title().replace('_', '')}"
    )
    for key, value in patch.items():
        if key == "options" and isinstance(value, Mapping):
            draft["options"] = {**dict(draft.get("options") or {}), **dict(value)}
        else:
            draft[key] = deepcopy(value)
    ProgramIntent.model_validate(draft)
    return draft


def _react_tool_preflight_for_intent(intent: ProgramIntent) -> dict[str, Any]:
    contracts = build_program_tool_contracts(intent)
    readiness = dict(contracts.get("react_v2_tool_readiness") or {})
    preflight = dict(readiness.get("pure_tool_adapter_preflight") or {})
    return {
        "schema_version": "program-react-v2-pure-tool-preflight-v1",
        "status": preflight.get("materialization_status")
        or "not_requested_or_no_tool_refs",
        "referenced_tool_ids": preflight.get("referenced_tool_ids", []),
        "all_referenced_tools_have_pure_contracts": preflight.get(
            "all_referenced_tools_have_pure_contracts", False
        ),
        "all_referenced_tool_schemas_bounded": preflight.get(
            "all_referenced_tool_schemas_bounded", False
        ),
        "all_referenced_adapter_blueprints_hash_bound": preflight.get(
            "all_referenced_adapter_blueprints_hash_bound", False
        ),
        "all_referenced_tools_have_replay_policy_preconditions": preflight.get(
            "all_referenced_tools_have_replay_policy_preconditions", False
        ),
        "ready_for_tool_adapter_materialization": preflight.get(
            "ready_for_tool_adapter_materialization", False
        ),
        "tool_binding_allowed": False,
        "tool_execution_allowed": False,
        "tool_contracts": {
            "schema_version": contracts.get("schema_version"),
            "tool_contract_count": contracts.get("tool_contract_count"),
            "tool_adapter_policy": contracts.get("tool_adapter_policy"),
        },
    }


def verify_architecture_contract_intent(path: Path) -> dict[str, Any]:
    source = path.expanduser().resolve()
    source_text = source.read_text(encoding="utf-8")
    source_hash = sha256_text(source_text)
    try:
        intent = load_program_intent(source)
    except Exception as exc:
        violation = str(exc)
        if "topology.modules must include at least one module" in violation:
            violation = "contract intent must declare topology modules"
        return {
            "schema_version": "program-architecture-contract-verification-v1",
            "status": "failed",
            "intent_path": str(source),
            "intent_hash": source_hash,
            "intent": None,
            "safe_modules": [],
            "violations": [violation],
            "materialization_allowed_by_contract_verification": False,
            "live_tool_binding_allowed": False,
            "custom_import_allowed": False,
            "external_retriever_allowed": False,
            "effect": {
                "candidate_program_materialized": False,
                "tool_called": False,
                "custom_import_loaded": False,
                "oracle_index_mutated": False,
                "ak_called": False,
                "governance_mutated": False,
                "external_authority_mutated": False,
            },
            "non_authority": _non_authority(),
        }
    topology = dict(intent.topology or {})
    modules = topology.get("modules") if isinstance(topology, Mapping) else None
    if not isinstance(modules, list) or not modules:
        return {
            "schema_version": "program-architecture-contract-verification-v1",
            "status": "failed",
            "intent_path": str(source),
            "intent_hash": source_hash,
            "intent": intent.model_dump(mode="json", exclude_none=True),
            "safe_modules": [],
            "violations": ["contract intent must declare topology modules"],
            "materialization_allowed_by_contract_verification": False,
            "materialization_gate": {
                "status": "blocked_by_contract_verification",
                "allows_live_tools": False,
                "allows_custom_imports": False,
                "allows_external_retrievers": False,
                "requires_review": True,
            },
            "live_tool_binding_allowed": False,
            "custom_import_allowed": False,
            "external_retriever_allowed": False,
            "effect": {
                "candidate_program_materialized": False,
                "tool_called": False,
                "custom_import_loaded": False,
                "oracle_index_mutated": False,
                "ak_called": False,
                "governance_mutated": False,
                "external_authority_mutated": False,
            },
            "non_authority": _non_authority(),
        }
    declarations = dict(intent.capabilities or {}).get("declarations") or []
    pure_tool_ids = {
        str(item.get("id") or item.get("name") or "")
        for item in declarations
        if isinstance(item, Mapping)
        and item.get("kind") == "tool"
        and str(item.get("effect_class") or "pure").strip().lower() == "pure"
    }
    react_v2_tool_preflight = _react_tool_preflight_for_intent(intent)
    violations: list[str] = []
    safe_modules: list[dict[str, Any]] = []
    for raw_module in modules:
        if not isinstance(raw_module, Mapping):
            violations.append("topology module is not an object")
            continue
        module = dict(raw_module)
        primitive = str(module.get("primitive") or "")
        module_id = str(module.get("id") or "")
        if primitive == "ReActV2":
            violations.append(
                f"ReActV2 module {module_id!r} is unavailable during the typed Core cutover"
            )
        elif primitive == "ReAct":
            react = (
                module.get("react") if isinstance(module.get("react"), Mapping) else {}
            )
            tools = module.get(
                "tools", react.get("tools") if isinstance(react, Mapping) else []
            )
            if tools != []:
                violations.append(f"ReAct module {module_id!r} must keep tools=[]")
            declared_tool_refs = (
                react.get("declared_tool_refs") if isinstance(react, Mapping) else []
            )
            if isinstance(declared_tool_refs, list):
                missing_tool_refs = sorted(
                    set(str(item) for item in declared_tool_refs) - pure_tool_ids
                )
                if missing_tool_refs:
                    violations.append(
                        f"ReAct module {module_id!r} tool_refs require matching pure tool declarations: {missing_tool_refs}"
                    )
        elif primitive in {"Predict", "ChainOfThought"}:
            pass
        elif primitive == "Retriever":
            retriever = module.get("retriever")
            if not isinstance(retriever, Mapping):
                violations.append(
                    f"Retriever module {module_id!r} requires bounded retriever config"
                )
            else:
                mode = str(retriever.get("mode") or "")
                if mode not in {"inline_corpus", "local_corpus_snapshot"}:
                    violations.append(
                        f"Retriever module {module_id!r} must use inline_corpus or local_corpus_snapshot mode"
                    )
        elif primitive == "ProgramOfThought":
            config = module.get("program_of_thought")
            sandbox = (
                dict(config.get("sandbox") or {}) if isinstance(config, Mapping) else {}
            )
            if any(
                sandbox.get(key)
                for key in [
                    "read_paths",
                    "write_paths",
                    "env_vars",
                    "network_access",
                    "tools",
                ]
            ):
                violations.append(
                    f"ProgramOfThought module {module_id!r} must keep an empty sandbox"
                )
            if sandbox.get("sync_files"):
                violations.append(
                    f"ProgramOfThought module {module_id!r} must keep sync_files=false"
                )
        else:
            violations.append(
                f"contract draft module {module_id!r} primitive {primitive!r} is not a supported contract-draft primitive"
            )
        safe_modules.append({"module_id": module_id, "primitive": primitive})
    if not violations and not any(
        str(module.get("primitive") or "") == "ReActV2"
        for module in modules
        if isinstance(module, Mapping)
    ):
        try:
            validate_materializable_pipeline_topology(intent)
        except Exception as exc:
            violations.append(str(exc))
    return {
        "schema_version": "program-architecture-contract-verification-v1",
        "status": "verified_contract_intent" if not violations else "failed",
        "intent_path": str(source),
        "intent_hash": source_hash,
        "intent": {
            "schema_version": intent.schema_version,
            "name": intent.name,
            "objective": intent.objective,
        },
        "safe_modules": safe_modules,
        "react_v2_tool_preflight": react_v2_tool_preflight,
        "violations": violations,
        "materialization_gate": {
            "status": "verified_for_explicit_program_gen_materialization"
            if not violations
            else "blocked",
            "program_gen_must_match_intent_hash": source_hash,
            "allows_live_tools": False,
            "allows_custom_imports": False,
            "allows_external_retrievers": False,
        },
        "materialization_allowed_by_contract_verification": not violations,
        "live_tool_binding_allowed": False,
        "custom_import_allowed": False,
        "external_retriever_allowed": False,
        "effect": {
            "candidate_program_materialized": False,
            "tool_called": False,
            "custom_import_loaded": False,
            "oracle_index_mutated": False,
            "ak_called": False,
            "governance_mutated": False,
            "external_authority_mutated": False,
        },
        "non_authority": _non_authority(),
    }


def write_architecture_contract_verification(
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
        "schema_version": "program-architecture-contract-verification-v1",
    }
    target.write_text(_json_text(updated), encoding="utf-8")
    return updated


def write_architecture_contract_drafts(
    payload: Mapping[str, Any], contract_outdir: Path
) -> dict[str, Any]:
    root = contract_outdir.expanduser().resolve()
    if root.name in _FORBIDDEN_OUTPUT_NAMES:
        raise ProgramArchitectureError(
            f"refusing to write contract drafts to generated candidate artifact path: {root.name}"
        )
    root.mkdir(parents=True, exist_ok=True)
    intents_dir = root / "contract_intents"
    intents_dir.mkdir(parents=True, exist_ok=True)
    source_payload = payload.get("source_intent_payload")
    if not isinstance(source_payload, Mapping):
        raise ProgramArchitectureError(
            "architecture plan missing source_intent_payload"
        )
    records: list[dict[str, Any]] = []
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ProgramArchitectureError("architecture plan candidates must be a list")
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, Mapping):
            continue
        candidate_id = _safe_candidate_id(raw_candidate.get("candidate_id"))
        preview = raw_candidate.get("topology_preview")
        if not isinstance(preview, Mapping):
            continue
        contract = preview.get("required_explicit_contract")
        if not isinstance(contract, Mapping):
            continue
        patch = contract.get("intent_patch")
        if not isinstance(patch, Mapping):
            continue
        draft = _merge_intent_patch(source_payload, patch, candidate_id=candidate_id)
        path = intents_dir / f"{candidate_id}.json"
        text = _json_text(draft)
        path.write_text(text, encoding="utf-8")
        records.append(
            {
                "candidate_id": candidate_id,
                "intent_path": str(path),
                "intent_hash": sha256_text(text),
                "status": "explicit_contract_draft_requires_operator_review",
                "materializable_claimed": False,
                "preconditions": list(
                    contract.get("production_readiness_missing") or []
                ),
                "materialize_command_after_review": f"dspx program-gen --intent {path} --outdir <outdir>/{candidate_id}",
            }
        )
    index = {
        "schema_version": "program-architecture-contract-drafts-v1",
        "status": "explicit_contract_drafts_only_not_materialized",
        "architecture_plan_schema": payload.get("schema_version"),
        "contract_draft_count": len(records),
        "contract_drafts": records,
        "effect": {
            "candidate_program_materialized": False,
            "provider_called": False,
            "tool_called": False,
            "oracle_index_mutated": False,
            "ak_called": False,
            "governance_mutated": False,
            "external_authority_mutated": False,
        },
        "non_authority": _non_authority(),
    }
    index_text = _json_text(index)
    index["artifact"] = {
        "path": str(root / "contract_drafts_index.json"),
        "payload_hash_excluding_artifact": sha256_text(index_text),
        "schema_version": index["schema_version"],
    }
    (root / "contract_drafts_index.json").write_text(
        _json_text(index), encoding="utf-8"
    )
    return index


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
