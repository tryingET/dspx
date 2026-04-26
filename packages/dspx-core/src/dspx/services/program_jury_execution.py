from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_refinement import (
    ProgramRefinementError,
    load_program_behavior_results,
    load_program_manifest,
)

PROGRAM_JURY_RESULTS_SCHEMA = "program-jury-results-v1"
PROGRAM_JURY_SCHEMA = "program-jury-v1"
PROGRAM_JURY_SELECTION_SCHEMA = "program-jury-selection-v1"
PROGRAM_JURY_RUBRIC_SCHEMA = "program-jury-rubric-v1"
PROGRAM_BEHAVIOR_RESULTS_SCHEMA = "program-behavior-results-v1"

_JUDGMENT_LABELS = (
    "supports_promotion",
    "withhold",
    "reject",
    "needs_more_evidence",
)

_RESULT_EFFECT = {
    "local_jury_evidence_only": True,
    "program_files_mutated": False,
    "promotion_review_mutated": False,
    "new_candidate_generated": False,
    "oracle_index_mutated": False,
    "external_authority_mutated": False,
    "governance_mutated": False,
}

_RESULT_NON_AUTHORITY = {
    "local_jury_evidence_only": True,
    "automatic_promotion": False,
    "winner_selection": False,
    "candidate_ranking": False,
    "oracle_ranking": False,
    "oracle_pruning": False,
    "oracle_promotion": False,
    "promotion_authority": False,
    "governance_authority": False,
    "external_mutation": False,
}


class ProgramJuryExecutionError(ValueError):
    """Raised when local program jury execution inputs are malformed."""


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramJuryExecutionError(f"{label} not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramJuryExecutionError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramJuryExecutionError(f"{label} must contain a JSON object: {source}")
    return payload


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


def _safe_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return int(text)
        except ValueError:
            return default
    return default


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


def _surface_path(
    manifest: Mapping[str, Any], manifest_path: Path, *, kind: str, default: str
) -> Path:
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    for raw_surface in _safe_list(candidate_assembly.get("surfaces")):
        if not isinstance(raw_surface, Mapping) or raw_surface.get("kind") != kind:
            continue
        raw_path = _first_text(raw_surface.get("path"))
        if raw_path:
            path = Path(raw_path)
            if not path.is_absolute():
                path = _manifest_root(manifest_path) / path
            return path
    return _manifest_root(manifest_path) / default


def _surface_hash(manifest: Mapping[str, Any], *, kind: str) -> str | None:
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    for raw_surface in _safe_list(candidate_assembly.get("surfaces")):
        if not isinstance(raw_surface, Mapping) or raw_surface.get("kind") != kind:
            continue
        return _first_text(raw_surface.get("content_hash"))
    return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_schema(
    payload: Mapping[str, Any], *, label: str, expected_schema: str
) -> None:
    if payload.get("schema_version") != expected_schema:
        raise ProgramJuryExecutionError(
            f"{label} schema_version must be {expected_schema}"
        )


def _validate_declared_hash(
    path: Path, manifest: Mapping[str, Any], *, kind: str, label: str
) -> None:
    declared_hash = _surface_hash(manifest, kind=kind)
    if declared_hash is None:
        return
    actual_hash = _sha256_file(path)
    if actual_hash != declared_hash:
        raise ProgramJuryExecutionError(
            f"{label} hash does not match manifest candidate_assembly surface declaration"
        )


def _load_jury_artifacts(
    manifest: Mapping[str, Any], manifest_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Path]]:
    paths = {
        "jury_path": _surface_path(
            manifest, manifest_path, kind="jury", default="jury.json"
        ),
        "jury_selection_path": _surface_path(
            manifest,
            manifest_path,
            kind="jury_selection",
            default="jury_selection.json",
        ),
        "jury_rubric_path": _surface_path(
            manifest,
            manifest_path,
            kind="jury_rubric",
            default="jury_rubric.json",
        ),
    }
    jury = _load_json_object(paths["jury_path"], label="program jury")
    selection = _load_json_object(
        paths["jury_selection_path"], label="program jury selection"
    )
    rubric = _load_json_object(paths["jury_rubric_path"], label="program jury rubric")
    _validate_schema(jury, label="program jury", expected_schema=PROGRAM_JURY_SCHEMA)
    _validate_schema(
        selection,
        label="program jury selection",
        expected_schema=PROGRAM_JURY_SELECTION_SCHEMA,
    )
    _validate_schema(
        rubric, label="program jury rubric", expected_schema=PROGRAM_JURY_RUBRIC_SCHEMA
    )
    _validate_declared_hash(
        paths["jury_path"], manifest, kind="jury", label="program jury"
    )
    _validate_declared_hash(
        paths["jury_selection_path"],
        manifest,
        kind="jury_selection",
        label="program jury selection",
    )
    _validate_declared_hash(
        paths["jury_rubric_path"],
        manifest,
        kind="jury_rubric",
        label="program jury rubric",
    )
    return jury, selection, rubric, paths


