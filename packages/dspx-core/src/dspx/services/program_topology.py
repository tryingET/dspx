# summary: "Infers, validates, schedules, and renders bounded materializable topologies for generated DSPy programs."
# read_when:
#   - "Changing topology inference, graph validation, supported primitives, or generated pipeline code."

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import re
from typing import Any, Mapping

from dspx.services.program_capabilities import (
    is_pipeline_module_materializable,
    materializable_pipeline_primitives,
    normalize_inline_retriever_config,
)
from dspx.services.program_contracts import sanitize_ident, surface_description

PIPELINE_MATERIALIZED_STATUS = "pipeline_materialized"
RETRIEVE_THEN_ANSWER_MATERIALIZED_STATUS = "retrieve_then_answer_materialized"
PROMPT_INFERRED_PIPELINE_RENDERER = "prompt_inferred_pipeline_renderer"
RETRIEVE_THEN_ANSWER_RENDERER = "retrieve_then_answer_topology_renderer"
MATERIALIZABLE_DECLARED_TOPOLOGY_KINDS = {
    "pipeline",
    "retrieve_then_answer",
    "router",
    "extract_transform_validate",
    "generate_critique_revise",
}
SUPPORTED_PIPELINE_PRIMITIVES = materializable_pipeline_primitives()
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


class ProgramTopologyMaterializationError(ValueError):
    """Raised when a declared topology cannot be safely materialized."""


_PROGRAM_OF_THOUGHT_INTERPRETER_KEYWORDS = {
    "3.1.3": "interpreter",
    "3.3.0": "interpreter_factory",
    "3.3.1": "interpreter_factory",
}


def _program_of_thought_interpreter_keyword() -> str:
    """Select the reviewed constructor lifecycle for the exact DSPy runtime."""

    try:
        dspy_version = version("dspy")
    except PackageNotFoundError as exc:
        raise ProgramTopologyMaterializationError(
            "ProgramOfThought materialization requires an installed dspy distribution"
        ) from exc
    try:
        return _PROGRAM_OF_THOUGHT_INTERPRETER_KEYWORDS[dspy_version]
    except KeyError as exc:
        supported = ", ".join(sorted(_PROGRAM_OF_THOUGHT_INTERPRETER_KEYWORDS))
        raise ProgramTopologyMaterializationError(
            f"ProgramOfThought materialization has no reviewed interpreter lifecycle for dspy {dspy_version!r}; supported exact versions: {supported}"
        ) from exc


def declared_pipeline_topology(intent: Any) -> dict[str, Any]:
    topology = dict(getattr(intent, "topology", {}) or {})
    if topology.get("kind") != "pipeline":
        return {}
    return topology


def declared_retrieve_then_answer_topology(intent: Any) -> dict[str, Any]:
    topology = dict(getattr(intent, "topology", {}) or {})
    if topology.get("kind") != "retrieve_then_answer":
        return {}
    return topology


def declared_named_materializable_topology(intent: Any) -> dict[str, Any]:
    topology = dict(getattr(intent, "topology", {}) or {})
    kind = str(topology.get("kind") or "")
    if kind not in MATERIALIZABLE_DECLARED_TOPOLOGY_KINDS - {
        "pipeline",
        "retrieve_then_answer",
    }:
        return {}
    return topology


def declared_materializable_topology(intent: Any) -> dict[str, Any]:
    return (
        declared_pipeline_topology(intent)
        or declared_retrieve_then_answer_topology(intent)
        or declared_named_materializable_topology(intent)
    )


def has_declared_pipeline_topology(intent: Any) -> bool:
    return bool(declared_pipeline_topology(intent))


def _objective_tokens(intent: Any) -> set[str]:
    text = " ".join(
        str(part or "")
        for part in [
            getattr(intent, "objective", ""),
            getattr(intent, "task_type", ""),
            " ".join(str(item) for item in getattr(intent, "constraints", []) or []),
        ]
    ).casefold()
    words = set(re.findall(r"[a-z][a-z0-9_\-]*", text))
    if "step" in words and "by" in words:
        words.add("step-by-step")
    if "multi" in words and "step" in words:
        words.add("multi-step")
    return words


def _module_inference_enabled(intent: Any) -> bool:
    options = getattr(intent, "options", {}) or {}
    if not isinstance(options, Mapping):
        return True
    if "module_inference" not in options and "prompt_module_inference" not in options:
        if bool(options.get("focused_json_bundle_runtime")):
            return False
    raw = options.get("module_inference", options.get("prompt_module_inference", True))
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().casefold() not in {"0", "false", "no", "off", "none"}


