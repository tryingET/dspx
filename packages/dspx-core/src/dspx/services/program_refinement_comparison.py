# summary: "Builds and revalidates non-authoritative source-versus-candidate comparisons over generated and optional runtime behavior evidence."
# read_when:
#   - "Changing refinement comparison deltas, runtime evidence rebinding, interpretation, lineage, or final-consumer validation."
from __future__ import annotations

from dspx.services.program_foundry_closure_reducers import (
    _safe_mapping as _safe_mapping,
    _safe_list as _safe_list,
    _string_list as _string_list,
    _first_text as _first_text,
    _identity_from_manifest as _identity_from_manifest,
    _output_fields as _output_fields,
    _behavior_examples as _behavior_examples,
    _failure_signals_from_behavior as _failure_signals_from_behavior,
    _safe_int as _safe_int,
    _status_counts as _status_counts,
    _runtime_artifact_hashes as _runtime_artifact_hashes,
    _runtime_summary as _runtime_summary,
    _episode_status_counts as _episode_status_counts,
    _failure_signals_from_episode as _failure_signals_from_episode,
    _behavior_summary as _behavior_summary,
    _failed_count as _failed_count,
    _count_for as _count_for,
    _behavior_delta as _behavior_delta,
    _interpretation as _interpretation,
)

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import prepare_sidecar_output_path
from dspx.services.program_runtime_episode import (
    load_validated_program_runtime_episode_bundle,
)

