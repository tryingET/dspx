# summary: "Deterministic import of a Misegraph evidence package into a program-intent-v2 intent, runtime inputs, and a dspx-misegraph-evidence-binding-v1 record."
# read_when:
#   - "Changing what `dspx foundry import-misegraph-evidence` emits or how the binding is derived."
#   - "Authoring the misegraph_source projection of a foundry evidence document."

"""Misegraph evidence package import (consumer side).

Input: a verified `misegraph-evidence-package-v1` directory (see
``program_foundry_misegraph_evidence_package``) and an operator-authored
answers file. Output: ``intent.json`` (program-intent-v2), ``inputs.json``,
``misegraph-evidence-binding.json`` (``dspx-misegraph-evidence-binding-v1``,
byte-for-byte the shape Misegraph's ``evidence verify-receipt`` deserializes
with ``deny_unknown_fields``), and ``misegraph-import-provenance.json``
carrying the answers-file hash and importer facts the closed binding cannot.

The output is a pure function of (package bytes, answers bytes, case
selection, outdir path). The importer never writes into the package dir, never
writes under a Misegraph repo root, and never invents an expected answer.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from dspx.services.program_foundry_misegraph_evidence_package import (
    CANONICAL_FILE,
    CHECK_FILE,
    RENDER_TEXT_FILE,
    SOURCE_FILE,
    MisegraphEvidencePackage,
    MisegraphEvidencePackageError,
    compact_canonical_json,
    load_misegraph_evidence_package,
    sha256_hex,
)
from dspx.services.program_intent import ProgramIntent

BINDING_SCHEMA_VERSION = "dspx-misegraph-evidence-binding-v1"
ANSWERS_SCHEMA_VERSION = "dspx-misegraph-example-answers-v1"
PROVENANCE_SCHEMA_VERSION = "dspx-misegraph-import-provenance-v1"
IMPORTER_SCHEMA_VERSION = "dspx-misegraph-evidence-import-v1"
DEFAULT_EXAMPLE_CASES: tuple[str, ...] = ("render-text", "check-json")

INTENT_FILE = "intent.json"
INPUTS_FILE = "inputs.json"
BINDING_FILE = "misegraph-evidence-binding.json"
PROVENANCE_FILE = "misegraph-import-provenance.json"
_BUNDLE_FILES = (INTENT_FILE, INPUTS_FILE, BINDING_FILE, PROVENANCE_FILE)

_ANSWERS_BYTE_BOUND = 1 << 20

# Every non-example field of the AK-5346/5352/5353 reference intent, kept
# identical so `dspx program-gen` and `dspx foundry` accept the emitted intent
# unchanged (same name, inputs/outputs, metric, options, quality criteria).
REFERENCE_INTENT_TEMPLATE: Mapping[str, Any] = {
    "capabilities": {},
    "constraints": [],
    "dataset": {},
    "datasets": {},
    "examples_path": None,
    "input_fields": [],
    "inputs": ["evidence"],
    "jury": {},
    "metric": "concept_coverage",
    "name": "AssessAMisegraphRecipeFromSupplied",
    "objective": (
        "Assess a Misegraph recipe from supplied source, canonical IR, and "
        "rendered evidence; return a concise fidelity judgment."
    ),
    "options": {
        "module_inference": True,
        "normalization": {
            "schema_version": "program-intent-normalization-v1",
            "source_hash": (
                "f70a8862634aa61534cc6461b79d8e00e8414861aec7696050a4fbf69bc18e7a"
            ),
            "source_kind": "prompt",
        },
        "quality_proposal": {
            "accepted": True,
            "feedback_turns": 0,
            "intent_sha256": (
                "f70a8862634aa61534cc6461b79d8e00e8414861aec7696050a4fbf69bc18e7a"
            ),
            "schema_version": "program-quality-criteria-proposal-v1",
        },
    },
    "output_fields": [],
    "outputs": ["answer"],
    "promotion": {},
    "quality_criteria": [
        {
            "evaluator": "concept_coverage",
            "forbidden_concepts": [],
            "id": "misegraph_recipe_fidelity",
            "min_score": 1.0,
            "output_field": "answer",
            "required_concept_groups": [
                ["espresso", "brownies"],
                ["ingredient", "process"],
                ["bake", "temperature"],
            ],
        }
    ],
    "runtime": {},
    "schema_version": "program-intent-v2",
    "task_type": "single_module",
    "topology": {},
}


class MisegraphEvidenceImportError(ValueError):
    """Raised when import inputs or output placement are invalid."""


@dataclass(frozen=True)
class MisegraphAnswers:
    """Operator-authored expected answers keyed by behavior case id."""

    path: Path
    sha256: str
    answers: Mapping[str, str]


def _pretty(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def load_misegraph_answers(path: Path) -> MisegraphAnswers:
    """Load a closed `dspx-misegraph-example-answers-v1` file."""

    source = path.expanduser()
    if source.is_symlink() or not source.is_file():
        raise MisegraphEvidenceImportError("answers file must be a regular file")
    data = source.read_bytes()
    if len(data) > _ANSWERS_BYTE_BOUND:
        raise MisegraphEvidenceImportError("answers file exceeds the size bound")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MisegraphEvidenceImportError(
            f"answers file is not valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "answers"}:
        raise MisegraphEvidenceImportError(
            "answers file must be an object with exactly schema_version and answers"
        )
    if payload["schema_version"] != ANSWERS_SCHEMA_VERSION:
        raise MisegraphEvidenceImportError(
            f"answers schema_version must be `{ANSWERS_SCHEMA_VERSION}`"
        )
    answers = payload["answers"]
    if not isinstance(answers, dict) or not answers:
        raise MisegraphEvidenceImportError("answers must be a non-empty object")
    for case_id, text in answers.items():
        if not isinstance(text, str) or not text.strip():
            raise MisegraphEvidenceImportError(
                f"answer for case `{case_id}` must be a non-blank string"
            )
    return MisegraphAnswers(
        path=source.resolve(), sha256=sha256_hex(data), answers=dict(answers)
    )


def select_example_cases(
    package: MisegraphEvidencePackage, cases: Sequence[str] | None
) -> tuple[str, ...]:
    selected = tuple(cases) if cases else DEFAULT_EXAMPLE_CASES
    if len(set(selected)) != len(selected):
        raise MisegraphEvidenceImportError("case selection repeats a case id")
    known = {case.id for case in package.behavior_cases}
    for case_id in selected:
        if case_id not in known:
            raise MisegraphEvidenceImportError(
                f"case `{case_id}` is not a behavior case of the package"
            )
    return selected


def build_example_evidence(package: MisegraphEvidencePackage, case_id: str) -> str:
    """Compact canonical JSON evidence for one behavior case."""

    if RENDER_TEXT_FILE not in package.files:
        raise MisegraphEvidenceImportError(
            f"package lacks `{RENDER_TEXT_FILE}`; the intent needs the text render"
        )
    case = package.case(case_id)
    evidence = {
        "recipe": dict(package.manifest["recipe"]),
        "package_sha256": package.package_sha256,
        "source": {
            "sha256": package.artifact_sha256(SOURCE_FILE),
            "text": package.text(SOURCE_FILE),
        },
        "canonical": {
            "sha256": package.artifact_sha256(CANONICAL_FILE),
            "json": package.json(CANONICAL_FILE),
        },
        "render": {
            "sha256": package.artifact_sha256(RENDER_TEXT_FILE),
            "text": package.text(RENDER_TEXT_FILE),
        },
        "check": {
            "sha256": package.artifact_sha256(CHECK_FILE),
            "diagnostics": package.json(CHECK_FILE)["diagnostics"],
        },
        "case": {"id": case.id, "argv": list(case.argv), "exit_code": case.exit_code},
    }
    return compact_canonical_json(evidence)


def build_misegraph_intent(
    package: MisegraphEvidencePackage,
    answers: MisegraphAnswers,
    cases: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build the program-intent-v2 payload; answers come only from the operator."""

    selected = select_example_cases(package, cases)
    examples: list[dict[str, Any]] = []
    for case_id in selected:
        answer = answers.answers.get(case_id)
        if answer is None:
            raise MisegraphEvidenceImportError(
                f"answers file has no entry for selected case `{case_id}`"
            )
        examples.append(
            {
                "inputs": {"evidence": build_example_evidence(package, case_id)},
                "outputs": {"answer": answer},
            }
        )
    intent = json.loads(json.dumps(REFERENCE_INTENT_TEMPLATE))
    intent["examples"] = examples
    ProgramIntent.model_validate(intent)
    return intent


