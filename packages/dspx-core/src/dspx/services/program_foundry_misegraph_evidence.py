# summary: "Deterministic import of a Misegraph evidence package into a program-intent-v2 intent (package-derived concept groups), runtime inputs, and a dspx-misegraph-evidence-binding-v1 record."
# read_when:
#   - "Changing what `dspx foundry import-misegraph-evidence` emits, how the expected projection is derived, or how the binding is derived."
#   - "Authoring the misegraph_source projection of a foundry evidence document."

"""Misegraph evidence package import (consumer side).

Input: a verified `misegraph-evidence-package-v1` directory (see
``program_foundry_misegraph_evidence_package``) and optionally an
operator-authored answers file. Output: ``intent.json`` (program-intent-v2),
``inputs.json``, ``misegraph-evidence-binding.json``
(``dspx-misegraph-evidence-binding-v1``, byte-for-byte the shape Misegraph's
``evidence verify-receipt`` deserializes with ``deny_unknown_fields``), and
``misegraph-import-provenance.json`` carrying the answers origin, the derived
expected projection, and importer facts the closed binding cannot.

The quality criterion's ``required_concept_groups`` are derived from the
package itself (``canonical.json`` recipe id tokens, ingredients, equipment,
bake temperature/duration; ``check.json`` error count) by
``derive_misegraph_expected``. When no answers file is supplied, the example
answer is the deterministic canonical projection string of those same facts
and provenance records ``answers.origin = "package_derived"``; an operator
answers file records ``answers.origin = "operator"``.

The output is a pure function of (package bytes, answers bytes or absence,
case selection, outdir path). The importer never writes into the package dir
and never writes under a Misegraph repo root.
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
from dspx.services.program_quality_evaluation import (
    evaluate_declared_quality,
    normalize_quality_criteria,
)

BINDING_SCHEMA_VERSION = "dspx-misegraph-evidence-binding-v1"
ANSWERS_SCHEMA_VERSION = "dspx-misegraph-example-answers-v1"
PROVENANCE_SCHEMA_VERSION = "dspx-misegraph-import-provenance-v1"
IMPORTER_SCHEMA_VERSION = "dspx-misegraph-evidence-import-v1"
EXPECTED_PROJECTION_SCHEMA_VERSION = "dspx-misegraph-expected-projection-v1"
ANSWERS_ORIGIN_OPERATOR = "operator"
ANSWERS_ORIGIN_PACKAGE_DERIVED = "package_derived"
QUALITY_CRITERION_ID = "misegraph_recipe_fidelity"
_MAX_CONCEPT_GROUPS = 20
_MAX_TERMS_PER_GROUP = 10
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


def _number_text(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MisegraphEvidenceImportError("canonical amount value must be numeric")
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def _amount_text(amount: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Return (display, alternative bound texts) for an exact or range amount."""

    kind = str(amount.get("kind") or "")
    if kind == "exact":
        value = _number_text(amount.get("value"))
        return value, [value]
    if kind == "range":
        low = _number_text(amount.get("min"))
        high = _number_text(amount.get("max"))
        return f"{low}-{high}", [low, high, f"{low}-{high}", f"{low}..{high}"]
    raise MisegraphEvidenceImportError(
        f"canonical amount kind `{kind or 'missing'}` is not supported by the projection"
    )