def _status_counts(behavior: Mapping[str, Any] | None) -> dict[str, int]:
    if behavior is None:
        return {}
    summary = _safe_mapping(behavior.get("summary"))
    raw_counts = summary.get("status_counts")
    if isinstance(raw_counts, Mapping):
        return {str(key): _safe_int(value) for key, value in sorted(raw_counts.items())}
    counts: dict[str, int] = {}
    for raw_record in _safe_list(behavior.get("examples")):
        if not isinstance(raw_record, Mapping):
            continue
        status = str(raw_record.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {status: counts[status] for status in sorted(counts)}


def _behavior_summary(behavior: Mapping[str, Any] | None) -> dict[str, Any]:
    if behavior is None:
        return {
            "present": False,
            "schema_version": None,
            "behavior_status": "insufficient_behavior_evidence",
            "example_count": 0,
            "status_counts": {},
        }
    summary = _safe_mapping(behavior.get("summary"))
    return {
        "present": True,
        "schema_version": behavior.get("schema_version"),
        "behavior_status": str(summary.get("status") or "unknown"),
        "example_count": _safe_int(summary.get("total")),
        "status_counts": _status_counts(behavior),
    }


def _behavior_failure_signals(behavior: Mapping[str, Any] | None) -> list[str]:
    if behavior is None:
        return []
    output_fields = _string_list(behavior.get("output_fields"))
    signals: list[str] = []
    for raw_record in _safe_list(behavior.get("examples")):
        if not isinstance(raw_record, Mapping):
            continue
        status = str(raw_record.get("status") or "unknown")
        if status == "passed":
            continue
        if status == "error":
            error = _safe_mapping(raw_record.get("error"))
            signals.append(f"error:{error.get('type') or 'unknown'}")
        elif status.startswith("degraded"):
            signals.append(status)
        else:
            signals.append(status)
        expected = _safe_mapping(raw_record.get("expected_outputs"))
        observed = _safe_mapping(raw_record.get("observed_outputs"))
        for field in output_fields:
            if (
                field in expected
                and field in observed
                and str(expected[field]) != str(observed[field])
            ):
                signals.append(f"mismatch:{field}")
            if field not in observed and status != "error":
                signals.append(f"missing_observed:{field}")
    unique: list[str] = []
    for signal in signals:
        if signal not in unique:
            unique.append(signal)
    return unique


def _rubric_by_juror(rubric: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rubrics: dict[str, dict[str, Any]] = {}
    for raw_item in _safe_list(rubric.get("juror_rubrics")):
        if not isinstance(raw_item, Mapping):
            continue
        juror_id = _first_text(raw_item.get("juror_id"))
        if juror_id:
            rubrics[juror_id] = dict(raw_item)
    return rubrics


def _judgment_for_behavior(behavior: Mapping[str, Any] | None) -> tuple[str, str, str]:
    if behavior is None:
        return (
            "needs_more_evidence",
            "low",
            "Unable to judge because behavior_results.json is not present for this candidate.",
        )
    summary = _safe_mapping(behavior.get("summary"))
    status = str(summary.get("status") or "unknown")
    if status == "passed":
        return (
            "withhold",
            "low",
            "Current example-backed behavior passed, but this local deterministic jury slice does not treat that as promotion approval.",
        )
    if status in {"failed", "error"} or status.startswith("degraded"):
        return (
            "needs_more_evidence",
            "low",
            "Current example-backed behavior did not establish enough reliable evidence for promotion review.",
        )
    return (
        "needs_more_evidence",
        "low",
        "Current example-backed behavior is limited and requires more evidence before adjudicator review.",
    )


def _criterion_results(
    *, juror_rubric: Mapping[str, Any], behavior: Mapping[str, Any] | None
) -> list[dict[str, Any]]:
    criteria = _string_list(juror_rubric.get("criteria")) or ["behavior_evidence"]
    behavior_status = _behavior_summary(behavior)["behavior_status"]
    signals = _behavior_failure_signals(behavior)
    results: list[dict[str, Any]] = []
    for criterion in criteria:
        if behavior is None:
            status = "unable_to_judge"
            rationale = (
                "No behavior_results.json evidence is available for this criterion."
            )
        elif behavior_status == "passed":
            status = "partially_satisfied"
            rationale = "Available eval_examples.py evidence passed, but the evidence slice is still narrow."
        elif signals:
            status = "not_satisfied"
            rationale = (
                "Observed behavior evidence includes: " + ", ".join(signals[:5]) + "."
            )
        else:
            status = "needs_more_evidence"
            rationale = (
                "Available behavior evidence is insufficient for this criterion."
            )
        results.append(
            {
                "criterion": criterion,
                "status": status,
                "rationale": rationale,
            }
        )
    return results


def _juror_results(
    *,
    selection: Mapping[str, Any],
    rubric: Mapping[str, Any],
    behavior: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    rubrics = _rubric_by_juror(rubric)
    judgment, confidence, base_rationale = _judgment_for_behavior(behavior)
    status = "judged" if behavior is not None else "unable_to_judge"
    evidence_refs = ["behavior_results.json"] if behavior is not None else []
    results: list[dict[str, Any]] = []
    for raw_juror in _safe_list(selection.get("selected_jurors")):
        if not isinstance(raw_juror, Mapping):
            continue
        juror = dict(raw_juror)
        juror_id = str(juror.get("id") or "juror")
        perspective = str(juror.get("perspective") or "unspecified")
        juror_rubric = rubrics.get(juror_id, {"criteria": []})
        results.append(
            {
                "juror_id": juror_id,
                "perspective": perspective,
                "provider": str(juror.get("provider") or "stub"),
                "model": str(juror.get("model") or "stub"),
                "execution_mode": "local_deterministic",
                "status": status,
                "judgment": judgment,
                "confidence": confidence,
                "rationale": base_rationale,
                "evidence_refs": list(evidence_refs),
                "criteria_results": _criterion_results(
                    juror_rubric=juror_rubric,
                    behavior=behavior,
                ),
            }
        )
    return results


def _aggregate(
    juror_results: list[dict[str, Any]], *, behavior_present: bool
) -> dict[str, Any]:
    counts = {label: 0 for label in _JUDGMENT_LABELS}
    for result in juror_results:
        judgment = str(result.get("judgment") or "needs_more_evidence")
        if judgment not in counts:
            counts[judgment] = 0
        counts[judgment] += 1
    nonzero = [label for label, count in counts.items() if count]
    disagreement_present = len(nonzero) > 1
    if not juror_results:
        agreement_level = "none"
    elif disagreement_present:
        agreement_level = "mixed"
    else:
        agreement_level = "high"
    if not behavior_present:
        status = "insufficient_behavior_evidence"
        summary = "Jurors could not judge because behavior_results.json is missing."
    elif counts.get("needs_more_evidence", 0) == len(juror_results):
        status = "completed"
        summary = "All jurors request more evidence based on current example-backed behavior_results.json."
    elif counts.get("withhold", 0) == len(juror_results):
        status = "completed"
        summary = "All jurors withhold on the narrow current evidence; this is not promotion approval."
    else:
        status = "completed"
        summary = "Jurors produced mixed local judgments; review the disagreement details before any adjudicator decision."
    return {
        "status": status,
        "judgment_counts": counts,
        "agreement_level": agreement_level,
        "disagreement_present": disagreement_present,
        "summary": summary,
    }


def build_program_jury_execution_result(*, manifest_path: Path) -> dict[str, Any]:
    """Build a local deterministic jury result sidecar from an existing assembly."""

    manifest_path = manifest_path.expanduser().resolve()
    try:
        manifest = load_program_manifest(manifest_path)
        behavior, behavior_path, _behavior_hash = load_program_behavior_results(
            manifest,
            manifest_path,
        )
    except ProgramRefinementError as exc:
        raise ProgramJuryExecutionError(str(exc)) from exc
    jury, selection, rubric, jury_paths = _load_jury_artifacts(manifest, manifest_path)
    if behavior is not None:
        _validate_schema(
            behavior,
            label="program behavior results",
            expected_schema=PROGRAM_BEHAVIOR_RESULTS_SCHEMA,
        )
    identity = _identity_from_manifest(manifest)
    behavior_summary = _behavior_summary(behavior)
    juror_results = _juror_results(
        selection=selection,
        rubric=rubric,
        behavior=behavior,
    )
    aggregate = _aggregate(
        juror_results,
        behavior_present=behavior_summary["present"] is True,
    )
    status = (
        "executed"
        if behavior_summary["present"] is True
        else "insufficient_behavior_evidence"
    )
    limits = [
        "Jury execution is limited to current eval_examples.py / behavior_results.json evidence.",
        "No dataset split was run by this command.",
        "Jury results are not promotion approval.",
        "Jury results do not rank or select a winner.",
    ]
    if behavior is None:
        limits.insert(0, "No behavior_results.json evidence was available to judge.")
    return {
        "schema_version": PROGRAM_JURY_RESULTS_SCHEMA,
        "status": status,
        "identity": identity,
        "created_from": {
            "manifest_path": str(manifest_path),
            "manifest_schema_version": manifest.get("schema_version"),
            "jury_path": str(jury_paths["jury_path"].resolve()),
            "jury_selection_path": str(jury_paths["jury_selection_path"].resolve()),
            "jury_rubric_path": str(jury_paths["jury_rubric_path"].resolve()),
            "behavior_results_path": str(behavior_path.resolve())
            if behavior_path is not None and behavior_path.exists()
            else None,
        },
        "jury": {
            "planned_jury_schema_version": jury.get("schema_version"),
            "selection_schema_version": selection.get("schema_version"),
            "rubric_schema_version": rubric.get("schema_version"),
            "selected_juror_count": _safe_int(selection.get("selected_juror_count")),
            "selected_perspectives": _string_list(
                selection.get("selected_perspectives")
            ),
            "execution_mode": "local_deterministic",
            "provider_backed_model_calls": False,
        },
        "behavior_evidence": behavior_summary,
        "juror_results": juror_results,
        "aggregate": aggregate,
        "interpretation": {
            "summary": "The jury results are local review evidence only.",
            "ready_for_promotion_decision": False,
            "limits": limits,
        },
        "effect": dict(_RESULT_EFFECT),
        "non_authority": dict(_RESULT_NON_AUTHORITY),
    }


def write_program_jury_execution_result(
    result: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    """Write the local jury result sidecar and return its payload."""

    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(result)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
