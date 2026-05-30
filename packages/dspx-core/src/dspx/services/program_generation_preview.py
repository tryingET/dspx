from __future__ import annotations

import re
from typing import Any, Mapping

from dspx.services.program_intent import ProgramIntent

_REASONING_CUES = {
    "adjudicate",
    "analyse",
    "analyze",
    "assess",
    "compare",
    "critique",
    "derive",
    "diagnose",
    "evaluate",
    "explain",
    "infer",
    "judge",
    "multi-step",
    "plan",
    "rationale",
    "reason",
    "review",
    "strategy",
    "synthesize",
}
_ROUTING_CUES = {"classify", "dispatch", "route", "triage"}
_GENERATION_CUES = {"answer", "draft", "recommend", "respond", "response"}
_EXTRACT_CUES = {"extract", "parse", "summarize", "summarise"}
_VALIDATE_CUES = {"check", "validate", "verify"}
_TOOL_CUES = {"tool", "tools", "tool-use", "tool_using", "function", "functions"}
_RETRIEVER_CUES = {
    "retrieve",
    "retrieval",
    "retriever",
    "search",
    "documents",
    "corpus",
}
_REACT_CUES = {"react", "agent", "agentic"}
_REACT_V2_CUES = {"reactv2", "react-v2", "react_v2"}
_PROGRAM_OF_THOUGHT_CUES = {
    "programofthought",
    "program-of-thought",
    "program_of_thought",
    "python",
    "calculation",
    "compute",
}
_CUSTOM_MODULE_CUES = {"custom", "import", "module", "package", "class"}
_MATERIALIZABLE_TOPOLOGY_KINDS = {
    "pipeline",
    "router",
    "retrieve_then_answer",
    "extract_transform_validate",
    "generate_critique_revise",
}


def preview_tokens(text: str) -> set[str]:
    words = set(re.findall(r"[a-z][a-z0-9_\-]*", text.casefold()))
    if "step" in words and "by" in words:
        words.add("step-by-step")
    if "multi" in words and "step" in words:
        words.add("multi-step")
    compact = text.casefold().replace(" ", "")
    if "programofthought" in compact:
        words.add("programofthought")
    if "reactv2" in compact or ({"react", "v2"} <= words):
        words.add("reactv2")
        words.discard("react")
    return words


def _declared_modules(intent: ProgramIntent) -> list[dict[str, Any]]:
    modules = dict(intent.topology or {}).get("modules")
    if not isinstance(modules, list):
        return []
    return [dict(module) for module in modules if isinstance(module, Mapping)]


def _declared_module_primitives(intent: ProgramIntent) -> set[str]:
    return {str(module.get("primitive") or "") for module in _declared_modules(intent)}


def _declared_capabilities(intent: ProgramIntent) -> list[dict[str, Any]]:
    declarations = dict(intent.capabilities or {}).get("declarations") or []
    if not isinstance(declarations, list):
        return []
    return [dict(item) for item in declarations if isinstance(item, Mapping)]


def _declared_capability_kinds(intent: ProgramIntent) -> set[str]:
    return {str(item.get("kind") or "") for item in _declared_capabilities(intent)}


def _declared_capability_primitives(intent: ProgramIntent) -> set[str]:
    primitives: set[str] = set()
    for item in _declared_capabilities(intent):
        primitive = str(item.get("primitive") or "")
        if primitive:
            primitives.add(primitive)
        kind = str(item.get("kind") or "")
        if kind == "retriever":
            primitives.add("Retriever")
        elif kind == "react":
            primitives.add("ReAct")
        elif kind == "react_v2":
            primitives.add("ReActV2")
        elif kind == "program_of_thought":
            primitives.add("ProgramOfThought")
        elif kind in {"custom_import", "custom_module"}:
            primitives.add("Custom")
    return primitives


