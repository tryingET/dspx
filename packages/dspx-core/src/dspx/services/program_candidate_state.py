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

PROGRAM_CANDIDATE_STATE_SCHEMA = "program-candidate-state-v1"
PROGRAM_MANIFEST_SCHEMA = "program-candidate-assembly-v1"
PROGRAM_ORACLE_REPORT_SCHEMA = "program-oracle-evidence-report-v1"
PROGRAM_REFINEMENT_PROPOSAL_SCHEMA = "program-refinement-proposal-v1"
PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA = "program-promotion-review-refined-v1"
PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA = "program-promotion-decision-record-v1"
PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA = (
    "program-refinement-candidate-comparison-v1"
)
PROGRAM_PROMOTION_PLAN_SCHEMA = "program-promotion-plan-v1"
PROGRAM_EXTERNAL_AUTHORITY_EXPORT_PREFLIGHT_SCHEMA = (
    "program-external-authority-export-preflight-v1"
)


class ProgramCandidateStateError(ValueError):
    """Raised when local program candidate state inputs are invalid."""


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramCandidateStateError(f"{label} not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramCandidateStateError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramCandidateStateError(f"{label} must contain a JSON object: {source}")
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


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _manifest_root(manifest_path: Path) -> Path:
    return manifest_path.expanduser().resolve().parent


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


def _identity_exactly_matches(
    actual: Mapping[str, Any], expected: Mapping[str, str | None]
) -> bool:
    if not actual:
        return False
    return all(
        expected_value is None or actual.get(key) == expected_value
        for key, expected_value in expected.items()
    )


def _identity_mismatch_keys(
    actual: Mapping[str, Any], expected: Mapping[str, str | None]
) -> list[str]:
    return [
        key
        for key, expected_value in expected.items()
        if expected_value is not None
        and actual.get(key) is not None
        and actual.get(key) != expected_value
    ]


def _assert_schema(payload: Mapping[str, Any], *, label: str, schema: str) -> None:
    if payload.get("schema_version") != schema:
        raise ProgramCandidateStateError(f"{label} schema_version must be {schema}")


def _optional_artifact_path(
    manifest: Mapping[str, Any], manifest_path: Path, *, artifact_key: str, default: str
) -> Path:
    artifact = _safe_mapping(manifest.get(artifact_key))
    raw_path = _first_text(artifact.get("path"), default)
    path = Path(raw_path or default)
    if not path.is_absolute():
        path = _manifest_root(manifest_path) / path
    return path


def _optional_hash(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return _sha256_file(path)


def _load_optional_artifact(
    path: Path | None, *, label: str, schema: str
) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    if path is None:
        return None, None, None
    source = path.expanduser().resolve()
    payload = _load_json_object(source, label=label)
    _assert_schema(payload, label=label, schema=schema)
    return payload, source, _sha256_file(source)


def _validate_non_authority_false(
    payload: Mapping[str, Any], *, label: str, keys: tuple[str, ...]
) -> None:
    non_authority = _safe_mapping(payload.get("non_authority"))
    invalid = [key for key in keys if non_authority.get(key) is not False]
    if invalid:
        raise ProgramCandidateStateError(
            f"{label} widens non-authority flags: " + ", ".join(invalid)
        )


def _validate_optional_inputs(
    *,
    candidate_identity: Mapping[str, str | None],
    source_identity: Mapping[str, str | None] | None,
    review: Mapping[str, Any] | None,
    decision: Mapping[str, Any] | None,
    comparison: Mapping[str, Any] | None,
    promotion_plan: Mapping[str, Any] | None,
    export_preflight: Mapping[str, Any] | None,
) -> None:
    source_or_candidate = [candidate_identity]
    if source_identity is not None:
        source_or_candidate.append(source_identity)

    if review is not None:
        _validate_non_authority_false(
            review,
            label="refined promotion review",
            keys=(
                "automatic_promotion",
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "program_mutation",
                "new_candidate_generation",
                "promotion_authority",
                "governance_authority",
                "external_mutation",
            ),
        )
        review_identity = _safe_mapping(review.get("identity"))
        if not any(_identity_exactly_matches(review_identity, item) for item in source_or_candidate):
            raise ProgramCandidateStateError(
                "refined promotion review identity does not match candidate/source identity: "
                + ", ".join(_identity_mismatch_keys(review_identity, candidate_identity))
            )

    if decision is not None:
        _validate_non_authority_false(
            decision,
            label="program promotion decision record",
            keys=(
                "automatic_promotion",
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "program_mutation",
                "refined_review_mutation",
                "new_candidate_generation",
                "governance_authority",
                "external_mutation",
            ),
        )
        decision_identity = _safe_mapping(decision.get("identity"))
        if not any(_identity_exactly_matches(decision_identity, item) for item in source_or_candidate):
            raise ProgramCandidateStateError(
                "program promotion decision record identity does not match candidate/source identity: "
                + ", ".join(_identity_mismatch_keys(decision_identity, candidate_identity))
            )

    if comparison is not None:
        _validate_non_authority_false(
            comparison,
            label="program candidate comparison",
            keys=(
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "winner_selection",
                "automatic_promotion",
                "program_mutation",
                "new_candidate_generation",
                "governance_authority",
                "external_mutation",
            ),
        )
        source_matches = _identity_exactly_matches(
            _safe_mapping(comparison.get("source_identity")), candidate_identity
        )
        candidate_matches = _identity_exactly_matches(
            _safe_mapping(comparison.get("candidate_identity")), candidate_identity
        )
        if not (source_matches or candidate_matches):
            raise ProgramCandidateStateError(
                "program candidate comparison must mention manifest identity as source or candidate"
            )

    if promotion_plan is not None:
        if promotion_plan.get("status") != "planned_not_applied":
            raise ProgramCandidateStateError(
                "program promotion plan must have status planned_not_applied"
            )
        if _safe_mapping(promotion_plan.get("eligibility")).get("allowed_for_apply") is not False:
            raise ProgramCandidateStateError(
                "program promotion plan must keep eligibility.allowed_for_apply false"
            )
        _validate_non_authority_false(
            promotion_plan,
            label="program promotion plan",
            keys=(
                "automatic_promotion",
                "apply_promotion",
                "external_authority_export",
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "winner_selection",
                "governance_authority",
                "external_mutation",
            ),
        )

    if export_preflight is not None:
        if export_preflight.get("status") not in {"ready_not_applied", "incomplete_preflight"}:
            raise ProgramCandidateStateError(
                "external authority export preflight status must be ready_not_applied or incomplete_preflight"
            )
        preflight = _safe_mapping(export_preflight.get("preflight"))
        if preflight.get("ready_for_future_apply") is not False:
            raise ProgramCandidateStateError(
                "external authority export preflight must keep ready_for_future_apply false"
            )
        if _safe_mapping(export_preflight.get("effect")).get("ak_called") is not False:
            raise ProgramCandidateStateError(
                "external authority export preflight must record ak_called false"
            )
        _validate_non_authority_false(
            export_preflight,
            label="external authority export preflight",
            keys=(
                "external_apply",
                "agent_kernel_mutation",
                "governance_authority",
                "promotion_authority",
                "oracle_authority",
                "winner_selection",
                "automatic_promotion",
            ),
        )
        preflight_identity = _safe_mapping(export_preflight.get("identity"))
        if not any(_identity_exactly_matches(preflight_identity, item) for item in source_or_candidate):
            raise ProgramCandidateStateError(
                "external authority export preflight identity does not match candidate/source identity"
            )


def _behavior_summary(
    behavior: Mapping[str, Any] | None, behavior_hash: str | None
) -> dict[str, Any]:
    if behavior is None:
        return {
            "present": False,
            "schema_version": None,
            "status": "insufficient_behavior_evidence",
            "example_count": 0,
            "status_counts": {},
            "sha256": None,
        }
    summary = _safe_mapping(behavior.get("summary"))
    return {
        "present": True,
        "schema_version": behavior.get("schema_version"),
        "status": str(summary.get("status") or "unknown"),
        "example_count": int(summary.get("total") or 0),
        "status_counts": _safe_mapping(summary.get("status_counts")),
        "sha256": behavior_hash,
    }


def _oracle_readability_summary(manifest: Mapping[str, Any], manifest_path: Path) -> dict[str, Any]:
    oracle = _safe_mapping(manifest.get("oracle_readability"))
    path_text = _first_text(oracle.get("path"))
    path = None
    if path_text is not None:
        path = Path(path_text)
        if not path.is_absolute():
            path = _manifest_root(manifest_path) / path
    return {
        "present": path is not None and path.exists(),
        "path": str(path) if path is not None else None,
        "schema_version": _safe_mapping(oracle.get("summary")).get("schema_version"),
        "sha256": _optional_hash(path),
        "oracle_invoked_by_program_gen": False,
        "authority": _safe_mapping(oracle.get("summary")).get("authority"),
    }


def _review_summary(review: Mapping[str, Any] | None) -> dict[str, Any]:
    if review is None:
        return {"present": False, "status": "missing"}
    readiness = _safe_mapping(review.get("review_readiness"))
    return {
        "present": True,
        "schema_version": review.get("schema_version"),
        "status": review.get("status"),
        "promotion_state": review.get("promotion_state"),
        "ready_for_adjudicator_review": readiness.get("ready_for_adjudicator_review") is True,
        "missing_required_evidence": _string_list(readiness.get("missing_required_evidence")),
    }


def _decision_summary(decision: Mapping[str, Any] | None) -> dict[str, Any]:
    if decision is None:
        return {"present": False, "status": "missing"}
    return {
        "present": True,
        "schema_version": decision.get("schema_version"),
        "status": decision.get("status"),
        "outcome": decision.get("outcome"),
        "promotion_state_after_decision": decision.get("promotion_state_after_decision"),
        "external_authority_exported": _safe_mapping(decision.get("decision_constraints")).get("external_authority_exported") is True,
    }


def _comparison_summary(
    comparison: Mapping[str, Any] | None, identity: Mapping[str, str | None]
) -> dict[str, Any]:
    if comparison is None:
        return {"present": False, "status": "missing"}
    role = "unrelated"
    if _identity_exactly_matches(_safe_mapping(comparison.get("source_identity")), identity):
        role = "source"
    elif _identity_exactly_matches(_safe_mapping(comparison.get("candidate_identity")), identity):
        role = "candidate"
    interpretation = _safe_mapping(comparison.get("interpretation"))
    return {
        "present": True,
        "schema_version": comparison.get("schema_version"),
        "status": comparison.get("status"),
        "manifest_role": role,
        "improvement_observed": interpretation.get("improvement_observed") is True,
        "needs_more_evidence": interpretation.get("needs_more_evidence") is True,
        "winner_selected": False,
    }


def _promotion_plan_summary(plan: Mapping[str, Any] | None) -> dict[str, Any]:
    if plan is None:
        return {"present": False, "status": "missing"}
    eligibility = _safe_mapping(plan.get("eligibility"))
    return {
        "present": True,
        "schema_version": plan.get("schema_version"),
        "status": plan.get("status"),
        "promotion_state": plan.get("promotion_state"),
        "target": _safe_mapping(plan.get("target")).get("kind"),
        "allowed_for_apply": eligibility.get("allowed_for_apply") is True,
        "missing_required_evidence": _string_list(eligibility.get("missing_required_evidence")),
    }


def _export_preflight_summary(preflight: Mapping[str, Any] | None) -> dict[str, Any]:
    if preflight is None:
        return {"present": False, "status": "missing"}
    preflight_block = _safe_mapping(preflight.get("preflight"))
    return {
        "present": True,
        "schema_version": preflight.get("schema_version"),
        "status": preflight.get("status"),
        "target": _safe_mapping(preflight.get("target")),
        "export_id": preflight.get("export_id"),
        "ready_for_future_apply": preflight_block.get("ready_for_future_apply") is True,
        "blocking_reasons": _string_list(preflight_block.get("blocking_reasons")),
        "ak_called": _safe_mapping(preflight.get("effect")).get("ak_called") is True,
        "external_authority_mutated": _safe_mapping(preflight.get("effect")).get("external_authority_mutated") is True,
    }


def _oracle_report_summary(report: Mapping[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {"present": False, "status": "missing"}
    return {
        "present": True,
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "total_records": int(report.get("total_records") or 0),
        "interpretation_only": _safe_mapping(report.get("non_authority")).get("oracle_interpretation_only") is True,
    }


def _proposal_summary(proposal: Mapping[str, Any] | None) -> dict[str, Any]:
    if proposal is None:
        return {"present": False, "status": "missing"}
    return {
        "present": True,
        "schema_version": proposal.get("schema_version"),
        "status": proposal.get("status"),
        "proposal_id": proposal.get("proposal_id"),
        "proposal_only": _safe_mapping(proposal.get("non_authority")).get("proposal_only") is True,
    }


def _overall_status(
    *,
    manifest: Mapping[str, Any],
    review: Mapping[str, Any] | None,
    decision: Mapping[str, Any] | None,
    promotion_plan: Mapping[str, Any] | None,
    export_preflight: Mapping[str, Any] | None,
) -> str:
    promotion_review = _safe_mapping(manifest.get("program_promotion_review"))
    if promotion_review.get("promotion_state") != "not_promoted":
        return "unexpected_promotion_state"
    if export_preflight is not None:
        return "not_promoted_external_preflighted_not_applied"
    if promotion_plan is not None:
        return "not_promoted_local_plan_present"
    if decision is not None:
        return "not_promoted_decision_recorded"
    if review is not None:
        return "not_promoted_reviewed"
    return "not_promoted_materialized"


def _required_next_steps(
    *,
    behavior: Mapping[str, Any] | None,
    review: Mapping[str, Any] | None,
    decision: Mapping[str, Any] | None,
    comparison: Mapping[str, Any] | None,
    export_preflight: Mapping[str, Any] | None,
) -> list[str]:
    steps: list[str] = []
    if behavior is None:
        steps.append("capture_behavior_evidence")
    if review is None:
        steps.append("build_refined_promotion_review")
    if decision is None:
        steps.append("record_local_adjudicator_decision")
    if comparison is None:
        steps.append("compare_candidate_behavior")
    if export_preflight is None:
        steps.append("build_external_authority_export_preflight")
    steps.extend(
        [
            "keep_promotion_not_applied",
            "future_apply_requires_exact_ak_target_contract",
            "future_apply_requires_external_duplicate_check",
            "future_apply_requires_apply_receipt",
            "future_apply_requires_rollback_failure_semantics",
        ]
    )
    unique: list[str] = []
    for step in steps:
        if step not in unique:
            unique.append(step)
    return unique


def _state_id(seed: Mapping[str, Any]) -> str:
    return "prog-cand-state-" + _sha256_payload(seed)[:16]


def build_program_candidate_state(
    *,
    manifest_path: Path,
    out_path: Path | None = None,
    source_manifest_path: Path | None = None,
    oracle_report_path: Path | None = None,
    refinement_proposal_path: Path | None = None,
    review_path: Path | None = None,
    decision_record_path: Path | None = None,
    comparison_path: Path | None = None,
    promotion_plan_path: Path | None = None,
    export_preflight_path: Path | None = None,
) -> dict[str, Any]:
    """Build one local truth-state artifact from existing program sidecars."""

    manifest_path = manifest_path.expanduser().resolve()
    try:
        manifest = load_program_manifest(manifest_path)
        behavior, behavior_path, behavior_hash = load_program_behavior_results(
            manifest,
            manifest_path,
        )
    except ProgramRefinementError as exc:
        raise ProgramCandidateStateError(str(exc)) from exc
    if manifest.get("schema_version") != PROGRAM_MANIFEST_SCHEMA:
        raise ProgramCandidateStateError(
            "program manifest schema_version must be " + PROGRAM_MANIFEST_SCHEMA
        )
    candidate_identity = _identity_from_manifest(manifest)
    source_manifest: dict[str, Any] | None = None
    source_identity: dict[str, str | None] | None = None
    source_manifest_hash: str | None = None
    source_manifest_resolved: Path | None = None
    if source_manifest_path is not None:
        source_manifest_resolved = source_manifest_path.expanduser().resolve()
        try:
            source_manifest = load_program_manifest(source_manifest_resolved)
        except ProgramRefinementError as exc:
            raise ProgramCandidateStateError(str(exc)) from exc
        source_identity = _identity_from_manifest(source_manifest)
        source_manifest_hash = _sha256_file(source_manifest_resolved)

    oracle_report, oracle_report_file, oracle_report_hash = _load_optional_artifact(
        oracle_report_path,
        label="program Oracle evidence report",
        schema=PROGRAM_ORACLE_REPORT_SCHEMA,
    )
    refinement_proposal, refinement_proposal_file, refinement_proposal_hash = (
        _load_optional_artifact(
            refinement_proposal_path,
            label="program refinement proposal",
            schema=PROGRAM_REFINEMENT_PROPOSAL_SCHEMA,
        )
    )
    review, review_file, review_hash = _load_optional_artifact(
        review_path,
        label="refined promotion review",
        schema=PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA,
    )
    decision, decision_file, decision_hash = _load_optional_artifact(
        decision_record_path,
        label="program promotion decision record",
        schema=PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA,
    )
    comparison, comparison_file, comparison_hash = _load_optional_artifact(
        comparison_path,
        label="program candidate comparison",
        schema=PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA,
    )
    promotion_plan, promotion_plan_file, promotion_plan_hash = _load_optional_artifact(
        promotion_plan_path,
        label="program promotion plan",
        schema=PROGRAM_PROMOTION_PLAN_SCHEMA,
    )
    export_preflight, export_preflight_file, export_preflight_hash = (
        _load_optional_artifact(
            export_preflight_path,
            label="external authority export preflight",
            schema=PROGRAM_EXTERNAL_AUTHORITY_EXPORT_PREFLIGHT_SCHEMA,
        )
    )

    _validate_optional_inputs(
        candidate_identity=candidate_identity,
        source_identity=source_identity,
        review=review,
        decision=decision,
        comparison=comparison,
        promotion_plan=promotion_plan,
        export_preflight=export_preflight,
    )

    manifest_hash = _sha256_file(manifest_path)
    execution_episode_path = _optional_artifact_path(
        manifest,
        manifest_path,
        artifact_key="execution_episode_artifact",
        default="execution_episode.json",
    )
    oracle_readability = _oracle_readability_summary(manifest, manifest_path)
    artifact_hashes = {
        "manifest_sha256": manifest_hash,
        "source_manifest_sha256": source_manifest_hash,
        "behavior_results_sha256": behavior_hash,
        "execution_episode_sha256": _optional_hash(execution_episode_path),
        "oracle_evidence_sha256": oracle_readability.get("sha256"),
        "oracle_report_sha256": oracle_report_hash,
        "refinement_proposal_sha256": refinement_proposal_hash,
        "review_sha256": review_hash,
        "decision_record_sha256": decision_hash,
        "comparison_sha256": comparison_hash,
        "promotion_plan_sha256": promotion_plan_hash,
        "export_preflight_sha256": export_preflight_hash,
    }
    state_seed = {
        "schema_version": PROGRAM_CANDIDATE_STATE_SCHEMA,
        "candidate_identity": candidate_identity,
        "artifact_hashes": {
            key: value for key, value in sorted(artifact_hashes.items()) if value
        },
    }
    state_id = _state_id(state_seed)
    status = _overall_status(
        manifest=manifest,
        review=review,
        decision=decision,
        promotion_plan=promotion_plan,
        export_preflight=export_preflight,
    )
    root_path = _safe_mapping(manifest.get("candidate_assembly")).get("root_path")
    payload = {
        "schema_version": PROGRAM_CANDIDATE_STATE_SCHEMA,
        "status": status,
        "state_id": state_id,
        "candidate_identity": candidate_identity,
        "source_identity": source_identity,
        "created_from": {
            "manifest_path": str(manifest_path),
            "manifest_schema_version": manifest.get("schema_version"),
            "source_manifest_path": str(source_manifest_resolved)
            if source_manifest_resolved is not None
            else None,
            "source_manifest_schema_version": source_manifest.get("schema_version")
            if source_manifest is not None
            else None,
            "behavior_results_path": str(behavior_path)
            if behavior_path is not None and behavior_path.exists()
            else None,
            "oracle_report_path": str(oracle_report_file)
            if oracle_report_file is not None
            else None,
            "refinement_proposal_path": str(refinement_proposal_file)
            if refinement_proposal_file is not None
            else None,
            "review_path": str(review_file) if review_file is not None else None,
            "decision_record_path": str(decision_file)
            if decision_file is not None
            else None,
            "comparison_path": str(comparison_file)
            if comparison_file is not None
            else None,
            "promotion_plan_path": str(promotion_plan_file)
            if promotion_plan_file is not None
            else None,
            "export_preflight_path": str(export_preflight_file)
            if export_preflight_file is not None
            else None,
        },
        "artifact_hashes": artifact_hashes,
        "candidate": {
            "root_path": root_path,
            "artifact_kind": _safe_mapping(manifest.get("candidate_assembly")).get("artifact_kind"),
            "assembly_status": _safe_mapping(manifest.get("candidate_assembly")).get("status"),
            "promotion_state": _safe_mapping(manifest.get("program_promotion_review")).get("promotion_state"),
            "candidate_status": _safe_mapping(manifest.get("program_promotion_review")).get("candidate_status"),
            "program_gen_source_command": _safe_mapping(manifest.get("request")).get("source_command"),
        },
        "evidence_state": {
            "behavior": _behavior_summary(behavior, behavior_hash),
            "execution_episode": {
                "present": execution_episode_path.exists(),
                "path": str(execution_episode_path),
                "sha256": _optional_hash(execution_episode_path),
                "schema_version": _safe_mapping(manifest.get("execution_episode_artifact")).get("schema_version"),
            },
            "oracle_readability": oracle_readability,
            "oracle_report": _oracle_report_summary(oracle_report),
            "refinement_proposal": _proposal_summary(refinement_proposal),
        },
        "promotion_state": {
            "review": _review_summary(review),
            "decision": _decision_summary(decision),
            "comparison": _comparison_summary(comparison, candidate_identity),
            "promotion_plan": _promotion_plan_summary(promotion_plan),
            "external_authority_export_preflight": _export_preflight_summary(
                export_preflight
            ),
        },
        "truth_summary": {
            "program_materialized": True,
            "behavior_evidence_present": behavior is not None,
            "oracle_report_present": oracle_report is not None,
            "review_present": review is not None,
            "decision_record_present": decision is not None,
            "comparison_present": comparison is not None,
            "promotion_plan_present": promotion_plan is not None,
            "external_authority_preflight_present": export_preflight is not None,
            "promotion_applied": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "ak_called": False,
            "winner_selected": False,
            "automatic_promotion": False,
            "ready_for_future_apply": False,
            "required_next_steps": _required_next_steps(
                behavior=behavior,
                review=review,
                decision=decision,
                comparison=comparison,
                export_preflight=export_preflight,
            ),
        },
        "effect": {
            "local_state_written": out_path is not None,
            "program_files_mutated": False,
            "sidecar_inputs_mutated": False,
            "oracle_index_mutated": False,
            "ak_called": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "promotion_state_changed": False,
        },
        "non_authority": {
            "state_summary_only": True,
            "preflight_only": True,
            "apply_promotion": False,
            "external_apply": False,
            "agent_kernel_mutation": False,
            "governance_authority": False,
            "promotion_authority": False,
            "oracle_authority": False,
            "winner_selection": False,
            "automatic_promotion": False,
        },
        "notes": [
            "This artifact summarizes local DSPx truth from existing artifacts only.",
            "It does not call AK, mutate external authority, mutate governance, select a winner, or promote a candidate.",
            "Future external apply requires an exact AK target contract, duplicate checks, an apply receipt, and rollback/failure semantics.",
        ],
    }
    return payload


def write_program_candidate_state(
    state: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Write the local candidate state sidecar."""

    target = out_path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    effect = _safe_mapping(payload.get("effect"))
    effect["local_state_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload
