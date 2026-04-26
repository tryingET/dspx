from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_refinement import (
    ProgramRefinementError,
    load_program_behavior_results,
    load_program_manifest,
)

PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA = (
    "program-refinement-candidate-comparison-v1"
)
PROGRAM_REFINEMENT_PROPOSAL_SCHEMA = "program-refinement-proposal-v1"
PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA = "program-promotion-decision-record-v1"

_COMPARISON_EFFECT = {
    "local_comparison_only": True,
    "source_program_files_mutated": False,
    "candidate_program_files_mutated": False,
    "new_candidate_generated": False,
    "external_authority_mutated": False,
    "governance_mutated": False,
}

_COMPARISON_NON_AUTHORITY = {
    "local_comparison_only": True,
    "oracle_ranking": False,
    "oracle_pruning": False,
    "oracle_promotion": False,
    "winner_selection": False,
    "automatic_promotion": False,
    "program_mutation": False,
    "new_candidate_generation": False,
    "governance_authority": False,
    "external_mutation": False,
}

_LIMITS = [
    "Comparison is limited to example-backed behavior_results.json from eval_examples.py.",
    "No model jury or dataset split was run.",
    "This comparison is not a promotion, ranking, or approval decision.",
]


class ProgramRefinementComparisonError(ValueError):
    """Raised when local refinement-candidate comparison inputs are invalid."""


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramRefinementComparisonError(f"{label} not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramRefinementComparisonError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramRefinementComparisonError(
            f"{label} must contain a JSON object: {source}"
        )
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


def _manifest_schema(manifest: Mapping[str, Any]) -> str | None:
    value = manifest.get("schema_version")
    return str(value) if value is not None else None


def _output_fields(
    manifest: Mapping[str, Any], behavior: Mapping[str, Any] | None
) -> list[str]:
    fields = _string_list(_safe_mapping(manifest.get("intent")).get("outputs"))
    if fields:
        return fields
    if behavior is not None:
        return _string_list(behavior.get("output_fields"))
    return []


