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
from dspx.dtos import ModuleSpec, SignatureGenRequest
from dspx.run_receipts import (
    build_mlflow_hints,
    build_run_receipt,
    current_receipt_lineage,
    write_run_receipt,
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ProgramIntent(BaseModel):
    """Structured one-intent contract for materializing a DSPy program assembly."""

    model_config = ConfigDict(extra="allow")

    name: str = "IntentProgram"
    objective: str
    inputs: list[str] = Field(default_factory=lambda: ["context"])
    outputs: list[str] = Field(default_factory=lambda: ["output"])
    constraints: list[str] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    examples_path: Optional[str] = None
    metric: Optional[str] = None
    runtime: dict[str, Any] = Field(default_factory=dict)
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

    @model_validator(mode="after")
    def _io_roles_must_not_overlap(self) -> "ProgramIntent":
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


def _sanitize_ident(name: str, fallback: str = "IntentProgram") -> str:
    value = re.sub(r"\W+", "_", str(name or "").strip()) or fallback
    if value[0].isdigit():
        value = f"_{value}"
    if keyword.iskeyword(value):
        value = f"{value}_"
    return value


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


def _safe_doc_literal(text: str) -> str:
    compact = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    return repr(compact or "Auto-generated DSPy program")


def _surface_description(text: str) -> str:
    """Return text safe for existing triple-quoted signature/module renderers."""

    compact = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    return (compact or "Auto-generated DSPy program").replace('"""', "'''")


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


def _intent_surface_names(intent: ProgramIntent) -> dict[str, str]:
    program_class = _sanitize_ident(intent.name)
    return {
        "program_class": program_class,
        "signature_class": f"{program_class}Signature",
        "module_class": f"{program_class}Module",
    }


def render_signature_surface(intent: ProgramIntent) -> tuple[str, dict[str, Any]]:
    """Render the signature surface through the signature generation service."""

    from dspx.services.signatures_service import run_generate_dto

    names = _intent_surface_names(intent)
    result = run_generate_dto(
        SignatureGenRequest(
            prompt=_surface_description(intent.objective),
            template_version=str(
                intent.options.get("signature_template_version") or "simple-v1"
            ),
            options={
                "class_name": names["signature_class"],
                "inputs": list(intent.inputs or ["context"]),
                "outputs": list(intent.outputs or ["output"]),
                "run_kind": "program-signature-surface",
            },
        )
    )
    return result.code, dict(result.metadata or {})


def render_module_surface(intent: ProgramIntent) -> tuple[str, dict[str, Any]]:
    """Render the module surface through the module generation service."""

    from dspx.services.module_service import run_generate as run_module_generate

    names = _intent_surface_names(intent)
    artifact = run_module_generate(
        ModuleSpec(
            name=names["module_class"],
            description=_surface_description(intent.objective),
            inputs=list(intent.inputs or ["context"]),
            outputs=list(intent.outputs or ["output"]),
            options={
                "template_version": str(
                    intent.options.get("module_template_version") or "simple-v1"
                ),
                "signature_class_name": names["signature_class"],
            },
        ),
        use_signature=True,
    )
    return artifact.code, dict(artifact.metadata or {})


def render_program_code(intent: ProgramIntent) -> str:
    """Render the program assembly surface that composes generated surfaces."""

    names = _intent_surface_names(intent)
    constraints = list(intent.constraints)
    metric = intent.metric or "unspecified"

    lines: list[str] = [
        "from __future__ import annotations",
        "",
        "import dspy",
        "",
        "from module import (",
        "    build_student as build_module_student,",
        "    io_spec,",
        "    normalize_output,",
        "    output_weights,",
        ")",
        "",
        f"OBJECTIVE = {intent.objective!r}",
        f"CONSTRAINTS = {constraints!r}",
        f"METRIC = {metric!r}",
        "",
        "",
        "def build_program() -> dspy.Module:",
        "    return build_module_student()",
        "",
        "",
        "def build_student(*, use_cot: bool = False) -> dspy.Module:",
        "    return build_module_student(use_cot=use_cot)",
        "",
        "",
        "def intent_summary() -> dict[str, object]:",
        "    return {",
        f"        'name': {intent.name!r},",
        "        'objective': OBJECTIVE,",
        "        'constraints': list(CONSTRAINTS),",
        "        'metric': METRIC,",
        "        'io': io_spec(),",
        f"        'signature_class': {names['signature_class']!r},",
        f"        'module_class': {names['module_class']!r},",
        "    }",
        "",
    ]
    return "\n".join(lines)


def render_eval_smoke(intent: ProgramIntent) -> str:
    program_class = _sanitize_ident(intent.name)
    sample_inputs = {name: f"sample_{name}" for name in intent.inputs}
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "from program import build_program, intent_summary, io_spec",
            "",
            "",
            "def main() -> None:",
            "    program = build_program()",
            "    assert program is not None",
            f"    assert io_spec()['inputs'] == {list(intent.inputs)!r}",
            f"    assert io_spec()['outputs'] == {list(intent.outputs)!r}",
            "    assert intent_summary()['objective']",
            f"    print('program smoke ok: {program_class}')",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
            f"SAMPLE_INPUTS = {sample_inputs!r}",
        ]
    )


