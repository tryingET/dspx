from __future__ import annotations

from typing import Any, Mapping
import keyword
import re

PROGRAM_CAPABILITY_CONTRACT_SCHEMA = "program-capability-contract-v1"
PROGRAM_CAPABILITY_REGISTRY_SCHEMA = "program-capability-registry-v1"
PROGRAM_CAPABILITY_DECLARATION_SCHEMA = "program-capability-declaration-v1"

_MATERIALIZABLE_PIPELINE_PRIMITIVES = {"Predict", "ChainOfThought"}
_CONDITIONAL_PIPELINE_PRIMITIVES = {"Retriever", "ReAct", "ProgramOfThought"}
_ALLOWED_TOPOLOGY_KINDS = [
    "pipeline",
    "router",
    "retrieve_then_answer",
    "extract_transform_validate",
    "generate_critique_revise",
]
_MAX_INLINE_RETRIEVER_K = 10
_MAX_INLINE_RETRIEVER_DOCUMENTS = 100
_MAX_INLINE_RETRIEVER_DOCUMENT_CHARS = 4000
_PRIMITIVE_CANONICAL_NAMES = {
    "predict": "Predict",
    "chainofthought": "ChainOfThought",
    "chain_of_thought": "ChainOfThought",
    "react": "ReAct",
    "programofthought": "ProgramOfThought",
    "program_of_thought": "ProgramOfThought",
    "retriever": "Retriever",
    "retrieve": "Retriever",
    "custom": "Custom",
}
_DECLARATION_KINDS = {
    "dspy_primitive",
    "retriever",
    "tool",
    "react",
    "program_of_thought",
    "custom_import",
    "custom_module",
}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DOTTED_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")

_DESCRIPTOR_EFFECTS = {
    "provider_called": False,
    "tool_called": False,
    "custom_import_loaded": False,
    "network": False,
    "filesystem_read": False,
    "filesystem_write": False,
    "subprocess": False,
    "external_authority": False,
}

_NON_AUTHORITY = {
    "ranking_authority": False,
    "promotion_authority": False,
    "activation_authority": False,
    "oracle_authority": False,
    "governance_authority": False,
    "canonical_mutation": False,
    "external_mutation": False,
}


def _canonical_primitive(value: object) -> str:
    text = str(value or "").strip()
    return _PRIMITIVE_CANONICAL_NAMES.get(text.lower(), text)