def _behavior_examples(behavior: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if behavior is None:
        return []
    return [
        dict(item)
        for item in _safe_list(behavior.get("examples"))
        if isinstance(item, Mapping)
    ]


def _failure_signals_from_behavior(
    behavior: Mapping[str, Any] | None, *, output_fields: list[str]
) -> list[str]:
    signals: list[str] = []
    for record in _behavior_examples(behavior):
        status = str(record.get("status") or "unknown")
        expected = _safe_mapping(record.get("expected_outputs"))
        observed = _safe_mapping(record.get("observed_outputs"))
        if status == "error":
            error = _safe_mapping(record.get("error"))
            signals.append(f"error:{error.get('type') or 'unknown'}")
        if status.startswith("degraded"):
            signals.append(status)
        for field in output_fields:
            if (
                field in expected
                and field in observed
                and str(expected[field]) != str(observed[field])
            ):
                signals.append(f"mismatch:{field}")
            if field not in observed and status != "error":
                signals.append(f"missing_observed:{field}")
        for note in _string_list(record.get("notes")):
            if "output mismatch" in note:
                for field in output_fields:
                    if field in note:
                        signals.append(f"mismatch:{field}")
    unique: list[str] = []
    for signal in signals:
        if signal not in unique:
            unique.append(signal)
    return unique


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


def _status_counts(behavior: Mapping[str, Any] | None) -> dict[str, int]:
    summary = _safe_mapping(behavior.get("summary")) if behavior is not None else {}
    raw_counts = summary.get("status_counts")
    if isinstance(raw_counts, Mapping):
        return {str(key): _safe_int(value) for key, value in sorted(raw_counts.items())}
    counts: dict[str, int] = {}
    for record in _behavior_examples(behavior):
        status = str(record.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _behavior_summary(
    *, manifest: Mapping[str, Any], behavior: Mapping[str, Any] | None
) -> dict[str, Any]:
    if behavior is None:
        return {
            "behavior_results_present": False,
            "behavior_status": "insufficient_behavior_evidence",
            "example_count": 0,
            "status_counts": {},
            "failure_signals": [],
        }
    summary = _safe_mapping(behavior.get("summary"))
    output_fields = _output_fields(manifest, behavior)
    return {
        "behavior_results_present": True,
        "behavior_status": str(summary.get("status") or "unknown"),
        "example_count": _safe_int(
            summary.get("total"), default=len(_behavior_examples(behavior))
        ),
        "status_counts": _status_counts(behavior),
        "failure_signals": _failure_signals_from_behavior(
            behavior,
            output_fields=output_fields,
        ),
    }


def _failed_count(summary: Mapping[str, Any]) -> int:
    counts = _safe_mapping(summary.get("status_counts"))
    return _safe_int(counts.get("failed"))


def _count_for(summary: Mapping[str, Any], key: str) -> int:
    counts = _safe_mapping(summary.get("status_counts"))
    return _safe_int(counts.get(key))


def _behavior_delta(
    source_summary: Mapping[str, Any], candidate_summary: Mapping[str, Any]
) -> dict[str, Any]:
    source_signals = set(_string_list(source_summary.get("failure_signals")))
    candidate_signals = set(_string_list(candidate_summary.get("failure_signals")))
    source_failed = _failed_count(source_summary)
    candidate_failed = _failed_count(candidate_summary)
    source_error = _count_for(source_summary, "error")
    candidate_error = _count_for(candidate_summary, "error")
    source_degraded = sum(
        count
        for status, count in _safe_mapping(source_summary.get("status_counts")).items()
        if str(status).startswith("degraded")
    )
    candidate_degraded = sum(
        count
        for status, count in _safe_mapping(
            candidate_summary.get("status_counts")
        ).items()
        if str(status).startswith("degraded")
    )
    return {
        "source_failed_count": source_failed,
        "candidate_failed_count": candidate_failed,
        "failed_count_delta": candidate_failed - source_failed,
        "source_error_count": source_error,
        "candidate_error_count": candidate_error,
        "error_count_delta": candidate_error - source_error,
        "source_degraded_count": source_degraded,
        "candidate_degraded_count": candidate_degraded,
        "degraded_count_delta": candidate_degraded - source_degraded,
        "status_changed": source_summary.get("behavior_status")
        != candidate_summary.get("behavior_status"),
        "failure_signals_removed": sorted(source_signals - candidate_signals),
        "failure_signals_added": sorted(candidate_signals - source_signals),
        "failure_signals_persisted": sorted(source_signals & candidate_signals),
    }


def _candidate_lineage(candidate_manifest: Mapping[str, Any]) -> dict[str, Any]:
    intent = _safe_mapping(candidate_manifest.get("intent"))
    options = _safe_mapping(intent.get("options"))
    lineage = _safe_mapping(options.get("refinement_lineage"))
    if lineage.get("schema_version") != "program-refinement-candidate-lineage-v1":
        return {}
    return lineage


def _identity_matches(
    actual: Mapping[str, Any], expected: Mapping[str, str | None]
) -> bool:
    for key, expected_value in expected.items():
        if expected_value is not None and actual.get(key) != expected_value:
            return False
    return True


def _load_optional_proposal(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    proposal = _load_json_object(path, label="program refinement proposal")
    if proposal.get("schema_version") != PROGRAM_REFINEMENT_PROPOSAL_SCHEMA:
        raise ProgramRefinementComparisonError(
            "program refinement proposal schema_version must be "
            + PROGRAM_REFINEMENT_PROPOSAL_SCHEMA
        )
    return proposal


def _load_optional_decision(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    decision = _load_json_object(path, label="program promotion decision record")
    if decision.get("schema_version") != PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA:
        raise ProgramRefinementComparisonError(
            "program promotion decision record schema_version must be "
            + PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA
        )
    return decision


def _lineage_payload(
    *,
    source_identity: Mapping[str, str | None],
    candidate_manifest: Mapping[str, Any],
    refinement_proposal: Mapping[str, Any] | None,
    decision_record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    lineage = _candidate_lineage(candidate_manifest)
    candidate_declares_lineage = bool(lineage)
    lineage_source_identity = _safe_mapping(lineage.get("source_identity"))
    source_matches = (
        _identity_matches(lineage_source_identity, source_identity)
        if candidate_declares_lineage
        else None
    )
    proposal_id = _first_text(
        lineage.get("refinement_proposal_id"),
        _safe_mapping(refinement_proposal or {}).get("proposal_id"),
    )
    decision_outcome = _first_text(
        lineage.get("decision_outcome"),
        _safe_mapping(decision_record or {}).get("outcome"),
    )
    return {
        "candidate_declares_refinement_lineage": candidate_declares_lineage,
        "source_identity_matches_candidate_lineage": source_matches,
        "decision_outcome": decision_outcome,
        "refinement_proposal_id": proposal_id,
        "proposal_input_present": refinement_proposal is not None,
        "decision_record_input_present": decision_record is not None,
    }


def _interpretation(
    *,
    source_summary: Mapping[str, Any],
    candidate_summary: Mapping[str, Any],
    delta: Mapping[str, Any],
) -> dict[str, Any]:
    source_present = source_summary.get("behavior_results_present") is True
    candidate_present = candidate_summary.get("behavior_results_present") is True
    if not source_present or not candidate_present:
        summary = "Comparison has insufficient example-backed behavior evidence for one or both candidates."
        improvement_observed = False
        needs_more_evidence = True
    else:
        removed = _string_list(delta.get("failure_signals_removed"))
        added = _string_list(delta.get("failure_signals_added"))
        failed_delta = int(delta.get("failed_count_delta") or 0)
        error_delta = int(delta.get("error_count_delta") or 0)
        degraded_delta = int(delta.get("degraded_count_delta") or 0)
        improvement_observed = bool(removed) and failed_delta <= 0 and error_delta <= 0
        if failed_delta < 0 or error_delta < 0 or degraded_delta < 0:
            improvement_observed = True
        if improvement_observed:
            summary = "The second candidate removed or reduced at least one observed example-backed behavior signal."
        elif _string_list(delta.get("failure_signals_persisted")):
            summary = "The second candidate did not remove the observed example-backed failure signal."
        elif added:
            summary = "The second candidate introduced new example-backed failure signals without removing prior signals."
        else:
            summary = "The second candidate behavior status is unchanged on the available example-backed evidence."
        needs_more_evidence = not improvement_observed or bool(added)
    return {
        "summary": summary,
        "improvement_observed": improvement_observed,
        "needs_more_evidence": needs_more_evidence,
        "limits": list(_LIMITS),
    }


def build_program_refinement_candidate_comparison(
    *,
    source_manifest_path: Path,
    candidate_manifest_path: Path,
    refinement_proposal_path: Path | None = None,
    decision_record_path: Path | None = None,
) -> dict[str, Any]:
    """Compare two existing program candidate manifests without mutating candidates."""

    source_manifest_path = source_manifest_path.expanduser().resolve()
    candidate_manifest_path = candidate_manifest_path.expanduser().resolve()
    refinement_proposal_path = (
        refinement_proposal_path.expanduser().resolve()
        if refinement_proposal_path is not None
        else None
    )
    decision_record_path = (
        decision_record_path.expanduser().resolve()
        if decision_record_path is not None
        else None
    )
    try:
        source_manifest = load_program_manifest(source_manifest_path)
        candidate_manifest = load_program_manifest(candidate_manifest_path)
        source_behavior, source_behavior_path, source_behavior_hash = (
            load_program_behavior_results(source_manifest, source_manifest_path)
        )
        candidate_behavior, candidate_behavior_path, candidate_behavior_hash = (
            load_program_behavior_results(candidate_manifest, candidate_manifest_path)
        )
    except ProgramRefinementError as exc:
        raise ProgramRefinementComparisonError(str(exc)) from exc

    proposal = _load_optional_proposal(refinement_proposal_path)
    decision = _load_optional_decision(decision_record_path)
    source_identity = _identity_from_manifest(source_manifest)
    candidate_identity = _identity_from_manifest(candidate_manifest)
    source_summary = _behavior_summary(
        manifest=source_manifest,
        behavior=source_behavior,
    )
    candidate_summary = _behavior_summary(
        manifest=candidate_manifest,
        behavior=candidate_behavior,
    )
    delta = _behavior_delta(source_summary, candidate_summary)
    status = (
        "compared"
        if source_summary["behavior_results_present"]
        and candidate_summary["behavior_results_present"]
        else "insufficient_behavior_evidence"
    )
    return {
        "schema_version": PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA,
        "status": status,
        "source_identity": source_identity,
        "candidate_identity": candidate_identity,
        "created_from": {
            "source_manifest_path": str(source_manifest_path),
            "candidate_manifest_path": str(candidate_manifest_path),
            "source_manifest_schema_version": _manifest_schema(source_manifest),
            "candidate_manifest_schema_version": _manifest_schema(candidate_manifest),
            "source_behavior_results_path": str(source_behavior_path)
            if source_behavior_path is not None and source_behavior_path.exists()
            else None,
            "candidate_behavior_results_path": str(candidate_behavior_path)
            if candidate_behavior_path is not None and candidate_behavior_path.exists()
            else None,
            "source_behavior_results_hash": source_behavior_hash,
            "candidate_behavior_results_hash": candidate_behavior_hash,
            "refinement_proposal_path": str(refinement_proposal_path)
            if refinement_proposal_path is not None
            else None,
            "decision_record_path": str(decision_record_path)
            if decision_record_path is not None
            else None,
        },
        "lineage": _lineage_payload(
            source_identity=source_identity,
            candidate_manifest=candidate_manifest,
            refinement_proposal=proposal,
            decision_record=decision,
        ),
        "behavior_comparison": {
            "source": source_summary,
            "candidate": candidate_summary,
            "delta": delta,
        },
        "interpretation": _interpretation(
            source_summary=source_summary,
            candidate_summary=candidate_summary,
            delta=delta,
        ),
        "effect": dict(_COMPARISON_EFFECT),
        "non_authority": dict(_COMPARISON_NON_AUTHORITY),
    }


def write_program_refinement_candidate_comparison(
    comparison: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Write the local comparison sidecar and return its JSON payload."""

    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(comparison)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