def _unique_terms(terms: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        text = " ".join(str(term).split())
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        unique.append(text)
    if len(unique) > _MAX_TERMS_PER_GROUP:
        unique = unique[:_MAX_TERMS_PER_GROUP]
    return unique


def _id_alternatives(identifier: str, name: object) -> list[str]:
    terms = [identifier, identifier.replace("_", " ")]
    if isinstance(name, str) and name.strip():
        terms.append(name)
    return _unique_terms(terms)


def _error_count(check_payload: Mapping[str, Any]) -> int:
    diagnostics = check_payload.get("diagnostics")
    if not isinstance(diagnostics, list):
        raise MisegraphEvidenceImportError("check.json diagnostics must be a list")
    count = 0
    for item in diagnostics:
        if not isinstance(item, Mapping):
            raise MisegraphEvidenceImportError(
                "check.json diagnostic must be an object"
            )
        level = str(item.get("level") or item.get("severity") or "").strip().lower()
        if level == "error":
            count += 1
    return count


def derive_misegraph_expected(
    package: MisegraphEvidencePackage, case_id: str
) -> dict[str, Any]:
    """Derive the expected concept groups and canonical projection from the package.

    Everything comes from ``canonical.json`` (recipe id tokens, ingredient
    ids/names, equipment, bake step temperature/duration), ``check.json``
    (error count) and the behavior case. Nothing is invented: the projection
    string is a deterministic restatement that the derived criterion accepts.
    """

    try:
        case = package.case(case_id)
    except MisegraphEvidencePackageError as exc:
        raise MisegraphEvidenceImportError(
            f"case `{case_id}` is not a behavior case of the package"
        ) from exc
    canonical = package.json(CANONICAL_FILE)
    if not isinstance(canonical, Mapping):
        raise MisegraphEvidenceImportError("canonical.json must be an object")
    check_payload = package.json(CHECK_FILE)
    if not isinstance(check_payload, Mapping):
        raise MisegraphEvidenceImportError("check.json must be an object")
    recipe_id = str(canonical.get("id") or "").strip()
    title = str(canonical.get("title") or "").strip()
    if not recipe_id:
        raise MisegraphEvidenceImportError("canonical.json lacks a recipe id")
    groups: list[list[str]] = []
    id_tokens = [token for token in recipe_id.split("_") if len(token) >= 2]
    for token in id_tokens:
        groups.append(_unique_terms([token]))

    ingredient_facts: list[dict[str, str]] = []
    for item in canonical.get("ingredients") or []:
        if not isinstance(item, Mapping):
            raise MisegraphEvidenceImportError("canonical ingredient must be an object")
        identifier = str(item.get("id") or "").strip()
        if not identifier:
            raise MisegraphEvidenceImportError("canonical ingredient lacks an id")
        name = item.get("name")
        quantity = item.get("quantity")
        quantity_text = ""
        if isinstance(quantity, Mapping) and isinstance(
            quantity.get("amount"), Mapping
        ):
            display, _ = _amount_text(quantity["amount"])
            unit = str(quantity.get("unit") or "").strip()
            quantity_text = f"{display} {unit}".strip()
        ingredient_facts.append(
            {
                "id": identifier,
                "name": str(name or identifier),
                "quantity": quantity_text,
            }
        )
        groups.append(_id_alternatives(identifier, name))

    equipment_facts: list[dict[str, str]] = []
    for item in canonical.get("equipment") or []:
        if not isinstance(item, Mapping):
            raise MisegraphEvidenceImportError("canonical equipment must be an object")
        identifier = str(item.get("id") or "").strip()
        if not identifier:
            raise MisegraphEvidenceImportError("canonical equipment lacks an id")
        name = item.get("name")
        equipment_facts.append({"id": identifier, "name": str(name or identifier)})
        groups.append(_id_alternatives(identifier, name))

    bake_facts: list[dict[str, str]] = []
    for step in canonical.get("steps") or []:
        if not isinstance(step, Mapping):
            raise MisegraphEvidenceImportError("canonical step must be an object")
        temperature = step.get("temperature")
        duration = step.get("duration")
        if not isinstance(temperature, Mapping) and not isinstance(duration, Mapping):
            continue
        step_id = str(step.get("id") or "").strip() or str(step.get("action") or "step")
        fact = {"step": step_id, "action": str(step.get("action") or "")}
        if isinstance(temperature, Mapping) and isinstance(
            temperature.get("amount"), Mapping
        ):
            display, bounds = _amount_text(temperature["amount"])
            unit = str(temperature.get("unit") or "").strip()
            fact["temperature"] = f"{display} {unit}".strip()
            terms: list[str] = []
            for bound in bounds:
                terms.extend(
                    [
                        f"{bound} {unit}",
                        f"{bound}{unit}",
                        f"{bound} °{unit}",
                        f"{bound}°{unit}",
                        f"{bound} degrees {unit}",
                    ]
                )
            groups.append(_unique_terms(terms))
        if isinstance(duration, Mapping) and isinstance(
            duration.get("amount"), Mapping
        ):
            display, bounds = _amount_text(duration["amount"])
            unit = str(duration.get("unit") or "").strip()
            fact["duration"] = f"{display} {unit}".strip()
            terms = []
            for bound in bounds:
                terms.extend([f"{bound} {unit}", f"{bound}{unit}"])
            groups.append(_unique_terms(terms))
        bake_facts.append(fact)

    error_count = _error_count(check_payload)
    if error_count == 0:
        groups.append(
            _unique_terms(
                [
                    "0 errors",
                    "zero errors",
                    "no errors",
                    "error_count 0",
                    "error_count: 0",
                    "0 diagnostics",
                    "zero diagnostics",
                    "no diagnostics",
                ]
            )
        )
    else:
        groups.append(
            _unique_terms(
                [
                    f"{error_count} errors",
                    f"{error_count} error",
                    f"error_count {error_count}",
                    f"error_count: {error_count}",
                ]
            )
        )
    if not groups or len(groups) > _MAX_CONCEPT_GROUPS:
        raise MisegraphEvidenceImportError(
            f"derived concept groups must number 1-{_MAX_CONCEPT_GROUPS}; got {len(groups)}"
        )

    diagnostics = check_payload.get("diagnostics")
    diagnostic_count = len(diagnostics) if isinstance(diagnostics, list) else 0
    conformance = package.manifest.get("conformance")
    conformance_map = dict(conformance) if isinstance(conformance, Mapping) else {}
    yield_value = canonical.get("yield")
    yield_text = ""
    if isinstance(yield_value, Mapping) and yield_value.get("amount") is not None:
        yield_text = (
            f"{_number_text(yield_value.get('amount'))} "
            f"{str(yield_value.get('unit') or '').strip()}"
        ).strip()
    sentences = [
        f"Misegraph evidence projection for case {case.id} (exit code {case.exit_code}).",
        f"Recipe {recipe_id}"
        + (f" '{title}'" if title else "")
        + (f" with id tokens {', '.join(id_tokens)}" if id_tokens else "")
        + (f"; yield {yield_text}" if yield_text else "")
        + ".",
    ]
    if ingredient_facts:
        sentences.append(
            "Ingredients: "
            + "; ".join(
                f"{fact['name']} ({fact['id']})"
                + (f" {fact['quantity']}" if fact["quantity"] else "")
                for fact in ingredient_facts
            )
            + "."
        )
    if equipment_facts:
        sentences.append(
            "Equipment: "
            + "; ".join(f"{fact['name']} ({fact['id']})" for fact in equipment_facts)
            + "."
        )
    for fact in bake_facts:
        parts = []
        if fact.get("temperature"):
            parts.append(f"temperature {fact['temperature']}")
        if fact.get("duration"):
            parts.append(f"duration {fact['duration']}")
        sentences.append(
            f"Step {fact['step']} ({fact['action']}): " + ", ".join(parts) + "."
        )
    sentences.append(
        f"Check: {error_count} errors, {diagnostic_count} diagnostics; "
        f"conformance status {conformance_map.get('status')}, "
        f"error_count {conformance_map.get('error_count')}, "
        f"warning_count {conformance_map.get('warning_count')}, "
        f"deny_warnings {str(bool(conformance_map.get('deny_warnings'))).lower()}."
    )
    sentences.append(
        "Source, canonical IR, and text render are hash-bound in the evidence; "
        "this projection is a deterministic restatement, not a judgment."
    )
    projection = " ".join(sentences)
    criterion = quality_criterion_for_groups(groups)
    evaluation = evaluate_declared_quality(
        normalize_quality_criteria([criterion], outputs=["answer"]),
        {"answer": projection},
    )
    if evaluation.get("status") != "passed":  # pragma: no cover - internal invariant
        raise MisegraphEvidenceImportError(
            "derived projection does not satisfy its own derived concept groups"
        )
    return {
        "schema_version": EXPECTED_PROJECTION_SCHEMA_VERSION,
        "case_id": case.id,
        "required_concept_groups": groups,
        "projection": projection,
        "projection_sha256": sha256_hex(projection.encode("utf-8")),
        "derived_from": [CANONICAL_FILE, CHECK_FILE, "manifest.json", "behavior.json"],
        "facts": {
            "recipe_id": recipe_id,
            "id_tokens": id_tokens,
            "ingredients": ingredient_facts,
            "equipment": equipment_facts,
            "bake_steps": bake_facts,
            "error_count": error_count,
            "diagnostic_count": diagnostic_count,
        },
    }


def quality_criterion_for_groups(groups: Sequence[Sequence[str]]) -> dict[str, Any]:
    """The template criterion with package-derived required concept groups."""

    template = REFERENCE_INTENT_TEMPLATE["quality_criteria"][0]
    criterion = json.loads(json.dumps(template))
    criterion["required_concept_groups"] = [list(group) for group in groups]
    return criterion


def build_misegraph_intent(
    package: MisegraphEvidencePackage,
    answers: MisegraphAnswers | None = None,
    cases: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build the program-intent-v2 payload with package-derived concept groups.

    ``outputs.answer`` is the operator's answer when an answers file is given,
    otherwise the deterministic package-derived projection for the case.
    """

    selected = select_example_cases(package, cases)
    examples: list[dict[str, Any]] = []
    groups: list[list[str]] | None = None
    for case_id in selected:
        expected = derive_misegraph_expected(package, case_id)
        derived_groups = [list(group) for group in expected["required_concept_groups"]]
        if groups is None:
            groups = derived_groups
        elif groups != derived_groups:  # pragma: no cover - package invariant
            raise MisegraphEvidenceImportError(
                "derived concept groups differ across selected cases"
            )
        if answers is not None:
            answer = answers.answers.get(case_id)
            if answer is None:
                raise MisegraphEvidenceImportError(
                    f"answers file has no entry for selected case `{case_id}`"
                )
        else:
            answer = str(expected["projection"])
        examples.append(
            {
                "inputs": {"evidence": build_example_evidence(package, case_id)},
                "outputs": {"answer": answer},
            }
        )
    intent = json.loads(json.dumps(REFERENCE_INTENT_TEMPLATE))
    intent["quality_criteria"] = [quality_criterion_for_groups(groups or [])]
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
    outdir: Path,
    answers_path: Path | None = None,
    cases: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Verify, build, and write intent/inputs/binding/provenance without clobbering."""

    try:
        package = load_misegraph_evidence_package(package_dir)
    except MisegraphEvidencePackageError as exc:
        raise MisegraphEvidenceImportError(f"package rejected: {exc}") from exc
    answers = load_misegraph_answers(answers_path) if answers_path is not None else None
    root = preflight_import_outdir(outdir, package=package)
    if answers is not None and (answers.path == root or root in answers.path.parents):
        raise MisegraphEvidenceImportError(
            "answers file must be outside the import outdir"
        )
    intent = build_misegraph_intent(package, answers, cases)
    inputs = build_misegraph_inputs(intent)
    selected = [str(item) for item in select_example_cases(package, cases)]
    expected_by_case = {
        case_id: derive_misegraph_expected(package, case_id) for case_id in selected
    }
    derived_groups = intent["quality_criteria"][0]["required_concept_groups"]
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
        "answers": (
            {
                "origin": ANSWERS_ORIGIN_OPERATOR,
                "schema_version": ANSWERS_SCHEMA_VERSION,
                "path": str(answers.path),
                "sha256": answers.sha256,
            }
            if answers is not None
            else {
                "origin": ANSWERS_ORIGIN_PACKAGE_DERIVED,
                "schema_version": None,
                "path": None,
                "sha256": None,
            }
        ),
        "expected_projection": {
            "schema_version": EXPECTED_PROJECTION_SCHEMA_VERSION,
            "quality_criterion_id": QUALITY_CRITERION_ID,
            "required_concept_groups": derived_groups,
            "derived_from": list(expected_by_case[selected[0]]["derived_from"]),
            "projection_sha256_by_case": {
                case_id: expected["projection_sha256"]
                for case_id, expected in expected_by_case.items()
            },
            "used_as_example_answer": answers is None,
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
            # A package-derived answer is a mechanical projection of package
            # facts authored by the importer, never an operator judgment.
            "answers_authored_by_importer": answers is None,
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