def _validate_identifier(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if not text or not _IDENTIFIER_RE.match(text) or keyword.iskeyword(text):
        raise ValueError(f"{label} must be a valid Python identifier")
    return text


def _validate_dotted_name(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if not text or not _DOTTED_NAME_RE.match(text):
        raise ValueError(f"{label} must be a dotted Python identifier path")
    return text


def _capability_id_for_primitive(primitive: str) -> str:
    return f"dspy.primitive.{primitive}"


def primitive_capability_id(primitive: object) -> str:
    return _capability_id_for_primitive(_canonical_primitive(primitive))


def materializable_pipeline_primitives() -> set[str]:
    return set(_MATERIALIZABLE_PIPELINE_PRIMITIVES)


def is_pipeline_primitive_materializable(primitive: object) -> bool:
    return _canonical_primitive(primitive) in _MATERIALIZABLE_PIPELINE_PRIMITIVES


def normalize_retriever_config(value: object, *, module_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(
            f"pipeline Retriever module {module_id!r} requires retriever object"
        )
    payload = dict(value)
    mode = str(payload.get("mode") or "").strip()
    if mode == "local_corpus_snapshot":
        extra_keys = set(payload) - {"mode", "k", "path", "id_field", "text_field"}
        if extra_keys:
            raise ValueError(
                f"pipeline Retriever module {module_id!r} retriever has unsupported keys: {sorted(extra_keys)}"
            )
        path = str(payload.get("path") or "").strip()
        if not path:
            raise ValueError(
                f"pipeline Retriever module {module_id!r} retriever.path must not be blank"
            )
        raw_k = payload.get("k", 3)
        if isinstance(raw_k, bool):
            raise ValueError(
                f"pipeline Retriever module {module_id!r} retriever.k must be an integer"
            )
        try:
            k = int(raw_k)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"pipeline Retriever module {module_id!r} retriever.k must be an integer"
            ) from exc
        if k < 1 or k > _MAX_INLINE_RETRIEVER_K:
            raise ValueError(
                f"pipeline Retriever module {module_id!r} retriever.k must be between 1 and {_MAX_INLINE_RETRIEVER_K}"
            )
        return {
            "mode": "local_corpus_snapshot",
            "path": path,
            "id_field": str(payload.get("id_field") or "id").strip() or "id",
            "text_field": str(payload.get("text_field") or "text").strip() or "text",
            "k": k,
        }
    return normalize_inline_retriever_config(value, module_id=module_id)


def normalize_inline_retriever_config(
    value: object, *, module_id: str
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(
            f"pipeline Retriever module {module_id!r} requires retriever object"
        )
    payload = dict(value)
    extra_keys = set(payload) - {"mode", "k", "documents"}
    if extra_keys:
        raise ValueError(
            f"pipeline Retriever module {module_id!r} retriever has unsupported keys: {sorted(extra_keys)}"
        )
    mode = str(payload.get("mode") or "").strip()
    if mode != "inline_corpus":
        raise ValueError(
            f"pipeline Retriever module {module_id!r} supports only retriever.mode='inline_corpus' or 'local_corpus_snapshot'"
        )
    raw_k = payload.get("k", 3)
    if isinstance(raw_k, bool):
        raise ValueError(
            f"pipeline Retriever module {module_id!r} retriever.k must be an integer"
        )
    try:
        k = int(raw_k)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"pipeline Retriever module {module_id!r} retriever.k must be an integer"
        ) from exc
    if k < 1 or k > _MAX_INLINE_RETRIEVER_K:
        raise ValueError(
            f"pipeline Retriever module {module_id!r} retriever.k must be between 1 and {_MAX_INLINE_RETRIEVER_K}"
        )
    raw_documents = payload.get("documents")
    if not isinstance(raw_documents, list) or not raw_documents:
        raise ValueError(
            f"pipeline Retriever module {module_id!r} retriever.documents must be a non-empty list"
        )
    if len(raw_documents) > _MAX_INLINE_RETRIEVER_DOCUMENTS:
        raise ValueError(
            f"pipeline Retriever module {module_id!r} retriever.documents must contain at most {_MAX_INLINE_RETRIEVER_DOCUMENTS} documents"
        )
    documents: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, raw_document in enumerate(raw_documents):
        if not isinstance(raw_document, Mapping):
            raise ValueError(
                f"pipeline Retriever module {module_id!r} document {index} must be an object"
            )
        document = dict(raw_document)
        extra_doc_keys = set(document) - {"id", "text"}
        if extra_doc_keys:
            raise ValueError(
                f"pipeline Retriever module {module_id!r} document {index} has unsupported keys: {sorted(extra_doc_keys)}"
            )
        doc_id = str(document.get("id") or "").strip()
        if not doc_id:
            raise ValueError(
                f"pipeline Retriever module {module_id!r} document {index} id must not be blank"
            )
        if doc_id in seen_ids:
            raise ValueError(
                f"pipeline Retriever module {module_id!r} document ids must be unique"
            )
        text = str(document.get("text") or "")
        if not text.strip():
            raise ValueError(
                f"pipeline Retriever module {module_id!r} document {doc_id!r} text must not be blank"
            )
        if len(text) > _MAX_INLINE_RETRIEVER_DOCUMENT_CHARS:
            raise ValueError(
                f"pipeline Retriever module {module_id!r} document {doc_id!r} text exceeds {_MAX_INLINE_RETRIEVER_DOCUMENT_CHARS} characters"
            )
        seen_ids.add(doc_id)
        documents.append({"id": doc_id, "text": text})
    return {"mode": "inline_corpus", "k": k, "documents": documents}


def is_pipeline_module_materializable(module: Mapping[str, Any]) -> bool:
    primitive = _canonical_primitive(module.get("primitive") or "Predict")
    if primitive in {"Predict", "ChainOfThought"}:
        return True
    if primitive == "ReAct":
        react = module.get("react")
        if not isinstance(react, Mapping):
            return False
        return react.get("tools") == [] and isinstance(react.get("max_iters"), int)
    if primitive == "ProgramOfThought":
        config = module.get("program_of_thought")
        if not isinstance(config, Mapping):
            return False
        sandbox = config.get("sandbox")
        return isinstance(config.get("max_iters"), int) and isinstance(sandbox, Mapping)
    if primitive == "Retriever":
        try:
            normalize_inline_retriever_config(
                module.get("retriever"), module_id=str(module.get("id") or "")
            )
        except ValueError:
            return False
        return True
    return False


def _primitive_contract(primitive: str) -> dict[str, Any]:
    primitive = _canonical_primitive(primitive)
    materializable = primitive in _MATERIALIZABLE_PIPELINE_PRIMITIVES
    conditional = primitive in _CONDITIONAL_PIPELINE_PRIMITIVES
    return {
        "schema_version": PROGRAM_CAPABILITY_CONTRACT_SCHEMA,
        "capability_id": _capability_id_for_primitive(primitive),
        "kind": "dspy_primitive",
        "primitive": primitive,
        "status": "materializable"
        if materializable
        else "conditionally_materializable_with_adapter"
        if conditional
        else "declared_only_not_materializable",
        "materializable": materializable,
        "conditional_materializable": conditional,
        "allowed_topology_kinds": ["single_module", *_ALLOWED_TOPOLOGY_KINDS]
        if materializable
        else list(_ALLOWED_TOPOLOGY_KINDS)
        if conditional
        else [],
        "materialization_policy": {
            "generated_code_only": materializable or conditional,
            "custom_import_allowed": False,
            "tool_binding_allowed": False,
            "retriever_binding_allowed": False,
            "bounded_inline_retriever_adapter_allowed": primitive == "Retriever",
            "local_corpus_snapshot_adapter_allowed": primitive == "Retriever",
            "live_external_retriever_binding_allowed": False,
            "react_loop_allowed": primitive == "ReAct",
            "program_of_thought_allowed": primitive == "ProgramOfThought",
            "provider_call_allowed_by_contract": False,
            "fail_closed_without_explicit_adapter": True,
        },
        "routing_policy": {
            "when_field_equals": materializable or conditional,
            "arbitrary_expression": False,
        },
        "effects": dict(_DESCRIPTOR_EFFECTS),
        "non_authority": dict(_NON_AUTHORITY),
    }


def builtin_capability_contracts() -> list[dict[str, Any]]:
    return [
        _primitive_contract(primitive)
        for primitive in [
            "Predict",
            "ChainOfThought",
            "Retriever",
            "ReAct",
            "ProgramOfThought",
            "Custom",
        ]
    ]


def capability_contract_for_primitive(primitive: object) -> dict[str, Any]:
    return _primitive_contract(_canonical_primitive(primitive))


def module_capability_ref(module: Mapping[str, Any]) -> dict[str, Any]:
    primitive = _canonical_primitive(module.get("primitive") or "Predict")
    materializable = primitive in _MATERIALIZABLE_PIPELINE_PRIMITIVES
    runtime_binding = "generated_dspy_primitive" if materializable else "none"
    status = "materializable" if materializable else "declared_only_not_materializable"
    if primitive == "Retriever" and is_pipeline_module_materializable(module):
        materializable = True
        status = "materializable_with_bounded_inline_adapter"
        runtime_binding = "generated_bounded_inline_retriever_adapter"
    if primitive == "ReAct" and is_pipeline_module_materializable(module):
        materializable = True
        status = "materializable_with_empty_tools"
        runtime_binding = "generated_bounded_react_no_tools"
    if primitive == "ProgramOfThought" and is_pipeline_module_materializable(module):
        materializable = True
        status = "materializable_with_empty_sandbox"
        runtime_binding = "generated_sandboxed_program_of_thought"
    return {
        "schema_version": PROGRAM_CAPABILITY_CONTRACT_SCHEMA,
        "capability_id": _capability_id_for_primitive(primitive),
        "primitive": primitive,
        "status": status,
        "materializable": materializable,
        "runtime_binding": runtime_binding,
    }


def normalize_capability_declaration(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("program intent capability declarations must contain objects")
    raw = dict(value)
    declaration_id = _validate_identifier(
        raw.get("id") or raw.get("name"), label="capability declaration id"
    )
    kind = str(raw.get("kind") or "").strip()
    if not kind:
        raise ValueError(
            f"capability declaration {declaration_id!r} kind must not be blank"
        )
    if kind not in _DECLARATION_KINDS:
        allowed = sorted(_DECLARATION_KINDS)
        raise ValueError(
            f"capability declaration {declaration_id!r} kind must be one of {allowed}"
        )
    normalized: dict[str, Any] = {
        "schema_version": PROGRAM_CAPABILITY_DECLARATION_SCHEMA,
        "id": declaration_id,
        "kind": kind,
        "status": "declared_only_not_bound",
        "materializable": False,
        "runtime_binding": "none",
        "effects": dict(_DESCRIPTOR_EFFECTS),
        "non_authority": dict(_NON_AUTHORITY),
    }
    if raw.get("primitive") is not None:
        normalized["primitive"] = _canonical_primitive(raw.get("primitive"))
    if raw.get("module") is not None:
        normalized["module"] = _validate_dotted_name(
            raw.get("module"), label=f"capability declaration {declaration_id!r} module"
        )
    if raw.get("import") is not None:
        normalized["import"] = _validate_dotted_name(
            raw.get("import"), label=f"capability declaration {declaration_id!r} import"
        )
    if raw.get("description") is not None:
        normalized["description"] = str(raw.get("description") or "")
    if raw.get("inputs") is not None:
        if not isinstance(raw.get("inputs"), list):
            raise ValueError(
                f"capability declaration {declaration_id!r} inputs must be a list"
            )
        normalized["inputs"] = [str(item) for item in raw.get("inputs") or []]
    if raw.get("outputs") is not None:
        if not isinstance(raw.get("outputs"), list):
            raise ValueError(
                f"capability declaration {declaration_id!r} outputs must be a list"
            )
        normalized["outputs"] = [str(item) for item in raw.get("outputs") or []]
    return normalized


def normalize_program_capabilities(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("program intent capabilities must be an object")
    payload = dict(value)
    declarations_raw = payload.get("declarations", [])
    if not isinstance(declarations_raw, list):
        raise ValueError("program intent capabilities.declarations must be a list")
    declarations = [normalize_capability_declaration(item) for item in declarations_raw]
    ids = [str(item["id"]) for item in declarations]
    if len(set(ids)) != len(ids):
        raise ValueError("program intent capability declaration ids must be unique")
    if not declarations:
        return {}
    return {
        "schema_version": "program-capabilities-v1",
        "status": "declared_only_not_bound",
        "declarations": declarations,
    }


def _used_capability_refs(intent: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    topology = dict(getattr(intent, "topology", {}) or {})
    if not topology:
        try:
            from dspx.services.program_topology import effective_pipeline_topology

            topology = dict(effective_pipeline_topology(intent) or {})
        except Exception:
            topology = {}
    modules = topology.get("modules") if topology else None
    if isinstance(modules, list) and modules:
        for raw_module in modules:
            if isinstance(raw_module, Mapping):
                module = dict(raw_module)
                ref = module_capability_ref(module)
                ref["module_id"] = str(module.get("id") or "")
                refs.append(ref)
    else:
        refs.append(
            {
                **module_capability_ref({"primitive": "Predict"}),
                "module_id": "generated_module",
            }
        )
    return refs


def build_program_capability_registry(intent: Any) -> dict[str, Any]:
    declarations = list(
        dict(getattr(intent, "capabilities", {}) or {}).get("declarations") or []
    )
    return {
        "schema_version": PROGRAM_CAPABILITY_REGISTRY_SCHEMA,
        "status": "descriptor_only_no_runtime_binding",
        "registry_kind": "generated_program_capability_contracts",
        "materialization_policy": {
            "default": "fail_closed",
            "materializable_primitives": sorted(_MATERIALIZABLE_PIPELINE_PRIMITIVES),
            "conditional_materializable_primitives": {
                "Retriever": "explicit bounded materializable topology module with retriever.mode=inline_corpus or local_corpus_snapshot only; local snapshots are normalized into generated inline adapters during materialization",
                "ReAct": "explicit bounded materializable topology module with tools=[] and bounded max_iters only",
                "ProgramOfThought": "explicit bounded materializable topology module with empty PythonInterpreter sandbox only",
            },
            "unsupported_primitives_are_declared_only": True,
            "custom_imports_are_declarations_only": True,
            "external_tools_retrievers_are_not_bound_or_executed": True,
            "react_materialization_requires_empty_tools": True,
            "program_of_thought_uses_empty_sandbox": True,
        },
        "builtin_capabilities": builtin_capability_contracts(),
        "declared_capabilities": declarations,
        "used_capability_refs": _used_capability_refs(intent),
        "effects": dict(_DESCRIPTOR_EFFECTS),
        "non_authority": dict(_NON_AUTHORITY),
        "notes": [
            "This registry is descriptor-only evidence for generated program capability boundaries.",
            "It does not import custom modules, bind live external tools/retrievers, call providers during materialization, rank candidates, promote programs, or mutate external authority.",
            "Current materialization supports generated Predict/ChainOfThought/ReAct/ProgramOfThought primitives plus explicit bounded inline Retriever adapters and materialization-time local_corpus_snapshot Retriever adapters in bounded pipeline/router/retrieve_then_answer/extract_transform_validate/generate_critique_revise topologies only.",
            "ReAct is generated only with an empty tools list; ProgramOfThought is generated only with an empty PythonInterpreter sandbox.",
        ],
    }