from dspx.services.program_foundry_provider_evidence import (
    PROVIDER_EVIDENCE_KIND_FIELD,
    provider_evidence_kind_from_behavior_results,
    weakest_provider_evidence_kind,
)
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
PROGRAM_BEHAVIOR_EPISODE_SCHEMA = "program-behavior-episode-v1"

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


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_recorded_path(raw_path: object, *, base_path: Path) -> Path | None:
    text = str(raw_path or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = base_path.parent / path
    return path.resolve()


def _manifest_root(manifest_path: Path) -> Path:
    return manifest_path.expanduser().resolve().parent


def _manifest_schema(manifest: Mapping[str, Any]) -> str | None:
    value = manifest.get("schema_version")
    return str(value) if value is not None else None


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
        raise ProgramRefinementComparisonError(
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
        raise ProgramRefinementComparisonError(
            "program behavior episode hash does not match manifest declaration(s): "
            + ", ".join(sorted(mismatches))
        )
    return episode, episode_path, actual_hash


def _load_validated_runtime_episode(
    runtime_episode_path: Path | None,
    *,
    manifest: Mapping[str, Any],
    manifest_path: Path,
    label: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, Path | None, str | None]:
    if runtime_episode_path is None:
        return None, None, None, None
    bundle = load_validated_program_runtime_episode_bundle(
        runtime_episode_path=runtime_episode_path,
        expected_manifest_path=manifest_path,
        expected_manifest=manifest,
        expected_manifest_sha256=_sha256_file(manifest_path),
        label=label,
        error_type=ProgramRefinementComparisonError,
    )
    return (
        bundle.runtime_episode,
        bundle.behavior_results,
        bundle.runtime_episode_path,
        bundle.runtime_episode_sha256,
    )


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


def build_program_refinement_candidate_comparison(
    *,
    source_manifest_path: Path,
    candidate_manifest_path: Path,
    refinement_proposal_path: Path | None = None,
    decision_record_path: Path | None = None,
    source_runtime_episode_path: Path | None = None,
    candidate_runtime_episode_path: Path | None = None,
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
    source_runtime_episode_path = (
        source_runtime_episode_path.expanduser().resolve()
        if source_runtime_episode_path is not None
        else None
    )
    candidate_runtime_episode_path = (
        candidate_runtime_episode_path.expanduser().resolve()
        if candidate_runtime_episode_path is not None
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
        source_episode, source_episode_path, source_episode_hash = (
            _load_program_behavior_episode(source_manifest, source_manifest_path)
        )
        candidate_episode, candidate_episode_path, candidate_episode_hash = (
            _load_program_behavior_episode(candidate_manifest, candidate_manifest_path)
        )
        (
            source_runtime_episode,
            source_runtime_behavior,
            source_runtime_episode_path,
            source_runtime_episode_hash,
        ) = _load_validated_runtime_episode(
            source_runtime_episode_path,
            manifest=source_manifest,
            manifest_path=source_manifest_path,
            label="source runtime episode",
        )
        (
            candidate_runtime_episode,
            candidate_runtime_behavior,
            candidate_runtime_episode_path,
            candidate_runtime_episode_hash,
        ) = _load_validated_runtime_episode(
            candidate_runtime_episode_path,
            manifest=candidate_manifest,
            manifest_path=candidate_manifest_path,
            label="candidate runtime episode",
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
        behavior_episode=source_episode,
    )
    candidate_summary = _behavior_summary(
        manifest=candidate_manifest,
        behavior=candidate_behavior,
        behavior_episode=candidate_episode,
    )
    source_runtime_summary = _runtime_summary(
        manifest=source_manifest,
        runtime_episode=source_runtime_episode,
        runtime_behavior=source_runtime_behavior,
    )
    candidate_runtime_summary = _runtime_summary(
        manifest=candidate_manifest,
        runtime_episode=candidate_runtime_episode,
        runtime_behavior=candidate_runtime_behavior,
    )
    delta = _behavior_delta(source_summary, candidate_summary)
    runtime_delta = _behavior_delta(source_runtime_summary, candidate_runtime_summary)
    runtime_compared = (
        source_runtime_summary["runtime_evidence_present"]
        and candidate_runtime_summary["runtime_evidence_present"]
    )
    generated_compared = (
        source_summary["behavior_evidence_present"]
        and candidate_summary["behavior_evidence_present"]
    )
    status = (
        "compared"
        if generated_compared or runtime_compared
        else "insufficient_behavior_evidence"
    )
    generated_interpretation = _interpretation(
        source_summary=source_summary,
        candidate_summary=candidate_summary,
        delta=delta,
    )
    runtime_interpretation = _interpretation(
        source_summary=source_runtime_summary,
        candidate_summary=candidate_runtime_summary,
        delta=runtime_delta,
    )
    evidence_conflict = (
        generated_compared
        and runtime_compared
        and (
            generated_interpretation.get("improvement_observed")
            != runtime_interpretation.get("improvement_observed")
            or generated_interpretation.get("needs_more_evidence")
            != runtime_interpretation.get("needs_more_evidence")
        )
    )
    if evidence_conflict:
        interpretation = {
            **generated_interpretation,
            "summary": "Generated behavior and runtime episode comparison evidence disagree; inspect runtime_evidence_comparison before planning.",
            "improvement_observed": False,
            "needs_more_evidence": True,
            "evidence_basis": "mixed_generated_and_runtime",
            "generated_evidence_compared": True,
            "runtime_evidence_compared": True,
            "evidence_conflict": True,
        }
    elif generated_compared or not runtime_compared:
        interpretation = {
            **generated_interpretation,
            "evidence_basis": "generated_behavior"
            if generated_compared
            else "insufficient_behavior_evidence",
            "generated_evidence_compared": generated_compared,
            "runtime_evidence_compared": runtime_compared,
            "evidence_conflict": False,
        }
    else:
        interpretation = {
            **runtime_interpretation,
            "evidence_basis": "runtime_episode",
            "generated_evidence_compared": False,
            "runtime_evidence_compared": True,
            "evidence_conflict": False,
        }
    provider_evidence_links = {
        "source_generated_behavior": provider_evidence_kind_from_behavior_results(
            source_behavior
        ),
        "candidate_generated_behavior": provider_evidence_kind_from_behavior_results(
            candidate_behavior
        ),
        "source_runtime_behavior": provider_evidence_kind_from_behavior_results(
            source_runtime_behavior
        ),
        "candidate_runtime_behavior": provider_evidence_kind_from_behavior_results(
            candidate_runtime_behavior
        ),
    }
    compared_links = [
        kind
        for name, kind in provider_evidence_links.items()
        if (name.endswith("generated_behavior") and generated_compared)
        or (name.endswith("runtime_behavior") and runtime_compared)
    ]
    provider_evidence_kind = (
        weakest_provider_evidence_kind(*compared_links) if compared_links else None
    )
    interpretation[PROVIDER_EVIDENCE_KIND_FIELD] = provider_evidence_kind
    interpretation["provider_evidence_links"] = provider_evidence_links
    runtime_interpretation[PROVIDER_EVIDENCE_KIND_FIELD] = (
        weakest_provider_evidence_kind(
            provider_evidence_links["source_runtime_behavior"],
            provider_evidence_links["candidate_runtime_behavior"],
        )
        if runtime_compared
        else None
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
            "source_manifest_hash": _sha256_file(source_manifest_path),
            "candidate_manifest_hash": _sha256_file(candidate_manifest_path),
            "source_behavior_results_path": str(source_behavior_path)
            if source_behavior_path is not None and source_behavior_path.exists()
            else None,
            "candidate_behavior_results_path": str(candidate_behavior_path)
            if candidate_behavior_path is not None and candidate_behavior_path.exists()
            else None,
            "source_behavior_results_hash": source_behavior_hash,
            "candidate_behavior_results_hash": candidate_behavior_hash,
            "source_behavior_episode_path": str(source_episode_path)
            if source_episode_path is not None and source_episode_path.exists()
            else None,
            "candidate_behavior_episode_path": str(candidate_episode_path)
            if candidate_episode_path is not None and candidate_episode_path.exists()
            else None,
            "source_behavior_episode_hash": source_episode_hash,
            "candidate_behavior_episode_hash": candidate_episode_hash,
            "source_runtime_episode_path": str(source_runtime_episode_path)
            if source_runtime_episode_path is not None
            else None,
            "candidate_runtime_episode_path": str(candidate_runtime_episode_path)
            if candidate_runtime_episode_path is not None
            else None,
            "source_runtime_episode_hash": source_runtime_episode_hash,
            "candidate_runtime_episode_hash": candidate_runtime_episode_hash,
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
        "runtime_evidence_comparison": {
            "source": source_runtime_summary,
            "candidate": candidate_runtime_summary,
            "delta": runtime_delta,
            "compared": runtime_compared,
            "interpretation": runtime_interpretation,
            "limits": [
                "Runtime episodes are already-produced local program-run evidence; comparison never reruns candidates.",
                "Runtime success, trace coverage, or Oracle-readable evidence is not promotion, activation, ranking, or owner acceptance.",
            ],
        },
        "interpretation": interpretation,
        "effect": dict(_COMPARISON_EFFECT),
        "non_authority": dict(_COMPARISON_NON_AUTHORITY),
    }


def _assert_comparison_identity_matches(
    actual: Mapping[str, Any], expected: Mapping[str, str | None], *, label: str
) -> None:
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if expected_value is None:
            if actual_value not in (None, ""):
                raise ProgramRefinementComparisonError(
                    f"{label} identity {key} mismatch: expected empty, got {actual_value!r}"
                )
            continue
        if str(actual_value or "") != str(expected_value):
            raise ProgramRefinementComparisonError(
                f"{label} identity {key} mismatch: expected {expected_value!r}, got {actual_value!r}"
            )


def _assert_recorded_hash(
    *, payload: Mapping[str, Any], key: str, current_hash: str | None
) -> None:
    recorded = payload.get(key)
    if current_hash is None:
        if recorded not in (None, ""):
            raise ProgramRefinementComparisonError(
                f"program candidate comparison {key} is present but current artifact is absent"
            )
        return
    if not isinstance(recorded, str) or not recorded.strip():
        raise ProgramRefinementComparisonError(
            f"program candidate comparison missing current artifact hash: {key}"
        )
    if recorded != current_hash:
        raise ProgramRefinementComparisonError(
            f"program candidate comparison stale artifact hash: {key}"
        )


def _assert_recorded_path_matches(
    *,
    payload: Mapping[str, Any],
    key: str,
    expected_path: Path | None,
    comparison_path: Path,
) -> None:
    recorded_path = _resolve_recorded_path(payload.get(key), base_path=comparison_path)
    if expected_path is None:
        if recorded_path is not None:
            raise ProgramRefinementComparisonError(
                f"program candidate comparison {key} is present but current artifact is absent"
            )
        return
    if recorded_path is None:
        raise ProgramRefinementComparisonError(
            f"program candidate comparison missing current artifact path: {key}"
        )
    if recorded_path != expected_path.expanduser().resolve():
        raise ProgramRefinementComparisonError(
            f"program candidate comparison stale artifact path: {key}"
        )


def _validate_recorded_runtime_episode(
    *,
    created_from: Mapping[str, Any],
    path_key: str,
    hash_key: str,
    manifest: Mapping[str, Any],
    manifest_path: Path,
    comparison_path: Path,
    label: str,
) -> None:
    runtime_path = _resolve_recorded_path(
        created_from.get(path_key), base_path=comparison_path
    )
    if runtime_path is None:
        _assert_recorded_hash(payload=created_from, key=hash_key, current_hash=None)
        return
    runtime_episode, _, _, runtime_hash = _load_validated_runtime_episode(
        runtime_path,
        manifest=manifest,
        manifest_path=manifest_path,
        label=label,
    )
    _ = runtime_episode
    _assert_recorded_hash(
        payload=created_from,
        key=hash_key,
        current_hash=runtime_hash,
    )


def _assert_current_view_matches(
    *,
    comparison: Mapping[str, Any],
    current_view: Mapping[str, Any],
    key: str,
) -> None:
    if _safe_mapping(comparison.get(key)) != _safe_mapping(current_view.get(key)):
        raise ProgramRefinementComparisonError(
            f"program candidate comparison {key} does not match current evidence"
        )


def validate_program_refinement_candidate_comparison_contract(
    *,
    comparison_path: Path,
    candidate_manifest_path: Path,
    source_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Validate a comparison sidecar against current manifests and evidence.

    This is a final-consumer guard for planning/workflow summaries: the sidecar
    schema and local-only flags are necessary but not sufficient. Consumers must
    also re-bind identities and recorded behavior evidence hashes to current
    files before treating the comparison as evidence.
    """

    comparison_path = comparison_path.expanduser().resolve()
    candidate_manifest_path = candidate_manifest_path.expanduser().resolve()
    comparison = _load_json_object(
        comparison_path, label="program candidate comparison"
    )
    if (
        comparison.get("schema_version")
        != PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA
    ):
        raise ProgramRefinementComparisonError(
            "program candidate comparison schema_version must be "
            + PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA
        )
    if comparison.get("status") not in {"compared", "insufficient_behavior_evidence"}:
        raise ProgramRefinementComparisonError(
            "program candidate comparison status must be compared or insufficient_behavior_evidence"
        )
    effect = _safe_mapping(comparison.get("effect"))
    if effect.get("local_comparison_only") is not True:
        raise ProgramRefinementComparisonError(
            "program candidate comparison must be local-comparison-only"
        )
    invalid_effect = [
        key
        for key in (
            "source_program_files_mutated",
            "candidate_program_files_mutated",
            "new_candidate_generated",
            "external_authority_mutated",
            "governance_mutated",
        )
        if effect.get(key) is not False
    ]
    if invalid_effect:
        raise ProgramRefinementComparisonError(
            "program candidate comparison widens effect flags: "
            + ", ".join(invalid_effect)
        )
    non_authority = _safe_mapping(comparison.get("non_authority"))
    if non_authority.get("local_comparison_only") is not True:
        raise ProgramRefinementComparisonError(
            "program candidate comparison must be local-only"
        )
    invalid_non_authority = [
        key
        for key in (
            "oracle_ranking",
            "oracle_pruning",
            "oracle_promotion",
            "winner_selection",
            "automatic_promotion",
            "program_mutation",
            "new_candidate_generation",
            "governance_authority",
            "external_mutation",
        )
        if non_authority.get(key) is not False
    ]
    if invalid_non_authority:
        raise ProgramRefinementComparisonError(
            "program candidate comparison widens non-authority flags: "
            + ", ".join(invalid_non_authority)
        )

    created_from = _safe_mapping(comparison.get("created_from"))
    recorded_candidate_manifest = _resolve_recorded_path(
        created_from.get("candidate_manifest_path"), base_path=comparison_path
    )
    if recorded_candidate_manifest is None:
        raise ProgramRefinementComparisonError(
            "program candidate comparison missing candidate_manifest_path"
        )
    if recorded_candidate_manifest != candidate_manifest_path:
        raise ProgramRefinementComparisonError(
            "program candidate comparison candidate_manifest_path does not match current candidate manifest"
        )
    recorded_source_manifest = _resolve_recorded_path(
        created_from.get("source_manifest_path"), base_path=comparison_path
    )
    if recorded_source_manifest is None:
        raise ProgramRefinementComparisonError(
            "program candidate comparison missing source_manifest_path"
        )
    if source_manifest_path is not None:
        source_manifest_path = source_manifest_path.expanduser().resolve()
        if recorded_source_manifest != source_manifest_path:
            raise ProgramRefinementComparisonError(
                "program candidate comparison source_manifest_path does not match current source manifest"
            )
    else:
        source_manifest_path = recorded_source_manifest

    source_manifest = load_program_manifest(source_manifest_path)
    candidate_manifest = load_program_manifest(candidate_manifest_path)
    if _manifest_schema(source_manifest) != "program-candidate-assembly-v1":
        raise ProgramRefinementComparisonError(
            "program candidate comparison source manifest schema_version must be program-candidate-assembly-v1"
        )
    if _manifest_schema(candidate_manifest) != "program-candidate-assembly-v1":
        raise ProgramRefinementComparisonError(
            "program candidate comparison candidate manifest schema_version must be program-candidate-assembly-v1"
        )
    _assert_comparison_identity_matches(
        _safe_mapping(comparison.get("source_identity")),
        _identity_from_manifest(source_manifest),
        label="program candidate comparison source",
    )
    _assert_comparison_identity_matches(
        _safe_mapping(comparison.get("candidate_identity")),
        _identity_from_manifest(candidate_manifest),
        label="program candidate comparison candidate",
    )

    _assert_recorded_hash(
        payload=created_from,
        key="source_manifest_hash",
        current_hash=_sha256_file(source_manifest_path),
    )
    _assert_recorded_hash(
        payload=created_from,
        key="candidate_manifest_hash",
        current_hash=_sha256_file(candidate_manifest_path),
    )
    source_behavior, source_behavior_path, source_behavior_hash = (
        load_program_behavior_results(source_manifest, source_manifest_path)
    )
    candidate_behavior, candidate_behavior_path, candidate_behavior_hash = (
        load_program_behavior_results(candidate_manifest, candidate_manifest_path)
    )
    _ = source_behavior, candidate_behavior
    source_episode, source_episode_path, source_episode_hash = (
        _load_program_behavior_episode(source_manifest, source_manifest_path)
    )
    candidate_episode, candidate_episode_path, candidate_episode_hash = (
        _load_program_behavior_episode(candidate_manifest, candidate_manifest_path)
    )
    _ = source_episode, candidate_episode
    _assert_recorded_path_matches(
        payload=created_from,
        key="source_behavior_results_path",
        expected_path=source_behavior_path
        if source_behavior_hash is not None
        else None,
        comparison_path=comparison_path,
    )
    _assert_recorded_path_matches(
        payload=created_from,
        key="candidate_behavior_results_path",
        expected_path=candidate_behavior_path
        if candidate_behavior_hash is not None
        else None,
        comparison_path=comparison_path,
    )
    _assert_recorded_path_matches(
        payload=created_from,
        key="source_behavior_episode_path",
        expected_path=source_episode_path if source_episode_hash is not None else None,
        comparison_path=comparison_path,
    )
    _assert_recorded_path_matches(
        payload=created_from,
        key="candidate_behavior_episode_path",
        expected_path=candidate_episode_path
        if candidate_episode_hash is not None
        else None,
        comparison_path=comparison_path,
    )
    _assert_recorded_hash(
        payload=created_from,
        key="source_behavior_results_hash",
        current_hash=source_behavior_hash,
    )
    _assert_recorded_hash(
        payload=created_from,
        key="candidate_behavior_results_hash",
        current_hash=candidate_behavior_hash,
    )
    _assert_recorded_hash(
        payload=created_from,
        key="source_behavior_episode_hash",
        current_hash=source_episode_hash,
    )
    _assert_recorded_hash(
        payload=created_from,
        key="candidate_behavior_episode_hash",
        current_hash=candidate_episode_hash,
    )
    _validate_recorded_runtime_episode(
        created_from=created_from,
        path_key="source_runtime_episode_path",
        hash_key="source_runtime_episode_hash",
        manifest=source_manifest,
        manifest_path=source_manifest_path,
        comparison_path=comparison_path,
        label="program candidate comparison source runtime episode",
    )
    _validate_recorded_runtime_episode(
        created_from=created_from,
        path_key="candidate_runtime_episode_path",
        hash_key="candidate_runtime_episode_hash",
        manifest=candidate_manifest,
        manifest_path=candidate_manifest_path,
        comparison_path=comparison_path,
        label="program candidate comparison candidate runtime episode",
    )
    current_view = build_program_refinement_candidate_comparison(
        source_manifest_path=source_manifest_path,
        candidate_manifest_path=candidate_manifest_path,
        source_runtime_episode_path=_resolve_recorded_path(
            created_from.get("source_runtime_episode_path"),
            base_path=comparison_path,
        ),
        candidate_runtime_episode_path=_resolve_recorded_path(
            created_from.get("candidate_runtime_episode_path"),
            base_path=comparison_path,
        ),
    )
    if comparison.get("status") != current_view.get("status"):
        raise ProgramRefinementComparisonError(
            "program candidate comparison status does not match current evidence"
        )
    _assert_current_view_matches(
        comparison=comparison,
        current_view=current_view,
        key="behavior_comparison",
    )
    _assert_current_view_matches(
        comparison=comparison,
        current_view=current_view,
        key="runtime_evidence_comparison",
    )
    _assert_current_view_matches(
        comparison=comparison,
        current_view=current_view,
        key="interpretation",
    )
    return current_view


def _comparison_protected_roots(payload: Mapping[str, Any]) -> list[Path]:
    roots: list[Path] = []
    created_from = payload.get("created_from")
    if not isinstance(created_from, Mapping):
        return roots
    for key in ("source_manifest_path", "candidate_manifest_path"):
        raw_path = created_from.get(key)
        if isinstance(raw_path, str) and raw_path.strip():
            roots.append(Path(raw_path).expanduser().resolve().parent)
    return roots


def write_program_refinement_candidate_comparison(
    comparison: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Write the local comparison sidecar and return its JSON payload."""

    payload = dict(comparison)
    out_path = prepare_sidecar_output_path(
        out_path,
        payload=payload,
        artifact_label="program refinement candidate comparison",
        payload_artifact_root_policy="forbid",
        extra_protected_roots=_comparison_protected_roots(payload),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
