from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional
import json
import keyword
import re

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dspx.cache import cache_dir
from dspx.services.program_capabilities import (
    normalize_program_capabilities,
    normalize_retriever_config,
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DECLARED_NOT_MATERIALIZED = "declared_not_materialized"
_ACCEPTED_TOPOLOGY_KINDS = {
    "single_module",
    "pipeline",
    "router",
    "retrieve_then_answer",
    "extract_transform_validate",
    "generate_critique_revise",
    "custom",
}
_PRIMITIVE_CANONICAL_NAMES = {
    "predict": "Predict",
    "chainofthought": "ChainOfThought",
    "chain_of_thought": "ChainOfThought",
    "react": "ReAct",
    "reactv2": "ReActV2",
    "react_v2": "ReActV2",
    "react-v2": "ReActV2",
    "programofthought": "ProgramOfThought",
    "program_of_thought": "ProgramOfThought",
    "retriever": "Retriever",
    "retrieve": "Retriever",
    "custom": "Custom",
}


def _validate_identifier(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if not text or not _IDENTIFIER_RE.match(text) or keyword.iskeyword(text):
        raise ValueError(f"{label} must be a valid Python identifier")
    return text


def _validate_identifier_list(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    fields = [_validate_identifier(item, label=label) for item in value]
    if not fields:
        raise ValueError(f"{label} must include at least one field")
    if len(set(fields)) != len(fields):
        raise ValueError(f"{label} fields must be unique")
    return fields


def _normalize_topology_signature(value: object, *, module_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"topology module {module_id!r} signature must be an object")
    signature = dict(value)
    name = _validate_identifier(
        signature.get("name"), label=f"topology module {module_id!r} signature.name"
    )
    inputs = _validate_identifier_list(
        signature.get("inputs"),
        label=f"topology module {module_id!r} signature.inputs",
    )
    outputs = _validate_identifier_list(
        signature.get("outputs"),
        label=f"topology module {module_id!r} signature.outputs",
    )
    return {"name": name, "inputs": inputs, "outputs": outputs}


def _bounded_int(
    value: object, *, label: str, default: int, minimum: int, maximum: int
) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    if not isinstance(value, (str, int)):
        raise ValueError(f"{label} must be an integer")
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return number


def _normalize_react_config(
    module: Mapping[str, Any], *, module_id: str
) -> dict[str, Any]:
    raw_tools = module.get("tools", [])
    if raw_tools is None:
        raw_tools = []
    if not isinstance(raw_tools, list):
        raise ValueError(f"topology ReAct module {module_id!r} tools must be a list")
    if raw_tools:
        raise ValueError(
            f"topology ReAct module {module_id!r} supports only an empty tools list in this renderer"
        )
    return {
        "tools": [],
        "max_iters": _bounded_int(
            module.get("max_iters"),
            label=f"topology ReAct module {module_id!r} max_iters",
            default=1,
            minimum=1,
            maximum=5,
        ),
    }


def _normalize_program_of_thought_config(
    module: Mapping[str, Any], *, module_id: str
) -> dict[str, Any]:
    return {
        "max_iters": _bounded_int(
            module.get("max_iters"),
            label=f"topology ProgramOfThought module {module_id!r} max_iters",
            default=1,
            minimum=1,
            maximum=3,
        ),
        "sandbox": {
            "read_paths": [],
            "write_paths": [],
            "env_vars": [],
            "network_access": [],
            "tools": [],
            "sync_files": False,
        },
    }


def _normalize_topology_module(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("topology modules must contain objects")
    module = dict(value)
    module_id = _validate_identifier(module.get("id"), label="topology module id")
    primitive = str(module.get("primitive") or "").strip()
    if not primitive:
        raise ValueError(f"topology module {module_id!r} primitive must not be blank")
    primitive = _PRIMITIVE_CANONICAL_NAMES.get(primitive.lower(), primitive)
    common_keys = {"id", "primitive", "signature", "role"}
    if primitive == "Retriever":
        extra_keys = set(module) - common_keys - {"retriever"}
        if extra_keys:
            raise ValueError(
                f"topology Retriever module {module_id!r} has unsupported keys: {sorted(extra_keys)}"
            )
    elif primitive in {"ReAct", "ReActV2"}:
        extra_keys = set(module) - common_keys - {"tools", "max_iters"}
        if extra_keys:
            raise ValueError(
                f"topology {primitive} module {module_id!r} has unsupported keys: {sorted(extra_keys)}"
            )
    elif primitive == "ProgramOfThought":
        extra_keys = set(module) - common_keys - {"max_iters"}
        if extra_keys:
            raise ValueError(
                f"topology ProgramOfThought module {module_id!r} has unsupported keys: {sorted(extra_keys)}"
            )
    elif "retriever" in module:
        raise ValueError(
            f"topology module {module_id!r} may declare retriever only when primitive is Retriever"
        )
    normalized: dict[str, Any] = {
        "id": module_id,
        "primitive": primitive,
        "signature": _normalize_topology_signature(
            module.get("signature"), module_id=module_id
        ),
    }
    role = str(module.get("role") or "").strip()
    if role:
        normalized["role"] = role
    if "retriever" in module:
        normalized["retriever"] = normalize_retriever_config(
            module.get("retriever"), module_id=module_id
        )
    if primitive in {"ReAct", "ReActV2"}:
        normalized["react"] = _normalize_react_config(module, module_id=module_id)
        if primitive == "ReActV2":
            normalized["react"]["version"] = "v2"
            normalized["react"]["status"] = (
                "experimental_declared_only_not_materializable"
            )
    if primitive == "ProgramOfThought":
        normalized["program_of_thought"] = _normalize_program_of_thought_config(
            module, module_id=module_id
        )
    return normalized


def _normalize_topology_when(
    value: object, *, source: str, target: str
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(
            "topology edge when clauses must be objects with field/equals; "
            f"invalid edge: {source!r} -> {target!r}"
        )
    when = dict(value)
    field = _validate_identifier(
        when.get("field"), label=f"topology edge {source!r}->{target!r} when.field"
    )
    if "equals" not in when:
        raise ValueError(
            "topology edge when clauses must include equals; "
            f"invalid edge: {source!r} -> {target!r}"
        )
    equals = when.get("equals")
    if isinstance(equals, (Mapping, list)):
        raise ValueError(
            "topology edge when.equals must be a scalar value; "
            f"invalid edge: {source!r} -> {target!r}"
        )
    return {"field": field, "equals": equals}


def _normalize_topology_edge(
    value: object, *, allowed_refs: set[str]
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("topology edges must contain objects")
    edge = dict(value)
    source = str(edge.get("from") or "").strip()
    target = str(edge.get("to") or "").strip()
    invalid = [ref for ref in (source, target) if ref not in allowed_refs]
    if invalid:
        allowed = sorted(allowed_refs)
        raise ValueError(
            "topology edges must reference input, output, or declared module ids; "
            f"invalid refs: {invalid}; allowed refs: {allowed}"
        )
    normalized: dict[str, Any] = {"from": source, "to": target}
    if "when" in edge:
        normalized["when"] = _normalize_topology_when(
            edge.get("when"), source=source, target=target
        )
    return normalized


def normalize_program_topology(value: object) -> dict[str, Any]:
    """Normalize and validate a declared program-intent topology contract.

    An absent or empty topology remains empty so the current renderer can keep the
    existing generated single-module scaffold. Any explicit topology is a
    declared planning contract only in this slice and must say so truthfully.
    """

    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("program intent topology must be an object")
    topology = dict(value)
    if not topology:
        return {}

    kind = str(topology.get("kind") or "").strip()
    if not kind:
        raise ValueError(
            "program intent topology.kind is required when topology is provided"
        )
    if kind not in _ACCEPTED_TOPOLOGY_KINDS:
        allowed = sorted(_ACCEPTED_TOPOLOGY_KINDS)
        raise ValueError(f"program intent topology.kind must be one of {allowed}")

    execution_status = str(
        topology.get("execution_status") or _DECLARED_NOT_MATERIALIZED
    ).strip()
    if execution_status != _DECLARED_NOT_MATERIALIZED:
        raise ValueError(
            "program intent topology.execution_status must be "
            f"{_DECLARED_NOT_MATERIALIZED!r}; explicit topology is not "
            "materialized or executed by this renderer"
        )

    raw_modules = topology.get("modules", [])
    if kind != "single_module" or "modules" in topology:
        if not isinstance(raw_modules, list):
            raise ValueError("program intent topology.modules must be a list")
        if kind != "single_module" and not raw_modules:
            raise ValueError(
                "program intent topology.modules must include at least one module "
                "when topology.kind is not single_module"
            )
    modules = [_normalize_topology_module(item) for item in raw_modules]
    module_ids = [str(module["id"]) for module in modules]
    if len(set(module_ids)) != len(module_ids):
        raise ValueError("program intent topology module ids must be unique")

    raw_edges = topology.get("edges", [])
    if "edges" in topology or kind != "single_module":
        if not isinstance(raw_edges, list):
            raise ValueError("program intent topology.edges must be a list")
    allowed_refs = {"input", "output", *module_ids}
    edges = [
        _normalize_topology_edge(item, allowed_refs=allowed_refs) for item in raw_edges
    ]

    return {
        "kind": kind,
        "execution_status": _DECLARED_NOT_MATERIALIZED,
        "modules": modules,
        "edges": edges,
    }


class ProgramIntent(BaseModel):
    """Structured one-intent contract for materializing a DSPy program assembly."""

    model_config = ConfigDict(extra="allow")

    schema_version: str = "program-intent-v2"
    name: str = "IntentProgram"
    objective: str
    inputs: list[str] = Field(default_factory=lambda: ["context"])
    outputs: list[str] = Field(default_factory=lambda: ["output"])
    input_fields: list[dict[str, Any]] = Field(default_factory=list)
    output_fields: list[dict[str, Any]] = Field(default_factory=list)
    task_type: str = "single_module"
    topology: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    examples_path: Optional[str] = None
    dataset: dict[str, Any] = Field(default_factory=dict)
    datasets: dict[str, Any] = Field(default_factory=dict)
    metric: Optional[str] = None
    runtime: dict[str, Any] = Field(default_factory=dict)
    jury: dict[str, Any] = Field(default_factory=dict)
    promotion: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def _schema_version_must_be_current(cls, value: str) -> str:
        if value != "program-intent-v2":
            raise ValueError("program intent schema_version must be program-intent-v2")
        return value

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("program intent name must not be blank")
        return text

    @field_validator("objective")
    @classmethod
    def _objective_must_not_be_blank(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("program intent objective must not be blank")
        return text

    @field_validator("task_type")
    @classmethod
    def _task_type_must_not_be_blank(cls, value: str) -> str:
        text = str(value or "single_module").strip()
        if not text:
            raise ValueError("program intent task_type must not be blank")
        return text

    @field_validator("inputs", "outputs")
    @classmethod
    def _fields_must_be_identifiers(cls, value: list[str]) -> list[str]:
        fields = [str(item).strip() for item in value]
        invalid = [
            item
            for item in fields
            if not item or not _IDENTIFIER_RE.match(item) or keyword.iskeyword(item)
        ]
        if not fields:
            raise ValueError("program intent fields must include at least one field")
        if invalid:
            raise ValueError(
                "program intent fields must be valid Python identifiers; "
                f"invalid entries: {invalid}"
            )
        if len(set(fields)) != len(fields):
            raise ValueError("program intent fields must be unique")
        return fields

    @field_validator(
        "jury",
        "promotion",
        "options",
        "runtime",
        "topology",
        "dataset",
        "datasets",
        "capabilities",
    )
    @classmethod
    def _mapping_fields_must_be_objects(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("program intent mapping fields must be objects")
        return dict(value)

    @field_validator("input_fields", "output_fields")
    @classmethod
    def _field_specs_must_be_valid(
        cls, value: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        seen: set[str] = set()
        invalid: list[str] = []
        for index, raw in enumerate(value or []):
            if not isinstance(raw, Mapping):
                invalid.append(f"{index}:<not-object>")
                continue
            item = dict(raw)
            name = str(item.get("name") or item.get("field") or "").strip()
            if not name or not _IDENTIFIER_RE.match(name) or keyword.iskeyword(name):
                invalid.append(f"{index}:{name or '<missing-name>'}")
                continue
            if name in seen:
                invalid.append(f"duplicate:{name}")
                continue
            seen.add(name)
            item["name"] = name
            if item.get("type") is not None:
                item["type"] = str(item.get("type") or "str")
            if item.get("desc") is None and item.get("description") is not None:
                item["desc"] = str(item.get("description"))
            fields.append(item)
        if invalid:
            raise ValueError(
                "program intent field specs must be objects with unique Python identifier names; "
                f"invalid entries: {invalid}"
            )
        return fields

    @model_validator(mode="after")
    def _io_roles_must_not_overlap(self) -> "ProgramIntent":
        if self.input_fields:
            self.inputs = [str(item["name"]) for item in self.input_fields]
        if self.output_fields:
            self.outputs = [str(item["name"]) for item in self.output_fields]
        overlap = sorted(set(self.inputs) & set(self.outputs))
        if overlap:
            raise ValueError(
                "program intent input/output field names must not overlap; "
                f"overlap: {overlap}"
            )
        self.topology = normalize_program_topology(self.topology)
        self.capabilities = normalize_program_capabilities(self.capabilities)
        return self


class ProgramArtifact(BaseModel):
    """Materialized one-intent program assembly result."""

    name: str
    root_path: str
    files: dict[str, str]
    manifest: dict[str, Any]
    receipt_path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def default_outdir(intent: ProgramIntent) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", intent.name.strip()).strip(".-_")
    slug = slug.lower() or "intent-program"
    return cache_dir() / "programs" / slug


def _load_json_or_yaml(path: Path) -> Any:
    source = path.expanduser().resolve()
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _resolve_program_intent_examples(payload: dict[str, Any], *, source: Path) -> None:
    examples_path_raw = payload.get("examples_path")
    if not examples_path_raw:
        return
    examples_path = Path(str(examples_path_raw)).expanduser()
    if not examples_path.is_absolute():
        examples_path = source.parent / examples_path
    examples_payload = _load_json_or_yaml(examples_path)
    if not isinstance(examples_payload, list) or not all(
        isinstance(item, Mapping) for item in examples_payload
    ):
        raise ValueError("program intent examples_path must contain a list of objects")
    payload["examples"] = [dict(item) for item in examples_payload]
    payload["examples_path"] = str(examples_path.resolve())


def load_program_intent(path: Path) -> ProgramIntent:
    """Load a program intent from JSON or YAML."""

    source = path.expanduser().resolve()
    payload = _load_json_or_yaml(source)
    if not isinstance(payload, Mapping):
        raise ValueError("program intent file must contain a mapping/object")
    resolved_payload = dict(payload)
    _resolve_program_intent_examples(resolved_payload, source=source)
    return ProgramIntent.model_validate(resolved_payload)
