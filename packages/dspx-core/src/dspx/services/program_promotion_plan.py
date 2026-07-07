from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import prepare_sidecar_output_path
from dspx.services.program_refinement import (
    ProgramRefinementError,
    load_program_behavior_results,
    load_program_manifest,
)
from dspx.services.program_promotion_decision import (
    ProgramPromotionDecisionError,
    validate_program_promotion_decision_record_contract,
)
from dspx.services.program_refinement_comparison import (
    ProgramRefinementComparisonError,
    validate_program_refinement_candidate_comparison_contract,
)

PROGRAM_PROMOTION_PLAN_SCHEMA = "program-promotion-plan-v1"
PROGRAM_MANIFEST_SCHEMA = "program-candidate-assembly-v1"
PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA = (
    "program-refinement-candidate-comparison-v1"
)
PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA = "program-promotion-review-refined-v1"
PROGRAM_BEHAVIOR_EPISODE_SCHEMA = "program-behavior-episode-v1"

SUPPORTED_LOCAL_TARGETS = {
    "local_preferred_candidate": "Local plan target for the named candidate manifest; no promotion is applied.",
    "local_review_packet": "Local plan target for carrying review evidence forward; no promotion is applied.",
    "local_adjudication_plan": "Local plan target for adjudication planning only; no promotion is applied.",
}

_FORBIDDEN_SOURCE_OUTPUT_NAMES = {
    "manifest.json",
    "manifest.json.meta.json",
    "program.py",
    "module.py",
    "signature.py",
    "eval_examples.py",
    "eval_behavior.py",
    "behavior_results.json",
    "behavior_episode.json",
    "oracle_evidence.json",
    "execution_episode.json",
}