def build_misegraph_inputs(intent: Mapping[str, Any]) -> dict[str, Any]:
    """Runtime inputs: exactly the first example's inputs."""

    examples = intent.get("examples")
    if not isinstance(examples, list) or not examples:
        raise MisegraphEvidenceImportError(
            "intent has no examples to derive inputs from"
        )
    return {"inputs": dict(examples[0]["inputs"])}


def build_misegraph_binding(
    package: MisegraphEvidencePackage,
    *,
    intent_path: Path,
    intent_bytes: bytes,
    inputs_path: Path,
    inputs_bytes: bytes,
    example_cases: Sequence[str],
) -> dict[str, Any]:
    """`dspx-misegraph-evidence-binding-v1`, closed to the Misegraph verifier shape."""

    return {
        "schema_version": BINDING_SCHEMA_VERSION,
        "package": {
            "dir": str(package.dir),
            "manifest_sha256": package.manifest_sha256,
            "package_sha256": package.package_sha256,
            "producer": dict(package.manifest["producer"]),
        },
        "validation": {
            "artifact_hashes_ok": True,
            "canonical_ir_schema_valid": True,
            "unknown_manifest_keys": [],
            "freshness": {
                "mode": "hash_bound",
                "check": "manifest_sha256_matches_at_import",
            },
        },
        "emitted": {
            "intent_path": str(intent_path),
            "intent_sha256": sha256_hex(intent_bytes),
            "inputs_path": str(inputs_path),
            "inputs_sha256": sha256_hex(inputs_bytes),
        },
        "example_cases": list(example_cases),
        "non_authority": {"misegraph_mutated": False, "acceptance_authority": False},
    }


