from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from dspx.security import confine_path, identity_matches_exact, identity_mismatch_keys
from dspx.services.artifact_boundary import (
    StableJsonArtifact,
    atomic_publish_bytes,
    prepare_sidecar_output_path,
    read_stable_json_artifact,
)
from dspx.services.program_evidence_closure import (
    CandidateArtifactSnapshot,
    read_candidate_snapshot_artifact,
    snapshot_candidate_artifact_closure,
)
from dspx.services.program_model_jury_validation import (
    validate_program_model_jury_results_contract,
)
from dspx.services.program_runtime_episode import (
    PROGRAM_RUNTIME_EPISODE_SCHEMA,
    validate_program_runtime_episode_contract,
)
from dspx.services.program_refinement import (
    ProgramRefinementError,
    load_program_behavior_results,
    load_program_manifest,
    validate_program_oracle_report_non_authority,
    validate_program_refinement_proposal_contract,
)

PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA = "program-promotion-review-refined-v1"
PROGRAM_PROMOTION_REVIEW_SCHEMA = "program-promotion-review-v1"
PROGRAM_PROMOTION_ADJUDICATION_REQUEST_SCHEMA = (
    "program-promotion-adjudication-request-v1"
)
PROGRAM_PROMOTION_DECISION_SCHEMA = "program-promotion-decision-v1"
PROGRAM_REFINEMENT_PROPOSAL_SCHEMA = "program-refinement-proposal-v1"
PROGRAM_BEHAVIOR_EPISODE_SCHEMA = "program-behavior-episode-v1"

_REFINED_PACKET_NON_AUTHORITY = {
    "local_review_packet_only": True,
    "automatic_promotion": False,
    "oracle_ranking": False,
    "oracle_pruning": False,
    "oracle_promotion": False,
    "program_mutation": False,
    "new_candidate_generation": False,
    "promotion_authority": False,
    "governance_authority": False,
    "external_mutation": False,
}

_REQUIRED_FALSE_REFINED_REVIEW_NON_AUTHORITY_FLAGS = tuple(
    key for key, value in _REFINED_PACKET_NON_AUTHORITY.items() if value is False
)

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
    "promotion_review.json",
    "promotion_adjudication_request.json",
    "promotion_decision_template.json",
}


class ProgramPromotionRefinementError(ValueError):
    """Raised when promotion-review refinement inputs are malformed."""


class ProgramPromotionRefinementCommitIndeterminateError(
    ProgramPromotionRefinementError
):
    """Raised after replacement when directory durability cannot be confirmed."""


def _snapshot_candidate_for_promotion_review(
    manifest_path: Path,
) -> CandidateArtifactSnapshot:
    try:
        return snapshot_candidate_artifact_closure(manifest_path)
    except (OSError, ValueError) as exc:
        raise ProgramPromotionRefinementError(
            f"candidate artifact closure is invalid: {exc}"
        ) from exc


def _load_snapshot_json_object(
    snapshot: CandidateArtifactSnapshot,
    *,
    kind: str,
    label: str,
) -> tuple[dict[str, Any], Path, str]:
    try:
        artifact, content = read_candidate_snapshot_artifact(snapshot, kind=kind)
    except (OSError, ValueError) as exc:
        raise ProgramPromotionRefinementError(
            f"{label} is not current in the validated candidate artifact closure: {exc}"
        ) from exc
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramPromotionRefinementError(
            f"{label} must contain valid UTF-8 JSON: {artifact.path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramPromotionRefinementError(
            f"{label} must contain a JSON object: {artifact.path}"
        )
    return payload, artifact.path, artifact.sha256


def _require_snapshot_artifact(
    snapshot: CandidateArtifactSnapshot,
    *,
    kind: str,
    loaded_path: Path | None,
    loaded_hash: str | None,
    loaded_payload: Mapping[str, Any] | None,
    label: str,
) -> None:
    snapshot_payload, snapshot_path, snapshot_hash = _load_snapshot_json_object(
        snapshot,
        kind=kind,
        label=label,
    )
    if loaded_path is None or loaded_hash is None or loaded_payload is None:
        raise ProgramPromotionRefinementError(
            f"{label} was not loaded from the validated candidate artifact closure"
        )
    if (
        loaded_path.expanduser().resolve() != snapshot_path
        or loaded_hash != snapshot_hash
        or dict(loaded_payload or {}) != snapshot_payload
    ):
        raise ProgramPromotionRefinementError(
            f"{label} did not load from the validated candidate artifact closure"
        )


def _require_candidate_snapshot_unchanged(
    original: CandidateArtifactSnapshot,
) -> None:
    try:
        current = snapshot_candidate_artifact_closure(original.manifest_path)
    except (OSError, ValueError) as exc:
        raise ProgramPromotionRefinementError(
            "candidate artifact closure changed during promotion review construction: "
            f"{exc}"
        ) from exc
    if current != original:
        raise ProgramPromotionRefinementError(
            "candidate artifact closure changed during promotion review construction"
        )


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramPromotionRefinementError(f"{label} not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramPromotionRefinementError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramPromotionRefinementError(
            f"{label} must contain a JSON object: {source}"
        )
    return payload


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


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
    for surface in _safe_list(candidate_assembly.get("surfaces")):
        if not isinstance(surface, Mapping) or surface.get("kind") != kind:
            continue
        raw_path = _first_text(surface.get("path"))
        if raw_path:
            path = Path(raw_path)
            if not path.is_absolute():
                path = _manifest_root(manifest_path) / path
            return path
    return _manifest_root(manifest_path) / default