def _declared_primitives(intent: ProgramIntent) -> set[str]:
    return _declared_module_primitives(intent) | _declared_capability_primitives(intent)


def _declared_topology_materializable_now(
    declared_kind: str, module_primitives: set[str]
) -> bool:
    if declared_kind not in _MATERIALIZABLE_TOPOLOGY_KINDS:
        return False
    if "ReActV2" in module_primitives:
        return False
    return True


def _declared_bounded_retriever(intent: ProgramIntent) -> dict[str, Any]:
    declarations = dict(intent.capabilities or {}).get("declarations") or []
    if not isinstance(declarations, list):
        return {}
    for raw_declaration in declarations:
        if not isinstance(raw_declaration, Mapping):
            continue
        declaration = dict(raw_declaration)
        if declaration.get("kind") != "retriever":
            continue
        retriever = declaration.get("retriever")
        if not isinstance(retriever, Mapping):
            continue
        mode = str(retriever.get("mode") or "")
        if mode in {"inline_corpus", "local_corpus_snapshot"}:
            return {
                "id": str(declaration.get("id") or "retrieve_context"),
                "retriever": dict(retriever),
            }
    return {}


def _declared_pure_tool_ids(intent: ProgramIntent) -> list[str]:
    declarations = dict(intent.capabilities or {}).get("declarations") or []
    if not isinstance(declarations, list):
        return []
    tool_ids: list[str] = []
    for raw_declaration in declarations:
        if not isinstance(raw_declaration, Mapping):
            continue
        declaration = dict(raw_declaration)
        if declaration.get("kind") != "tool":
            continue
        if str(declaration.get("effect_class") or "pure").strip().lower() != "pure":
            continue
        tool_id = str(declaration.get("id") or declaration.get("name") or "").strip()
        if tool_id:
            tool_ids.append(tool_id)
    return tool_ids