def _pascal_name(value: str, *, fallback: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", value) if part]
    if not parts:
        return fallback
    return sanitize_ident(
        "".join(part[:1].upper() + part[1:] for part in parts), fallback=fallback
    )


def _signature(
    name: str, *, inputs: list[str], outputs: list[str]
) -> dict[str, list[str] | str]:
    return {"name": name, "inputs": list(inputs), "outputs": list(outputs)}


def _with_intermediate(inputs: list[str], name: str) -> list[str]:
    return [*inputs, *([] if name in inputs else [name])]


def _prompt_inference_notes(reason: str) -> list[str]:
    return [
        "No explicit topology was declared; program-gen inferred a bounded generated module topology from the objective/task wording.",
        reason,
        "Inference is deterministic, local, and limited to generated Predict/ChainOfThought modules; no custom Python imports, tools, external retrievers, ReAct, ranking, promotion, or external authority mutation are performed.",
    ]


def prompt_inferred_pipeline_topology(intent: Any) -> dict[str, Any]:
    """Infer a safe generated module topology from the user intent.

    This is deliberately conservative: it only upgrades no-topology intents from the
    default Predict scaffold to generated Predict/ChainOfThought pipeline modules
    when the prompt contains clear routing, extraction/validation, or reasoning
    cues. It does not infer arbitrary custom imports or non-supported DSPy
    primitives.
    """

    if getattr(intent, "topology", {}) or not _module_inference_enabled(intent):
        return {}
    tokens = _objective_tokens(intent)
    inputs = [str(item) for item in getattr(intent, "inputs", []) or ["context"]]
    outputs = [str(item) for item in getattr(intent, "outputs", []) or ["output"]]
    first_output = outputs[0]

    if tokens & _ROUTING_CUES and tokens & _GENERATION_CUES:
        final_id = f"produce_{first_output}"
        return {
            "kind": "pipeline",
            "execution_status": "prompt_inferred_not_materialized",
            "origin": "prompt_inferred",
            "inference_reason": "routing/generation cues favor a generated classifier plus reasoned output module over a single Predict scaffold.",
            "modules": [
                {
                    "id": "classify_route",
                    "primitive": "Predict",
                    "signature": _signature(
                        "ClassifyRoute",
                        inputs=inputs,
                        outputs=["route"],
                    ),
                    "role": "Classify the input into the most useful route before generating the final output.",
                },
                {
                    "id": final_id,
                    "primitive": "ChainOfThought",
                    "signature": _signature(
                        _pascal_name(final_id, fallback="ProduceOutput"),
                        inputs=_with_intermediate(inputs, "route"),
                        outputs=outputs,
                    ),
                    "role": "Use the route and original inputs to produce the requested output with reasoning.",
                },
            ],
            "edges": [
                {"from": "input", "to": "classify_route"},
                {"from": "classify_route", "to": final_id},
                {"from": final_id, "to": "output"},
            ],
            "notes": _prompt_inference_notes(
                "Detected routing plus generation cues in the prompt."
            ),
        }

    if tokens & _EXTRACT_CUES and tokens & _VALIDATE_CUES:
        final_id = f"validate_{first_output}"
        return {
            "kind": "pipeline",
            "execution_status": "prompt_inferred_not_materialized",
            "origin": "prompt_inferred",
            "inference_reason": "extract/validate cues favor an extraction module plus a reasoned validation/output module over a single Predict scaffold.",
            "modules": [
                {
                    "id": "extract_evidence",
                    "primitive": "Predict",
                    "signature": _signature(
                        "ExtractEvidence",
                        inputs=inputs,
                        outputs=["evidence"],
                    ),
                    "role": "Extract the evidence needed by the final generated program output.",
                },
                {
                    "id": final_id,
                    "primitive": "ChainOfThought",
                    "signature": _signature(
                        _pascal_name(final_id, fallback="ValidateOutput"),
                        inputs=_with_intermediate(inputs, "evidence"),
                        outputs=outputs,
                    ),
                    "role": "Validate extracted evidence and produce the requested output.",
                },
            ],
            "edges": [
                {"from": "input", "to": "extract_evidence"},
                {"from": "extract_evidence", "to": final_id},
                {"from": final_id, "to": "output"},
            ],
            "notes": _prompt_inference_notes(
                "Detected extraction plus validation cues in the prompt."
            ),
        }

    if tokens & _REASONING_CUES:
        module_id = f"reason_{first_output}"
        return {
            "kind": "pipeline",
            "execution_status": "prompt_inferred_not_materialized",
            "origin": "prompt_inferred",
            "inference_reason": "reasoning/review cues favor a generated ChainOfThought module over a single Predict scaffold.",
            "modules": [
                {
                    "id": module_id,
                    "primitive": "ChainOfThought",
                    "signature": _signature(
                        _pascal_name(module_id, fallback="ReasonedOutput"),
                        inputs=inputs,
                        outputs=outputs,
                    ),
                    "role": "Reason over the supplied inputs before producing the requested output.",
                }
            ],
            "edges": [
                {"from": "input", "to": module_id},
                {"from": module_id, "to": "output"},
            ],
            "notes": _prompt_inference_notes(
                "Detected reasoning/review cues in the prompt."
            ),
        }
    return {}


def _materialized_status_for_kind(kind: str) -> str:
    if kind == "pipeline":
        return PIPELINE_MATERIALIZED_STATUS
    if kind == "retrieve_then_answer":
        return RETRIEVE_THEN_ANSWER_MATERIALIZED_STATUS
    return f"{kind}_materialized"


def _renderer_for_kind(kind: str) -> str:
    if kind == "pipeline":
        return "pipeline_topology_renderer"
    if kind == "retrieve_then_answer":
        return RETRIEVE_THEN_ANSWER_RENDERER
    return f"{kind}_topology_renderer"


def _adapt_retrieve_then_answer_topology(intent: Any) -> dict[str, Any]:
    topology = declared_retrieve_then_answer_topology(intent)
    if not topology:
        return {}
    modules = [
        dict(item) for item in topology.get("modules", []) if isinstance(item, Mapping)
    ]
    if not any(str(module.get("primitive") or "") == "Retriever" for module in modules):
        raise ProgramTopologyMaterializationError(
            "retrieve_then_answer topology materialization requires at least one bounded inline Retriever module"
        )
    if not any(str(module.get("primitive") or "") != "Retriever" for module in modules):
        raise ProgramTopologyMaterializationError(
            "retrieve_then_answer topology materialization requires an answer module after retrieval"
        )
    return {
        **topology,
        "execution_status": RETRIEVE_THEN_ANSWER_MATERIALIZED_STATUS,
        "materialized_from_kind": "retrieve_then_answer",
        "renderer": RETRIEVE_THEN_ANSWER_RENDERER,
    }


def _adapt_named_materializable_topology(intent: Any) -> dict[str, Any]:
    topology = declared_named_materializable_topology(intent)
    if not topology:
        return {}
    kind = str(topology.get("kind") or "")
    return {
        **topology,
        "execution_status": _materialized_status_for_kind(kind),
        "materialized_from_kind": kind,
        "renderer": _renderer_for_kind(kind),
    }


def _role(module: Mapping[str, Any]) -> str:
    return str(module.get("role") or "").strip()


def _edge_exists(edges: list[dict[str, Any]], source: str, target: str) -> bool:
    return any(
        str(edge.get("from") or "") == source and str(edge.get("to") or "") == target
        for edge in edges
    )


def _validate_generate_critique_revise_contract(
    *,
    modules: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    intent_outputs: list[str],
) -> None:
    """Validate named generate->critique->revise semantics, not just DAG shape."""

    by_role = {_role(module): module for module in modules if _role(module)}
    required_roles = ["generate_draft", "critique_draft", "revise_final"]
    missing_roles = [role for role in required_roles if role not in by_role]
    if missing_roles:
        raise ProgramTopologyMaterializationError(
            "generate_critique_revise topology requires stage roles "
            f"{required_roles}; missing roles: {missing_roles}"
        )
    draft_module = by_role["generate_draft"]
    critique_module = by_role["critique_draft"]
    revise_module = by_role["revise_final"]
    draft_id = _module_id(draft_module)
    critique_id = _module_id(critique_module)
    revise_id = _module_id(revise_module)
    draft_outputs = set(_signature_outputs(draft_module))
    critique_inputs = set(_signature_inputs(critique_module))
    revise_inputs = set(_signature_inputs(revise_module))
    revise_outputs = set(_signature_outputs(revise_module))
    if not draft_outputs & critique_inputs:
        raise ProgramTopologyMaterializationError(
            "generate_critique_revise topology requires generate_draft outputs to feed critique_draft inputs"
        )
    if not draft_outputs & revise_inputs:
        raise ProgramTopologyMaterializationError(
            "generate_critique_revise topology requires generate_draft outputs to feed revise_final inputs"
        )
    if not set(_signature_outputs(critique_module)) & revise_inputs:
        raise ProgramTopologyMaterializationError(
            "generate_critique_revise topology requires critique_draft outputs to feed revise_final inputs"
        )
    required_edges = [
        (draft_id, critique_id),
        (draft_id, revise_id),
        (critique_id, revise_id),
        (revise_id, "output"),
    ]
    missing_edges = [edge for edge in required_edges if not _edge_exists(edges, *edge)]
    if missing_edges:
        raise ProgramTopologyMaterializationError(
            "generate_critique_revise topology requires explicit draft/critique/revise edges; "
            f"missing edges: {missing_edges}"
        )
    missing_outputs = sorted(set(intent_outputs) - revise_outputs)
    if missing_outputs:
        raise ProgramTopologyMaterializationError(
            "generate_critique_revise topology requires revise_final to produce all declared outputs; "
            f"missing outputs: {missing_outputs}"
        )


def _validate_extract_transform_validate_contract(
    *,
    modules: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    intent_outputs: list[str],
) -> None:
    by_role = {_role(module): module for module in modules if _role(module)}
    required_roles = ["extract", "transform", "validate"]
    missing_roles = [role for role in required_roles if role not in by_role]
    if missing_roles:
        raise ProgramTopologyMaterializationError(
            "extract_transform_validate topology requires stage roles "
            f"{required_roles}; missing roles: {missing_roles}"
        )
    extract_module = by_role["extract"]
    transform_module = by_role["transform"]
    validate_module = by_role["validate"]
    if not set(_signature_outputs(extract_module)) & set(
        _signature_inputs(transform_module)
    ):
        raise ProgramTopologyMaterializationError(
            "extract_transform_validate topology requires extract outputs to feed transform inputs"
        )
    if not set(_signature_outputs(transform_module)) & set(
        _signature_inputs(validate_module)
    ):
        raise ProgramTopologyMaterializationError(
            "extract_transform_validate topology requires transform outputs to feed validate inputs"
        )
    required_edges = [
        (_module_id(extract_module), _module_id(transform_module)),
        (_module_id(transform_module), _module_id(validate_module)),
        (_module_id(validate_module), "output"),
    ]
    missing_edges = [edge for edge in required_edges if not _edge_exists(edges, *edge)]
    if missing_edges:
        raise ProgramTopologyMaterializationError(
            "extract_transform_validate topology requires explicit extract/transform/validate edges; "
            f"missing edges: {missing_edges}"
        )
    missing_outputs = sorted(
        set(intent_outputs) - set(_signature_outputs(validate_module))
    )
    if missing_outputs:
        raise ProgramTopologyMaterializationError(
            "extract_transform_validate topology requires validate stage to produce all declared outputs; "
            f"missing outputs: {missing_outputs}"
        )


def _validate_retrieve_then_answer_contract(
    *, modules: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> None:
    """Fail closed unless retrieval actually feeds an answer path.

    Generic pipeline DAG validity only proves that every module can run and that
    declared outputs can be produced. ``retrieve_then_answer`` has a stronger
    semantic promise: every bounded inline Retriever branch must feed at least
    one non-Retriever answer module that can reach the declared output edge.
    """

    module_by_id = {_module_id(module): module for module in modules}
    retriever_ids = {
        module_id
        for module_id, module in module_by_id.items()
        if str(module.get("primitive") or "") == "Retriever"
    }
    answer_ids = set(module_by_id) - retriever_ids
    adjacency: dict[str, set[str]] = {module_id: set() for module_id in module_by_id}
    output_sources: set[str] = set()
    for edge in edges:
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source in module_by_id and target in module_by_id:
            adjacency[source].add(target)
        if source in module_by_id and target == "output":
            output_sources.add(source)

    def reaches_output(module_id: str) -> bool:
        pending = [module_id]
        seen: set[str] = set()
        while pending:
            current = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            if current in output_sources:
                return True
            pending.extend(sorted(adjacency.get(current, set()) - seen))
        return False

    disconnected: list[str] = []
    for retriever_id in sorted(retriever_ids):
        retriever_outputs = set(_signature_outputs(module_by_id[retriever_id]))
        fed_answer_ids: list[str] = []
        for answer_id in sorted(adjacency.get(retriever_id, set()) & answer_ids):
            answer_inputs = set(_signature_inputs(module_by_id[answer_id]))
            if retriever_outputs & answer_inputs and reaches_output(answer_id):
                fed_answer_ids.append(answer_id)
        if not fed_answer_ids:
            disconnected.append(retriever_id)
    if disconnected:
        raise ProgramTopologyMaterializationError(
            "retrieve_then_answer topology requires every Retriever output to feed "
            "a downstream answer module that reaches output; disconnected retrievers: "
            f"{disconnected}"
        )


def effective_pipeline_topology(intent: Any) -> dict[str, Any]:
    return (
        declared_pipeline_topology(intent)
        or _adapt_retrieve_then_answer_topology(intent)
        or _adapt_named_materializable_topology(intent)
        or prompt_inferred_pipeline_topology(intent)
    )


def pipeline_topology_origin(intent: Any) -> str | None:
    if declared_pipeline_topology(intent):
        return "declared"
    if declared_retrieve_then_answer_topology(intent):
        return "declared_retrieve_then_answer"
    if declared_named_materializable_topology(intent):
        kind = str(
            declared_named_materializable_topology(intent).get("kind") or "named"
        )
        return f"declared_{kind}"
    if prompt_inferred_pipeline_topology(intent):
        return "prompt_inferred"
    return None


def has_materializable_pipeline_topology(intent: Any) -> bool:
    return bool(effective_pipeline_topology(intent))


def _module_signature(module: Mapping[str, Any]) -> dict[str, Any]:
    signature = module.get("signature")
    return dict(signature) if isinstance(signature, Mapping) else {}


def _declared_react_v2_modules(modules: list[dict[str, Any]]) -> list[str]:
    """Keep ReActV2 descriptor-only during the typed Core cutover."""

    return [
        str(module.get("id") or "")
        for module in modules
        if str(module.get("primitive") or "") == "ReActV2"
    ]


def validate_materializable_pipeline_topology(intent: Any) -> dict[str, Any]:
    """Return the normalized pipeline topology or fail for unsupported execution."""

    topology = effective_pipeline_topology(intent)
    if not topology:
        return {}
    topology = dict(topology)
    modules = [
        dict(item) for item in topology.get("modules", []) if isinstance(item, Mapping)
    ]
    topology["modules"] = modules
    if not modules:
        raise ProgramTopologyMaterializationError(
            "pipeline topology materialization requires at least one module"
        )
    react_v2_not_enabled = _declared_react_v2_modules(modules)
    unsupported = sorted(
        {
            str(module.get("primitive") or "")
            for module in modules
            if not is_pipeline_module_materializable(module)
        }
        | ({"ReActV2"} if react_v2_not_enabled else set())
    )
    if unsupported:
        allowed = ", ".join(
            sorted(
                [
                    *SUPPORTED_PIPELINE_PRIMITIVES,
                    "Retriever:inline_corpus",
                    "ReAct:tools=[]",
                    "ProgramOfThought:empty_sandbox",
                ]
            )
        )
        raise ProgramTopologyMaterializationError(
            "pipeline topology materialization supports only module primitives "
            f"{allowed} under the capability-registry materialization policy; "
            f"unsupported primitives: {unsupported}"
        )
    for module in modules:
        if str(module.get("primitive") or "") != "Retriever":
            continue
        normalize_inline_retriever_config(
            module.get("retriever"), module_id=str(module.get("id") or "")
        )
        outputs = _signature_outputs(module)
        if len(outputs) != 1:
            raise ProgramTopologyMaterializationError(
                "pipeline Retriever modules must declare exactly one signature output"
            )
    signature_names = [
        str(_module_signature(module).get("name") or "") for module in modules
    ]
    if len(set(signature_names)) != len(signature_names):
        raise ProgramTopologyMaterializationError(
            "pipeline topology materialization requires unique signature.name values"
        )
    module_class_names = [module_class_name(module) for module in modules]
    if len(set(module_class_names)) != len(module_class_names):
        raise ProgramTopologyMaterializationError(
            "pipeline topology materialization requires unique generated module class names"
        )
    edges = [
        dict(item) for item in topology.get("edges", []) if isinstance(item, Mapping)
    ]
    for edge in edges:
        when = edge.get("when")
        if when is None:
            continue
        if not isinstance(when, Mapping):
            raise ProgramTopologyMaterializationError(
                "pipeline topology supports only simple when.field/equals routing clauses"
            )
        if set(when) - {"field", "equals"}:
            raise ProgramTopologyMaterializationError(
                "pipeline topology supports only simple when.field/equals routing clauses"
            )
    _validate_pipeline_graph_contract(
        modules=modules,
        edges=edges,
        intent_inputs=[str(item) for item in getattr(intent, "inputs", [])],
        intent_outputs=[str(item) for item in getattr(intent, "outputs", [])],
    )
    if declared_retrieve_then_answer_topology(intent):
        _validate_retrieve_then_answer_contract(modules=modules, edges=edges)
    declared_kind = str(declared_materializable_topology(intent).get("kind") or "")
    if declared_kind == "generate_critique_revise":
        _validate_generate_critique_revise_contract(
            modules=modules,
            edges=edges,
            intent_outputs=[str(item) for item in getattr(intent, "outputs", [])],
        )
    if declared_kind == "extract_transform_validate":
        _validate_extract_transform_validate_contract(
            modules=modules,
            edges=edges,
            intent_outputs=[str(item) for item in getattr(intent, "outputs", [])],
        )
    return topology


def _validate_pipeline_graph_contract(
    *,
    modules: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    intent_inputs: list[str],
    intent_outputs: list[str],
) -> None:
    module_ids = [_module_id(module) for module in modules]
    module_id_set = set(module_ids)
    inbound_by_module: dict[str, list[dict[str, Any]]] = {
        module_id: [] for module_id in module_ids
    }
    module_outputs: dict[str, set[str]] = {
        _module_id(module): set(_signature_outputs(module)) for module in modules
    }
    module_inputs: dict[str, set[str]] = {
        _module_id(module): set(_signature_inputs(module)) for module in modules
    }
    produced_outputs = (
        set().union(*module_outputs.values()) if module_outputs else set()
    )
    missing_declared_outputs = sorted(set(intent_outputs) - produced_outputs)
    if missing_declared_outputs:
        raise ProgramTopologyMaterializationError(
            "pipeline topology declared outputs are not produced by any module: "
            f"{missing_declared_outputs}"
        )
    output_edge_sources = {
        str(edge.get("from") or "")
        for edge in edges
        if str(edge.get("to") or "") == "output"
        and str(edge.get("from") or "") in module_id_set
    }
    edge_reachable_outputs: set[str] = set()
    for source in output_edge_sources:
        edge_reachable_outputs.update(module_outputs[source])
    missing_output_edges = sorted(set(intent_outputs) - edge_reachable_outputs)
    if missing_output_edges:
        raise ProgramTopologyMaterializationError(
            "pipeline topology declared outputs require an edge from a producing "
            f"module to output; missing outputs: {missing_output_edges}"
        )

    adjacency: dict[str, set[str]] = {module_id: set() for module_id in module_ids}
    indegree: dict[str, int] = {module_id: 0 for module_id in module_ids}
    intent_input_set = set(intent_inputs)
    for edge in edges:
        target = str(edge.get("to") or "")
        source = str(edge.get("from") or "")
        when = edge.get("when")
        if isinstance(when, Mapping):
            when_field = str(when.get("field") or "")
            available_when_fields = set(intent_input_set)
            if source in module_id_set:
                available_when_fields.update(module_outputs[source])
            if when_field not in available_when_fields:
                raise ProgramTopologyMaterializationError(
                    "pipeline topology when.field must be available from program "
                    "inputs or the source module outputs; "
                    f"edge={source!r}->{target!r} field={when_field!r}"
                )
        if target in inbound_by_module:
            inbound_by_module[target].append(edge)
        if source in module_id_set and target in module_id_set:
            if target not in adjacency[source]:
                adjacency[source].add(target)
                indegree[target] += 1

    missing_inbound = sorted(
        module_id for module_id, inbound in inbound_by_module.items() if not inbound
    )
    if missing_inbound:
        raise ProgramTopologyMaterializationError(
            "pipeline topology modules require at least one inbound edge: "
            f"{missing_inbound}"
        )

    for module_id, required_inputs in module_inputs.items():
        inbound_module_ids = {
            str(edge.get("from") or "")
            for edge in inbound_by_module[module_id]
            if str(edge.get("from") or "") in module_id_set
        }
        available_from_inbound = set(intent_input_set)
        for inbound_module_id in inbound_module_ids:
            available_from_inbound.update(module_outputs[inbound_module_id])
        missing_inputs = sorted(required_inputs - available_from_inbound)
        if missing_inputs:
            raise ProgramTopologyMaterializationError(
                "pipeline topology module inputs must be provided by program inputs "
                "or direct inbound module outputs; "
                f"module={module_id!r} missing={missing_inputs}"
            )

    ready = [module_id for module_id, degree in indegree.items() if degree == 0]
    visited: list[str] = []
    while ready:
        module_id = ready.pop(0)
        visited.append(module_id)
        for target in sorted(adjacency[module_id]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if len(visited) != len(module_ids):
        cyclic = sorted(
            module_id for module_id, degree in indegree.items() if degree > 0
        )
        raise ProgramTopologyMaterializationError(
            f"pipeline topology module graph must be acyclic; cyclic modules: {cyclic}"
        )


def materializes_pipeline_topology(intent: Any) -> bool:
    if not has_materializable_pipeline_topology(intent):
        return False
    validate_materializable_pipeline_topology(intent)
    return True


def _scheduler_plan_for_topology(topology: Mapping[str, Any]) -> dict[str, Any]:
    modules = [
        dict(item) for item in topology.get("modules", []) if isinstance(item, Mapping)
    ]
    edges = [
        dict(item) for item in topology.get("edges", []) if isinstance(item, Mapping)
    ]
    module_ids = [_module_id(module) for module in modules]
    module_id_set = set(module_ids)
    adjacency: dict[str, set[str]] = {module_id: set() for module_id in module_ids}
    indegree: dict[str, int] = {module_id: 0 for module_id in module_ids}
    inbound_edges: dict[str, list[dict[str, Any]]] = {
        module_id: [] for module_id in module_ids
    }
    output_producers: list[str] = []
    for edge in edges:
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if target in module_id_set:
            inbound_edges[target].append(edge)
        if source in module_id_set and target in module_id_set:
            if target not in adjacency[source]:
                adjacency[source].add(target)
                indegree[target] += 1
        if source in module_id_set and target == "output":
            output_producers.append(source)

    declaration_index = {module_id: index for index, module_id in enumerate(module_ids)}
    ready = [module_id for module_id in module_ids if indegree[module_id] == 0]
    scheduled: list[str] = []
    while ready:
        ready.sort(key=lambda module_id: declaration_index[module_id])
        module_id = ready.pop(0)
        scheduled.append(module_id)
        for target in sorted(
            adjacency[module_id], key=lambda item: declaration_index[item]
        ):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)

    return {
        "schema_version": "program-topology-scheduler-plan-v1",
        "status": "deterministic_local_dag_schedule",
        "scheduler": "bounded_ready_queue",
        "module_order": scheduled,
        "declaration_order": module_ids,
        "output_producers": output_producers,
        "module_readiness": {
            module_id: {
                "required_inputs": _signature_inputs(module),
                "produced_outputs": _signature_outputs(module),
                "inbound_edges": inbound_edges[module_id],
                "primitive": str(module.get("primitive") or "Predict"),
            }
            for module_id, module in zip(module_ids, modules, strict=True)
        },
        "effect": {
            "provider_called": False,
            "tool_called": False,
            "retriever_called": False,
            "custom_import_loaded": False,
            "authority_mutated": False,
        },
    }


def materialized_pipeline_topology(intent: Any) -> dict[str, Any]:
    topology = validate_materializable_pipeline_topology(intent)
    if not topology:
        return {}
    materialized = dict(topology)
    declared = declared_materializable_topology(intent)
    declared_kind = str(declared.get("kind") or "")
    if declared_kind and declared_kind != "pipeline":
        materialized["execution_status"] = _materialized_status_for_kind(declared_kind)
        materialized["materialized_from_kind"] = declared_kind
        materialized["renderer"] = _renderer_for_kind(declared_kind)
    else:
        materialized["execution_status"] = PIPELINE_MATERIALIZED_STATUS
    materialized["scheduler_plan"] = _scheduler_plan_for_topology(materialized)
    return materialized


def module_class_name(module: Mapping[str, Any]) -> str:
    signature = _module_signature(module)
    return f"{sanitize_ident(str(signature.get('name') or module.get('id')))}Module"


def _signature_class_name(module: Mapping[str, Any]) -> str:
    signature = _module_signature(module)
    return sanitize_ident(str(signature.get("name") or module.get("id")))


def _signature_inputs(module: Mapping[str, Any]) -> list[str]:
    signature = _module_signature(module)
    return [str(item) for item in signature.get("inputs", [])]


def _signature_outputs(module: Mapping[str, Any]) -> list[str]:
    signature = _module_signature(module)
    return [str(item) for item in signature.get("outputs", [])]


def _module_id(module: Mapping[str, Any]) -> str:
    return str(module.get("id") or "")


def _field_line(name: str, *, role: str) -> str:
    field_factory = "InputField" if role == "input" else "OutputField"
    desc = f"{name.replace('_', ' ')} ({role})"
    return f"    {name}: str = dspy.{field_factory}(desc={desc!r})"


_MAX_PROVIDER_SIGNATURE_DESCRIPTION_CHARS = 16_000


def _provider_signature_description(intent: Any, module: Mapping[str, Any]) -> str:
    """Project the declared program contract into the provider-visible signature."""
    role = str(module.get("role") or "").strip()
    objective = str(getattr(intent, "objective", "") or "").strip()
    parts = [f"Module role: {role}." if role else ""]
    if objective and objective != role:
        parts.append(f"Program objective: {objective}.")
    constraints = [
        str(item).strip()
        for item in list(getattr(intent, "constraints", []) or [])
        if str(item).strip()
    ]
    if constraints:
        parts.append("Program constraints: " + "; ".join(constraints) + ".")

    output_names = set(_signature_outputs(module))
    for raw_criterion in list(getattr(intent, "quality_criteria", []) or []):
        if not isinstance(raw_criterion, Mapping):
            continue
        criterion = dict(raw_criterion)
        output_field = str(criterion.get("output_field") or "")
        if output_field not in output_names:
            continue
        groups = [
            "(" + " or ".join(repr(str(term)) for term in group) + ")"
            for group in list(criterion.get("required_concept_groups") or [])
        ]
        criterion_id = str(criterion.get("id") or "declared_quality")
        min_score = float(criterion.get("min_score", 1.0))
        contract = (
            f"Declared quality criterion {criterion_id!r} for output "
            f"{output_field!r}: required concept groups "
            + " and ".join(groups)
            + f"; minimum coverage score {min_score:g}."
        )
        forbidden = [
            str(term) for term in list(criterion.get("forbidden_concepts") or [])
        ]
        if forbidden:
            contract += (
                " Forbidden phrases: "
                + ", ".join(repr(term) for term in forbidden)
                + "."
            )
        parts.append(contract)

    description = surface_description(" ".join(part for part in parts if part))
    if len(description) > _MAX_PROVIDER_SIGNATURE_DESCRIPTION_CHARS:
        raise ProgramTopologyMaterializationError(
            "provider-facing signature description exceeds "
            f"{_MAX_PROVIDER_SIGNATURE_DESCRIPTION_CHARS} characters"
        )
    return description


def render_pipeline_signature_surface(intent: Any) -> tuple[str, dict[str, Any]]:
    topology = validate_materializable_pipeline_topology(intent)
    modules = [dict(item) for item in topology.get("modules", [])]
    lines = ["import dspy", ""]
    for index, module in enumerate(modules):
        signature_name = _signature_class_name(module)
        doc = _provider_signature_description(intent, module)
        lines.extend(
            [
                f"class {signature_name}(dspy.Signature):",
                f"    {doc!r}",
                "",
            ]
        )
        lines.extend(
            _field_line(name, role="input") for name in _signature_inputs(module)
        )
        lines.extend(
            _field_line(name, role="output") for name in _signature_outputs(module)
        )
        if index != len(modules) - 1:
            lines.extend(["", ""])
    lines.append("")
    return "\n".join(lines), {
        "topology_materialized": True,
        "topology_kind": "pipeline",
        "signature_classes": [_signature_class_name(module) for module in modules],
    }


def render_pipeline_module_surface(intent: Any) -> tuple[str, dict[str, Any]]:
    topology = validate_materializable_pipeline_topology(intent)
    modules = [dict(item) for item in topology.get("modules", [])]
    signature_names = [_signature_class_name(module) for module in modules]
    lines: list[str] = ["import json", "", "import dspy", "", "from signature import ("]
    lines.extend(f"    {name}," for name in signature_names)
    lines.extend([")", ""])
    if any(str(module.get("primitive") or "") == "Retriever" for module in modules):
        lines.extend(
            [
                "",
                "def _retriever_tokens(value: object) -> set[str]:",
                "    text = ''.join(ch.lower() if ch.isalnum() else ' ' for ch in str(value))",
                "    return {part for part in text.split() if part}",
                "",
                "",
                "def _select_inline_documents(query: object, documents: list[dict[str, str]], k: int) -> list[dict[str, object]]:",
                "    query_tokens = _retriever_tokens(query)",
                "    scored: list[tuple[int, int, dict[str, str]]] = []",
                "    for index, document in enumerate(documents):",
                "        document_tokens = _retriever_tokens(document.get('text', ''))",
                "        score = len(query_tokens & document_tokens)",
                "        scored.append((score, index, document))",
                "    scored.sort(key=lambda item: (-item[0], item[1]))",
                "    selected = []",
                "    for score, _index, document in scored[:k]:",
                "        selected.append({'id': document.get('id', ''), 'text': document.get('text', ''), 'score': score})",
                "    return selected",
                "",
            ]
        )
    for index, module in enumerate(modules):
        signature_name = _signature_class_name(module)
        class_name = module_class_name(module)
        primitive = str(module.get("primitive") or "Predict")
        doc = surface_description(
            str(module.get("role") or getattr(intent, "objective", ""))
        )
        input_names = _signature_inputs(module)
        input_params = ", ".join(f"{name}: str" for name in input_names)
        call_args = ", ".join(f"{name}={name}" for name in input_names)
        if primitive == "Retriever":
            retriever = normalize_inline_retriever_config(
                module.get("retriever"), module_id=str(module.get("id") or "")
            )
            output_name = _signature_outputs(module)[0]
            query_expr = (
                " + ' ' + ".join(f"str({name})" for name in input_names) or "''"
            )
            lines.extend(
                [
                    f"class {class_name}(dspy.Module):",
                    f"    {doc!r}",
                    "",
                    f"    _DOCUMENTS = {retriever['documents']!r}",
                    f"    _K = {retriever['k']!r}",
                    "",
                    "    def __init__(self, use_cot: bool = False) -> None:",
                    "        super().__init__()",
                    "",
                    f"    def forward(self, {input_params}) -> dspy.Prediction:",
                    f"        selected = _select_inline_documents({query_expr}, self._DOCUMENTS, self._K)",
                    f"        return dspy.Prediction({output_name}=json.dumps(selected, ensure_ascii=False, sort_keys=True))",
                ]
            )
        elif primitive == "ReAct":
            react = dict(module.get("react") or {})
            max_iters = int(react.get("max_iters") or 1)
            declared_tool_refs = [
                str(item)
                for item in react.get("declared_tool_refs", [])
                if str(item).strip()
            ]
            lines.extend(
                [
                    f"class {class_name}(dspy.Module):",
                    f"    {doc!r}",
                    "",
                    f"    _MAX_ITERS = {max_iters!r}",
                    f"    _DECLARED_TOOL_REFS = {declared_tool_refs!r}",
                    "    _TOOL_BINDING_STATUS = 'declared_refs_only_not_bound'",
                    "",
                    "    def __init__(self, use_cot: bool = False) -> None:",
                    "        super().__init__()",
                    f"        self.predict = dspy.ReAct({signature_name}, tools=[], max_iters={max_iters!r})",
                    "",
                    f"    def forward(self, {input_params}) -> dspy.Prediction:",
                    f"        return self.predict({call_args})",
                ]
            )
        elif primitive == "ProgramOfThought":
            config = dict(module.get("program_of_thought") or {})
            max_iters = int(config.get("max_iters") or 1)
            interpreter_keyword = _program_of_thought_interpreter_keyword()
            interpreter_factory_prefix = (
                "lambda: " if interpreter_keyword == "interpreter_factory" else ""
            )
            interpreter_binding = f"{interpreter_keyword}={interpreter_factory_prefix}dspy.PythonInterpreter("
            lines.extend(
                [
                    f"class {class_name}(dspy.Module):",
                    f"    {doc!r}",
                    "",
                    f"    _MAX_ITERS = {max_iters!r}",
                    "    _TRUSTED_LOCAL_CORE_PRODUCTION_STATUS = 'excluded_lm_generated_runtime_code'",
                    "",
                    "    def __init__(self, use_cot: bool = False) -> None:",
                    "        super().__init__()",
                    "        self.predict = dspy.ProgramOfThought(",
                    f"            {signature_name},",
                    f"            max_iters={max_iters!r},",
                    f"            {interpreter_binding}",
                    "                enable_read_paths=[],",
                    "                enable_write_paths=[],",
                    "                enable_env_vars=[],",
                    "                enable_network_access=[],",
                    "                tools={},",
                    "                sync_files=False,",
                    "            ),",
                    "        )",
                    "",
                    f"    def forward(self, {input_params}) -> dspy.Prediction:",
                    f"        return self.predict({call_args})",
                ]
            )
        else:
            lines.extend(
                [
                    f"class {class_name}(dspy.Module):",
                    f"    {doc!r}",
                    "",
                    "    def __init__(self, use_cot: bool = False) -> None:",
                    "        super().__init__()",
                    f"        self.predict = dspy.{primitive}({signature_name})",
                    "",
                    f"    def forward(self, {input_params}) -> dspy.Prediction:",
                    f"        return self.predict({call_args})",
                ]
            )
        if index != len(modules) - 1:
            lines.extend(["", ""])
    lines.extend(
        [
            "",
            "",
            "def build_modules(*, use_cot: bool = False) -> dict[str, dspy.Module]:",
            '    """Construct the generated topology module instances."""',
            "    return {",
        ]
    )
    lines.extend(
        f"        {_module_id(module)!r}: {module_class_name(module)}(use_cot=use_cot),"
        for module in modules
    )
    lines.extend(
        [
            "    }",
            "",
            "",
            "def io_spec() -> dict[str, list[str]]:",
            '    """Return the declared program IO contract."""',
            f"    return {{'inputs': {list(getattr(intent, 'inputs', []))!r}, 'outputs': {list(getattr(intent, 'outputs', []))!r}}}",
            "",
            "",
            "def output_weights() -> dict[str, float]:",
            '    """Provide deterministic output weighting for evaluation."""',
            "    return {",
        ]
    )
    lines.extend(f"        {name!r}: 1.0," for name in getattr(intent, "outputs", []))
    lines.extend(
        [
            "    }",
            "",
            "",
            "def normalize_output(",
            "    key: str,",
            "    gold: str,",
            "    pred: str,",
            "    pred_name: str | None = None,",
            "    pred_trace: object | None = None,",
            ") -> tuple[str, str]:",
            '    """Normalize gold/pred pairs for deterministic checks."""',
            "    if _json_container_text(gold) and _json_container_text(pred):",
            "        return _normalize_json_text(gold), _normalize_json_text(pred)",
            "    return gold, pred",
            "",
            "",
            "def _json_container_text(value: str) -> bool:",
            "    text = value.strip()",
            "    return (text.startswith('{') and text.endswith('}')) or (text.startswith('[') and text.endswith(']'))",
            "",
            "",
            "def _normalize_json_text(value: str) -> str:",
            "    parsed = json.loads(value.strip())",
            "    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(',', ':'))",
            "",
        ]
    )
    return "\n".join(lines), {
        "topology_materialized": True,
        "topology_kind": "pipeline",
        "module_classes": [module_class_name(module) for module in modules],
    }


def render_pipeline_program_code(intent: Any) -> str:
    topology = validate_materializable_pipeline_topology(intent)
    modules = [dict(item) for item in topology.get("modules", [])]
    module_classes = [module_class_name(module) for module in modules]
    program_class = (
        f"{sanitize_ident(getattr(intent, 'name', 'IntentProgram'))}PipelineProgram"
    )
    constraints = list(getattr(intent, "constraints", []))
    metric = getattr(intent, "metric", None) or "unspecified"
    quality_criteria = list(getattr(intent, "quality_criteria", []) or [])
    declared_topology = declared_materializable_topology(intent)
    inferred_topology = prompt_inferred_pipeline_topology(intent)
    materialized_topology = materialized_pipeline_topology(intent)
    declared_kind = str(declared_topology.get("kind") or "")
    if declared_kind:
        renderer = _renderer_for_kind(declared_kind)
    elif inferred_topology and not declared_topology:
        renderer = PROMPT_INFERRED_PIPELINE_RENDERER
    else:
        renderer = "pipeline_topology_renderer"
    materialization_scope = {
        "topology_declared": bool(declared_topology),
        "topology_inferred": bool(inferred_topology and not declared_topology),
        "topology_materialized": True,
        "current_renderer": renderer,
    }
    runtime = getattr(intent, "runtime", {}) or {}
    protected_snapshot_profile = (
        runtime.get("generated_source_profile") == "protected_snapshot"
    )
    module_signatures = {
        _module_id(module): {
            "inputs": _signature_inputs(module),
            "outputs": _signature_outputs(module),
        }
        for module in modules
    }
    module_primitives = {
        _module_id(module): str(module.get("primitive") or "Predict")
        for module in modules
    }
    lines: list[str] = [
        "from __future__ import annotations",
        "",
        "import json",
        "from pathlib import Path",
        "from typing import Any",
        "",
        "import dspy",
        "",
        "from module import (",
    ]
    lines.extend(f"    {name}," for name in module_classes)
    lines.extend(
        [
            "    io_spec,",
            "    normalize_output,",
            "    output_weights,",
            ")",
            "",
            f"OBJECTIVE = {getattr(intent, 'objective', '')!r}",
            f"CONSTRAINTS = {constraints!r}",
            f"METRIC = {metric!r}",
            f"QUALITY_CRITERIA = {quality_criteria!r}",
            f"DECLARED_TOPOLOGY = {declared_topology!r}",
            f"INFERRED_TOPOLOGY = {inferred_topology!r}",
            f"MATERIALIZED_TOPOLOGY = {materialized_topology!r}",
            f"TOPOLOGY_EXECUTION_STATUS = {materialized_topology.get('execution_status', PIPELINE_MATERIALIZED_STATUS)!r}",
            f"MATERIALIZATION_SCOPE = {materialization_scope!r}",
            f"SCHEDULER_PLAN = {dict(materialized_topology.get('scheduler_plan') or {})!r}",
            f"MODULE_ORDER = {[_module_id(module) for module in modules]!r}",
            f"MODULE_SIGNATURES = {module_signatures!r}",
            f"MODULE_PRIMITIVES = {module_primitives!r}",
            f"PROGRAM_OUTPUTS = {list(getattr(intent, 'outputs', []))!r}",
            f"EDGES = {list(topology.get('edges', []))!r}",
            "PROGRAM_TEMPLATE_VERSION = 'program-candidate-assembly-v1'",
            "",
            "",
            *(
                [
                    "def load_manifest() -> dict[str, Any]:",
                    "    return {}",
                    "",
                    "",
                    "def _manifest_hash() -> str:",
                    "    return ''",
                    "",
                    "",
                ]
                if protected_snapshot_profile
                else [
                    "def assembly_manifest_path() -> Path:",
                    "    return Path(__file__).with_name('manifest.json')",
                    "",
                    "",
                    "def load_manifest() -> dict[str, Any]:",
                    "    path = assembly_manifest_path()",
                    "    if not path.exists():",
                    "        return {}",
                    "    try:",
                    "        payload = json.loads(path.read_text(encoding='utf-8'))",
                    "    except Exception:",
                    "        return {}",
                    "    return dict(payload) if isinstance(payload, dict) else {}",
                    "",
                    "",
                    "def _current_manifest_hash() -> str:",
                    "    path = assembly_manifest_path()",
                    "    if not path.exists():",
                    "        return ''",
                    "    try:",
                    "        import hashlib",
                    "",
                    "        return hashlib.sha256(path.read_bytes()).hexdigest()",
                    "    except Exception:",
                    "        return ''",
                    "",
                    "",
                    "def _receipt_manifest_hash() -> str:",
                    "    path = Path(str(assembly_manifest_path()) + '.meta.json')",
                    "    if not path.exists():",
                    "        return ''",
                    "    try:",
                    "        payload = json.loads(path.read_text(encoding='utf-8'))",
                    "    except Exception:",
                    "        return ''",
                    "    if not isinstance(payload, dict):",
                    "        return ''",
                    "    value = payload.get('hash') or payload.get('output_hash')",
                    "    return str(value) if value else ''",
                    "",
                    "",
                    "def _manifest_hash() -> str:",
                    "    return _receipt_manifest_hash() or _current_manifest_hash()",
                    "",
                    "",
                ]
            ),
            *(
                [
                    "def configure_observability(",
                    "    *,",
                    "    run_name: str = 'program-runtime',",
                    "    run_kind: str = 'program-runtime',",
                    ") -> bool:",
                    "    return False",
                    "",
                    "",
                    "def end_observability_run(started: bool, *, status: str = 'FINISHED') -> None:",
                    "    return None",
                    "",
                    "",
                ]
                if protected_snapshot_profile
                else [
                    "def program_observability_tags() -> dict[str, str]:",
                    "    manifest = load_manifest()",
                    "    assembly = manifest.get('candidate_assembly')",
                    "    if not isinstance(assembly, dict):",
                    "        assembly = {}",
                    "    tags = {",
                    "        'program.name': str(intent_summary().get('name') or ''),",
                    "        'program.assembly_id': str(assembly.get('assembly_id') or ''),",
                    "        'program.candidate_id': str(assembly.get('candidate_id') or ''),",
                    "    }",
                    "    manifest_hash = _manifest_hash()",
                    "    if manifest_hash:",
                    "        tags['program.manifest_hash'] = manifest_hash",
                    "    return {key: value for key, value in tags.items() if value}",
                    "",
                    "",
                    "def configure_observability(",
                    "    *,",
                    "    run_name: str = 'program-runtime',",
                    "    run_kind: str = 'program-runtime',",
                    ") -> bool:",
                    "    try:",
                    "        from dspx.tracing import enable_mlflow_from_env, ensure_run_with_standard_tags, get_mlflow",
                    "",
                    "        enable_mlflow_from_env()",
                    "        if get_mlflow() is None:",
                    "            return False",
                    "        extra_tags = program_observability_tags()",
                    "        if run_kind in {'program-runtime', 'program-eval'} and not extra_tags.get('program.assembly_id'):",
                    "            return False",
                    "        return ensure_run_with_standard_tags(",
                    "            'program',",
                    "            template_version=PROGRAM_TEMPLATE_VERSION,",
                    "            run_name=run_name,",
                    "            run_kind=run_kind,",
                    "            output_basename='program.py',",
                    "            output_hash=_manifest_hash(),",
                    "            extra=extra_tags,",
                    "        )",
                    "    except Exception:",
                    "        return False",
                    "",
                    "",
                    "def _active_mlflow():",
                    "    try:",
                    "        from dspx.tracing import get_mlflow",
                    "",
                    "        mlflow = get_mlflow()",
                    "        if mlflow is None or mlflow.active_run() is None:",
                    "            return None",
                    "        return mlflow",
                    "    except Exception:",
                    "        return None",
                    "",
                    "",
                    "def _set_observability_status(status: str, *, error: Exception | None = None) -> None:",
                    "    mlflow = _active_mlflow()",
                    "    if mlflow is None:",
                    "        return",
                    "    try:",
                    "        mlflow.set_tag('program.runtime.status', status)",
                    "    except Exception:",
                    "        pass",
                    "    try:",
                    "        mlflow.log_metric('program.runtime.error', 1.0 if error is not None else 0.0)",
                    "    except Exception:",
                    "        pass",
                    "    if error is not None:",
                    "        try:",
                    "            mlflow.set_tag('program.runtime.error_type', type(error).__name__)",
                    "        except Exception:",
                    "            pass",
                    "",
                    "",
                    "def end_observability_run(started: bool, *, status: str = 'FINISHED') -> None:",
                    "    if not started:",
                    "        return",
                    "    try:",
                    "        from dspx.tracing import get_mlflow",
                    "",
                    "        mlflow = get_mlflow()",
                    "        if mlflow is not None:",
                    "            try:",
                    "                mlflow.end_run(status=status)",
                    "            except TypeError:",
                    "                mlflow.end_run()",
                    "    except Exception:",
                    "        pass",
                    "",
                    "",
                    "def run_with_observability(**inputs: object) -> dspy.Prediction:",
                    "    started = configure_observability(run_name='program-runtime', run_kind='program-runtime')",
                    "    end_status = 'FINISHED'",
                    "    try:",
                    "        program = build_program()",
                    "        prediction = program(**inputs)",
                    "        _set_observability_status('passed')",
                    "        return prediction",
                    "    except Exception as exc:",
                    "        end_status = 'FAILED'",
                    "        _set_observability_status('failed', error=exc)",
                    "        raise",
                    "    finally:",
                    "        end_observability_run(started, status=end_status)",
                    "",
                    "",
                ]
            ),
            *(
                [
                    "def _prediction_mapping(prediction: object) -> dict[str, object]:",
                    "    return dict(prediction)",
                    "",
                    "",
                ]
                if protected_snapshot_profile
                else [
                    "def _prediction_mapping(prediction: object) -> dict[str, object]:",
                    "    if isinstance(prediction, dict):",
                    "        return dict(prediction)",
                    "    for method_name in ('toDict', 'to_dict', 'model_dump'):",
                    "        method = getattr(prediction, method_name, None)",
                    "        if callable(method):",
                    "            try:",
                    "                payload = method()",
                    "            except Exception:",
                    "                continue",
                    "            if isinstance(payload, dict):",
                    "                return dict(payload)",
                    "    return {}",
                    "",
                    "",
                ]
            ),
            "def _edge_condition_matches(edge: dict[str, object], state: dict[str, object]) -> bool:",
            "    when = edge.get('when')",
            "    if not isinstance(when, dict):",
            "        return True",
            "    field = str(when.get('field') or '')",
            "    return str(state.get(field, '')) == str(when.get('equals'))",
            "",
            "",
            "def _edge_source_ready(edge: dict[str, object], executed: set[str]) -> bool:",
            "    source = str(edge.get('from') or '')",
            "    return source == 'input' or source in executed",
            "",
            "",
            "def _module_ready(module_id: str, state: dict[str, object], executed: set[str]) -> bool:",
            "    inputs = list(MODULE_SIGNATURES[module_id]['inputs'])",
            "    if any(name not in state for name in inputs):",
            "        return False",
            "    inbound = [edge for edge in EDGES if edge.get('to') == module_id]",
            "    if not inbound:",
            "        return False",
            "    return any(",
            "        _edge_source_ready(edge, executed) and _edge_condition_matches(edge, state)",
            "        for edge in inbound",
            "    )",
            "",
            "",
            "def _output_edges_ready(module_id: str, state: dict[str, object], executed: set[str]) -> bool:",
            "    outbound = [edge for edge in EDGES if edge.get('from') == module_id and edge.get('to') == 'output']",
            "    return any(",
            "        _edge_source_ready(edge, executed) and _edge_condition_matches(edge, state)",
            "        for edge in outbound",
            "    )",
            "",
            "",
            "def _missing_declared_outputs(outputs: dict[str, object]) -> list[str]:",
            "    return [name for name in PROGRAM_OUTPUTS if name not in outputs]",
            "",
            "",
            f"class {program_class}(dspy.Module):",
            '    """Composed explicit pipeline topology program."""',
            "",
            "    def __init__(self, use_cot: bool = False) -> None:",
            "        super().__init__()",
        ]
    )
    lines.extend(
        f"        self.{_module_id(module)} = {module_class_name(module)}(use_cot=use_cot)"
        for module in modules
    )
    forward_params = ", ".join(f"{name}: str" for name in getattr(intent, "inputs", []))
    state_payload = ", ".join(
        f"{name!r}: {name}" for name in getattr(intent, "inputs", [])
    )
    static_dispatch: list[str] = []
    for index, module in enumerate(modules):
        branch = "if" if index == 0 else "elif"
        module_id = _module_id(module)
        static_dispatch.extend(
            [
                f"                {branch} module_id == {module_id!r}:",
                f"                    prediction = self.{module_id}(**kwargs)",
            ]
        )
    static_dispatch.extend(
        [
            "                else:",
            "                    raise RuntimeError(f'unknown pipeline module: {module_id}')",
        ]
    )
    output_mapping = [
        "                for output_name in signature['outputs']:",
        "                    if output_name in mapped:",
        "                        state[output_name] = mapped[output_name]",
    ]
    if not protected_snapshot_profile:
        output_mapping.extend(
            [
                "                    elif hasattr(prediction, output_name):",
                "                        state[output_name] = getattr(prediction, output_name)",
            ]
        )
    output_mapping.extend(
        [
            "                    if output_name in state:",
            "                        call_outputs[output_name] = state[output_name]",
        ]
    )
    lines.extend(
        [
            "",
            f"    def forward(self, {forward_params}) -> dspy.Prediction:",
            f"        state: dict[str, object] = {{{state_payload}}}",
            "        delivered_outputs: dict[str, object] = {}",
            "        self._last_runtime_trace = {'schema_version': 'program-runtime-trace-fragment-v1', 'module_calls': [], 'final_outputs': {}, 'scheduler_events': []}",
            "        executed: set[str] = set()",
            "        pending: set[str] = set(MODULE_ORDER)",
            "        while pending:",
            "            progressed = False",
            "            for module_id in MODULE_ORDER:",
            "                if module_id not in pending:",
            "                    continue",
            "                if not _module_ready(module_id, state, executed):",
            "                    continue",
            "                signature = MODULE_SIGNATURES[module_id]",
            "                kwargs = {name: state[name] for name in signature['inputs']}",
            *static_dispatch,
            "                executed.add(module_id)",
            "                pending = pending - {module_id}",
            "                progressed = True",
            "                mapped = _prediction_mapping(prediction)",
            "                call_outputs: dict[str, object] = {}",
            *output_mapping,
            "                self._last_runtime_trace['module_calls'].append({",
            "                    'module_id': module_id,",
            "                    'primitive': MODULE_PRIMITIVES.get(module_id, 'Predict'),",
            "                    'inputs': _jsonable(kwargs),",
            "                    'outputs': _jsonable(call_outputs),",
            "                    'status': 'executed',",
            "                    'react_steps': [],",
            "                    'react_v2_steps': [],",
            "                    'program_of_thought_steps': [],",
            "                    'tool_call_intents': [],",
            "                    'tool_call_results': [],",
            "                })",
            "                if _output_edges_ready(module_id, state, executed):",
            "                    for output_name in signature['outputs']:",
            "                        if output_name in PROGRAM_OUTPUTS and output_name in state:",
            "                            delivered_outputs[output_name] = state[output_name]",
            "            if not progressed:",
            "                missing_outputs = _missing_declared_outputs(delivered_outputs)",
            "                if missing_outputs:",
            "                    self._last_runtime_trace['scheduler_events'].append({'status': 'scheduler_stalled', 'missing_outputs': list(missing_outputs), 'pending': sorted(pending)})",
            "                    raise RuntimeError(",
            "                        'pipeline topology scheduler stalled before producing declared outputs: '",
            "                        f'missing_outputs={missing_outputs} pending={sorted(pending)}'",
            "                    )",
            "                break",
            "        missing_outputs = _missing_declared_outputs(delivered_outputs)",
            "        if missing_outputs:",
            "            self._last_runtime_trace['scheduler_events'].append({'status': 'completed_missing_outputs', 'missing_outputs': list(missing_outputs), 'pending': sorted(pending)})",
            "            raise RuntimeError(",
            "                'pipeline topology completed without declared outputs: '",
            "                f'missing_outputs={missing_outputs}'",
            "            )",
            "        self._last_runtime_trace['scheduler_events'].append({'status': 'completed', 'missing_outputs': [], 'pending': []})",
            "        self._last_runtime_trace['final_outputs'] = _jsonable(delivered_outputs)",
            f"        return dspy.Prediction({', '.join(f'{name}=_jsonable(delivered_outputs[{name!r}])' for name in getattr(intent, 'outputs', []))})",
            "",
            "",
            "def _jsonable(value: object) -> object:",
            "    if value is None or isinstance(value, (str, int, float, bool)):",
            "        return value",
            "    if isinstance(value, dict):",
            "        return {str(key): _jsonable(item) for key, item in value.items()}",
            "    if isinstance(value, (list, tuple)):",
            "        return [_jsonable(item) for item in value]",
            "    return str(value)",
            "",
            "",
            "def build_program() -> dspy.Module:",
            f"    return {program_class}()",
            "",
            "",
            "def build_student(*, use_cot: bool = False) -> dspy.Module:",
            f"    return {program_class}(use_cot=use_cot)",
            "",
            "",
            "def intent_summary() -> dict[str, object]:",
            "    return {",
            f"        'name': {getattr(intent, 'name', '')!r},",
            "        'objective': OBJECTIVE,",
            "        'constraints': list(CONSTRAINTS),",
            "        'metric': METRIC,",
            "        'quality_criteria': list(QUALITY_CRITERIA),",
            "        'io': io_spec(),",
            "        'declared_topology': dict(DECLARED_TOPOLOGY),",
            "        'inferred_topology': dict(INFERRED_TOPOLOGY),",
            "        'materialized_topology': dict(MATERIALIZED_TOPOLOGY),",
            "        'topology_execution_status': TOPOLOGY_EXECUTION_STATUS,",
            "        'materialization_scope': dict(MATERIALIZATION_SCOPE),",
            "        'scheduler_plan': dict(SCHEDULER_PLAN),",
            "        'module_order': list(MODULE_ORDER),",
            f"        'program_class': {program_class!r},",
            "    }",
            "",
        ]
    )
    return "\n".join(lines)