def _is_misegraph_repo_root(candidate: Path) -> bool:
    cargo = candidate / "Cargo.toml"
    if not cargo.is_file():
        return False
    try:
        text = cargo.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(
        line.strip().replace(" ", "") == 'name="misegraph"'
        for line in text.splitlines()
    )


def preflight_import_outdir(outdir: Path, *, package: MisegraphEvidencePackage) -> Path:
    raw = outdir.expanduser().absolute()
    if raw.is_symlink() or (raw.exists() and not raw.is_dir()):
        raise MisegraphEvidenceImportError(
            "import outdir must be a real directory path"
        )
    root = raw.resolve()
    if root == package.dir or package.dir in root.parents:
        raise MisegraphEvidenceImportError(
            "import outdir must be outside the package dir"
        )
    if root in package.dir.parents:
        raise MisegraphEvidenceImportError(
            "import outdir must not contain the package dir"
        )
    for ancestor in (root, *root.parents):
        if _is_misegraph_repo_root(ancestor):
            raise MisegraphEvidenceImportError(
                "import outdir must not be under a Misegraph repository root"
            )
    for name in _BUNDLE_FILES:
        if (raw / name).exists() or (raw / name).is_symlink():
            raise MisegraphEvidenceImportError(f"refusing to overwrite existing {name}")
    return root


def _write_new_file(root_fd: int, name: str, data: bytes) -> None:
    """Atomic no-clobber write: temp file, fsync, hard-link into place."""

    temporary = f".{name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o644, dir_fd=root_fd)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
        except FileExistsError as exc:
            raise MisegraphEvidenceImportError(
                f"refusing to overwrite existing {name}"
            ) from exc
        os.fsync(root_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=root_fd)
        except FileNotFoundError:
            pass


