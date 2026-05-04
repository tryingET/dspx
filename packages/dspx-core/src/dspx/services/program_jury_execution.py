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
PROGRAM_BEHAVIOR_EPISODE_SCHEMA = "program-behavior-episode-v1"

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


def _declared_behavior_episode_path(
    manifest: Mapping[str, Any], manifest_path: Path
) -> Path | None:
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    behavior_orchestration = _safe_mapping(
        execution_episode.get("behavior_orchestration")
    )
    episode_path = _first_text(behavior_orchestration.get("result_artifact"))
    if episode_path is None:
        episode_artifact = _safe_mapping(manifest.get("behavior_episode_artifact"))
        episode_path = _first_text(episode_artifact.get("path"))
    if episode_path is None:
        candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
        for surface in _safe_list(candidate_assembly.get("surfaces")):
            if not isinstance(surface, Mapping):
                continue
            if surface.get("kind") == "behavior_episode":
                episode_path = _first_text(surface.get("path"))
                break
    if episode_path is None:
        request = _safe_mapping(manifest.get("request"))
        if request.get("behavior_episode_hash"):
            episode_path = "behavior_episode.json"
    if episode_path is None:
        return None
    path = Path(episode_path)
    if not path.is_absolute():
        path = _manifest_root(manifest_path) / path
    return path


