from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional
import json
import keyword
import re

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dspx.cache import cache_dir

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
    metric: Optional[str] = None
    runtime: dict[str, Any] = Field(default_factory=dict)
    jury: dict[str, Any] = Field(default_factory=dict)
    promotion: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)

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

    @field_validator("jury", "promotion", "options", "runtime", "topology")
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
