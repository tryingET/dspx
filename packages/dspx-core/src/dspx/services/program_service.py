from __future__ import annotations

import json
import keyword
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dspx.cache import cache_dir, cache_enabled, make_key, sha256_text
from dspx.run_receipts import (
    build_mlflow_hints,
    build_run_receipt,
    current_receipt_lineage,
    write_run_receipt,
)
from dspx.services.program_contracts import (
    intent_field_specs as _intent_field_specs,
    intent_surface_names as _intent_surface_names,
)
from dspx.services.program_jury import (
    build_jury_rubric,
    build_jury_selection,
    jury_plan_defaults as _jury_plan_defaults,
)
from dspx.services.program_promotion import (
    build_promotion_adjudication_request,
    build_promotion_review,
)
from dspx.services.program_surfaces import (
    render_eval_examples,
    render_eval_jury,
    render_eval_promotion,
    render_eval_smoke,
    render_module_surface,
    render_program_code,
    render_signature_surface,
)

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


def _default_outdir(intent: ProgramIntent) -> Path:
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


def _intent_payload(intent: ProgramIntent) -> dict[str, Any]:
    return intent.model_dump(mode="json", exclude_none=True)


def _json_text(payload: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _program_cache_file(cache_key: str) -> Path:
    path = cache_dir() / "program" / f"{cache_key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _build_ids(intent: ProgramIntent, surface_bundle_text: str) -> dict[str, str]:
    payload = _intent_payload(intent)
    request_id = f"prog-req-{make_key({'intent': payload})[:12]}"
    candidate_id = f"prog-cand-{make_key({'request_id': request_id, 'code': surface_bundle_text})[:12]}"
    assembly_id = (
        f"prog-asm-{make_key({'candidate_id': candidate_id, 'intent': payload})[:12]}"
    )
    episode_id = (
        f"prog-ep-{make_key({'assembly_id': assembly_id, 'phase': 'materialize'})[:12]}"
    )
    receipt_bundle_id = f"prog-rb-{make_key({'episode_id': episode_id, 'code': surface_bundle_text})[:12]}"
    return {
        "request_id": request_id,
        "candidate_id": candidate_id,
        "assembly_id": assembly_id,
        "episode_id": episode_id,
        "receipt_bundle_id": receipt_bundle_id,
    }


def _examples_plan_metadata(
    intent: ProgramIntent, *, examples_hash: Optional[str]
) -> dict[str, Any]:
    if intent.examples_path:
        source = "examples_path"
    elif intent.examples:
        source = "inline"
    else:
        source = "none"
    return {
        "source": source,
        "count": len(intent.examples or []),
        "path": intent.examples_path,
        "hash": examples_hash,
    }


def build_program_plan(
    intent: ProgramIntent, *, examples_hash: Optional[str] = None
) -> dict[str, Any]:
    """Build the deterministic ProgramPlan v1 contract from a ProgramIntent."""

    names = _intent_surface_names(intent)
    topology = dict(intent.topology or {})
    if not topology:
        topology = {
            "kind": "single_module",
            "modules": [
                {
                    "name": names["module_class"],
                    "signature": names["signature_class"],
                    "inputs": list(intent.inputs),
                    "outputs": list(intent.outputs),
                }
            ],
            "edges": [],
        }
    has_examples = bool(intent.examples)
    surfaces: list[dict[str, Any]] = [
        {"kind": "plan", "path": "plan.json", "generator": "program-gen"},
        {"kind": "jury", "path": "jury.json", "generator": "program-gen"},
        {
            "kind": "jury_selection",
            "path": "jury_selection.json",
            "generator": "program-gen",
        },
        {
            "kind": "jury_rubric",
            "path": "jury_rubric.json",
            "generator": "program-gen",
        },
        {
            "kind": "promotion_review",
            "path": "promotion_review.json",
            "generator": "program-gen",
        },
        {
            "kind": "promotion_adjudication_request",
            "path": "promotion_adjudication_request.json",
            "generator": "program-gen",
        },
        {
            "kind": "promotion_decision_template",
            "path": "promotion_decision_template.json",
            "generator": "program-gen",
        },
        {"kind": "intent", "path": "intent.json", "generator": "program-gen"},
        {"kind": "signature", "path": "signature.py", "generator": "signature-gen"},
        {"kind": "module", "path": "module.py", "generator": "module-gen"},
        {"kind": "program", "path": "program.py", "generator": "program-gen"},
        {"kind": "smoke_harness", "path": "eval_smoke.py", "generator": "program-gen"},
        {"kind": "jury_harness", "path": "eval_jury.py", "generator": "program-gen"},
        {
            "kind": "promotion_harness",
            "path": "eval_promotion.py",
            "generator": "program-gen",
        },
    ]
    if has_examples:
        surfaces.extend(
            [
                {
                    "kind": "examples",
                    "path": "examples.json",
                    "generator": "program-gen",
                },
                {
                    "kind": "examples_harness",
                    "path": "eval_examples.py",
                    "generator": "program-gen",
                },
            ]
        )
    return {
        "schema_version": "program-plan-v1",
        "intent": {
            "schema_version": intent.schema_version,
            "name": intent.name,
            "objective": intent.objective,
        },
        "task_type": intent.task_type or "single_module",
        "fields": {
            "inputs": _intent_field_specs(intent, role="input"),
            "outputs": _intent_field_specs(intent, role="output"),
        },
        "topology": topology,
        "surfaces": surfaces,
        "metric": intent.metric or "unspecified",
        "runtime": dict(intent.runtime),
        "constraints": list(intent.constraints),
        "examples": _examples_plan_metadata(intent, examples_hash=examples_hash),
        "evaluation_strategy": _jury_plan_defaults(intent),
        "non_authority": {
            "candidate_assembly": "materialized_not_promoted",
            "program_gen_evidence": "non_authoritative",
            "oracle_role": "behavioral_interpreter_only",
            "ranking_pruning_promotion": False,
            "governance_authority": False,
        },
    }


def _write_json(path: Path, payload: Mapping[str, Any] | list[Any]) -> str:
    text = _json_text(payload)
    path.write_text(text, encoding="utf-8")
    return text


def _run_python_harness(root: Path, filename: str, *, label: str) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, filename],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    result: dict[str, Any] = {
        "command": [sys.executable, filename],
        "returncode": proc.returncode,
        "stdout": stdout[-500:],
        "stderr": stderr[-500:],
    }
    if proc.returncode != 0:
        raise ValueError(
            f"program {label} failed: rc={proc.returncode} stderr={stderr[-240:]}"
        )
    return result