def _declared_behavior_episode_hashes(manifest: Mapping[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    request = _safe_mapping(manifest.get("request"))
    request_hash = _first_text(request.get("behavior_episode_hash"))
    if request_hash:
        hashes["request.behavior_episode_hash"] = request_hash

    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    behavior_orchestration = _safe_mapping(
        execution_episode.get("behavior_orchestration")
    )
    orchestration_hash = _first_text(behavior_orchestration.get("result_hash"))
    if orchestration_hash:
        hashes["execution_episode.behavior_orchestration.result_hash"] = (
            orchestration_hash
        )

    episode_artifact = _safe_mapping(manifest.get("behavior_episode_artifact"))
    artifact_hash = _first_text(episode_artifact.get("content_hash"))
    if artifact_hash:
        hashes["manifest.behavior_episode_artifact.content_hash"] = artifact_hash

    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    evidence = _safe_mapping(receipt_bundle.get("evidence"))
    evidence_hash = _first_text(evidence.get("behavior_episode_hash"))
    if evidence_hash:
        hashes["receipt_bundle.evidence.behavior_episode_hash"] = evidence_hash

    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    for surface in _safe_list(candidate_assembly.get("surfaces")):
        if not isinstance(surface, Mapping):
            continue
        if surface.get("kind") == "behavior_episode":
            surface_hash = _first_text(surface.get("content_hash"))
            if surface_hash:
                hashes["candidate_assembly.surfaces.behavior_episode.content_hash"] = (
                    surface_hash
                )
    return hashes


def _load_program_behavior_episode(
    manifest: Mapping[str, Any], manifest_path: Path
) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    episode_path = _declared_behavior_episode_path(manifest, manifest_path)
    if episode_path is None or not episode_path.exists():
        return None, episode_path, None

    episode = _load_json_object(episode_path, label="program behavior episode")
    if episode.get("schema_version") != PROGRAM_BEHAVIOR_EPISODE_SCHEMA:
        raise ProgramJuryExecutionError(
            "program behavior episode schema_version must be "
            + PROGRAM_BEHAVIOR_EPISODE_SCHEMA
        )
    actual_hash = _sha256_file(episode_path)
    declared_hashes = _declared_behavior_episode_hashes(manifest)
    mismatches = [
        name
        for name, declared_hash in declared_hashes.items()
        if declared_hash != actual_hash
    ]
    if mismatches:
        raise ProgramJuryExecutionError(
            "program behavior episode hash does not match manifest declaration(s): "
            + ", ".join(sorted(mismatches))
        )
    return episode, episode_path, actual_hash


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


def _episode_status_counts(episode: Mapping[str, Any] | None) -> dict[str, int]:
    if episode is None:
        return {}
    summary = _safe_mapping(episode.get("summary"))
    raw_counts = summary.get("status_counts")
    if isinstance(raw_counts, Mapping):
        return {str(key): _safe_int(value) for key, value in sorted(raw_counts.items())}
    counts: dict[str, int] = {}
    for key in ("passed", "failed", "error", "degraded"):
        value = _safe_int(summary.get(key))
        if value:
            counts[key] = value
    return {key: counts[key] for key in sorted(counts)}


def _behavior_summary(
    behavior: Mapping[str, Any] | None,
    behavior_episode: Mapping[str, Any] | None,
) -> dict[str, Any]:
    episode_summary = _safe_mapping((behavior_episode or {}).get("summary"))
    if behavior is None and behavior_episode is None:
        return {
            "present": False,
            "schema_version": None,
            "behavior_status": "insufficient_behavior_evidence",
            "example_count": 0,
            "source_count": 0,
            "status_counts": {},
            "behavior_results_present": False,
            "behavior_episode_present": False,
            "behavior_evidence_kind": None,
        }
    if behavior is not None:
        summary = _safe_mapping(behavior.get("summary"))
        return {
            "present": True,
            "schema_version": behavior.get("schema_version"),
            "behavior_status": str(summary.get("status") or "unknown"),
            "example_count": _safe_int(summary.get("total")),
            "source_count": _safe_int(episode_summary.get("source_count"), default=1),
            "status_counts": _status_counts(behavior),
            "behavior_results_present": True,
            "behavior_episode_present": behavior_episode is not None,
            "behavior_evidence_kind": "behavior_results",
        }
    assert behavior_episode is not None
    return {
        "present": True,
        "schema_version": behavior_episode.get("schema_version"),
        "behavior_status": str(episode_summary.get("status") or "unknown"),
        "example_count": _safe_int(episode_summary.get("total")),
        "source_count": _safe_int(episode_summary.get("source_count")),
        "status_counts": _episode_status_counts(behavior_episode),
        "behavior_results_present": False,
        "behavior_episode_present": True,
        "behavior_evidence_kind": "behavior_episode",
    }


def _behavior_results_failure_signals(
    behavior: Mapping[str, Any] | None,
) -> list[str]:
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
    return _unique_strings(signals)


def _behavior_episode_failure_signals(
    behavior_episode: Mapping[str, Any] | None,
) -> list[str]:
    if behavior_episode is None:
        return []
    signals: list[str] = []
    for source in _safe_list(behavior_episode.get("sources")):
        if not isinstance(source, Mapping):
            continue
        source_label = _first_text(
            source.get("split"), source.get("source_kind"), "source"
        )
        summary = _safe_mapping(source.get("summary"))
        if _safe_int(summary.get("failed")):
            signals.append(f"failed:{source_label}")
        if _safe_int(summary.get("error")):
            signals.append(f"error:{source_label}")
        if _safe_int(summary.get("degraded")):
            signals.append(f"degraded:{source_label}")
        behavior_status = _first_text(source.get("behavior_status"))
        if behavior_status in {"failed", "error"} or str(behavior_status).startswith(
            "degraded"
        ):
            signals.append(f"source_status:{source_label}:{behavior_status}")
    return _unique_strings(signals)


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
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


def _evidence_label(behavior_summary: Mapping[str, Any]) -> str:
    kind = behavior_summary.get("behavior_evidence_kind")
    if kind == "behavior_results":
        return "example-backed behavior_results.json evidence"
    if kind == "behavior_episode":
        return "bounded behavior_episode.json evidence"
    return "behavior evidence"


def _judgment_for_behavior(
    behavior_summary: Mapping[str, Any],
) -> tuple[str, str, str]:
    if behavior_summary.get("present") is not True:
        return (
            "needs_more_evidence",
            "low",
            "Unable to judge because no behavior_results.json or behavior_episode.json evidence is present for this candidate.",
        )
    status = str(behavior_summary.get("behavior_status") or "unknown")
    evidence_label = _evidence_label(behavior_summary)
    if status == "passed":
        return (
            "withhold",
            "low",
            f"Current {evidence_label} passed, but this local deterministic jury slice does not treat that as promotion approval.",
        )
    if status in {"failed", "error"} or status.startswith("degraded"):
        return (
            "needs_more_evidence",
            "low",
            f"Current {evidence_label} did not establish enough reliable evidence for promotion review.",
        )
    return (
        "needs_more_evidence",
        "low",
        f"Current {evidence_label} is limited and requires more evidence before adjudicator review.",
    )


def _criterion_results(
    *,
    juror_rubric: Mapping[str, Any],
    behavior_summary: Mapping[str, Any],
    failure_signals: list[str],
) -> list[dict[str, Any]]:
    criteria = _string_list(juror_rubric.get("criteria")) or ["behavior_evidence"]
    behavior_status = str(behavior_summary.get("behavior_status") or "unknown")
    evidence_label = _evidence_label(behavior_summary)
    results: list[dict[str, Any]] = []
    for criterion in criteria:
        if behavior_summary.get("present") is not True:
            status = "unable_to_judge"
            rationale = "No behavior evidence is available for this criterion."
        elif behavior_status == "passed":
            status = "partially_satisfied"
            rationale = f"Available {evidence_label} passed, but the evidence slice is still narrow."
        elif failure_signals:
            status = "not_satisfied"
            rationale = (
                "Observed behavior evidence includes: "
                + ", ".join(failure_signals[:5])
                + "."
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
    behavior_summary: Mapping[str, Any],
    failure_signals: list[str],
    evidence_refs: list[str],
) -> list[dict[str, Any]]:
    rubrics = _rubric_by_juror(rubric)
    judgment, confidence, base_rationale = _judgment_for_behavior(behavior_summary)
    status = "judged" if behavior_summary.get("present") is True else "unable_to_judge"
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
                    behavior_summary=behavior_summary,
                    failure_signals=failure_signals,
                ),
            }
        )
    return results