def render_eval_examples(intent: ProgramIntent) -> str:
    """Render a deterministic examples-binding validation harness."""

    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import json",
            "from pathlib import Path",
            "",
            "from program import io_spec",
            "",
            "",
            "def _mapping_for(example: dict[str, object], role: str) -> dict[str, object]:",
            "    nested = example.get(role)",
            "    if isinstance(nested, dict):",
            "        return dict(nested)",
            "    return example",
            "",
            "",
            "def main() -> None:",
            "    examples = json.loads(Path('examples.json').read_text(encoding='utf-8'))",
            "    assert isinstance(examples, list)",
            "    spec = io_spec()",
            "    inputs = list(spec['inputs'])",
            "    outputs = list(spec['outputs'])",
            "    for index, example in enumerate(examples):",
            "        assert isinstance(example, dict), f'example {index} must be an object'",
            "        input_values = _mapping_for(example, 'inputs')",
            "        output_values = _mapping_for(example, 'outputs')",
            "        missing_inputs = [name for name in inputs if name not in input_values]",
            "        missing_outputs = [name for name in outputs if name not in output_values]",
            "        assert not missing_inputs, f'example {index} missing inputs: {missing_inputs}'",
            "        assert not missing_outputs, f'example {index} missing outputs: {missing_outputs}'",
            "    print(f'program examples ok: {len(examples)} example(s)')",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
        ]
    )


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
    examples_payload = list(intent.examples or [])
    eval_examples_code = render_eval_examples(intent) if examples_payload else None
    bundle_parts = [signature_code, module_code, program_code, eval_smoke_code]
    if eval_examples_code is not None:
        bundle_parts.append(eval_examples_code)
    surface_bundle_text = "\n\n".join(bundle_parts)
    ids = _build_ids(intent, surface_bundle_text)
    intent_payload = _intent_payload(intent)
    intent_hash = sha256_text(json.dumps(intent_payload, sort_keys=True))
    surface_hashes = {
        "signature.py": sha256_text(signature_code),
        "module.py": sha256_text(module_code),
        "program.py": sha256_text(program_code),
        "eval_smoke.py": sha256_text(eval_smoke_code),
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
    }
    if eval_examples_code is not None:
        generated_files["eval_examples.py"] = eval_examples_code
    for relative, content in generated_files.items():
        compile(content, str(root / relative), "exec")
        (root / relative).write_text(content, encoding="utf-8")

    _write_json(root / "intent.json", intent_payload)
    examples_hash = None
    if examples_payload:
        examples_text = _write_json(root / "examples.json", examples_payload)
        examples_hash = sha256_text(examples_text)
    smoke_result = _run_eval_smoke(root)
    examples_result = _run_eval_examples(root) if examples_payload else None
    generated_file_names = sorted(
        [
            *generated_files.keys(),
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
            "intent",
            *(["examples"] if examples_payload else []),
            "signature",
            "module",
            "program",
            "eval_harness",
        ],
        "root_path": str(root),
        "entrypoint": "program.py",
        "content_hash": assembly_hash,
        "status": "materialized",
        "surfaces": [
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
            "program_hash": program_hash,
            "assembly_hash": assembly_hash,
            "surface_hashes": surface_hashes,
            **({"examples_hash": examples_hash} if examples_hash is not None else {}),
            "surface_generation": {
                "signature": "signature-gen",
                "module": "module-gen",
                "program": "program-gen",
                "eval_harness": "program-gen",
                **(
                    {"examples_harness": "program-gen"}
                    if examples_result is not None
                    else {}
                ),
            },
            "generated_files": generated_file_names,
            "smoke": smoke_result,
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
        },
        "intent": intent_payload,
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
            "generated_files": generated_file_names,
        },
        extra={
            "program_intent": intent_payload,
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