def _contract_skeleton(kind: str, intent: ProgramIntent) -> dict[str, Any]:
    first_input = (intent.inputs or ["context"])[0]
    first_output = (intent.outputs or ["answer"])[0]
    pure_tool_ids = _declared_pure_tool_ids(intent)
    bounded_retriever = _declared_bounded_retriever(intent)
    if kind == "retrieve_then_answer" and bounded_retriever:
        return {
            "intent_patch": {
                "topology": {
                    "kind": "retrieve_then_answer",
                    "execution_status": "declared_not_materialized",
                    "modules": [
                        {
                            "id": "retrieve_context",
                            "primitive": "Retriever",
                            "role": "retrieve_context",
                            "signature": {
                                "name": "RetrieveContext",
                                "inputs": list(intent.inputs or [first_input]),
                                "outputs": ["passages"],
                            },
                            "retriever": bounded_retriever["retriever"],
                        },
                        {
                            "id": "answer_question",
                            "primitive": "ChainOfThought",
                            "role": "answer_question",
                            "signature": {
                                "name": "AnswerQuestion",
                                "inputs": [
                                    *list(intent.inputs or [first_input]),
                                    "passages",
                                ],
                                "outputs": list(intent.outputs or [first_output]),
                            },
                        },
                    ],
                    "edges": [
                        {"from": "input", "to": "retrieve_context"},
                        {"from": "retrieve_context", "to": "answer_question"},
                        {"from": "answer_question", "to": "output"},
                    ],
                }
            },
            "production_readiness_missing": [
                "Review bounded retriever declaration before materialization; live external retrievers remain disabled.",
                "Run receipt replay after materialization to verify retriever adapter and runtime traces.",
            ],
        }
    if kind == "ReActV2":
        return {
            "intent_patch": {
                "options": {
                    "enable_react_v2_materialization": True,
                    "react_v2_materialization": True,
                },
                "topology": {
                    "kind": "pipeline",
                    "execution_status": "declared_not_materialized",
                    "modules": [
                        {
                            "id": "react_v2_reasoner",
                            "primitive": "ReActV2",
                            "signature": {
                                "name": "ReactV2Reasoner",
                                "inputs": list(intent.inputs or [first_input]),
                                "outputs": list(intent.outputs or [first_output]),
                            },
                            "tools": [],
                            "tool_refs": pure_tool_ids,
                            "max_iters": 1,
                        }
                    ],
                    "edges": [
                        {"from": "input", "to": "react_v2_reasoner"},
                        {"from": "react_v2_reasoner", "to": "output"},
                    ],
                },
            },
            "production_readiness_missing": [
                "Confirm installed DSPy exposes public dspy.ReActV2 before materialization.",
                "Keep tools=[] until generated tool adapters have authority/effect/redaction/timeout/sandbox/replay/receipt contracts.",
                "Run generated-module policy and receipt replay after materialization.",
            ],
        }
    if kind == "router":
        return {
            "intent_patch": {
                "topology": {
                    "kind": "router",
                    "execution_status": "declared_not_materialized",
                    "modules": [
                        {
                            "id": "classify_route",
                            "primitive": "Predict",
                            "role": "classify_route",
                            "signature": {
                                "name": "ClassifyRoute",
                                "inputs": list(intent.inputs or [first_input]),
                                "outputs": ["route"],
                            },
                        },
                        {
                            "id": "generate_response",
                            "primitive": "ChainOfThought",
                            "role": "generate_final",
                            "signature": {
                                "name": "GenerateResponse",
                                "inputs": [
                                    *list(intent.inputs or [first_input]),
                                    "route",
                                ],
                                "outputs": list(intent.outputs or [first_output]),
                            },
                        },
                    ],
                    "edges": [
                        {"from": "input", "to": "classify_route"},
                        {"from": "classify_route", "to": "generate_response"},
                        {"from": "generate_response", "to": "output"},
                    ],
                }
            },
            "production_readiness_missing": [
                "Review route taxonomy before adding conditional branches; this draft uses a bounded unconditional route-then-generate DAG."
            ],
        }
    if kind == "extract_transform_validate":
        return {
            "intent_patch": {
                "topology": {
                    "kind": "extract_transform_validate",
                    "execution_status": "declared_not_materialized",
                    "modules": [
                        {
                            "id": "extract_evidence",
                            "primitive": "Predict",
                            "role": "extract",
                            "signature": {
                                "name": "ExtractEvidence",
                                "inputs": list(intent.inputs or [first_input]),
                                "outputs": ["evidence"],
                            },
                        },
                        {
                            "id": "transform_draft",
                            "primitive": "ChainOfThought",
                            "role": "transform",
                            "signature": {
                                "name": "TransformDraft",
                                "inputs": [
                                    *list(intent.inputs or [first_input]),
                                    "evidence",
                                ],
                                "outputs": ["draft"],
                            },
                        },
                        {
                            "id": "validate_final",
                            "primitive": "ChainOfThought",
                            "role": "validate",
                            "signature": {
                                "name": "ValidateFinal",
                                "inputs": [
                                    *list(intent.inputs or [first_input]),
                                    "draft",
                                ],
                                "outputs": list(intent.outputs or [first_output]),
                            },
                        },
                    ],
                    "edges": [
                        {"from": "input", "to": "extract_evidence"},
                        {"from": "extract_evidence", "to": "transform_draft"},
                        {"from": "transform_draft", "to": "validate_final"},
                        {"from": "validate_final", "to": "output"},
                    ],
                }
            },
            "production_readiness_missing": [
                "Review extracted/derived field names before materialization."
            ],
        }
    if kind == "generate_critique_revise":
        return {
            "intent_patch": {
                "topology": {
                    "kind": "generate_critique_revise",
                    "execution_status": "declared_not_materialized",
                    "modules": [
                        {
                            "id": "generate_draft",
                            "primitive": "ChainOfThought",
                            "role": "generate_draft",
                            "signature": {
                                "name": "GenerateDraft",
                                "inputs": list(intent.inputs or [first_input]),
                                "outputs": ["draft"],
                            },
                        },
                        {
                            "id": "critique_draft",
                            "primitive": "ChainOfThought",
                            "role": "critique_draft",
                            "signature": {
                                "name": "CritiqueDraft",
                                "inputs": [
                                    *list(intent.inputs or [first_input]),
                                    "draft",
                                ],
                                "outputs": ["critique"],
                            },
                        },
                        {
                            "id": "revise_final",
                            "primitive": "ChainOfThought",
                            "role": "revise_final",
                            "signature": {
                                "name": "ReviseFinal",
                                "inputs": [
                                    *list(intent.inputs or [first_input]),
                                    "draft",
                                    "critique",
                                ],
                                "outputs": list(intent.outputs or [first_output]),
                            },
                        },
                    ],
                    "edges": [
                        {"from": "input", "to": "generate_draft"},
                        {"from": "generate_draft", "to": "critique_draft"},
                        {"from": "generate_draft", "to": "revise_final"},
                        {"from": "critique_draft", "to": "revise_final"},
                        {"from": "revise_final", "to": "output"},
                    ],
                }
            },
            "production_readiness_missing": [
                "Review that one bounded generate->critique->revise pass is sufficient; no open-ended loop is generated."
            ],
        }
    if kind == "ReAct":
        return {
            "intent_patch": {
                "topology": {
                    "kind": "pipeline",
                    "execution_status": "declared_not_materialized",
                    "modules": [
                        {
                            "id": "react_reasoner",
                            "primitive": "ReAct",
                            "signature": {
                                "name": "ReactReasoner",
                                "inputs": list(intent.inputs or [first_input]),
                                "outputs": list(intent.outputs or [first_output]),
                            },
                            "tools": [],
                            "max_iters": 1,
                        }
                    ],
                    "edges": [
                        {"from": "input", "to": "react_reasoner"},
                        {"from": "react_reasoner", "to": "output"},
                    ],
                }
            },
            "production_readiness_missing": [
                "Keep tools=[] until generated tool adapters have authority/effect/redaction/timeout/sandbox/replay/receipt contracts.",
                "Run generated-module policy and receipt replay after materialization.",
            ],
        }
    if kind == "ProgramOfThought":
        return {
            "intent_patch": {
                "topology": {
                    "kind": "pipeline",
                    "execution_status": "declared_not_materialized",
                    "modules": [
                        {
                            "id": "program_of_thought_reasoner",
                            "primitive": "ProgramOfThought",
                            "signature": {
                                "name": "ProgramOfThoughtReasoner",
                                "inputs": list(intent.inputs or [first_input]),
                                "outputs": list(intent.outputs or [first_output]),
                            },
                            "max_iters": 1,
                        }
                    ],
                    "edges": [
                        {"from": "input", "to": "program_of_thought_reasoner"},
                        {"from": "program_of_thought_reasoner", "to": "output"},
                    ],
                }
            },
            "production_readiness_missing": [
                "Keep the ProgramOfThought sandbox empty unless a future reviewed sandbox policy lands.",
                "Run generated-module policy and receipt replay after materialization.",
            ],
        }
    return {}