def _run_eval_smoke(root: Path) -> dict[str, Any]:
    return _run_python_harness(root, "eval_smoke.py", label="eval smoke")


def _run_eval_examples(root: Path) -> dict[str, Any]:
    return _run_python_harness(root, "eval_examples.py", label="examples validation")


def _run_eval_jury(root: Path) -> dict[str, Any]:
    return _run_python_harness(root, "eval_jury.py", label="jury validation")


def _run_eval_promotion(root: Path) -> dict[str, Any]:
    return _run_python_harness(root, "eval_promotion.py", label="promotion validation")


def materialize_program_from_intent(
    intent: ProgramIntent,
    *,
    outdir: Optional[Path] = None,
    intent_source: Optional[Path] = None,
) -> ProgramArtifact:
    """Materialize a runnable program-shaped candidate assembly from one intent."""

    root = (
        (outdir if outdir is not None else _default_outdir(intent))
        .expanduser()
        .resolve()
    )
    root.mkdir(parents=True, exist_ok=True)

    signature_code, signature_metadata = render_signature_surface(intent)
    module_code, module_metadata = render_module_surface(intent)
    program_code = render_program_code(intent)
    eval_smoke_code = render_eval_smoke(intent)
    eval_jury_code = render_eval_jury()
    eval_promotion_code = render_eval_promotion()
    examples_payload = list(intent.examples or [])
    examples_text = _json_text(examples_payload) if examples_payload else None
    examples_hash = sha256_text(examples_text) if examples_text is not None else None
    program_plan = build_program_plan(intent, examples_hash=examples_hash)
    jury_payload = dict(program_plan["evaluation_strategy"])
    jury_selection = build_jury_selection(jury_payload)
    jury_rubric = build_jury_rubric(intent, jury_selection)
    promotion_review = build_promotion_review(
        intent,
        has_examples=bool(examples_payload),
        jury_selection=jury_selection,
        jury_rubric=jury_rubric,
    )
    promotion_adjudication_request = build_promotion_adjudication_request(
        promotion_review
    )
    promotion_decision_template = dict(
        promotion_adjudication_request["decision_record_template"]
    )
    plan_text = _json_text(program_plan)
    jury_text = _json_text(jury_payload)
    jury_selection_text = _json_text(jury_selection)
    jury_rubric_text = _json_text(jury_rubric)
    promotion_review_text = _json_text(promotion_review)
    promotion_adjudication_request_text = _json_text(promotion_adjudication_request)
    promotion_decision_template_text = _json_text(promotion_decision_template)
    plan_hash = sha256_text(plan_text)
    jury_hash = sha256_text(jury_text)
    jury_selection_hash = sha256_text(jury_selection_text)
    jury_rubric_hash = sha256_text(jury_rubric_text)
    promotion_review_hash = sha256_text(promotion_review_text)
    promotion_adjudication_request_hash = sha256_text(
        promotion_adjudication_request_text
    )
    promotion_decision_template_hash = sha256_text(promotion_decision_template_text)
    eval_examples_code = render_eval_examples(intent) if examples_payload else None
    bundle_parts = [
        plan_text,
        jury_text,
        jury_selection_text,
        jury_rubric_text,
        promotion_review_text,
        promotion_adjudication_request_text,
        promotion_decision_template_text,
        signature_code,
        module_code,
        program_code,
        eval_smoke_code,
        eval_jury_code,
        eval_promotion_code,
    ]
    if eval_examples_code is not None:
        bundle_parts.append(eval_examples_code)
    surface_bundle_text = "\n\n".join(bundle_parts)
    ids = _build_ids(intent, surface_bundle_text)
    intent_payload = _intent_payload(intent)
    intent_hash = sha256_text(json.dumps(intent_payload, sort_keys=True))
    surface_hashes = {
        "plan.json": plan_hash,
        "jury.json": jury_hash,
        "jury_selection.json": jury_selection_hash,
        "jury_rubric.json": jury_rubric_hash,
        "promotion_review.json": promotion_review_hash,
        "promotion_adjudication_request.json": promotion_adjudication_request_hash,
        "promotion_decision_template.json": promotion_decision_template_hash,
        "signature.py": sha256_text(signature_code),
        "module.py": sha256_text(module_code),
        "program.py": sha256_text(program_code),
        "eval_smoke.py": sha256_text(eval_smoke_code),
        "eval_jury.py": sha256_text(eval_jury_code),
        "eval_promotion.py": sha256_text(eval_promotion_code),
    }
    if eval_examples_code is not None:
        surface_hashes["eval_examples.py"] = sha256_text(eval_examples_code)
    program_hash = surface_hashes["program.py"]
    assembly_hash = sha256_text(surface_bundle_text)

    generated_files = {
        "signature.py": signature_code,
        "module.py": module_code,
        "program.py": program_code,
        "eval_smoke.py": eval_smoke_code,
        "eval_jury.py": eval_jury_code,
        "eval_promotion.py": eval_promotion_code,
    }
    if eval_examples_code is not None:
        generated_files["eval_examples.py"] = eval_examples_code
    for relative, content in generated_files.items():
        compile(content, str(root / relative), "exec")
        (root / relative).write_text(content, encoding="utf-8")

    (root / "plan.json").write_text(plan_text, encoding="utf-8")
    (root / "jury.json").write_text(jury_text, encoding="utf-8")
    (root / "jury_selection.json").write_text(jury_selection_text, encoding="utf-8")
    (root / "jury_rubric.json").write_text(jury_rubric_text, encoding="utf-8")
    (root / "promotion_review.json").write_text(promotion_review_text, encoding="utf-8")
    (root / "promotion_adjudication_request.json").write_text(
        promotion_adjudication_request_text, encoding="utf-8"
    )
    (root / "promotion_decision_template.json").write_text(
        promotion_decision_template_text, encoding="utf-8"
    )
    _write_json(root / "intent.json", intent_payload)
    if examples_text is not None:
        (root / "examples.json").write_text(examples_text, encoding="utf-8")
    smoke_result = _run_eval_smoke(root)
    jury_result = _run_eval_jury(root)
    promotion_result = _run_eval_promotion(root)
    examples_result = _run_eval_examples(root) if examples_payload else None
    generated_file_names = sorted(
        [
            *generated_files.keys(),
            "plan.json",
            "jury.json",
            "jury_selection.json",
            "jury_rubric.json",
            "promotion_review.json",
            "promotion_adjudication_request.json",
            "promotion_decision_template.json",
            "intent.json",
            *(["examples.json"] if examples_payload else []),
            "manifest.json",
        ]
    )

    candidate_assembly = {
        "assembly_id": ids["assembly_id"],
        "request_id": ids["request_id"],
        "candidate_id": ids["candidate_id"],
        "artifact_kind": "program",
        "surface_kinds": [
            "plan",
            "jury",
            "jury_selection",
            "jury_rubric",
            "promotion_review",
            "promotion_adjudication_request",
            "promotion_decision_template",
            "intent",
            *(["examples"] if examples_payload else []),
            "signature",
            "module",
            "program",
            "eval_harness",
            "jury_harness",
            "promotion_harness",
        ],
        "root_path": str(root),
        "entrypoint": "program.py",
        "content_hash": assembly_hash,
        "status": "materialized",
        "surfaces": [
            {
                "kind": "plan",
                "path": "plan.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["plan.json"],
                "schema_version": program_plan["schema_version"],
            },
            {
                "kind": "jury",
                "path": "jury.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["jury.json"],
                "schema_version": jury_payload["schema_version"],
            },
            {
                "kind": "jury_selection",
                "path": "jury_selection.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["jury_selection.json"],
                "schema_version": jury_selection["schema_version"],
                "status": jury_selection["status"],
            },
            {
                "kind": "jury_rubric",
                "path": "jury_rubric.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["jury_rubric.json"],
                "schema_version": jury_rubric["schema_version"],
            },
            {
                "kind": "promotion_review",
                "path": "promotion_review.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["promotion_review.json"],
                "schema_version": promotion_review["schema_version"],
                "promotion_state": promotion_review["promotion_state"],
            },
            {
                "kind": "promotion_adjudication_request",
                "path": "promotion_adjudication_request.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["promotion_adjudication_request.json"],
                "schema_version": promotion_adjudication_request["schema_version"],
                "status": promotion_adjudication_request["status"],
            },
            {
                "kind": "promotion_decision_template",
                "path": "promotion_decision_template.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["promotion_decision_template.json"],
                "schema_version": promotion_decision_template["schema_version"],
                "status": promotion_decision_template["status"],
            },
            {
                "kind": "signature",
                "path": "signature.py",
                "generator": "signature-gen",
                "content_hash": surface_hashes["signature.py"],
                "metadata": signature_metadata,
            },
            {
                "kind": "module",
                "path": "module.py",
                "generator": "module-gen",
                "content_hash": surface_hashes["module.py"],
                "metadata": module_metadata,
            },
            {
                "kind": "program",
                "path": "program.py",
                "generator": "program-gen",
                "content_hash": surface_hashes["program.py"],
            },
            {
                "kind": "eval_harness",
                "path": "eval_smoke.py",
                "generator": "program-gen",
                "content_hash": surface_hashes["eval_smoke.py"],
            },
            {
                "kind": "jury_harness",
                "path": "eval_jury.py",
                "generator": "program-gen",
                "content_hash": surface_hashes["eval_jury.py"],
            },
            {
                "kind": "promotion_harness",
                "path": "eval_promotion.py",
                "generator": "program-gen",
                "content_hash": surface_hashes["eval_promotion.py"],
            },
            *(
                [
                    {
                        "kind": "examples_harness",
                        "path": "eval_examples.py",
                        "generator": "program-gen",
                        "content_hash": surface_hashes["eval_examples.py"],
                    }
                ]
                if eval_examples_code is not None
                else []
            ),
        ],
    }
    execution_episode = {
        "episode_id": ids["episode_id"],
        "request_id": ids["request_id"],
        "candidate_id": ids["candidate_id"],
        "assembly_id": ids["assembly_id"],
        "phase": "materialize",
        "evaluator": "deterministic_program_bundle_smoke",
        "status": "passed",
        "runtime_conditions": dict(intent.runtime),
        "metadata": {
            "smoke": smoke_result,
            "jury": jury_result,
            "promotion": promotion_result,
            **({"examples": examples_result} if examples_result is not None else {}),
        },
    }
    receipt_bundle = {
        "receipt_bundle_id": ids["receipt_bundle_id"],
        "request_id": ids["request_id"],
        "candidate_id": ids["candidate_id"],
        "assembly_id": ids["assembly_id"],
        "episode_id": ids["episode_id"],
        "status": "captured",
        "evidence": {
            "intent_hash": intent_hash,
            "plan_hash": plan_hash,
            "jury_hash": jury_hash,
            "jury_selection_hash": jury_selection_hash,
            "jury_rubric_hash": jury_rubric_hash,
            "promotion_review_hash": promotion_review_hash,
            "promotion_adjudication_request_hash": promotion_adjudication_request_hash,
            "promotion_decision_template_hash": promotion_decision_template_hash,
            "program_hash": program_hash,
            "assembly_hash": assembly_hash,
            "surface_hashes": surface_hashes,
            **({"examples_hash": examples_hash} if examples_hash is not None else {}),
            "surface_generation": {
                "plan": "program-gen",
                "jury": "program-gen",
                "jury_selection": "program-gen",
                "jury_rubric": "program-gen",
                "promotion_review": "program-gen",
                "promotion_adjudication_request": "program-gen",
                "promotion_decision_template": "program-gen",
                "signature": "signature-gen",
                "module": "module-gen",
                "program": "program-gen",
                "eval_harness": "program-gen",
                "jury_harness": "program-gen",
                "promotion_harness": "program-gen",
                **(
                    {"examples_harness": "program-gen"}
                    if examples_result is not None
                    else {}
                ),
            },
            "generated_files": generated_file_names,
            "smoke": smoke_result,
            "jury": jury_result,
            "promotion": promotion_result,
            **({"examples": examples_result} if examples_result is not None else {}),
        },
    }

    manifest = {
        "schema_version": "program-candidate-assembly-v1",
        "request": {
            "request_id": ids["request_id"],
            "source_command": "program-gen",
            "goal": intent.objective,
            "intent_source": str(intent_source.expanduser().resolve())
            if intent_source is not None
            else None,
            "intent_hash": intent_hash,
            "plan_hash": plan_hash,
            "jury_hash": jury_hash,
            "jury_selection_hash": jury_selection_hash,
            "jury_rubric_hash": jury_rubric_hash,
            "promotion_review_hash": promotion_review_hash,
            "promotion_adjudication_request_hash": promotion_adjudication_request_hash,
            "promotion_decision_template_hash": promotion_decision_template_hash,
        },
        "intent": intent_payload,
        "program_plan": program_plan,
        "program_jury_selection": jury_selection,
        "program_jury_rubric": jury_rubric,
        "program_promotion_review": promotion_review,
        "program_promotion_adjudication_request": promotion_adjudication_request,
        "program_promotion_decision_template": promotion_decision_template,
        "candidate_assembly": candidate_assembly,
        "execution_episode": execution_episode,
        "receipt_bundle": receipt_bundle,
    }
    manifest_path = root / "manifest.json"
    manifest_text = _write_json(manifest_path, manifest)
    manifest_hash = sha256_text(manifest_text)

    cache_key = make_key({"kind": "program", "intent": intent_payload})
    cache_file = _program_cache_file(cache_key)
    cache_is_enabled = cache_enabled()
    if cache_is_enabled:
        _write_json(
            cache_file,
            {
                "code": manifest_text,
                "manifest": manifest,
                "intent": intent_payload,
                "kind": "program",
            },
        )

    receipt = build_run_receipt(
        run_kind="program-gen",
        output_path=manifest_path,
        output_hash=manifest_hash,
        template_version="program-candidate-assembly-v1",
        cache_key=cache_key,
        cache_file=str(cache_file),
        cache_enabled=cache_is_enabled,
        replay_inputs={"intent": intent_payload},
        run_summary={
            "backend": "program_candidate_assembly",
            "assembly_id": ids["assembly_id"],
            "episode_id": ids["episode_id"],
            "receipt_bundle_id": ids["receipt_bundle_id"],
            "plan_hash": plan_hash,
            "jury_hash": jury_hash,
            "jury_selection_hash": jury_selection_hash,
            "jury_rubric_hash": jury_rubric_hash,
            "promotion_review_hash": promotion_review_hash,
            "promotion_adjudication_request_hash": promotion_adjudication_request_hash,
            "promotion_decision_template_hash": promotion_decision_template_hash,
            "generated_files": generated_file_names,
        },
        extra={
            "program_intent": intent_payload,
            "program_plan": program_plan,
            "program_jury_selection": jury_selection,
            "program_jury_rubric": jury_rubric,
            "program_promotion_review": promotion_review,
            "program_promotion_adjudication_request": promotion_adjudication_request,
            "program_promotion_decision_template": promotion_decision_template,
            "program_candidate_assembly": candidate_assembly,
            "program_execution_episode": execution_episode,
            "program_receipt_bundle": receipt_bundle,
            "mlflow_hints": build_mlflow_hints(
                run_kind="program-gen",
                template_version="program-candidate-assembly-v1",
                output_path=manifest_path,
                output_hash=manifest_hash,
                cache_key=cache_key,
                extra_expected_tags={"service": "program"},
            ),
            **current_receipt_lineage(),
        },
        outcome="success",
    )
    receipt_path = write_run_receipt(manifest_path, receipt)

    return ProgramArtifact(
        name=intent.name,
        root_path=str(root),
        files={
            relative: str((root / relative).resolve()) for relative in generated_files
        },
        manifest=manifest,
        receipt_path=str(receipt_path),
        metadata={
            "request_id": ids["request_id"],
            "candidate_id": ids["candidate_id"],
            "assembly_id": ids["assembly_id"],
            "episode_id": ids["episode_id"],
            "receipt_bundle_id": ids["receipt_bundle_id"],
            "intent_hash": intent_hash,
            "plan_hash": plan_hash,
            "jury_hash": jury_hash,
            "jury_selection_hash": jury_selection_hash,
            "jury_rubric_hash": jury_rubric_hash,
            "promotion_review_hash": promotion_review_hash,
            "promotion_adjudication_request_hash": promotion_adjudication_request_hash,
            "promotion_decision_template_hash": promotion_decision_template_hash,
            "program_hash": program_hash,
            "assembly_hash": assembly_hash,
        },
    )


def run_generate_from_intent_path(
    intent_path: Path,
    *,
    outdir: Optional[Path] = None,
) -> ProgramArtifact:
    intent = load_program_intent(intent_path)
    return materialize_program_from_intent(
        intent,
        outdir=outdir,
        intent_source=intent_path,
    )