def write_import_bundle(
    *,
    package_dir: Path,
    answers_path: Path,
    outdir: Path,
    cases: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Verify, build, and write intent/inputs/binding/provenance without clobbering."""

    try:
        package = load_misegraph_evidence_package(package_dir)
    except MisegraphEvidencePackageError as exc:
        raise MisegraphEvidenceImportError(f"package rejected: {exc}") from exc
    answers = load_misegraph_answers(answers_path)
    root = preflight_import_outdir(outdir, package=package)
    if answers.path == root or root in answers.path.parents:
        raise MisegraphEvidenceImportError(
            "answers file must be outside the import outdir"
        )
    intent = build_misegraph_intent(package, answers, cases)
    inputs = build_misegraph_inputs(intent)
    selected = [str(item) for item in select_example_cases(package, cases)]
    intent_bytes = _pretty(intent)
    inputs_bytes = _pretty(inputs)
    intent_path = root / INTENT_FILE
    inputs_path = root / INPUTS_FILE
    binding = build_misegraph_binding(
        package,
        intent_path=intent_path,
        intent_bytes=intent_bytes,
        inputs_path=inputs_path,
        inputs_bytes=inputs_bytes,
        example_cases=selected,
    )
    binding_bytes = _pretty(binding)
    provenance = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "importer_schema_version": IMPORTER_SCHEMA_VERSION,
        "package_sha256": package.package_sha256,
        "manifest_sha256": package.manifest_sha256,
        "answers": {
            "schema_version": ANSWERS_SCHEMA_VERSION,
            "path": str(answers.path),
            "sha256": answers.sha256,
        },
        "binding": {
            "path": str(root / BINDING_FILE),
            "sha256": sha256_hex(binding_bytes),
        },
        "example_cases": selected,
        "canonical_ir_validator": package.canonical_ir_validator,
        "non_authority": {
            "misegraph_mutated": False,
            "acceptance_authority": False,
            "answers_authored_by_importer": False,
        },
    }
    root.mkdir(parents=True, exist_ok=True)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    try:
        _write_new_file(root_fd, INTENT_FILE, intent_bytes)
        _write_new_file(root_fd, INPUTS_FILE, inputs_bytes)
        _write_new_file(root_fd, BINDING_FILE, binding_bytes)
        _write_new_file(root_fd, PROVENANCE_FILE, _pretty(provenance))
    finally:
        os.close(root_fd)
    return {
        "status": "ok",
        "outdir": str(root),
        "intent_path": str(intent_path),
        "inputs_path": str(inputs_path),
        "binding_path": str(root / BINDING_FILE),
        "provenance_path": str(root / PROVENANCE_FILE),
        "binding": binding,
        "provenance": provenance,
    }


def build_misegraph_source_projection(
    binding: Mapping[str, Any], *, package: MisegraphEvidencePackage | None = None
) -> dict[str, Any]:
    """`misegraph_source` block for docs/project/*-evidence.json from a binding."""

    if binding.get("schema_version") != BINDING_SCHEMA_VERSION:
        raise MisegraphEvidenceImportError(
            f"binding schema_version must be `{BINDING_SCHEMA_VERSION}`"
        )
    bound = binding.get("package")
    if not isinstance(bound, Mapping):
        raise MisegraphEvidenceImportError("binding lacks a package block")
    if package is None:
        try:
            package = load_misegraph_evidence_package(Path(str(bound["dir"])))
        except MisegraphEvidencePackageError as exc:
            raise MisegraphEvidenceImportError(f"package rejected: {exc}") from exc
    if package.manifest_sha256 != bound.get("manifest_sha256"):
        raise MisegraphEvidenceImportError(
            "binding manifest_sha256 does not match the package"
        )
    if package.package_sha256 != bound.get("package_sha256"):
        raise MisegraphEvidenceImportError(
            "binding package_sha256 does not match the package"
        )

    def artifact(name: str) -> dict[str, str]:
        return {
            "path": str(package.dir / name),
            "sha256": package.artifact_sha256(name),
        }

    projection = {
        "source": artifact(SOURCE_FILE),
        "canonical": artifact(CANONICAL_FILE),
        "render": artifact(RENDER_TEXT_FILE),
        "package": {
            "schema_version": str(package.manifest["schema_version"]),
            "dir": str(package.dir),
            "manifest_sha256": package.manifest_sha256,
            "package_sha256": package.package_sha256,
            "binding_schema_version": BINDING_SCHEMA_VERSION,
            "example_cases": list(binding.get("example_cases") or []),
        },
    }
    return projection