def _topology_candidate_preview(
    token_set: set[str], intent: ProgramIntent
) -> list[dict[str, Any]]:
    declared_topology = dict(intent.topology or {})
    declared_kind = str(declared_topology.get("kind") or "")
    declared_module_primitives = _declared_module_primitives(intent)
    declared_primitives = declared_module_primitives | _declared_capability_primitives(
        intent
    )
    capability_kinds = _declared_capability_kinds(intent)
    candidates: list[dict[str, Any]] = []

    def add(
        kind: str,
        *,
        source: str,
        confidence: str,
        reason: str,
        materializable_now: bool,
        renderer: str,
        boundary: str,
    ) -> None:
        duplicate = any(
            candidate["kind"] == kind and candidate["source"] == source
            for candidate in candidates
        )
        if duplicate:
            return
        candidate: dict[str, Any] = {
            "kind": kind,
            "source": source,
            "confidence": confidence,
            "reason": reason,
            "materializable_now": materializable_now,
            "renderer": renderer,
            "safety_boundary": boundary,
        }
        contract = _contract_skeleton(kind, intent)
        if contract:
            candidate["required_explicit_contract"] = contract
        candidates.append(candidate)

    if declared_kind:
        add(
            declared_kind,
            source="declared_topology",
            confidence="operator_declared",
            reason="The intent includes an explicit topology.kind; program-gen preserves it before deciding what subset can materialize.",
            materializable_now=_declared_topology_materializable_now(
                declared_kind, declared_module_primitives
            ),
            renderer=(
                f"{declared_kind}_topology_renderer"
                if declared_kind != "custom"
                else "declared_only_single_module_fallback"
            ),
            boundary="Declared topology is evidence/assumption metadata unless the bounded renderer validates it; custom remains policy-only.",
        )
    if token_set & _ROUTING_CUES and token_set & _GENERATION_CUES:
        add(
            "router",
            source="objective_cues",
            confidence="medium",
            reason="Routing/classification cues plus generation/response cues suggest a route-then-answer graph.",
            materializable_now=True,
            renderer="bounded_pipeline_router_renderer",
            boundary="Only generated modules and simple equality routing are in scope; no executable expressions or external authority are used.",
        )
    if (
        token_set & _RETRIEVER_CUES
        or "Retriever" in declared_primitives
        or "retriever" in capability_kinds
    ):
        add(
            "retrieve_then_answer",
            source="objective_or_capability_cues",
            confidence="medium",
            reason="Retrieval/search/document cues suggest a retrieve-then-answer posture.",
            materializable_now="Retriever" in declared_module_primitives,
            renderer="retrieve_then_answer_topology_renderer",
            boundary="Only explicit inline_corpus or local_corpus_snapshot Retriever declarations can materialize; live retrievers remain disabled.",
        )
    if token_set & _EXTRACT_CUES and token_set & _VALIDATE_CUES:
        add(
            "extract_transform_validate",
            source="objective_cues",
            confidence="medium",
            reason="Extraction plus validation cues suggest distinct extract/transform/validate stages.",
            materializable_now=True,
            renderer="extract_transform_validate_topology_renderer",
            boundary="Rendered through the bounded composed-program subset only.",
        )
    if token_set & _REASONING_CUES and {"critique", "revise", "review"} & token_set:
        add(
            "generate_critique_revise",
            source="objective_cues",
            confidence="medium",
            reason="Generation plus critique/review/revision cues suggest a generate-critique-revise loop shape.",
            materializable_now=True,
            renderer="generate_critique_revise_topology_renderer",
            boundary="Rendered as a bounded acyclic generated-module graph, not an open-ended loop.",
        )
    if token_set & _REASONING_CUES and not candidates:
        add(
            "pipeline",
            source="objective_cues",
            confidence="medium",
            reason="Reasoning/review cues suggest a generated ChainOfThought stage rather than a plain Predict scaffold.",
            materializable_now=True,
            renderer="prompt_inferred_pipeline_renderer",
            boundary="Deterministic local inference only; no provider-backed topology inference is used.",
        )
    if (
        token_set & _REACT_CUES and not token_set & _REACT_V2_CUES
    ) or "ReAct" in declared_primitives:
        add(
            "ReAct",
            source="objective_or_declared_primitive",
            confidence="medium",
            reason="ReAct/agent cues or declared ReAct primitives indicate an agentic reasoning candidate.",
            materializable_now="ReAct" in declared_module_primitives,
            renderer="bounded_react_no_tools_adapter",
            boundary="ReAct stays no-tool; dspy.Tool binding is not enabled.",
        )
    if token_set & _REACT_V2_CUES or "ReActV2" in declared_primitives:
        add(
            "ReActV2",
            source="objective_or_declared_primitive",
            confidence="medium",
            reason="ReActV2 cues or declared ReActV2 primitives indicate the DSPy 3.3 structured agent candidate.",
            materializable_now=False,
            renderer="experimental_react_v2_no_tools_adapter",
            boundary="ReActV2 is DSPy 3.3 beta/experimental: materialization requires explicit opt-in, public dspy.ReActV2, and tools=[].",
        )
    if (
        token_set & _PROGRAM_OF_THOUGHT_CUES
        or "ProgramOfThought" in declared_primitives
    ):
        add(
            "ProgramOfThought",
            source="objective_or_declared_primitive",
            confidence="medium",
            reason="Program-of-thought/computation cues indicate a code-reasoning candidate.",
            materializable_now="ProgramOfThought" in declared_module_primitives,
            renderer="sandboxed_program_of_thought_adapter",
            boundary="ProgramOfThought uses an empty sandbox: no filesystem, network, env, tools, or synced files.",
        )
    if token_set & _CUSTOM_MODULE_CUES or "Custom" in declared_primitives:
        add(
            "custom",
            source="objective_or_declared_primitive",
            confidence="low",
            reason="Custom/import/module cues indicate a possible custom module reference.",
            materializable_now=False,
            renderer="declared_only_policy_surface",
            boundary="Custom modules/imports remain declared-only; no arbitrary import or execution policy is enabled.",
        )
    if not candidates:
        add(
            "single_module",
            source="default",
            confidence="low",
            reason="No clear topology cue was detected; the safe baseline is a single generated Predict module.",
            materializable_now=True,
            renderer="single_module_scaffold",
            boundary="No live tools, retrievers, custom imports, ranking, promotion, or authority mutation are enabled.",
        )
    return candidates