_REQUIRED_FALSE_COMPARISON_NON_AUTHORITY_FLAGS = (
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

_REQUIRED_FALSE_REVIEW_NON_AUTHORITY_FLAGS = (
    "automatic_promotion",
    "oracle_ranking",
    "oracle_pruning",
    "oracle_promotion",
    "program_mutation",
    "new_candidate_generation",
    "promotion_authority",
    "governance_authority",
    "external_mutation",
)

_PLAN_EFFECT = {
    "local_plan_only": True,
    "candidate_program_files_mutated": False,
    "decision_record_mutated": False,
    "comparison_mutated": False,
    "external_authority_mutated": False,
    "governance_mutated": False,
    "oracle_index_mutated": False,
}

_PLAN_NON_AUTHORITY = {
    "local_plan_only": True,
    "automatic_promotion": False,
    "apply_promotion": False,
    "external_authority_export": False,
    "oracle_ranking": False,
    "oracle_pruning": False,
    "oracle_promotion": False,
    "winner_selection": False,
    "governance_authority": False,
    "external_mutation": False,
}


class ProgramPromotionPlanError(ValueError):
    """Raised when local promotion/adjudication planning inputs are invalid."""


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramPromotionPlanError(f"{label} not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramPromotionPlanError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramPromotionPlanError(f"{label} must contain a JSON object: {source}")
    return payload


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _identity_matches_exact(
    actual: Mapping[str, Any], expected: Mapping[str, str | None]
) -> bool:
    return all(
        expected_value is None or actual.get(key) == expected_value
        for key, expected_value in expected.items()
    )


def _assert_identity_matches_exact(
    actual: Mapping[str, Any], expected: Mapping[str, str | None], *, label: str
) -> None:
    mismatches = [
        key
        for key, expected_value in expected.items()
        if expected_value is not None and actual.get(key) != expected_value
    ]
    if mismatches:
        raise ProgramPromotionPlanError(
            f"{label} identity does not match expected identity: "
            + ", ".join(sorted(mismatches))
        )


def _artifact_path_from_manifest(
    manifest: Mapping[str, Any], manifest_path: Path, *, artifact_key: str, default: str
) -> Path:
    artifact = _safe_mapping(manifest.get(artifact_key))
    raw_path = _first_text(artifact.get("path"), default)
    path = Path(raw_path or default)
    if not path.is_absolute():
        path = _manifest_root(manifest_path) / path
    return path


def _optional_artifact_hash(path: Path) -> str | None:
    return _sha256_file(path) if path.exists() else None


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
        raise ProgramPromotionPlanError(
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
        raise ProgramPromotionPlanError(
            "program behavior episode hash does not match manifest declaration(s): "
            + ", ".join(sorted(mismatches))
        )
    return episode, episode_path, actual_hash


def _load_decision_record(
    path: Path, *, expected_identities: list[Mapping[str, Any]]
) -> dict[str, Any]:
    decision = _load_json_object(path, label="program promotion decision record")
    try:
        validate_program_promotion_decision_record_contract(
            decision,
            expected_identities=expected_identities,
            require_non_promoting=True,
        )
    except ProgramPromotionDecisionError as exc:
        raise ProgramPromotionPlanError(str(exc)) from exc
    return decision


def _load_comparison(
    path: Path, *, candidate_manifest_path: Path, source_manifest_path: Path | None
) -> dict[str, Any]:
    try:
        return validate_program_refinement_candidate_comparison_contract(
            comparison_path=path,
            candidate_manifest_path=candidate_manifest_path,
            source_manifest_path=source_manifest_path,
        )
    except (ProgramRefinementComparisonError, ProgramRefinementError) as exc:
        raise ProgramPromotionPlanError(str(exc)) from exc


def _load_optional_review(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    review = _load_json_object(path, label="refined promotion review")
    if review.get("schema_version") != PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA:
        raise ProgramPromotionPlanError(
            "refined promotion review schema_version must be "
            + PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA
        )
    if review.get("promotion_state") != "not_promoted":
        raise ProgramPromotionPlanError(
            "refined promotion review must keep promotion_state not_promoted"
        )
    non_authority = _safe_mapping(review.get("non_authority"))
    if non_authority.get("local_review_packet_only") is not True:
        raise ProgramPromotionPlanError(
            "refined promotion review must be a local review packet only"
        )
    invalid = [
        key
        for key in _REQUIRED_FALSE_REVIEW_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid:
        raise ProgramPromotionPlanError(
            "refined promotion review widens non-authority flags: " + ", ".join(invalid)
        )
    return review


def _target_payload(target: str) -> dict[str, Any]:
    target_kind = str(target or "").strip()
    if target_kind not in SUPPORTED_LOCAL_TARGETS:
        allowed = ", ".join(sorted(SUPPORTED_LOCAL_TARGETS))
        raise ProgramPromotionPlanError(
            f"unsupported local promotion plan target {target_kind!r}; allowed targets: {allowed}"
        )
    return {
        "kind": target_kind,
        "description": SUPPORTED_LOCAL_TARGETS[target_kind],
        "apply_supported": False,
    }


def _authority_owner_payload(authority_owner: str) -> dict[str, str]:
    owner = str(authority_owner or "").strip()
    if not owner:
        raise ProgramPromotionPlanError("promotion plan requires authority-owner")
    return {"kind": "human_operator", "id": owner, "source": "cli"}


def _eligibility_payload(
    *,
    behavior_present: bool,
    behavior_results_present: bool,
    behavior_episode_present: bool,
    comparison: Mapping[str, Any],
    decision: Mapping[str, Any],
    authority_owner: str,
    target_supported: bool,
    review: Mapping[str, Any] | None,
) -> dict[str, Any]:
    comparison_status = str(comparison.get("status") or "unknown")
    decision_outcome = str(decision.get("outcome") or "unknown")
    decision_status = str(decision.get("status") or "unknown")
    local_conditions = {
        "behavior_evidence_present": behavior_present,
        "comparison_present": True,
        "comparison_status_compared": comparison_status == "compared",
        "decision_record_present": True,
        "decision_status_recorded": decision_status == "recorded",
        "authority_owner_present": bool(str(authority_owner or "").strip()),
        "target_supported": target_supported,
    }
    missing: list[str] = []
    if not behavior_present:
        missing.append("no_candidate_behavior_evidence")
    if comparison_status != "compared":
        missing.append("no_compared_candidate_comparison")
    if decision_status != "recorded":
        missing.append("no_recorded_decision_record")
    if not local_conditions["authority_owner_present"]:
        missing.append("no_authority_owner_declared")
    if not target_supported:
        missing.append("unsupported_local_target")
    review_missing = []
    if review is not None:
        readiness = _safe_mapping(review.get("review_readiness"))
        review_missing = _safe_string_list(readiness.get("missing_required_evidence"))
    if "no_model_jury_execution_episode" in review_missing or review is None:
        missing.append("no_model_jury_execution_episode")
    missing.extend(["no_external_authority_contract", "apply_not_supported"])
    unique_missing: list[str] = []
    for item in missing:
        if item not in unique_missing:
            unique_missing.append(item)
    eligible_for_local_plan = all(local_conditions.values())
    return {
        "status": "eligible_for_local_plan_only"
        if eligible_for_local_plan
        else "not_eligible",
        "behavior_evidence_present": behavior_present,
        "behavior_results_present": behavior_results_present,
        "behavior_episode_present": behavior_episode_present,
        "behavior_evidence_kind": "behavior_results"
        if behavior_results_present
        else "behavior_episode"
        if behavior_episode_present
        else None,
        "comparison_present": True,
        "comparison_status": comparison_status,
        "decision_record_present": True,
        "decision_status": decision_status,
        "decision_outcome": decision_outcome,
        "authority_owner_present": local_conditions["authority_owner_present"],
        "target_supported": target_supported,
        "allowed_for_apply": False,
        "missing_required_evidence": unique_missing,
        "notes": [
            "Local plan captures evidence needed for a later operator decision.",
            "This plan is not promotion and cannot be applied by this command.",
        ],
    }


def _assert_plan_hash_field(
    evidence_hashes: Mapping[str, Any], *, field: str, actual_hash: str | None
) -> None:
    declared = _first_text(evidence_hashes.get(field))
    if actual_hash is None:
        if declared is not None:
            raise ProgramPromotionPlanError(
                f"program promotion plan {field} must be null when current artifact is absent"
            )
        return
    if declared != actual_hash:
        raise ProgramPromotionPlanError(
            f"program promotion plan {field} does not match current artifact hash"
        )


def _assert_plan_effect_flags(plan: Mapping[str, Any]) -> None:
    effect = _safe_mapping(plan.get("effect"))
    for key, expected in _PLAN_EFFECT.items():
        if effect.get(key) is not expected:
            raise ProgramPromotionPlanError(
                f"program promotion plan effect.{key} must be {expected!r}"
            )

    non_authority = _safe_mapping(plan.get("non_authority"))
    for key, expected in _PLAN_NON_AUTHORITY.items():
        if non_authority.get(key) is not expected:
            raise ProgramPromotionPlanError(
                f"program promotion plan non_authority.{key} must be {expected!r}"
            )


def validate_program_promotion_plan_contract(
    plan: Mapping[str, Any],
    *,
    expected_identities: list[Mapping[str, Any]],
    valid_manifest_hashes: set[str],
    expected_candidate_manifest_path: Path | None = None,
    decision_record_sha256: str | None = None,
    comparison_sha256: str | None = None,
) -> Path:
    """Validate a local promotion plan before a final consumer summarizes it."""

    if plan.get("schema_version") != PROGRAM_PROMOTION_PLAN_SCHEMA:
        raise ProgramPromotionPlanError(
            "program promotion plan schema_version must be "
            + PROGRAM_PROMOTION_PLAN_SCHEMA
        )
    if plan.get("status") != "planned_not_applied":
        raise ProgramPromotionPlanError(
            "program promotion plan status must be planned_not_applied"
        )
    if plan.get("promotion_state") != "not_promoted":
        raise ProgramPromotionPlanError(
            "program promotion plan promotion_state must be not_promoted"
        )

    target = _safe_mapping(plan.get("target"))
    target_kind = _first_text(target.get("kind"))
    if target_kind not in SUPPORTED_LOCAL_TARGETS:
        raise ProgramPromotionPlanError(
            "program promotion plan target.kind must be a supported local target"
        )
    if target.get("apply_supported") is not False:
        raise ProgramPromotionPlanError(
            "program promotion plan target.apply_supported must be false"
        )

    authority_owner = _safe_mapping(plan.get("authority_owner"))
    if authority_owner.get("kind") != "human_operator" or not _first_text(
        authority_owner.get("id")
    ):
        raise ProgramPromotionPlanError(
            "program promotion plan must preserve a human_operator authority_owner id"
        )

    plan_identity = _safe_mapping(plan.get("candidate_identity"))
    if not any(
        _identity_matches_exact(plan_identity, expected)
        for expected in expected_identities
    ):
        raise ProgramPromotionPlanError(
            "program promotion plan candidate_identity does not match expected identity"
        )

    created_from = _safe_mapping(plan.get("created_from"))
    raw_manifest_path = _first_text(created_from.get("candidate_manifest_path"))
    if raw_manifest_path is None:
        raise ProgramPromotionPlanError(
            "program promotion plan missing created_from.candidate_manifest_path"
        )
    candidate_manifest_path = Path(raw_manifest_path).expanduser().resolve()
    if (
        expected_candidate_manifest_path is not None
        and candidate_manifest_path
        != expected_candidate_manifest_path.expanduser().resolve()
    ):
        raise ProgramPromotionPlanError(
            "program promotion plan candidate_manifest_path does not match expected manifest path"
        )

    try:
        manifest = load_program_manifest(candidate_manifest_path)
        behavior, _behavior_path, behavior_hash = load_program_behavior_results(
            manifest,
            candidate_manifest_path,
        )
        behavior_episode, _behavior_episode_path, behavior_episode_hash = (
            _load_program_behavior_episode(manifest, candidate_manifest_path)
        )
    except ProgramRefinementError as exc:
        raise ProgramPromotionPlanError(str(exc)) from exc
    if manifest.get("schema_version") != PROGRAM_MANIFEST_SCHEMA:
        raise ProgramPromotionPlanError(
            "program promotion plan candidate manifest schema_version must be "
            + PROGRAM_MANIFEST_SCHEMA
        )
    _assert_identity_matches_exact(
        plan_identity,
        _identity_from_manifest(manifest),
        label="program promotion plan candidate",
    )

    evidence_hashes = _safe_mapping(plan.get("evidence_hashes"))
    candidate_manifest_hash = _sha256_file(candidate_manifest_path)
    if evidence_hashes.get("candidate_manifest_hash") != candidate_manifest_hash:
        raise ProgramPromotionPlanError(
            "program promotion plan candidate_manifest_hash does not match current manifest"
        )
    if candidate_manifest_hash not in valid_manifest_hashes:
        raise ProgramPromotionPlanError(
            "program promotion plan candidate_manifest_hash is not valid for this consumer"
        )

    execution_episode_hash = _optional_artifact_hash(
        _artifact_path_from_manifest(
            manifest,
            candidate_manifest_path,
            artifact_key="execution_episode_artifact",
            default="execution_episode.json",
        )
    )
    oracle_evidence_hash = _optional_artifact_hash(
        _manifest_root(candidate_manifest_path) / "oracle_evidence.json"
    )
    _assert_plan_hash_field(
        evidence_hashes,
        field="candidate_behavior_results_hash",
        actual_hash=behavior_hash if isinstance(behavior, Mapping) else None,
    )
    _assert_plan_hash_field(
        evidence_hashes,
        field="candidate_behavior_episode_hash",
        actual_hash=behavior_episode_hash
        if isinstance(behavior_episode, Mapping)
        else None,
    )
    _assert_plan_hash_field(
        evidence_hashes,
        field="candidate_execution_episode_hash",
        actual_hash=execution_episode_hash,
    )
    _assert_plan_hash_field(
        evidence_hashes,
        field="candidate_oracle_evidence_hash",
        actual_hash=oracle_evidence_hash,
    )

    raw_comparison_path = _first_text(created_from.get("comparison_path"))
    raw_decision_path = _first_text(created_from.get("decision_record_path"))
    if raw_comparison_path is None or raw_decision_path is None:
        raise ProgramPromotionPlanError(
            "program promotion plan must bind comparison and decision record paths"
        )
    comparison_path = Path(raw_comparison_path).expanduser().resolve()
    decision_record_path = Path(raw_decision_path).expanduser().resolve()
    raw_source_manifest_path = _first_text(created_from.get("source_manifest_path"))
    source_manifest_path = (
        Path(raw_source_manifest_path).expanduser().resolve()
        if raw_source_manifest_path is not None
        else None
    )
    comparison = _load_comparison(
        comparison_path,
        candidate_manifest_path=candidate_manifest_path,
        source_manifest_path=source_manifest_path,
    )
    comparison_hash = _sha256_file(comparison_path)
    if evidence_hashes.get("comparison_hash") != comparison_hash:
        raise ProgramPromotionPlanError(
            "program promotion plan comparison_hash does not match current comparison"
        )
    if comparison_sha256 is not None and comparison_sha256 != comparison_hash:
        raise ProgramPromotionPlanError(
            "program promotion plan comparison_hash does not match supplied comparison"
        )
    source_identity = _safe_mapping(comparison.get("source_identity"))
    _load_decision_record(decision_record_path, expected_identities=[source_identity])
    decision_hash = _sha256_file(decision_record_path)
    if evidence_hashes.get("decision_record_hash") != decision_hash:
        raise ProgramPromotionPlanError(
            "program promotion plan decision_record_hash does not match current decision record"
        )
    if decision_record_sha256 is not None and decision_record_sha256 != decision_hash:
        raise ProgramPromotionPlanError(
            "program promotion plan decision_record_hash does not match supplied decision record"
        )

    raw_review_path = _first_text(created_from.get("review_path"))
    if raw_review_path is not None:
        review = _load_optional_review(Path(raw_review_path).expanduser().resolve())
        if review is not None:
            _assert_identity_matches_exact(
                _safe_mapping(review.get("identity")),
                {key: str(value) for key, value in source_identity.items()},
                label="program promotion plan refined review",
            )

    eligibility = _safe_mapping(plan.get("eligibility"))
    if eligibility.get("allowed_for_apply") is not False:
        raise ProgramPromotionPlanError(
            "program promotion plan eligibility.allowed_for_apply must be false"
        )
    if eligibility.get("comparison_present") is not True:
        raise ProgramPromotionPlanError(
            "program promotion plan must record comparison_present true"
        )
    if eligibility.get("decision_record_present") is not True:
        raise ProgramPromotionPlanError(
            "program promotion plan must record decision_record_present true"
        )

    audit = _safe_mapping(plan.get("audit_trail"))
    for field, expected in (
        ("candidate_manifest_hash", candidate_manifest_hash),
        ("decision_record_hash", decision_hash),
        ("comparison_hash", comparison_hash),
        ("candidate_behavior_results_hash", behavior_hash),
        ("candidate_behavior_episode_hash", behavior_episode_hash),
    ):
        if expected is not None and audit.get(field) != expected:
            raise ProgramPromotionPlanError(
                f"program promotion plan audit_trail.{field} does not match current evidence"
            )

    reversibility = _safe_mapping(plan.get("reversibility"))
    if reversibility.get("apply_status") != "not_applied":
        raise ProgramPromotionPlanError(
            "program promotion plan reversibility.apply_status must be not_applied"
        )
    if reversibility.get("rollback_required") is not False:
        raise ProgramPromotionPlanError(
            "program promotion plan reversibility.rollback_required must be false"
        )

    _assert_plan_effect_flags(plan)
    return candidate_manifest_path


def build_program_promotion_plan(
    *,
    manifest_path: Path,
    decision_record_path: Path,
    comparison_path: Path,
    target: str,
    authority_owner: str,
    review_path: Path | None = None,
    source_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Build a local non-authoritative adjudication/promotion plan sidecar."""

    manifest_path = manifest_path.expanduser().resolve()
    decision_record_path = decision_record_path.expanduser().resolve()
    comparison_path = comparison_path.expanduser().resolve()
    review_path = (
        review_path.expanduser().resolve() if review_path is not None else None
    )
    source_manifest_path = (
        source_manifest_path.expanduser().resolve()
        if source_manifest_path is not None
        else None
    )
    try:
        manifest = load_program_manifest(manifest_path)
        behavior, behavior_path, behavior_hash = load_program_behavior_results(
            manifest,
            manifest_path,
        )
        behavior_episode, behavior_episode_path, behavior_episode_hash = (
            _load_program_behavior_episode(manifest, manifest_path)
        )
    except ProgramRefinementError as exc:
        raise ProgramPromotionPlanError(str(exc)) from exc
    if manifest.get("schema_version") != PROGRAM_MANIFEST_SCHEMA:
        raise ProgramPromotionPlanError(
            "program manifest schema_version must be " + PROGRAM_MANIFEST_SCHEMA
        )

    comparison = _load_comparison(
        comparison_path,
        candidate_manifest_path=manifest_path,
        source_manifest_path=source_manifest_path,
    )
    source_identity = _safe_mapping(comparison.get("source_identity"))
    decision = _load_decision_record(
        decision_record_path,
        expected_identities=[source_identity],
    )
    review = _load_optional_review(review_path)
    target_info = _target_payload(target)
    authority_info = _authority_owner_payload(authority_owner)

    candidate_identity = _identity_from_manifest(manifest)
    _assert_identity_matches_exact(
        _safe_mapping(comparison.get("candidate_identity")),
        candidate_identity,
        label="program candidate comparison candidate",
    )
    source_identity = _safe_mapping(comparison.get("source_identity"))
    if source_manifest_path is not None:
        source_manifest = load_program_manifest(source_manifest_path)
        _assert_identity_matches_exact(
            source_identity,
            _identity_from_manifest(source_manifest),
            label="program candidate comparison source",
        )
    if review is not None:
        _assert_identity_matches_exact(
            _safe_mapping(review.get("identity")),
            {key: str(value) for key, value in source_identity.items()},
            label="refined promotion review",
        )

    candidate_manifest_hash = _sha256_file(manifest_path)
    decision_record_hash = _sha256_file(decision_record_path)
    comparison_hash = _sha256_file(comparison_path)
    execution_episode_hash = _optional_artifact_hash(
        _artifact_path_from_manifest(
            manifest,
            manifest_path,
            artifact_key="execution_episode_artifact",
            default="execution_episode.json",
        )
    )
    oracle_evidence_hash = _optional_artifact_hash(
        _manifest_root(manifest_path) / "oracle_evidence.json"
    )
    comparison_created_from = _safe_mapping(comparison.get("created_from"))
    source_behavior_hash = _first_text(
        comparison_created_from.get("source_behavior_results_hash")
    )
    candidate_behavior_hash = _first_text(
        behavior_hash,
        comparison_created_from.get("candidate_behavior_results_hash"),
    )
    source_behavior_episode_hash = _first_text(
        comparison_created_from.get("source_behavior_episode_hash")
    )
    candidate_behavior_episode_hash = _first_text(
        behavior_episode_hash,
        comparison_created_from.get("candidate_behavior_episode_hash"),
    )
    behavior_present = (
        isinstance(behavior, Mapping)
        and behavior_hash is not None
        or isinstance(behavior_episode, Mapping)
        and behavior_episode_hash is not None
    )
    created_at = _utc_now_iso()

    return {
        "schema_version": PROGRAM_PROMOTION_PLAN_SCHEMA,
        "status": "planned_not_applied",
        "promotion_state": "not_promoted",
        "target": target_info,
        "authority_owner": authority_info,
        "candidate_identity": candidate_identity,
        "created_from": {
            "candidate_manifest_path": str(manifest_path),
            "candidate_manifest_schema_version": manifest.get("schema_version"),
            "decision_record_path": str(decision_record_path),
            "decision_record_schema_version": decision.get("schema_version"),
            "comparison_path": str(comparison_path),
            "comparison_schema_version": comparison.get("schema_version"),
            "review_path": str(review_path) if review_path is not None else None,
            "review_schema_version": review.get("schema_version")
            if review is not None
            else None,
            "source_manifest_path": str(source_manifest_path)
            if source_manifest_path is not None
            else None,
            "candidate_behavior_episode_path": str(behavior_episode_path)
            if behavior_episode_path is not None and behavior_episode_path.exists()
            else None,
            "candidate_behavior_episode_schema_version": behavior_episode.get(
                "schema_version"
            )
            if behavior_episode is not None
            else None,
        },
        "evidence_hashes": {
            "candidate_manifest_hash": candidate_manifest_hash,
            "candidate_behavior_results_hash": candidate_behavior_hash,
            "candidate_behavior_episode_hash": candidate_behavior_episode_hash,
            "candidate_execution_episode_hash": execution_episode_hash,
            "candidate_oracle_evidence_hash": oracle_evidence_hash,
            "decision_record_hash": decision_record_hash,
            "comparison_hash": comparison_hash,
        },
        "eligibility": _eligibility_payload(
            behavior_present=behavior_present,
            behavior_results_present=isinstance(behavior, Mapping)
            and behavior_hash is not None,
            behavior_episode_present=isinstance(behavior_episode, Mapping)
            and behavior_episode_hash is not None,
            comparison=comparison,
            decision=decision,
            authority_owner=authority_owner,
            target_supported=True,
            review=review,
        ),
        "audit_trail": {
            "candidate_manifest_hash": candidate_manifest_hash,
            "decision_record_hash": decision_record_hash,
            "comparison_hash": comparison_hash,
            "source_behavior_results_hash": source_behavior_hash,
            "source_behavior_episode_hash": source_behavior_episode_hash,
            "candidate_behavior_results_hash": candidate_behavior_hash,
            "candidate_behavior_episode_hash": candidate_behavior_episode_hash,
            "created_at": created_at,
            "created_by": authority_info["id"],
        },
        "reversibility": {
            "apply_status": "not_applied",
            "rollback_required": False,
            "rollback_supported": False,
            "supersession_supported": False,
            "notes": [
                "No rollback is required because no promotion was applied.",
                "Future apply surfaces must record supersession/rollback semantics separately.",
            ],
        },
        "effect": dict(_PLAN_EFFECT),
        "non_authority": dict(_PLAN_NON_AUTHORITY),
        "notes": [
            "This artifact is a local plan only and records no promotion.",
            "The command writes only the requested plan sidecar.",
            "Future apply surface required before any external authority mutation can exist.",
        ],
    }


def _prepare_plan_output_path(plan: Mapping[str, Any], out_path: Path) -> Path:
    try:
        return prepare_sidecar_output_path(
            out_path,
            payload=plan,
            artifact_label="promotion plan",
            protected_names=_FORBIDDEN_SOURCE_OUTPUT_NAMES,
            payload_artifact_root_policy="forbid",
        )
    except ValueError as exc:
        raise ProgramPromotionPlanError(str(exc)) from exc


def write_program_promotion_plan(
    plan: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Write the local promotion/adjudication plan sidecar."""

    out_path = _prepare_plan_output_path(plan, out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(plan)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
