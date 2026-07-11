# summary: "Runs a bounded local GEPA refinement attempt and records hash-bound optimizer evidence without claiming a program candidate."
# read_when:
#   - "Changing GEPA evidence selection, optimizer inputs, output classification, path isolation, or non-authority posture."
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from dspx.services.program_refinement import load_program_manifest
from dspx.services.optimize_service import run_gepa_optimize

PROGRAM_REFINEMENT_GEPA_RESULT_SCHEMA = "program-refinement-gepa-result-v1"
_MAX_GEPA_OUTPUT_MANIFEST_BYTES = 2 * 1024 * 1024

_GEPA_EFFECT_BASE = {
    "source_program_files_mutated": False,
    "source_dataset_artifacts_mutated": False,
    "external_authority_mutated": False,
    "governance_mutated": False,
}

_GEPA_NON_AUTHORITY = {
    "local_refinement_only": True,
    "automatic_promotion": False,
    "oracle_ranking": False,
    "oracle_pruning": False,
    "oracle_promotion": False,
    "winner_selection": False,
    "external_authority_export": False,
    "governance_authority": False,
    "external_mutation": False,
}


class ProgramRefinementGepaError(ValueError):
    """Raised when a local GEPA refinement request is malformed."""


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramRefinementGepaError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramRefinementGepaError(f"{label} must be valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ProgramRefinementGepaError(f"{label} must contain a JSON object: {path}")
    return payload


def _identity_from_manifest(manifest: Mapping[str, Any]) -> dict[str, str | None]:
    request = _safe_mapping(manifest.get("request"))
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    return {
        "request_id": _first_text(
            request.get("request_id"),
            candidate_assembly.get("request_id"),
            execution_episode.get("request_id"),
            receipt_bundle.get("request_id"),
        ),
        "candidate_id": _first_text(
            candidate_assembly.get("candidate_id"),
            execution_episode.get("candidate_id"),
            receipt_bundle.get("candidate_id"),
        ),
        "assembly_id": _first_text(
            candidate_assembly.get("assembly_id"),
            execution_episode.get("assembly_id"),
            receipt_bundle.get("assembly_id"),
        ),
        "episode_id": _first_text(
            execution_episode.get("episode_id"),
            receipt_bundle.get("episode_id"),
        ),
        "receipt_bundle_id": _first_text(receipt_bundle.get("receipt_bundle_id")),
    }


def _manifest_root(manifest_path: Path) -> Path:
    return manifest_path.expanduser().resolve().parent


def _candidate_root(manifest: Mapping[str, Any], manifest_path: Path) -> Path:
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    raw_root = str(candidate_assembly.get("root_path") or "").strip()
    if raw_root:
        root = Path(raw_root).expanduser()
        if not root.is_absolute():
            root = _manifest_root(manifest_path) / root
        return root.resolve()
    return _manifest_root(manifest_path)


def _is_same_or_descendant(path: Path, parent: Path) -> bool:
    return path == parent or path.is_relative_to(parent)


def _assert_no_path_overlap(
    *, label: str, path: Path, protected_label: str, protected: Path
) -> None:
    if _is_same_or_descendant(path, protected):
        raise ProgramRefinementGepaError(
            f"{label} must be outside {protected_label}: {path}"
        )
    if _is_same_or_descendant(protected, path):
        raise ProgramRefinementGepaError(
            f"{label} must not contain {protected_label}: {path}"
        )


def _preflight_gepa_output_paths(
    *,
    manifest: Mapping[str, Any],
    manifest_path: Path,
    outdir: Path,
    result_out: Path | None = None,
) -> None:
    source_root = _candidate_root(manifest, manifest_path)
    resolved_outdir = outdir.expanduser().resolve()
    _assert_no_path_overlap(
        label="GEPA output directory",
        path=resolved_outdir,
        protected_label="source candidate root",
        protected=source_root,
    )
    if result_out is None:
        return
    resolved_result = result_out.expanduser().resolve()
    _assert_no_path_overlap(
        label="GEPA result sidecar path",
        path=resolved_result,
        protected_label="source candidate root",
        protected=source_root,
    )
    if _is_same_or_descendant(
        resolved_result, resolved_outdir
    ) or _is_same_or_descendant(resolved_outdir, resolved_result):
        raise ProgramRefinementGepaError(
            "GEPA result sidecar path must not overlap the GEPA output directory: "
            f"{resolved_result}"
        )


def _resolve_under_manifest_root(
    manifest_path: Path, raw_path: str | None
) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = _manifest_root(manifest_path) / path
    return path.resolve()


def _surface_path(
    manifest: Mapping[str, Any],
    manifest_path: Path,
    *,
    kind: str,
    default: str | None = None,
) -> Path | None:
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    for surface in _safe_list(candidate_assembly.get("surfaces")):
        if not isinstance(surface, Mapping) or surface.get("kind") != kind:
            continue
        path = _resolve_under_manifest_root(
            manifest_path, _first_text(surface.get("path"))
        )
        if path is not None:
            return path
    if default is None:
        return None
    return (_manifest_root(manifest_path) / default).resolve()


def _program_path(manifest: Mapping[str, Any], manifest_path: Path) -> Path:
    path = _surface_path(manifest, manifest_path, kind="program", default="program.py")
    if path is None:
        raise ProgramRefinementGepaError("program manifest does not declare program.py")
    if not path.exists():
        raise ProgramRefinementGepaError(f"program.py not found: {path}")
    return path


def _intent_fields(manifest: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    intent = _safe_mapping(manifest.get("intent"))
    inputs = _string_list(intent.get("inputs"))
    outputs = _string_list(intent.get("outputs"))
    if not inputs or not outputs:
        raise ProgramRefinementGepaError(
            "program manifest intent must declare non-empty inputs and outputs for GEPA refinement"
        )
    return inputs, outputs


def _metric_for_gepa(
    metric: str | None, manifest: Mapping[str, Any]
) -> tuple[str, str]:
    raw = str(
        metric or _safe_mapping(manifest.get("intent")).get("metric") or "exact_match"
    ).strip()
    if raw in {"exact_match", "exact"}:
        return raw, "exact"
    if raw in {"contains", "f1"}:
        return raw, raw
    return raw, "exact"


def _load_jsonl_records(path: Path, *, label: str) -> list[dict[str, Any]]:
    if path.suffix.lower() != ".jsonl":
        raise ProgramRefinementGepaError(f"{label} must be a JSONL file: {path}")
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ProgramRefinementGepaError(f"{label} not found: {path}") from exc
    for line_number, line in enumerate(lines, 1):
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProgramRefinementGepaError(
                f"{label} row {line_number} must be valid JSON"
            ) from exc
        if not isinstance(payload, Mapping):
            raise ProgramRefinementGepaError(
                f"{label} row {line_number} must be an object"
            )
        records.append(dict(payload))
    return records


def _normalize_example_records(
    records: Sequence[Mapping[str, Any]],
    *,
    input_fields: list[str],
    output_fields: list[str],
    label: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        raw_inputs = record.get("inputs")
        raw_outputs = record.get("outputs")
        if not isinstance(raw_inputs, Mapping):
            raise ProgramRefinementGepaError(
                f"{label} record {index} missing object inputs"
            )
        if not isinstance(raw_outputs, Mapping):
            raise ProgramRefinementGepaError(
                f"{label} record {index} missing object outputs"
            )
        inputs = dict(raw_inputs)
        outputs = dict(raw_outputs)
        missing_inputs = [name for name in input_fields if name not in inputs]
        missing_outputs = [name for name in output_fields if name not in outputs]
        if missing_inputs:
            raise ProgramRefinementGepaError(
                f"{label} record {index} missing input fields: {missing_inputs}"
            )
        if missing_outputs:
            raise ProgramRefinementGepaError(
                f"{label} record {index} missing output fields: {missing_outputs}"
            )
        normalized.append({"inputs": inputs, "outputs": outputs})
    return normalized


def _load_inline_examples(
    path: Path, *, input_fields: list[str], output_fields: list[str]
) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        raise ProgramRefinementGepaError(
            f"examples.json must be valid JSON: {path}"
        ) from exc
    if not isinstance(payload, list):
        raise ProgramRefinementGepaError(f"examples.json must contain a list: {path}")
    records = [dict(item) for item in payload if isinstance(item, Mapping)]
    return _normalize_example_records(
        records,
        input_fields=input_fields,
        output_fields=output_fields,
        label="examples.json",
    )


def _count_behavior_examples(path: Path | None) -> int | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, Mapping):
        return None
    summary = _safe_mapping(payload.get("summary"))
    total = summary.get("total")
    if isinstance(total, int):
        return total
    examples = payload.get("examples")
    return len(examples) if isinstance(examples, list) else None


def _select_evidence_inputs(
    *,
    manifest: Mapping[str, Any],
    manifest_path: Path,
    input_fields: list[str],
    output_fields: list[str],
    train_path: Path | None,
    validation_path: Path | None,
) -> dict[str, Any]:
    created_from: dict[str, Any] = {
        "manifest_path": str(manifest_path),
        "source_manifest_schema_version": manifest.get("schema_version"),
        "dataset_manifest_path": None,
        "train_dataset_path": None,
        "validation_dataset_path": None,
        "behavior_results_path": None,
        "train_behavior_results_path": None,
        "validation_behavior_results_path": None,
    }
    limitations: list[str] = []
    held_out_validation = False

    if train_path is not None or validation_path is not None:
        if train_path is None or validation_path is None:
            raise ProgramRefinementGepaError(
                "GEPA refinement requires both --train and --validation when explicit dataset files are supplied"
            )
        resolved_train = train_path.expanduser().resolve()
        resolved_validation = validation_path.expanduser().resolve()
        train_records = _normalize_example_records(
            _load_jsonl_records(resolved_train, label="train dataset"),
            input_fields=input_fields,
            output_fields=output_fields,
            label="train dataset",
        )
        validation_records = _normalize_example_records(
            _load_jsonl_records(resolved_validation, label="validation dataset"),
            input_fields=input_fields,
            output_fields=output_fields,
            label="validation dataset",
        )
        held_out_validation = resolved_train != resolved_validation
        if not held_out_validation:
            limitations.append(
                "Explicit train and validation paths are identical; validation is not held out."
            )
        created_from["train_dataset_path"] = str(resolved_train)
        created_from["validation_dataset_path"] = str(resolved_validation)
        return {
            "created_from": created_from,
            "source": "explicit_dataset_files",
            "train_records": train_records,
            "validation_records": validation_records,
            "held_out_validation": held_out_validation,
            "limitations": limitations,
        }

    dataset_manifest_path = _surface_path(
        manifest,
        manifest_path,
        kind="dataset_manifest",
        default="dataset_manifest.json",
    )
    if dataset_manifest_path is not None and dataset_manifest_path.exists():
        dataset_manifest = _load_json_object(
            dataset_manifest_path, label="dataset manifest"
        )
        artifacts = _safe_mapping(dataset_manifest.get("artifacts"))
        train_artifact = _safe_mapping(artifacts.get("train"))
        validation_artifact = _safe_mapping(artifacts.get("validation"))
        train_split = _resolve_under_manifest_root(
            manifest_path,
            _first_text(train_artifact.get("path")) or "splits/train.jsonl",
        )
        validation_split = _resolve_under_manifest_root(
            manifest_path,
            _first_text(validation_artifact.get("path")) or "splits/validation.jsonl",
        )
        if (
            train_split is not None
            and validation_split is not None
            and train_split.exists()
            and validation_split.exists()
        ):
            train_records = _normalize_example_records(
                _load_jsonl_records(train_split, label="manifest train split"),
                input_fields=input_fields,
                output_fields=output_fields,
                label="manifest train split",
            )
            validation_records = _normalize_example_records(
                _load_jsonl_records(
                    validation_split, label="manifest validation split"
                ),
                input_fields=input_fields,
                output_fields=output_fields,
                label="manifest validation split",
            )
            train_behavior = _resolve_under_manifest_root(
                manifest_path,
                _first_text(train_artifact.get("behavior_results"))
                or "behavior_results.train.json",
            )
            validation_behavior = _resolve_under_manifest_root(
                manifest_path,
                _first_text(validation_artifact.get("behavior_results"))
                or "behavior_results.validation.json",
            )
            created_from.update(
                {
                    "dataset_manifest_path": str(dataset_manifest_path),
                    "train_dataset_path": str(train_split),
                    "validation_dataset_path": str(validation_split),
                    "train_behavior_results_path": str(train_behavior)
                    if train_behavior and train_behavior.exists()
                    else None,
                    "validation_behavior_results_path": str(validation_behavior)
                    if validation_behavior and validation_behavior.exists()
                    else None,
                }
            )
            held_out_validation = train_split != validation_split
            if not validation_records:
                limitations.append(
                    "Manifest validation split is empty; GEPA can only use training examples."
                )
            return {
                "created_from": created_from,
                "source": "manifest_dataset_splits",
                "train_records": train_records,
                "validation_records": validation_records,
                "held_out_validation": held_out_validation,
                "limitations": limitations,
            }

    examples_path = _surface_path(
        manifest, manifest_path, kind="examples", default="examples.json"
    )
    behavior_path = _surface_path(
        manifest,
        manifest_path,
        kind="behavior_results",
        default="behavior_results.json",
    )
    examples = (
        _load_inline_examples(
            examples_path, input_fields=input_fields, output_fields=output_fields
        )
        if examples_path is not None and examples_path.exists()
        else []
    )
    created_from["behavior_results_path"] = (
        str(behavior_path) if behavior_path and behavior_path.exists() else None
    )
    if examples:
        limitations.append(
            "Inline examples are not a deterministic held-out dataset split."
        )
        behavior_count = _count_behavior_examples(behavior_path)
        if behavior_count is None:
            limitations.append(
                "behavior_results.json was not available for the inline examples fallback."
            )
        if len(examples) == 1:
            limitations.append(
                "Only one inline example is available; it is reused for validation and is not held out."
            )
            validation_records = list(examples)
        else:
            validation_records = [examples[-1]]
            examples = examples[:-1]
            held_out_validation = True
        return {
            "created_from": created_from,
            "source": "inline_examples",
            "train_records": examples,
            "validation_records": validation_records,
            "held_out_validation": held_out_validation,
            "limitations": limitations,
        }

    limitations.append(
        "No explicit dataset files, manifest dataset splits, or inline examples were available."
    )
    return {
        "created_from": created_from,
        "source": "inline_examples",
        "train_records": [],
        "validation_records": [],
        "held_out_validation": False,
        "limitations": limitations,
    }


def _csv_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _write_optimizer_csv(
    path: Path,
    records: list[Mapping[str, Any]],
    *,
    input_fields: list[str],
    output_fields: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [*input_fields, *output_fields]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for record in records:
            inputs = _safe_mapping(record.get("inputs"))
            outputs = _safe_mapping(record.get("outputs"))
            row = {name: _csv_value(inputs[name]) for name in input_fields}
            row.update({name: _csv_value(outputs[name]) for name in output_fields})
            writer.writerow(row)


def _classify_gepa_output(outdir: Path) -> dict[str, Any]:
    manifest_path = outdir / "manifest.json"
    base: dict[str, Any] = {
        "root_path": str(outdir),
        "manifest_path": str(manifest_path),
        "manifest_present": manifest_path.exists(),
        "manifest_valid": False,
        "manifest_sha256": None,
        "manifest_schema_version": None,
        "manifest_kind": None,
        "candidate_assembly_manifest": False,
        "readiness": {
            "status": "optimizer_output_unverified_not_candidate",
            "ready_for_future_candidate_materializer": False,
            "blockers": [],
        },
    }
    blockers = base["readiness"]["blockers"]
    if not manifest_path.exists():
        blockers.append("optimizer_output_manifest_missing")
        return base
    try:
        size = manifest_path.stat().st_size
    except OSError as exc:
        blockers.append(f"optimizer_output_manifest_unreadable:{type(exc).__name__}")
        return base
    if size > _MAX_GEPA_OUTPUT_MANIFEST_BYTES:
        blockers.append("optimizer_output_manifest_too_large")
        return base
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        blockers.append("optimizer_output_manifest_invalid_json")
        return base
    except OSError as exc:
        blockers.append(f"optimizer_output_manifest_unreadable:{type(exc).__name__}")
        return base
    if not isinstance(payload, Mapping):
        blockers.append("optimizer_output_manifest_not_object")
        return base
    base.update(
        {
            "manifest_valid": True,
            "manifest_sha256": _sha256_file(manifest_path),
            "manifest_schema_version": payload.get("schema_version"),
            "manifest_kind": "dspy_gepa_optimizer_output_manifest",
        }
    )
    base["readiness"] = {
        "status": "optimizer_output_hash_bound_not_candidate",
        "ready_for_future_candidate_materializer": True,
        "blockers": [
            "no_program_candidate_assembly_materializer_in_this_command",
            "candidate_field_remains_null_until_explicit_materializer_lands",
        ],
    }
    return base


def _base_result(
    *, manifest_path: Path, manifest: Mapping[str, Any], evidence: Mapping[str, Any]
) -> dict[str, Any]:
    train_records = list(evidence.get("train_records") or [])
    validation_records = list(evidence.get("validation_records") or [])
    return {
        "schema_version": PROGRAM_REFINEMENT_GEPA_RESULT_SCHEMA,
        "status": "degraded",
        "created_from": dict(evidence["created_from"]),
        "source_identity": _identity_from_manifest(manifest),
        "evidence_inputs": {
            "source": evidence.get("source"),
            "train_examples_count": len(train_records),
            "validation_examples_count": len(validation_records),
            "held_out_validation": evidence.get("held_out_validation") is True,
            "limitations": list(evidence.get("limitations") or []),
        },
        "gepa": {
            "attempted": False,
            "status": "skipped",
            "metric": None,
            "max_metric_calls": None,
            "notes": [],
        },
        "candidate": None,
        "lineage": {
            "source_identity": _identity_from_manifest(manifest),
            "refinement_kind": "gepa",
            "authority": "local_gepa_refinement_lineage_only_non_authoritative",
        },
        "effect": {
            "local_gepa_candidate_generated": False,
            **_GEPA_EFFECT_BASE,
        },
        "non_authority": dict(_GEPA_NON_AUTHORITY),
        "notes": [
            "This is a local GEPA refinement attempt sidecar only.",
            "It does not rank, select a winner, promote, export authority, or mutate governance.",
            f"Source manifest was read from {manifest_path}.",
        ],
    }


def build_program_refinement_gepa_result(
    *,
    manifest_path: Path,
    outdir: Path,
    train_path: Path | None = None,
    validation_path: Path | None = None,
    metric: str | None = None,
    max_metric_calls: int = 2,
    result_out: Path | None = None,
) -> dict[str, Any]:
    """Run a bounded local GEPA attempt for an existing program candidate manifest.

    The current DSPx GEPA optimizer can produce a loadable DSPy optimizer output,
    but it does not yet materialize a new ``program-candidate-assembly-v1``. This
    service records that truth explicitly: GEPA may be attempted, while the
    candidate field remains null until a real candidate-assembly materializer lands.
    """

    manifest_path = manifest_path.expanduser().resolve()
    outdir = outdir.expanduser().resolve()
    manifest = load_program_manifest(manifest_path)
    _preflight_gepa_output_paths(
        manifest=manifest,
        manifest_path=manifest_path,
        outdir=outdir,
        result_out=result_out,
    )
    input_fields, output_fields = _intent_fields(manifest)
    evidence = _select_evidence_inputs(
        manifest=manifest,
        manifest_path=manifest_path,
        input_fields=input_fields,
        output_fields=output_fields,
        train_path=train_path,
        validation_path=validation_path,
    )
    result = _base_result(
        manifest_path=manifest_path, manifest=manifest, evidence=evidence
    )
    declared_metric, optimizer_metric = _metric_for_gepa(metric, manifest)
    result["gepa"].update(
        {
            "metric": declared_metric,
            "optimizer_metric": optimizer_metric,
            "max_metric_calls": int(max_metric_calls),
        }
    )

    train_records = list(evidence.get("train_records") or [])
    validation_records = list(evidence.get("validation_records") or [])
    if not train_records:
        result["status"] = "insufficient_behavior_evidence"
        result["gepa"].update(
            {
                "attempted": False,
                "status": "insufficient_behavior_evidence",
                "reason": "GEPA requires at least one train example from explicit files, manifest splits, or inline examples.",
            }
        )
        return result

    input_dir = outdir / "_gepa_inputs"
    train_csv = input_dir / "train.csv"
    validation_csv = input_dir / "validation.csv"
    _write_optimizer_csv(
        train_csv, train_records, input_fields=input_fields, output_fields=output_fields
    )
    val_csv: Path | None = None
    if validation_records:
        val_csv = validation_csv
        _write_optimizer_csv(
            validation_csv,
            validation_records,
            input_fields=input_fields,
            output_fields=output_fields,
        )
    else:
        result["evidence_inputs"]["limitations"].append(
            "No validation examples were available; GEPA was run without a validation set."
        )

    program_path = _program_path(manifest, manifest_path)
    result["gepa"]["attempted"] = True
    result["gepa"]["prepared_inputs"] = {
        "train_csv_path": str(train_csv),
        "train_csv_sha256": _sha256_file(train_csv),
        "validation_csv_path": str(val_csv) if val_csv is not None else None,
        "validation_csv_sha256": _sha256_file(val_csv) if val_csv is not None else None,
    }
    try:
        gepa_result = run_gepa_optimize(
            program_path=program_path,
            train_path=train_csv,
            val_path=val_csv,
            out_dir=outdir,
            input_keys=input_fields,
            output_keys=output_fields,
            auto=None,
            max_metric_calls=int(max_metric_calls),
            metric=optimizer_metric,
            seed=0,
        )
    except Exception as exc:
        result["status"] = "gepa_unavailable_for_program_candidate"
        result["gepa"].update(
            {
                "status": "degraded",
                "reason": str(exc),
                "error_type": type(exc).__name__,
                "notes": [
                    "GEPA was attempted but did not complete safely for this program candidate shape.",
                    "No program-candidate-assembly-v1 was materialized.",
                ],
            }
        )
        return result

    result["status"] = "degraded"
    result["gepa"].update(
        {
            "status": "completed",
            "input_keys": list(gepa_result.input_keys),
            "output_keys": list(gepa_result.output_keys),
            "chosen_output_keys": list(gepa_result.chosen_output_keys),
            "output_weights": dict(gepa_result.output_weights),
            "student_provider": gepa_result.student_provider,
            "reflection_provider": gepa_result.reflection_provider,
            "notes": [
                "GEPA completed and wrote a local DSPy optimizer output.",
                "The existing optimizer output is not a program-candidate-assembly-v1 manifest, so no refinement candidate is claimed.",
            ],
        }
    )
    gepa_output = _classify_gepa_output(outdir)
    result["gepa_output"] = gepa_output
    if gepa_output["readiness"]["ready_for_future_candidate_materializer"] is not True:
        result["status"] = "gepa_output_unverified"
        result["gepa"]["notes"].append(
            "GEPA completed, but the optimizer output manifest is not hash-bound for future candidate materialization."
        )
    result["effect"]["local_gepa_candidate_generated"] = False
    return result


def write_program_refinement_gepa_result(
    result: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    """Write the local GEPA refinement result sidecar."""

    out_path = out_path.expanduser().resolve()
    payload = dict(result)
    created_from = _safe_mapping(payload.get("created_from"))
    manifest_text = str(created_from.get("manifest_path") or "").strip()
    gepa_output = _safe_mapping(payload.get("gepa_output"))
    output_text = str(gepa_output.get("root_path") or "").strip()
    if manifest_text and output_text:
        manifest_path = Path(manifest_text).expanduser().resolve()
        manifest = load_program_manifest(manifest_path)
        _preflight_gepa_output_paths(
            manifest=manifest,
            manifest_path=manifest_path,
            outdir=Path(output_text),
            result_out=out_path,
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_json_text(payload), encoding="utf-8")
    return payload