def _feature_boundary_preview(
    token_set: set[str], intent: ProgramIntent
) -> dict[str, Any]:
    declared_primitives = _declared_primitives(intent)
    capability_kinds = _declared_capability_kinds(intent)
    tools_needed = bool(
        token_set & _TOOL_CUES or capability_kinds & {"tool", "react", "react_v2"}
    )
    retriever_needed = bool(
        token_set & _RETRIEVER_CUES
        or "Retriever" in declared_primitives
        or "retriever" in capability_kinds
    )
    react_requested = bool(
        (token_set & _REACT_CUES and not token_set & _REACT_V2_CUES)
        or "ReAct" in declared_primitives
    )
    react_v2_requested = bool(
        token_set & _REACT_V2_CUES or "ReActV2" in declared_primitives
    )
    program_of_thought_requested = bool(
        token_set & _PROGRAM_OF_THOUGHT_CUES
        or "ProgramOfThought" in declared_primitives
    )
    custom_requested = bool(
        token_set & _CUSTOM_MODULE_CUES
        or "Custom" in declared_primitives
        or capability_kinds & {"custom_import", "custom_module"}
    )
    return {
        "tools": {
            "need_detected": tools_needed,
            "enabled": False,
            "status": "disabled_descriptor_only",
            "boundary": "Tool declarations may be recorded, but dspy.Tool/live tool execution is not bound by program-gen.",
        },
        "retrievers": {
            "need_detected": retriever_needed,
            "safe_modes_available": ["inline_corpus", "local_corpus_snapshot"],
            "live_retrievers_enabled": False,
            "status": "bounded_declared_adapters_only"
            if retriever_needed
            else "not_requested",
            "boundary": "Retriever materialization requires an explicit bounded Retriever topology module; external/live retrievers remain disabled.",
        },
        "react": {
            "requested": react_requested,
            "tools_enabled": False,
            "status": "no_tool_boundary",
            "boundary": "ReAct materialization is explicit, bounded, and tools=[] only.",
        },
        "react_v2": {
            "requested": react_v2_requested,
            "tool_need_detected": bool(react_v2_requested and tools_needed),
            "tools_enabled": False,
            "tool_binding_status": "blocked_until_safe_tool_adapter_contract",
            "status": "experimental_no_tool_explicit_opt_in_boundary",
            "boundary": "ReActV2 follows the DSPy 3.3 beta boundary: explicit opt-in, public dspy.ReActV2 availability, and tools=[] only.",
            "why_tools_not_enabled": [
                "DSPy 3.3 beta ReActV2 availability does not by itself define DSPx tool authority, effect, redaction, timeout, sandbox, replay, or receipt contracts.",
                "program_tool_contracts.json is descriptor-only in this slice; no generated dspy.Tool adapter hash/provenance exists yet.",
                "Enabling ReActV2 tools would allow external side effects unless every tool is explicitly declared, bounded, replay-visible, and policy-checked before materialization.",
            ],
            "safe_next_action": "Declare desired tools as descriptor-only capability/tool contracts first; materialize ReActV2 with tools=[] until a reviewed generated tool-adapter policy lands.",
        },
        "program_of_thought": {
            "requested": program_of_thought_requested,
            "sandbox": "empty",
            "status": "empty_sandbox_boundary",
            "boundary": "No filesystem, network, env vars, tools, or sync files are exposed.",
        },
        "custom_modules": {
            "requested": custom_requested,
            "imports_enabled": False,
            "status": "blocked_policy_only",
            "boundary": "Custom module/import requests remain declarations and policy metadata only.",
        },
    }