def _validate_schema(
    payload: Mapping[str, Any], *, label: str, expected_schema: str
) -> None:
    if payload.get("schema_version") != expected_schema:
        raise ProgramPromotionRefinementError(
            f"{label} schema_version must be {expected_schema}"
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
    if path.is_absolute():
        raise ProgramPromotionRefinementError(
            "program behavior episode path must be candidate-relative"
        )
    try:
        return confine_path(_manifest_root(manifest_path), path, strict=True)
    except ValueError as exc:
        raise ProgramPromotionRefinementError(
            "program behavior episode path escapes candidate root"
        ) from exc


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
    _validate_schema(
        episode,
        label="program behavior episode",
        expected_schema=PROGRAM_BEHAVIOR_EPISODE_SCHEMA,
    )
    actual_hash = hashlib.sha256(episode_path.read_bytes()).hexdigest()
    declared_hashes = _declared_behavior_episode_hashes(manifest)
    if not declared_hashes:
        raise ProgramPromotionRefinementError(
            "program behavior episode must have a manifest-declared content hash"
        )
    mismatches = [
        name
        for name, declared_hash in declared_hashes.items()
        if declared_hash != actual_hash
    ]
    if mismatches:
        raise ProgramPromotionRefinementError(
            "program behavior episode hash does not match manifest declaration(s): "
            + ", ".join(sorted(mismatches))
        )
    return episode, episode_path, actual_hash


def _identity_matches(left: Mapping[str, Any], right: Mapping[str, str | None]) -> bool:
    return identity_matches_exact(left, right)


def _assert_identity_matches(
    actual: Mapping[str, Any], expected: Mapping[str, str | None], *, label: str
) -> None:
    mismatches = identity_mismatch_keys(actual, expected)
    if mismatches:
        raise ProgramPromotionRefinementError(
            f"{label} identity does not exactly match manifest identity: "
            + ", ".join(sorted(mismatches))
        )


def _raise_contract_error(
    error_type: type[Exception], message: str, exc: Exception | None = None
) -> None:
    if exc is None:
        raise error_type(message)
    raise error_type(message) from exc


def _created_from_path(
    created_from: Mapping[str, Any],
    key: str,
    *,
    label: str,
    base_path: Path | None,
    error_type: type[Exception],
    required: bool = True,
) -> Path | None:
    raw_path = _first_text(created_from.get(key))
    if raw_path is None:
        if required:
            _raise_contract_error(error_type, f"{label} must include {key}")
        return None
    path = Path(raw_path).expanduser()
    if not path.is_absolute() and base_path is not None:
        path = base_path.parent / path
    return Path(os.path.abspath(path))


def _validate_created_from_hash(
    created_from: Mapping[str, Any],
    *,
    path_key: str,
    hash_key: str,
    label: str,
    base_path: Path | None,
    error_type: type[Exception],
    required: bool = True,
) -> tuple[Path | None, str | None]:
    path = _created_from_path(
        created_from,
        path_key,
        label=label,
        base_path=base_path,
        error_type=error_type,
        required=required,
    )
    declared_hash = _first_text(created_from.get(hash_key))
    if path is None:
        if declared_hash is not None:
            _raise_contract_error(
                error_type, f"{label} must not include {hash_key} without {path_key}"
            )
        return None, None
    if declared_hash is None:
        _raise_contract_error(error_type, f"{label} must include {hash_key}")
    try:
        actual_hash = _sha256_file(path)
    except FileNotFoundError as exc:
        _raise_contract_error(error_type, f"{label} not found: {path}", exc)
    assert declared_hash is not None
    if actual_hash != declared_hash:
        _raise_contract_error(
            error_type,
            f"{label} hash does not match current file for {path_key}",
        )
    return path, actual_hash


def _validate_created_from_expected_ref(
    created_from: Mapping[str, Any],
    *,
    path_key: str,
    hash_key: str,
    label: str,
    valid_refs: Mapping[Path, str] | None,
    base_path: Path | None,
    error_type: type[Exception],
    required: bool = False,
) -> tuple[Path | None, str | None]:
    path, declared_hash = _validate_created_from_hash(
        created_from,
        path_key=path_key,
        hash_key=hash_key,
        label=label,
        base_path=base_path,
        error_type=error_type,
        required=required,
    )
    if valid_refs is None or path is None:
        return path, declared_hash
    normalized_refs = {
        ref_path.expanduser().resolve(): ref_hash
        for ref_path, ref_hash in valid_refs.items()
    }
    expected_hash = normalized_refs.get(path)
    if expected_hash is None:
        _raise_contract_error(
            error_type,
            f"{label} path does not match expected input",
        )
    if declared_hash != expected_hash:
        _raise_contract_error(
            error_type,
            f"{label} hash does not match expected input",
        )
    return path, declared_hash


def validate_program_promotion_review_refined_contract(
    refined_review: Mapping[str, Any],
    *,
    refined_review_path: Path | None = None,
    expected_identity: Mapping[str, Any] | None = None,
    valid_manifest_refs: Mapping[Path, str] | None = None,
    valid_oracle_report_refs: Mapping[Path, str] | None = None,
    valid_refinement_proposal_refs: Mapping[Path, str] | None = None,
    valid_behavior_results_refs: Mapping[Path, str] | None = None,
    valid_behavior_episode_refs: Mapping[Path, str] | None = None,
    valid_model_jury_results_refs: Mapping[Path, str] | None = None,
    valid_runtime_episode_refs: Mapping[Path, str] | None = None,
    error_type: type[ValueError] = ProgramPromotionRefinementError,
) -> None:
    """Validate a refined promotion-review sidecar before downstream consumption."""

    if refined_review.get("schema_version") != PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA:
        _raise_contract_error(
            error_type,
            "refined promotion review schema_version must be "
            + PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA,
        )
    if refined_review.get("promotion_state") != "not_promoted":
        _raise_contract_error(
            error_type,
            "refined promotion review must keep promotion_state not_promoted",
        )
    if refined_review.get("status") not in {
        "insufficient_behavior_evidence",
        "needs_more_evidence",
        "review_packet_ready",
    }:
        _raise_contract_error(
            error_type, "refined promotion review status is not supported"
        )

    created_from = _safe_mapping(refined_review.get("created_from"))
    manifest_path, manifest_hash = _validate_created_from_expected_ref(
        created_from,
        path_key="manifest_path",
        hash_key="manifest_sha256",
        label="refined promotion review manifest ref",
        valid_refs=valid_manifest_refs,
        base_path=refined_review_path,
        error_type=error_type,
        required=True,
    )
    assert manifest_path is not None and manifest_hash is not None
    try:
        manifest = load_program_manifest(manifest_path)
    except ProgramRefinementError as exc:
        _raise_contract_error(error_type, str(exc), exc)
    manifest_identity = _identity_from_manifest(manifest)
    identity = _safe_mapping(refined_review.get("identity"))
    mismatches = identity_mismatch_keys(identity, manifest_identity)
    if mismatches:
        _raise_contract_error(
            error_type,
            "refined promotion review identity does not match current manifest identity: "
            + ", ".join(sorted(mismatches)),
        )
    if expected_identity:
        expected_mismatches = identity_mismatch_keys(identity, expected_identity)
        if expected_mismatches:
            _raise_contract_error(
                error_type,
                "refined promotion review identity does not match expected identity: "
                + ", ".join(sorted(expected_mismatches)),
            )

    oracle_report_path, oracle_report_hash = _validate_created_from_expected_ref(
        created_from,
        path_key="oracle_report_path",
        hash_key="oracle_report_sha256",
        label="refined promotion review Oracle report ref",
        valid_refs=valid_oracle_report_refs,
        base_path=refined_review_path,
        error_type=error_type,
        required=True,
    )
    refinement_proposal_path, refinement_proposal_hash = (
        _validate_created_from_expected_ref(
            created_from,
            path_key="refinement_proposal_path",
            hash_key="refinement_proposal_sha256",
            label="refined promotion review proposal ref",
            valid_refs=valid_refinement_proposal_refs,
            base_path=refined_review_path,
            error_type=error_type,
            required=True,
        )
    )
    for path_key, hash_key, label in (
        (
            "original_promotion_review_path",
            "original_promotion_review_sha256",
            "refined promotion review original review ref",
        ),
        (
            "original_promotion_adjudication_request_path",
            "original_promotion_adjudication_request_sha256",
            "refined promotion review original adjudication-request ref",
        ),
        (
            "original_promotion_decision_template_path",
            "original_promotion_decision_template_sha256",
            "refined promotion review original decision-template ref",
        ),
    ):
        _validate_created_from_hash(
            created_from,
            path_key=path_key,
            hash_key=hash_key,
            label=label,
            base_path=refined_review_path,
            error_type=error_type,
        )

    _validate_created_from_expected_ref(
        created_from,
        path_key="behavior_results_path",
        hash_key="behavior_results_sha256",
        label="refined promotion review behavior-results ref",
        valid_refs=valid_behavior_results_refs,
        base_path=refined_review_path,
        error_type=error_type,
        required=False,
    )
    _validate_created_from_expected_ref(
        created_from,
        path_key="behavior_episode_path",
        hash_key="behavior_episode_sha256",
        label="refined promotion review behavior-episode ref",
        valid_refs=valid_behavior_episode_refs,
        base_path=refined_review_path,
        error_type=error_type,
        required=False,
    )
    model_jury_results_path, model_jury_results_hash = (
        _validate_created_from_expected_ref(
            created_from,
            path_key="model_jury_results_path",
            hash_key="model_jury_results_sha256",
            label="refined promotion review model-jury ref",
            valid_refs=valid_model_jury_results_refs,
            base_path=refined_review_path,
            error_type=error_type,
            required=False,
        )
    )
    runtime_episode_path, runtime_episode_hash = _validate_created_from_expected_ref(
        created_from,
        path_key="runtime_episode_path",
        hash_key="runtime_episode_sha256",
        label="refined promotion review runtime-episode ref",
        valid_refs=valid_runtime_episode_refs,
        base_path=refined_review_path,
        error_type=error_type,
        required=False,
    )

    model_jury_summary = _safe_mapping(
        _safe_mapping(refined_review.get("evidence_summary")).get("model_jury_results")
    )
    model_jury_path = _first_text(created_from.get("model_jury_results_path"))
    model_jury_hash = _first_text(created_from.get("model_jury_results_sha256"))
    if model_jury_summary.get("present") is True:
        if model_jury_path is None or model_jury_hash is None:
            _raise_contract_error(
                error_type,
                "refined promotion review model-jury summary requires path and hash refs",
            )
        if _first_text(model_jury_summary.get("sha256")) != model_jury_hash:
            _raise_contract_error(
                error_type,
                "refined promotion review model-jury summary hash does not match created_from",
            )

    contract_observations: list[StableJsonArtifact] = []

    def observe_contract(
        path: Path | None,
        content_hash: str | None,
        *,
        label: str,
    ) -> StableJsonArtifact | None:
        if path is None:
            return None
        try:
            observation = read_stable_json_artifact(
                path,
                label=label,
                error_type=ProgramPromotionRefinementError,
            )
        except ProgramPromotionRefinementError as exc:
            _raise_contract_error(error_type, str(exc), exc)
        if observation.sha256 != content_hash:
            _raise_contract_error(error_type, f"{label} hash changed while validating")
        contract_observations.append(observation)
        return observation

    oracle_observation = observe_contract(
        oracle_report_path,
        oracle_report_hash,
        label="refined promotion review Oracle report",
    )
    proposal_observation = observe_contract(
        refinement_proposal_path,
        refinement_proposal_hash,
        label="refined promotion review proposal",
    )
    assert oracle_observation is not None and proposal_observation is not None
    oracle_report = oracle_observation.payload
    try:
        if oracle_report.get("schema_version") != "program-oracle-evidence-report-v1":
            raise ProgramPromotionRefinementError(
                "program Oracle evidence report schema_version must be program-oracle-evidence-report-v1"
            )
        validate_program_oracle_report_non_authority(oracle_report)
        _, oracle_matched = _validate_oracle_report_identity(
            oracle_report,
            manifest_identity,
        )
        _validate_refinement_proposal(
            proposal_observation.payload,
            identity=manifest_identity,
            manifest_path=manifest_path,
            manifest_hash=manifest_hash,
            oracle_report_path=oracle_observation.path,
            oracle_report_hash=oracle_observation.sha256,
            behavior_path=_created_from_path(
                created_from,
                "behavior_results_path",
                label="refined promotion review behavior results",
                base_path=refined_review_path,
                error_type=ProgramPromotionRefinementError,
                required=False,
            ),
            behavior_hash=_first_text(created_from.get("behavior_results_sha256")),
        )
    except (ProgramRefinementError, ProgramPromotionRefinementError) as exc:
        _raise_contract_error(error_type, str(exc), exc)
    evidence_summary = _safe_mapping(refined_review.get("evidence_summary"))
    expected_oracle_summary = {
        "present": True,
        "status": oracle_report.get("status"),
        "total_records": int(oracle_report.get("total_records") or 0),
        "record_matched": oracle_matched,
    }
    if _safe_mapping(evidence_summary.get("oracle_report")) != expected_oracle_summary:
        _raise_contract_error(
            error_type,
            "refined promotion review Oracle summary does not match current evidence",
        )
    expected_proposal_summary = {
        "present": True,
        "status": proposal_observation.payload.get("status"),
        "proposal_id": proposal_observation.payload.get("proposal_id"),
    }
    if (
        _safe_mapping(evidence_summary.get("refinement_proposal"))
        != expected_proposal_summary
    ):
        _raise_contract_error(
            error_type,
            "refined promotion review proposal summary does not match current evidence",
        )
    model_observation = observe_contract(
        model_jury_results_path,
        model_jury_results_hash,
        label="refined promotion review model-jury results",
    )
    if model_observation is not None:
        validate_program_model_jury_results_contract(
            model_observation.payload,
            label="refined promotion review model-jury results",
            error_type=error_type,
            valid_manifest_refs={manifest_path: manifest_hash},
        )
        model_identity_mismatches = identity_mismatch_keys(
            _safe_mapping(model_observation.payload.get("identity")),
            manifest_identity,
        )
        if model_identity_mismatches:
            _raise_contract_error(
                error_type,
                "refined promotion review model-jury identity does not match manifest identity: "
                + ", ".join(sorted(model_identity_mismatches)),
            )
    expected_model_summary = _model_jury_summary(
        model_observation.payload if model_observation else None,
        path=model_observation.path if model_observation else None,
        content_hash=model_observation.sha256 if model_observation else None,
    )
    if (
        _safe_mapping(evidence_summary.get("model_jury_results"))
        != expected_model_summary
    ):
        _raise_contract_error(
            error_type,
            "refined promotion review model-jury summary does not match current evidence",
        )
    runtime_observation = observe_contract(
        runtime_episode_path,
        runtime_episode_hash,
        label="refined promotion review runtime episode",
    )
    if runtime_observation is not None:
        validate_program_runtime_episode_contract(
            runtime_observation.payload,
            runtime_episode_path=runtime_observation.path,
            expected_manifest_path=manifest_path,
            expected_manifest=manifest,
            expected_manifest_sha256=manifest_hash,
            error_type=error_type,
        )
    expected_runtime_summary = _runtime_episode_summary(
        runtime_observation.payload if runtime_observation else None,
        path=runtime_observation.path if runtime_observation else None,
        content_hash=runtime_observation.sha256 if runtime_observation else None,
    )
    if (
        _safe_mapping(evidence_summary.get("runtime_episode"))
        != expected_runtime_summary
    ):
        _raise_contract_error(
            error_type,
            "refined promotion review runtime summary does not match current evidence",
        )

    non_authority = _safe_mapping(refined_review.get("non_authority"))
    if non_authority.get("local_review_packet_only") is not True:
        _raise_contract_error(
            error_type, "refined promotion review must be a local review packet only"
        )
    invalid = [
        key
        for key in _REQUIRED_FALSE_REFINED_REVIEW_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid:
        _raise_contract_error(
            error_type,
            "refined promotion review widens non-authority flags: "
            + ", ".join(invalid),
        )
    for observation in contract_observations:
        try:
            current = read_stable_json_artifact(
                observation.path,
                label="refined promotion review input recheck",
                error_type=ProgramPromotionRefinementError,
            )
        except ProgramPromotionRefinementError as exc:
            _raise_contract_error(error_type, str(exc), exc)
        if current.sha256 != observation.sha256:
            _raise_contract_error(
                error_type,
                "refined promotion review input changed during contract validation",
            )


def _validate_oracle_report_identity(
    report: Mapping[str, Any], identity: Mapping[str, str | None]
) -> tuple[dict[str, Any] | None, bool]:
    records = [
        item for item in _safe_list(report.get("records")) if isinstance(item, Mapping)
    ]
    if not records:
        return None, False
    for record in records:
        record_identity = _safe_mapping(record.get("identity"))
        if _identity_matches(record_identity, identity):
            return dict(record), True
    raise ProgramPromotionRefinementError(
        "program Oracle evidence report does not contain a record matching manifest identity"
    )


def _validate_refinement_proposal(
    proposal: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    manifest_path: Path,
    manifest_hash: str,
    oracle_report_path: Path,
    oracle_report_hash: str,
    behavior_path: Path | None,
    behavior_hash: str | None,
) -> dict[str, Any]:
    valid_behavior_refs = (
        {behavior_path: behavior_hash}
        if behavior_path is not None and behavior_hash is not None
        else None
    )
    try:
        validate_program_refinement_proposal_contract(
            proposal,
            expected_identity=identity,
            valid_manifest_refs={manifest_path: manifest_hash},
            valid_oracle_report_refs={oracle_report_path: oracle_report_hash},
            valid_behavior_results_refs=valid_behavior_refs,
            error_type=ProgramPromotionRefinementError,
        )
    except ProgramRefinementError as exc:
        raise ProgramPromotionRefinementError(str(exc)) from exc
    return dict(proposal)


def _load_model_jury_results(
    observation: StableJsonArtifact | None,
    *,
    identity: Mapping[str, str | None],
    manifest_path: Path,
    manifest_hash: str,
) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    if observation is None:
        return None, None, None
    payload = observation.payload
    validate_program_model_jury_results_contract(
        payload,
        label="program model jury results",
        error_type=ProgramPromotionRefinementError,
        valid_manifest_refs={manifest_path: manifest_hash},
    )
    _assert_identity_matches(
        _safe_mapping(payload.get("identity")),
        identity,
        label="program model jury results",
    )
    return payload, observation.path, observation.sha256


def _runtime_episode_summary(
    runtime_episode: Mapping[str, Any] | None,
    *,
    path: Path | None,
    content_hash: str | None,
) -> dict[str, Any]:
    if runtime_episode is None:
        return {
            "present": False,
            "schema_version": None,
            "status": "missing",
            "runtime_episode_id": None,
            "sha256": None,
            "evidence_only": True,
            "promotion_authority": False,
            "activation_authority": False,
        }
    artifact_hashes = _safe_mapping(runtime_episode.get("artifact_hashes"))
    return {
        "present": True,
        "schema_version": runtime_episode.get("schema_version"),
        "status": runtime_episode.get("status"),
        "runtime_episode_id": runtime_episode.get("runtime_episode_id"),
        "contract_mode": runtime_episode.get("contract_mode"),
        "path": str(path.resolve()) if path is not None else None,
        "sha256": content_hash,
        "source_manifest_sha256": artifact_hashes.get("source_manifest_sha256"),
        "runtime_inputs_sha256": artifact_hashes.get("runtime_inputs_sha256"),
        "behavior_results_sha256": artifact_hashes.get("behavior_results_sha256"),
        "program_runtime_traces_sha256": artifact_hashes.get(
            "program_runtime_traces_sha256"
        ),
        "oracle_evidence_sha256": artifact_hashes.get("oracle_evidence_sha256"),
        "evidence_only": True,
        "promotion_authority": False,
        "activation_authority": False,
        "shared_oracle_mutated": False,
    }


def _model_jury_summary(
    model_jury_results: Mapping[str, Any] | None,
    *,
    path: Path | None,
    content_hash: str | None,
) -> dict[str, Any]:
    if model_jury_results is None:
        return {"present": False}
    jury = _safe_mapping(model_jury_results.get("jury"))
    aggregate = _safe_mapping(model_jury_results.get("aggregate"))
    adjudicator = _safe_mapping(model_jury_results.get("adjudicator"))
    return {
        "present": True,
        "path": str(path) if path is not None else None,
        "sha256": content_hash,
        "schema_version": model_jury_results.get("schema_version"),
        "status": model_jury_results.get("status"),
        "execution_mode": jury.get("execution_mode"),
        "provider_backed_model_calls": jury.get("provider_backed_model_calls") is True,
        "selected_juror_count": _safe_int(jury.get("selected_juror_count")),
        "judgment_counts": _safe_mapping(aggregate.get("judgment_counts")),
        "recommendation": aggregate.get("recommendation"),
        "improvement_request_count": len(
            _safe_list(aggregate.get("unique_improvement_requests"))
        ),
        "adjudicator_repo": adjudicator.get("repo"),
        "promotion_authority": adjudicator.get("promotion_authority") is True,
    }


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


def _behavior_evidence_summary(
    behavior: Mapping[str, Any] | None,
    behavior_episode: Mapping[str, Any] | None,
) -> dict[str, Any]:
    episode_summary = _safe_mapping((behavior_episode or {}).get("summary"))
    if behavior is None and behavior_episode is None:
        return {
            "present": False,
            "status": "insufficient_behavior_evidence",
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
            "status": str(summary.get("status") or "unknown"),
            "example_count": _safe_int(summary.get("total")),
            "source_count": _safe_int(episode_summary.get("source_count"), default=1),
            "status_counts": _safe_mapping(summary.get("status_counts")),
            "behavior_results_present": True,
            "behavior_episode_present": behavior_episode is not None,
            "behavior_evidence_kind": "behavior_results",
        }
    assert behavior_episode is not None
    return {
        "present": True,
        "status": str(episode_summary.get("status") or "unknown"),
        "example_count": _safe_int(episode_summary.get("total")),
        "source_count": _safe_int(episode_summary.get("source_count")),
        "status_counts": _episode_status_counts(behavior_episode),
        "behavior_results_present": False,
        "behavior_episode_present": True,
        "behavior_evidence_kind": "behavior_episode",
    }


def _promotion_policy(review: Mapping[str, Any]) -> dict[str, Any]:
    return _safe_mapping(review.get("promotion_policy"))


def _evidence_requirement_status(
    review: Mapping[str, Any], requirement_name: str
) -> str | None:
    for raw in _safe_list(review.get("evidence_requirements")):
        if not isinstance(raw, Mapping):
            continue
        if raw.get("name") == requirement_name:
            return _first_text(raw.get("status"))
    return None


def _missing_required_evidence(
    *,
    review: Mapping[str, Any],
    behavior_present: bool,
    oracle_matched: bool,
    proposal_present: bool,
    model_jury_present: bool,
) -> list[str]:
    policy = _promotion_policy(review)
    missing: list[str] = []
    if (
        bool(policy.get("requires_behavioral_evaluation", True))
        and not behavior_present
    ):
        missing.append("no_behavioral_evaluation_episode")
    if not oracle_matched and behavior_present:
        missing.append("no_matching_oracle_program_evidence_report_record")
    if not proposal_present:
        missing.append("no_program_refinement_proposal")
    if bool(policy.get("requires_jury_execution", True)):
        jury_status = _evidence_requirement_status(
            review, "model_jury_execution_episode"
        )
        if (
            jury_status != "satisfied_by_current_model_jury_episode"
            and not model_jury_present
        ):
            missing.append("no_model_jury_execution_episode")
    if bool(policy.get("requires_adjudicator_decision", True)):
        decision = _safe_mapping(review.get("decision"))
        if decision.get("status") != "decided" or not decision.get("outcome"):
            missing.append("no_promotion_adjudicator_decision")
    return missing


def _status_for_packet(
    *, behavior_present: bool, oracle_matched: bool, proposal: Mapping[str, Any]
) -> str:
    if (
        not behavior_present
        or proposal.get("status") == "insufficient_behavior_evidence"
    ):
        return "insufficient_behavior_evidence"
    if not oracle_matched:
        return "needs_more_evidence"
    return "review_packet_ready"


def _load_original_promotion_artifacts(
    manifest: Mapping[str, Any], manifest_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Path]]:
    paths = {
        "original_promotion_review_path": _surface_path(
            manifest,
            manifest_path,
            kind="promotion_review",
            default="promotion_review.json",
        ),
        "original_promotion_adjudication_request_path": _surface_path(
            manifest,
            manifest_path,
            kind="promotion_adjudication_request",
            default="promotion_adjudication_request.json",
        ),
        "original_promotion_decision_template_path": _surface_path(
            manifest,
            manifest_path,
            kind="promotion_decision_template",
            default="promotion_decision_template.json",
        ),
    }
    review = _load_json_object(
        paths["original_promotion_review_path"], label="original promotion review"
    )
    request = _load_json_object(
        paths["original_promotion_adjudication_request_path"],
        label="original promotion adjudication request",
    )
    decision_template = _load_json_object(
        paths["original_promotion_decision_template_path"],
        label="original promotion decision template",
    )
    _validate_schema(
        review,
        label="original promotion review",
        expected_schema=PROGRAM_PROMOTION_REVIEW_SCHEMA,
    )
    _validate_schema(
        request,
        label="original promotion adjudication request",
        expected_schema=PROGRAM_PROMOTION_ADJUDICATION_REQUEST_SCHEMA,
    )
    _validate_schema(
        decision_template,
        label="original promotion decision template",
        expected_schema=PROGRAM_PROMOTION_DECISION_SCHEMA,
    )
    if review.get("promotion_state") != "not_promoted":
        raise ProgramPromotionRefinementError(
            "original promotion review must keep promotion_state not_promoted"
        )
    if request.get("decision_record_template") != decision_template:
        raise ProgramPromotionRefinementError(
            "original promotion adjudication request decision template does not match original promotion decision template"
        )
    return review, request, decision_template, paths


def load_program_promotion_inputs(
    *,
    manifest_path: Path,
    oracle_report_path: Path,
    refinement_proposal_path: Path,
    model_jury_results_path: Path | None = None,
    runtime_episode_path: Path | None = None,
) -> dict[str, Any]:
    """Load and validate all existing evidence for local promotion-review refinement."""

    manifest_path = Path(os.path.abspath(manifest_path.expanduser()))
    oracle_report_path = Path(os.path.abspath(oracle_report_path.expanduser()))
    refinement_proposal_path = Path(
        os.path.abspath(refinement_proposal_path.expanduser())
    )
    candidate_snapshot = _snapshot_candidate_for_promotion_review(manifest_path)
    try:
        manifest = load_program_manifest(manifest_path)
        if manifest != candidate_snapshot.manifest:
            raise ProgramPromotionRefinementError(
                "candidate manifest changed after the artifact closure was validated"
            )
        behavior, behavior_path, behavior_hash = load_program_behavior_results(
            manifest,
            manifest_path,
        )
        if behavior_path is not None or behavior_hash is not None:
            _require_snapshot_artifact(
                candidate_snapshot,
                kind="behavior_results",
                loaded_path=behavior_path,
                loaded_hash=behavior_hash,
                loaded_payload=behavior if isinstance(behavior, Mapping) else None,
                label="program behavior results",
            )
        behavior_episode, behavior_episode_path, behavior_episode_hash = (
            _load_program_behavior_episode(manifest, manifest_path)
        )
        if behavior_episode_path is not None or behavior_episode_hash is not None:
            _require_snapshot_artifact(
                candidate_snapshot,
                kind="behavior_episode",
                loaded_path=behavior_episode_path,
                loaded_hash=behavior_episode_hash,
                loaded_payload=behavior_episode
                if isinstance(behavior_episode, Mapping)
                else None,
                label="program behavior episode",
            )
        oracle_observation = read_stable_json_artifact(
            oracle_report_path,
            label="program Oracle evidence report",
            error_type=ProgramPromotionRefinementError,
        )
        report = oracle_observation.payload
        if report.get("schema_version") != "program-oracle-evidence-report-v1":
            raise ProgramPromotionRefinementError(
                "program Oracle evidence report schema_version must be program-oracle-evidence-report-v1"
            )
        validate_program_oracle_report_non_authority(report)
    except ProgramRefinementError as exc:
        raise ProgramPromotionRefinementError(str(exc)) from exc
    identity = _identity_from_manifest(manifest)
    oracle_record, oracle_matched = _validate_oracle_report_identity(report, identity)
    manifest_hash = candidate_snapshot.manifest_sha256
    proposal_observation = read_stable_json_artifact(
        refinement_proposal_path,
        label="program refinement proposal",
        error_type=ProgramPromotionRefinementError,
    )
    proposal = _validate_refinement_proposal(
        proposal_observation.payload,
        identity=identity,
        manifest_path=manifest_path,
        manifest_hash=manifest_hash,
        oracle_report_path=oracle_observation.path,
        oracle_report_hash=oracle_observation.sha256,
        behavior_path=behavior_path,
        behavior_hash=behavior_hash,
    )
    model_jury_observation = (
        read_stable_json_artifact(
            model_jury_results_path,
            label="program model jury results",
            error_type=ProgramPromotionRefinementError,
        )
        if model_jury_results_path is not None
        else None
    )
    model_jury_results, model_jury_results_file, model_jury_results_hash = (
        _load_model_jury_results(
            model_jury_observation,
            identity=identity,
            manifest_path=manifest_path,
            manifest_hash=manifest_hash,
        )
    )
    runtime_observation = (
        read_stable_json_artifact(
            runtime_episode_path,
            label="program runtime episode",
            error_type=ProgramPromotionRefinementError,
        )
        if runtime_episode_path is not None
        else None
    )
    runtime_episode: dict[str, Any] | None = None
    runtime_episode_file: Path | None = None
    runtime_episode_hash: str | None = None
    if runtime_observation is not None:
        runtime_episode_file = runtime_observation.path
        runtime_episode = runtime_observation.payload
        if runtime_episode.get("schema_version") != PROGRAM_RUNTIME_EPISODE_SCHEMA:
            raise ProgramPromotionRefinementError(
                f"program runtime episode schema_version must be {PROGRAM_RUNTIME_EPISODE_SCHEMA}"
            )
        validate_program_runtime_episode_contract(
            runtime_episode,
            runtime_episode_path=runtime_episode_file,
            expected_manifest_path=manifest_path,
            expected_manifest=manifest,
            expected_manifest_sha256=manifest_hash,
            error_type=ProgramPromotionRefinementError,
        )
        runtime_episode_hash = runtime_observation.sha256
    review, request, decision_template, promotion_paths = (
        _load_original_promotion_artifacts(
            manifest,
            manifest_path,
        )
    )
    promotion_hashes: dict[str, str] = {}
    for kind, path_key, label, loaded_payload in (
        (
            "promotion_review",
            "original_promotion_review_path",
            "original promotion review",
            review,
        ),
        (
            "promotion_adjudication_request",
            "original_promotion_adjudication_request_path",
            "original promotion adjudication request",
            request,
        ),
        (
            "promotion_decision_template",
            "original_promotion_decision_template_path",
            "original promotion decision template",
            decision_template,
        ),
    ):
        loaded_path = promotion_paths[path_key]
        loaded_hash = _sha256_file(loaded_path)
        _require_snapshot_artifact(
            candidate_snapshot,
            kind=kind,
            loaded_path=loaded_path,
            loaded_hash=loaded_hash,
            loaded_payload=loaded_payload,
            label=label,
        )
        promotion_hashes[path_key] = loaded_hash
    _require_candidate_snapshot_unchanged(candidate_snapshot)
    return {
        "manifest_path": manifest_path,
        "manifest": manifest,
        "candidate_snapshot": candidate_snapshot,
        "manifest_hash": manifest_hash,
        "identity": identity,
        "behavior": behavior,
        "behavior_path": behavior_path,
        "behavior_hash": behavior_hash,
        "behavior_episode": behavior_episode,
        "behavior_episode_path": behavior_episode_path,
        "behavior_episode_hash": behavior_episode_hash,
        "oracle_report_path": oracle_report_path,
        "oracle_report": report,
        "oracle_report_hash": oracle_observation.sha256,
        "oracle_record": oracle_record,
        "oracle_matched": oracle_matched,
        "refinement_proposal_path": refinement_proposal_path,
        "refinement_proposal": proposal,
        "refinement_proposal_hash": proposal_observation.sha256,
        "model_jury_results": model_jury_results,
        "model_jury_results_path": model_jury_results_file,
        "model_jury_results_hash": model_jury_results_hash,
        "runtime_episode": runtime_episode,
        "runtime_episode_path": runtime_episode_file,
        "runtime_episode_hash": runtime_episode_hash,
        "promotion_review": review,
        "promotion_adjudication_request": request,
        "promotion_decision_template": decision_template,
        "promotion_paths": promotion_paths,
        "promotion_hashes": promotion_hashes,
    }


def validate_promotion_refinement_inputs(inputs: Mapping[str, Any]) -> None:
    """Validate cross-input consistency for a loaded promotion refinement packet."""

    report = _safe_mapping(inputs.get("oracle_report"))
    proposal = _safe_mapping(inputs.get("refinement_proposal"))
    review = _safe_mapping(inputs.get("promotion_review"))
    if report.get("schema_version") != "program-oracle-evidence-report-v1":
        raise ProgramPromotionRefinementError(
            "program Oracle evidence report schema_version must be program-oracle-evidence-report-v1"
        )
    if proposal.get("schema_version") != PROGRAM_REFINEMENT_PROPOSAL_SCHEMA:
        raise ProgramPromotionRefinementError(
            "program refinement proposal schema_version must be "
            + PROGRAM_REFINEMENT_PROPOSAL_SCHEMA
        )
    if review.get("promotion_state") != "not_promoted":
        raise ProgramPromotionRefinementError(
            "promotion review refinement requires an unpromoted original shell"
        )


def build_program_promotion_refinement(
    *,
    manifest_path: Path,
    oracle_report_path: Path,
    refinement_proposal_path: Path,
    model_jury_results_path: Path | None = None,
    runtime_episode_path: Path | None = None,
) -> dict[str, Any]:
    """Build a local non-authoritative refined promotion-review packet."""

    inputs = load_program_promotion_inputs(
        manifest_path=manifest_path,
        oracle_report_path=oracle_report_path,
        refinement_proposal_path=refinement_proposal_path,
        model_jury_results_path=model_jury_results_path,
        runtime_episode_path=runtime_episode_path,
    )
    validate_promotion_refinement_inputs(inputs)

    identity = _safe_mapping(inputs["identity"])
    behavior = inputs.get("behavior")
    behavior_episode = inputs.get("behavior_episode")
    behavior_present = isinstance(behavior, Mapping) or isinstance(
        behavior_episode,
        Mapping,
    )
    behavior_summary = _behavior_evidence_summary(
        behavior if isinstance(behavior, Mapping) else None,
        behavior_episode if isinstance(behavior_episode, Mapping) else None,
    )
    report = _safe_mapping(inputs.get("oracle_report"))
    proposal = _safe_mapping(inputs.get("refinement_proposal"))
    review = _safe_mapping(inputs.get("promotion_review"))
    request = _safe_mapping(inputs.get("promotion_adjudication_request"))
    promotion_paths = _safe_mapping(inputs.get("promotion_paths"))
    oracle_matched = bool(inputs.get("oracle_matched"))
    model_jury_results = inputs.get("model_jury_results")
    model_jury_present = isinstance(model_jury_results, Mapping)
    runtime_episode = inputs.get("runtime_episode")
    runtime_episode_present = isinstance(runtime_episode, Mapping)
    missing = _missing_required_evidence(
        review=review,
        behavior_present=behavior_present,
        oracle_matched=oracle_matched,
        proposal_present=True,
        model_jury_present=model_jury_present,
    )
    model_jury_missing = "no_model_jury_execution_episode" in missing
    adjudicator_missing = "no_promotion_adjudicator_decision" in missing
    ready_for_adjudicator_review = not missing
    adjudication_status = (
        "ready_for_adjudicator_review"
        if ready_for_adjudicator_review
        else "not_ready_missing_required_evidence"
    )
    behavior_path = inputs.get("behavior_path")
    behavior_path_text = (
        str(Path(behavior_path).resolve())
        if isinstance(behavior_path, Path) and behavior_path.exists()
        else None
    )
    behavior_episode_path = inputs.get("behavior_episode_path")
    behavior_episode_path_text = (
        str(Path(behavior_episode_path).resolve())
        if isinstance(behavior_episode_path, Path) and behavior_episode_path.exists()
        else None
    )
    model_jury_results_path = inputs.get("model_jury_results_path")
    model_jury_results_path_text = (
        str(Path(model_jury_results_path).resolve())
        if isinstance(model_jury_results_path, Path)
        and model_jury_results_path.exists()
        else None
    )
    runtime_episode_path = inputs.get("runtime_episode_path")
    runtime_episode_path_text = (
        str(Path(runtime_episode_path).resolve())
        if isinstance(runtime_episode_path, Path) and runtime_episode_path.exists()
        else None
    )
    manifest_path = Path(inputs["manifest_path"]).resolve()
    oracle_report_path = Path(inputs["oracle_report_path"]).resolve()
    refinement_proposal_path = Path(inputs["refinement_proposal_path"]).resolve()
    original_promotion_review_path = Path(
        promotion_paths["original_promotion_review_path"]
    ).resolve()
    original_promotion_adjudication_request_path = Path(
        promotion_paths["original_promotion_adjudication_request_path"]
    ).resolve()
    original_promotion_decision_template_path = Path(
        promotion_paths["original_promotion_decision_template_path"]
    ).resolve()
    promotion_hashes = _safe_mapping(inputs.get("promotion_hashes"))

    packet = {
        "schema_version": PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA,
        "status": _status_for_packet(
            behavior_present=behavior_present,
            oracle_matched=oracle_matched,
            proposal=proposal,
        ),
        "promotion_state": "not_promoted",
        "candidate_status": str(review.get("candidate_status") or "exploratory"),
        "identity": identity,
        "created_from": {
            "manifest_path": str(manifest_path),
            "manifest_sha256": inputs.get("manifest_hash"),
            "behavior_results_path": behavior_path_text,
            "behavior_results_sha256": inputs.get("behavior_hash")
            if behavior_path_text is not None
            else None,
            "behavior_episode_path": behavior_episode_path_text,
            "behavior_episode_sha256": inputs.get("behavior_episode_hash")
            if behavior_episode_path_text is not None
            else None,
            "oracle_report_path": str(oracle_report_path),
            "oracle_report_sha256": inputs.get("oracle_report_hash"),
            "refinement_proposal_path": str(refinement_proposal_path),
            "refinement_proposal_sha256": inputs.get("refinement_proposal_hash"),
            "model_jury_results_path": model_jury_results_path_text,
            "model_jury_results_sha256": inputs.get("model_jury_results_hash")
            if model_jury_results_path_text is not None
            else None,
            "runtime_episode_path": runtime_episode_path_text,
            "runtime_episode_sha256": inputs.get("runtime_episode_hash")
            if runtime_episode_path_text is not None
            else None,
            "original_promotion_review_path": str(original_promotion_review_path),
            "original_promotion_review_sha256": promotion_hashes.get(
                "original_promotion_review_path"
            ),
            "original_promotion_adjudication_request_path": str(
                original_promotion_adjudication_request_path
            ),
            "original_promotion_adjudication_request_sha256": promotion_hashes.get(
                "original_promotion_adjudication_request_path"
            ),
            "original_promotion_decision_template_path": str(
                original_promotion_decision_template_path
            ),
            "original_promotion_decision_template_sha256": promotion_hashes.get(
                "original_promotion_decision_template_path"
            ),
        },
        "evidence_summary": {
            "behavior": behavior_summary,
            "oracle_report": {
                "present": True,
                "status": report.get("status"),
                "total_records": int(report.get("total_records") or 0),
                "record_matched": oracle_matched,
            },
            "refinement_proposal": {
                "present": True,
                "status": proposal.get("status"),
                "proposal_id": proposal.get("proposal_id"),
            },
            "model_jury_results": _model_jury_summary(
                model_jury_results if isinstance(model_jury_results, Mapping) else None,
                path=model_jury_results_path
                if isinstance(model_jury_results_path, Path)
                else None,
                content_hash=inputs.get("model_jury_results_hash")
                if isinstance(inputs.get("model_jury_results_hash"), str)
                else None,
            ),
            "runtime_episode": _runtime_episode_summary(
                runtime_episode if isinstance(runtime_episode, Mapping) else None,
                path=runtime_episode_path
                if isinstance(runtime_episode_path, Path)
                else None,
                content_hash=inputs.get("runtime_episode_hash")
                if isinstance(inputs.get("runtime_episode_hash"), str)
                else None,
            ),
        },
        "review_readiness": {
            "behavior_evidence_present": behavior_present,
            "oracle_report_present": True,
            "refinement_proposal_present": True,
            "model_jury_execution_present": model_jury_present
            or not model_jury_missing,
            "adjudicator_decision_present": not adjudicator_missing,
            "ready_for_adjudicator_review": ready_for_adjudicator_review,
            "missing_required_evidence": missing,
        },
        "promotion_review_delta": {
            "behavioral_evaluation_episode": "satisfied_by_current_behavior_episode"
            if behavior_present
            else "missing_behavior_evidence",
            "oracle_interpretation": "satisfied_by_explicit_oracle_report"
            if oracle_matched
            else "explicit_oracle_report_without_matching_record",
            "bounded_refinement_proposal": "available_non_authoritative",
            "model_jury_execution": "satisfied_by_explicit_model_jury_results"
            if model_jury_present
            else "missing_model_jury_execution",
            "promotion_authority": "unchanged_required_adjudicator",
        },
        "adjudication_packet": {
            "status": adjudication_status,
            "decision_question": request.get("decision_question"),
            "original_allowed_outcomes": list(request.get("allowed_outcomes") or []),
            "local_packet_recommended_review_outcomes": [
                "withhold",
                "reject",
                "request_more_evidence",
            ],
            "forbidden_outcomes_without_explicit_adjudicator": ["promote"],
            "evidence_refs": [
                "manifest.json",
                "promotion_review.json",
                "promotion_adjudication_request.json",
                "promotion_decision_template.json",
                *(["behavior_results.json"] if behavior_path_text is not None else []),
                *(
                    ["behavior_episode.json"]
                    if behavior_episode_path_text is not None
                    else []
                ),
                "oracle_report",
                "refinement_proposal",
                *(
                    ["model_jury_results"]
                    if model_jury_results_path_text is not None
                    else []
                ),
                *(["runtime_episode"] if runtime_episode_present else []),
            ],
        },
        "non_authority": dict(_REFINED_PACKET_NON_AUTHORITY),
        "notes": [
            "This is a local promotion-review evidence packet only.",
            "It consumes existing behavior evidence, an explicit Oracle report, an explicit refinement proposal, and optional explicit model-jury results without mutating generated program artifacts.",
            "Promotion remains unavailable without an explicit adjudicator decision and any other required local evidence.",
            "Oracle interpretation remains non-authoritative and cannot rank, prune, promote, or block candidates.",
        ],
    }
    candidate_snapshot = inputs.get("candidate_snapshot")
    if not isinstance(candidate_snapshot, CandidateArtifactSnapshot):
        raise ProgramPromotionRefinementError(
            "promotion review inputs are missing the validated candidate artifact snapshot"
        )
    _require_candidate_snapshot_unchanged(candidate_snapshot)
    return packet


def _prepare_refinement_output_path(packet: Mapping[str, Any], out_path: Path) -> Path:
    try:
        return prepare_sidecar_output_path(
            out_path,
            payload=packet,
            artifact_label="promotion review",
            protected_names=_FORBIDDEN_SOURCE_OUTPUT_NAMES,
            payload_artifact_root_policy="forbid",
        )
    except ValueError as exc:
        raise ProgramPromotionRefinementError(str(exc)) from exc


def _validate_packet_candidate_closure(packet: Mapping[str, Any]) -> None:
    created_from = _safe_mapping(packet.get("created_from"))
    validate_program_promotion_review_refined_contract(
        packet,
        error_type=ProgramPromotionRefinementError,
    )
    manifest_path_text = _first_text(created_from.get("manifest_path"))
    manifest_hash = _first_text(created_from.get("manifest_sha256"))
    if manifest_path_text is None or manifest_hash is None:
        raise ProgramPromotionRefinementError(
            "promotion review packet must include manifest path and hash provenance"
        )
    snapshot = _snapshot_candidate_for_promotion_review(Path(manifest_path_text))
    if snapshot.manifest_sha256 != manifest_hash:
        raise ProgramPromotionRefinementError(
            "promotion review packet manifest hash is stale at publication"
        )
    for kind, path_key, hash_key, required in (
        (
            "behavior_results",
            "behavior_results_path",
            "behavior_results_sha256",
            False,
        ),
        (
            "behavior_episode",
            "behavior_episode_path",
            "behavior_episode_sha256",
            False,
        ),
        (
            "promotion_review",
            "original_promotion_review_path",
            "original_promotion_review_sha256",
            True,
        ),
        (
            "promotion_adjudication_request",
            "original_promotion_adjudication_request_path",
            "original_promotion_adjudication_request_sha256",
            True,
        ),
        (
            "promotion_decision_template",
            "original_promotion_decision_template_path",
            "original_promotion_decision_template_sha256",
            True,
        ),
    ):
        path_text = _first_text(created_from.get(path_key))
        content_hash = _first_text(created_from.get(hash_key))
        if path_text is None and content_hash is None and not required:
            continue
        if path_text is None or content_hash is None:
            raise ProgramPromotionRefinementError(
                f"promotion review packet has incomplete {kind} provenance"
            )
        artifact = next(
            (candidate for candidate in snapshot.artifacts if candidate.kind == kind),
            None,
        )
        if (
            artifact is None
            or Path(path_text).expanduser().resolve() != artifact.path
            or content_hash != artifact.sha256
        ):
            raise ProgramPromotionRefinementError(
                f"promotion review packet {kind} provenance is stale at publication"
            )

    _require_candidate_snapshot_unchanged(snapshot)


def write_program_promotion_refinement(
    packet: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    """Write the refined local promotion-review packet and return its payload."""

    lexical_target = Path(os.path.abspath(out_path.expanduser()))
    target = _prepare_refinement_output_path(packet, lexical_target)
    if target != lexical_target:
        raise ProgramPromotionRefinementError(
            "promotion review output path must not resolve through symlink components"
        )
    payload = dict(packet)
    _validate_packet_candidate_closure(payload)
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_publish_bytes(
        target,
        content,
        label="promotion review",
        precommit=lambda: _validate_packet_candidate_closure(payload),
        error_type=ProgramPromotionRefinementError,
        indeterminate_error_type=ProgramPromotionRefinementCommitIndeterminateError,
    )
    return payload