def _aggregate(
    juror_results: list[dict[str, Any]], *, behavior_summary: Mapping[str, Any]
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
    if behavior_summary.get("present") is not True:
        status = "insufficient_behavior_evidence"
        summary = "Jurors could not judge because behavior_results.json and behavior_episode.json are missing."
    elif counts.get("needs_more_evidence", 0) == len(juror_results):
        status = "completed"
        summary = (
            "All jurors request more evidence based on current "
            + _evidence_label(behavior_summary)
            + "."
        )
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
        behavior_episode, behavior_episode_path, _behavior_episode_hash = (
            _load_program_behavior_episode(manifest, manifest_path)
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
    behavior_summary = _behavior_summary(behavior, behavior_episode)
    failure_signals = _behavior_results_failure_signals(behavior)
    if behavior is None:
        failure_signals = _behavior_episode_failure_signals(behavior_episode)
    evidence_refs = []
    if behavior is not None:
        evidence_refs.append("behavior_results.json")
    if behavior_episode is not None:
        evidence_refs.append("behavior_episode.json")
    juror_results = _juror_results(
        selection=selection,
        rubric=rubric,
        behavior_summary=behavior_summary,
        failure_signals=failure_signals,
        evidence_refs=evidence_refs,
    )
    aggregate = _aggregate(
        juror_results,
        behavior_summary=behavior_summary,
    )
    status = (
        "executed"
        if behavior_summary["present"] is True
        else "insufficient_behavior_evidence"
    )
    limits = [
        "Jury execution is limited to already-generated behavior_results.json and/or bounded behavior_episode.json evidence.",
        "No example, dataset split, model jury, Oracle, topology, or custom-module execution is run by this command.",
        "Jury results are not promotion approval.",
        "Jury results do not rank or select a winner.",
    ]
    if behavior is None and behavior_episode is None:
        limits.insert(
            0,
            "No behavior_results.json or behavior_episode.json evidence was available to judge.",
        )
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
            "behavior_episode_path": str(behavior_episode_path.resolve())
            if behavior_episode_path is not None and behavior_episode_path.exists()
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