def _unsupported_or_preserved_features(
    token_set: set[str], intent: ProgramIntent
) -> list[dict[str, str]]:
    preview = _feature_boundary_preview(token_set, intent)
    features: list[dict[str, str]] = []
    for key, item in preview.items():
        if item.get("need_detected") or item.get("requested"):
            features.append(
                {
                    "feature": key,
                    "status": str(item.get("status") or "review_required"),
                    "message": str(
                        item.get("boundary") or "Review before materialization."
                    ),
                }
            )
    return features


def _materialization_questions(intent: ProgramIntent) -> list[dict[str, str]]:
    questions = []
    if not intent.examples and not intent.examples_path:
        questions.append(
            {
                "kind": "examples",
                "question": "What examples should prove the generated behavior before trusting the candidate?",
            }
        )
    if not intent.metric:
        questions.append(
            {
                "kind": "metric",
                "question": "Which metric or review criterion should guide later evaluation?",
            }
        )
    if not intent.topology:
        questions.append(
            {
                "kind": "topology",
                "question": "Should the operator accept the inferred topology candidate or declare an explicit topology before materialization?",
            }
        )
    return questions


def build_generation_assumption_preview(
    token_set: set[str], intent: ProgramIntent
) -> dict[str, Any]:
    return {
        "schema_version": "program-generation-assumptions-preview-v1",
        "status": "preview_only_not_materialization_authority",
        "topology_candidates": _topology_candidate_preview(token_set, intent),
        "unsupported_or_preserved_declared_only_features": _unsupported_or_preserved_features(
            token_set, intent
        ),
        "capability_boundaries": _feature_boundary_preview(token_set, intent),
        "missing_questions": _materialization_questions(intent),
        "safe_next_actions": [
            "Review this preview before materialization.",
            "Add explicit topology when the inferred candidate is wrong or too vague.",
            "Use only bounded inline/local retriever declarations; do not expect live retriever/tool execution.",
            "Keep custom module/import requests declared-only until a reviewed safe import policy exists.",
        ],
        "effect": {
            "program_materialized": False,
            "tool_called": False,
            "retriever_called": False,
            "custom_import_loaded": False,
            "authority_mutated": False,
        },
    }
