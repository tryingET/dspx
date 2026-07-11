from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import (
    ArtifactEnvelopePolicy,
    identity_matches_exactly,
    prepare_sidecar_output_path,
    require_false_envelope_flags,
    sha256_file as _artifact_sha256_file,
    validate_artifact_envelope,
)
from dspx.services.program_external_authority_export import (
    ProgramExternalAuthorityExportError,
    validate_program_external_authority_export_preflight_contract,
)
from dspx.services.program_evidence_adjudication_validation import (
    validate_program_evidence_adjudication_contract,
)
from dspx.services.program_evidence_closure import (
    CandidateArtifactSnapshot,
    open_directory_no_symlinks,
    snapshot_candidate_artifact_closure,
)
from dspx.services.program_jury_result_validation import (
    PROGRAM_JURY_RESULTS_SCHEMA,
    validate_program_jury_results_contract,
)
from dspx.services.program_meta_adjudication import (
    ProgramMetaAdjudicationError,
    validate_program_meta_adjudication_plan_contract,
)
from dspx.services.program_model_jury_validation import (
    PROGRAM_MODEL_JURY_RESULTS_SCHEMA,
    validate_program_model_jury_results_contract,
)
from dspx.services.program_oracle_publication import (
    ProgramOraclePublicationError,
    validate_program_oracle_publication_preflight_contract,
    validate_program_oracle_publication_receipt_contract,
)
from dspx.services.program_runtime_episode import (
    PROGRAM_RUNTIME_EPISODE_SCHEMA,
    validate_program_runtime_episode_contract,
)
from dspx.services.program_promotion_decision import (
    ProgramPromotionDecisionError,
    validate_program_promotion_decision_record_contract,
)
from dspx.services.program_promotion_plan import (
    ProgramPromotionPlanError,
    validate_program_promotion_plan_contract,
)
from dspx.services.program_promotion_refinement import (
    ProgramPromotionRefinementError,
    validate_program_promotion_review_refined_contract,
)
from dspx.services.program_refinement_comparison import (
    ProgramRefinementComparisonError,
    validate_program_refinement_candidate_comparison_contract,
)
from dspx.services.program_refinement_gepa_candidate_contracts import (
    validate_program_refinement_gepa_result_contract,
)
from dspx.services.program_refinement import (
    ProgramRefinementError,
    load_program_behavior_results,
    validate_program_refinement_proposal_contract,
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
PROGRAM_META_ADJUDICATION_PLAN_SCHEMA = "program-meta-adjudication-plan-v1"
PROGRAM_EXTERNAL_AUTHORITY_EXPORT_PREFLIGHT_SCHEMA = (
    "program-external-authority-export-preflight-v1"
)
PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA = (
    "program-oracle-shared-publication-preflight-v1"
)
PROGRAM_ORACLE_PUBLICATION_RECEIPT_SCHEMA = (
    "program-oracle-shared-publication-receipt-v1"
)
PROGRAM_BEHAVIOR_EPISODE_SCHEMA = "program-behavior-episode-v1"
GEN_GENERATION_GATE_PREFLIGHT_SCHEMA = "gen-generation-gate-preflight-v1"
GEN_FITNESS_RESULTS_SCHEMA = "gen-fitness-results-v1"
PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA = "program-evidence-adjudication-v1"
PROGRAM_REFINEMENT_GEPA_RESULT_SCHEMA = "program-refinement-gepa-result-v1"
ACTIVATION_PACKET_SCHEMA = "generated-cognition-program-production-activation-packet-v1"

_FORBIDDEN_OUTPUT_NAMES = {
    "manifest.json",
    "manifest.json.meta.json",
    "promotion_review.json",
    "promotion_adjudication_request.json",
    "promotion_decision_template.json",
    "promotion_review_refined.json",
    "promotion_decision_record.json",
    "promotion_plan.json",
    "jury_results.json",
    "model_jury_results.json",
    "behavior_results.json",
    "behavior_episode.json",
    "oracle_evidence.json",
    "execution_episode.json",
    "gepa_refinement_result.json",
}


class ProgramCandidateStateError(ValueError):
    """Raised when local program candidate state inputs are invalid."""


class ProgramCandidateStateCommitIndeterminateError(ProgramCandidateStateError):
    """Raised after replacement when directory durability cannot be confirmed."""


def _require_snapshot_unchanged(
    original: CandidateArtifactSnapshot,
    *,
    label: str,
) -> None:
    try:
        current = snapshot_candidate_artifact_closure(original.manifest_path)
    except (OSError, ValueError) as exc:
        raise ProgramCandidateStateError(
            f"{label} artifact closure changed during state construction: {exc}"
        ) from exc
    if current != original:
        raise ProgramCandidateStateError(
            f"{label} artifact closure changed during state construction"
        )


def _require_loaded_hash_matches_snapshot(
    snapshot: CandidateArtifactSnapshot,
    *,
    kind: str,
    loaded_hash: str | None,
    label: str,
) -> None:
    expected = next(
        (artifact.sha256 for artifact in snapshot.artifacts if artifact.kind == kind),
        None,
    )
    if expected is not None and loaded_hash != expected:
        raise ProgramCandidateStateError(
            f"{label} did not load from the validated candidate snapshot"
        )


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
        raise ProgramCandidateStateError(
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


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _sha256_file(path: Path) -> str:
    return _artifact_sha256_file(path)


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
    return identity_matches_exactly(actual, expected)


def _identity_role(
    actual: Mapping[str, Any],
    *,
    candidate_identity: Mapping[str, str | None],
    source_identity: Mapping[str, str | None] | None = None,
) -> str:
    if _identity_exactly_matches(actual, candidate_identity):
        return "candidate"
    if source_identity is not None and _identity_exactly_matches(
        actual, source_identity
    ):
        return "source"
    return "unrelated"


def _assert_schema(payload: Mapping[str, Any], *, label: str, schema: str) -> None:
    validate_artifact_envelope(
        payload,
        label=label,
        policy=ArtifactEnvelopePolicy(schema_version=schema),
        error_type=ProgramCandidateStateError,
    )


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
        raise ProgramCandidateStateError(
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
        raise ProgramCandidateStateError(
            "program behavior episode hash does not match manifest declaration(s): "
            + ", ".join(sorted(mismatches))
        )
    return episode, episode_path, actual_hash


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
    require_false_envelope_flags(
        payload,
        section="non_authority",
        keys=keys,
        label=label,
        error_type=ProgramCandidateStateError,
    )


def _validate_export_preflight_artifact_hashes(
    export_preflight: Mapping[str, Any],
    *,
    current_manifest_hash: str,
    source_manifest_hash: str | None,
    decision_hash: str | None,
    comparison_hash: str | None,
) -> None:
    artifact_hashes = _safe_mapping(export_preflight.get("artifact_hashes"))
    valid_manifest_hashes = {current_manifest_hash}
    if source_manifest_hash is not None:
        valid_manifest_hashes.add(source_manifest_hash)
    if artifact_hashes.get("manifest_sha256") not in valid_manifest_hashes:
        raise ProgramCandidateStateError(
            "external authority export preflight manifest_sha256 does not match candidate/source manifest"
        )
    for field, expected_hash, label in (
        ("decision_record_sha256", decision_hash, "decision record"),
        ("comparison_sha256", comparison_hash, "comparison"),
    ):
        if expected_hash is not None and artifact_hashes.get(field) != expected_hash:
            raise ProgramCandidateStateError(
                f"external authority export preflight {field} does not match supplied {label}"
            )

    refs_by_kind: dict[str, Mapping[str, Any]] = {}
    planned_payload = _safe_mapping(export_preflight.get("planned_payload"))
    for ref in _safe_list(planned_payload.get("evidence_refs")):
        if not isinstance(ref, Mapping):
            raise ProgramCandidateStateError(
                "external authority export preflight evidence refs must be objects"
            )
        kind = _first_text(ref.get("kind"))
        raw_path = _first_text(ref.get("path"))
        expected_hash = _first_text(ref.get("sha256"))
        if kind is None or raw_path is None or expected_hash is None:
            raise ProgramCandidateStateError(
                "external authority export preflight evidence refs must include kind, path, and sha256"
            )
        refs_by_kind[kind] = ref

    expected_refs = {
        "program_manifest": artifact_hashes.get("manifest_sha256"),
        "promotion_decision_record": decision_hash,
        "candidate_comparison": comparison_hash,
    }
    for kind, expected_hash in expected_refs.items():
        if expected_hash is None:
            continue
        ref = refs_by_kind.get(kind)
        if ref is None:
            raise ProgramCandidateStateError(
                f"external authority export preflight is missing {kind} evidence ref"
            )
        if ref.get("sha256") != expected_hash:
            raise ProgramCandidateStateError(
                f"external authority export preflight {kind} evidence ref hash mismatch"
            )


def _validate_program_jury_result_artifact_hashes(
    jury_results: Mapping[str, Any],
    *,
    current_manifest_path: Path,
    current_manifest_hash: str,
    source_manifest_path: Path | None,
    source_manifest_hash: str | None,
    behavior_hash: str | None,
    behavior_episode_hash: str | None,
) -> None:
    valid_manifest_refs = {current_manifest_path: current_manifest_hash}
    if source_manifest_path is not None and source_manifest_hash is not None:
        valid_manifest_refs[source_manifest_path] = source_manifest_hash
    validate_program_jury_results_contract(
        jury_results,
        valid_manifest_refs=valid_manifest_refs,
        label="program jury results",
        error_type=ProgramCandidateStateError,
        current_manifest_path=current_manifest_path,
        current_behavior_results_sha256=behavior_hash,
        current_behavior_episode_sha256=behavior_episode_hash,
        outside_root_message="outside the bound manifest root",
    )


def _validate_meta_adjudication_plan_sidecar_freshness(
    meta_adjudication_plan: Mapping[str, Any],
    *,
    supplied_sidecar_refs: Mapping[str, tuple[Path, str]],
) -> None:
    sidecars = _safe_mapping(meta_adjudication_plan.get("sidecars"))
    for key, raw_status in sidecars.items():
        if not isinstance(raw_status, Mapping) or raw_status.get("present") is not True:
            continue
        status = _safe_mapping(raw_status)
        if status.get("status") != "present" or status.get(
            "schema_version"
        ) != status.get("required_schema"):
            raise ProgramCandidateStateError(
                f"meta-adjudication plan {key} sidecar must have present status and expected schema"
            )
        raw_path = _first_text(status.get("path"))
        claimed_hash = _first_text(status.get("sha256"))
        if raw_path is None or claimed_hash is None:
            raise ProgramCandidateStateError(
                f"meta-adjudication plan {key} sidecar ref must include path and sha256"
            )
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise ProgramCandidateStateError(
                f"meta-adjudication plan {key} sidecar is missing: {path}"
            )
        if _sha256_file(path) != claimed_hash:
            raise ProgramCandidateStateError(
                f"meta-adjudication plan {key} sidecar sha256 does not match current file"
            )
        supplied_ref = supplied_sidecar_refs.get(key)
        if supplied_ref is None:
            continue
        supplied_path, supplied_hash = supplied_ref
        if path != supplied_path or claimed_hash != supplied_hash:
            raise ProgramCandidateStateError(
                f"meta-adjudication plan {key} sidecar does not match supplied {key}"
            )


def _validate_optional_inputs(
    *,
    candidate_identity: Mapping[str, str | None],
    source_identity: Mapping[str, str | None] | None,
    refinement_proposal: Mapping[str, Any] | None,
    refinement_proposal_path: Path | None,
    refinement_proposal_hash: str | None,
    review: Mapping[str, Any] | None,
    review_path: Path | None,
    decision: Mapping[str, Any] | None,
    jury_results: Mapping[str, Any] | None,
    model_jury_results: Mapping[str, Any] | None,
    comparison: Mapping[str, Any] | None,
    comparison_path: Path | None,
    promotion_plan: Mapping[str, Any] | None,
    export_preflight: Mapping[str, Any] | None,
    meta_adjudication_plan: Mapping[str, Any] | None,
    activation_packet: Mapping[str, Any] | None,
    oracle_publication_preflight: Mapping[str, Any] | None,
    oracle_publication_receipt: Mapping[str, Any] | None,
    gepa_refinement: Mapping[str, Any] | None,
    current_manifest_path: Path,
    current_manifest_hash: str,
    oracle_report_path: Path | None,
    oracle_report_hash: str | None,
    current_program_hash: str | None,
    source_manifest_path: Path | None,
    source_manifest_hash: str | None,
    source_program_hash: str | None,
    behavior_path: Path | None,
    behavior_hash: str | None,
    behavior_episode_path: Path | None,
    behavior_episode_hash: str | None,
    source_behavior_path: Path | None,
    source_behavior_hash: str | None,
    source_behavior_episode_path: Path | None,
    source_behavior_episode_hash: str | None,
    model_jury_results_path: Path | None,
    model_jury_results_hash: str | None,
    sidecar_hashes: Mapping[str, str | None],
    comparison_hash: str | None,
    supplied_sidecar_refs: Mapping[str, tuple[Path, str]],
) -> dict[str, Any] | None:
    validated_comparison: dict[str, Any] | None = None
    source_or_candidate = [candidate_identity]
    if source_identity is not None:
        source_or_candidate.append(source_identity)
    valid_manifest_refs = {current_manifest_path: current_manifest_hash}
    if source_manifest_path is not None and source_manifest_hash is not None:
        valid_manifest_refs[source_manifest_path] = source_manifest_hash

    def refs_for_identity(
        identity: Mapping[str, Any],
        *,
        current_path: Path | None,
        current_hash: str | None,
        source_path: Path | None,
        source_hash: str | None,
    ) -> dict[Path, str]:
        if source_identity is not None and _identity_exactly_matches(
            identity, source_identity
        ):
            return {source_path: source_hash} if source_path and source_hash else {}
        return {current_path: current_hash} if current_path and current_hash else {}

    valid_model_jury_results_refs: dict[Path, str] = {}
    if model_jury_results_path is not None and model_jury_results_hash is not None:
        valid_model_jury_results_refs[model_jury_results_path] = model_jury_results_hash

    if refinement_proposal is not None:
        proposal_identity = _safe_mapping(refinement_proposal.get("identity"))
        expected_proposal_identity = (
            source_identity
            if source_identity is not None
            and _identity_exactly_matches(proposal_identity, source_identity)
            else candidate_identity
        )
        try:
            validate_program_refinement_proposal_contract(
                refinement_proposal,
                expected_identity=expected_proposal_identity,
                valid_manifest_refs=valid_manifest_refs,
                valid_oracle_report_refs={oracle_report_path: oracle_report_hash}
                if oracle_report_path is not None and oracle_report_hash is not None
                else None,
                valid_behavior_results_refs=refs_for_identity(
                    expected_proposal_identity,
                    current_path=behavior_path,
                    current_hash=behavior_hash,
                    source_path=source_behavior_path,
                    source_hash=source_behavior_hash,
                ),
                error_type=ProgramCandidateStateError,
            )
        except ProgramRefinementError as exc:
            raise ProgramCandidateStateError(str(exc)) from exc

    if review is not None:
        if review_path is None:
            raise ProgramCandidateStateError(
                "refined promotion review path is required for contract validation"
            )
        review_identity = _safe_mapping(review.get("identity"))
        expected_review_identity = (
            source_identity
            if source_identity is not None
            and _identity_exactly_matches(review_identity, source_identity)
            else candidate_identity
        )
        try:
            validate_program_promotion_review_refined_contract(
                review,
                refined_review_path=review_path,
                expected_identity=expected_review_identity,
                valid_manifest_refs=valid_manifest_refs,
                valid_oracle_report_refs={oracle_report_path: oracle_report_hash}
                if oracle_report_path is not None and oracle_report_hash is not None
                else None,
                valid_refinement_proposal_refs={
                    refinement_proposal_path: refinement_proposal_hash
                }
                if refinement_proposal_path is not None
                and refinement_proposal_hash is not None
                else None,
                valid_behavior_results_refs=refs_for_identity(
                    expected_review_identity,
                    current_path=behavior_path,
                    current_hash=behavior_hash,
                    source_path=source_behavior_path,
                    source_hash=source_behavior_hash,
                ),
                valid_behavior_episode_refs=refs_for_identity(
                    expected_review_identity,
                    current_path=behavior_episode_path,
                    current_hash=behavior_episode_hash,
                    source_path=source_behavior_episode_path,
                    source_hash=source_behavior_episode_hash,
                ),
                valid_model_jury_results_refs=valid_model_jury_results_refs,
                error_type=ProgramCandidateStateError,
            )
        except ProgramPromotionRefinementError as exc:
            raise ProgramCandidateStateError(str(exc)) from exc

    if decision is not None:
        try:
            validate_program_promotion_decision_record_contract(
                decision,
                expected_identities=source_or_candidate,
            )
        except ProgramPromotionDecisionError as exc:
            raise ProgramCandidateStateError(str(exc)) from exc

    if jury_results is not None:
        jury_identity = _safe_mapping(jury_results.get("identity"))
        if not any(
            _identity_exactly_matches(jury_identity, item)
            for item in source_or_candidate
        ):
            raise ProgramCandidateStateError(
                "program jury results identity does not match candidate/source identity"
            )
        _validate_program_jury_result_artifact_hashes(
            jury_results,
            current_manifest_path=current_manifest_path,
            current_manifest_hash=current_manifest_hash,
            source_manifest_path=source_manifest_path,
            source_manifest_hash=source_manifest_hash,
            behavior_hash=behavior_hash,
            behavior_episode_hash=behavior_episode_hash,
        )

    if model_jury_results is not None:
        valid_manifest_refs = {current_manifest_path: current_manifest_hash}
        if source_manifest_path is not None and source_manifest_hash is not None:
            valid_manifest_refs[source_manifest_path] = source_manifest_hash
        validate_program_model_jury_results_contract(
            model_jury_results,
            label="program model jury results",
            error_type=ProgramCandidateStateError,
            valid_manifest_refs=valid_manifest_refs,
        )
        model_jury_identity = _safe_mapping(model_jury_results.get("identity"))
        if not any(
            _identity_exactly_matches(model_jury_identity, item)
            for item in source_or_candidate
        ):
            raise ProgramCandidateStateError(
                "program model jury results identity does not match candidate/source identity"
            )

    if comparison is not None:
        if comparison_path is None:
            raise ProgramCandidateStateError(
                "program candidate comparison path is required for contract validation"
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
        comparison_created_from = _safe_mapping(comparison.get("created_from"))
        comparison_candidate_manifest_path = current_manifest_path
        comparison_source_manifest_path = source_manifest_path
        if source_matches and not candidate_matches:
            raw_candidate_manifest_path = _first_text(
                comparison_created_from.get("candidate_manifest_path")
            )
            if raw_candidate_manifest_path is None:
                raise ProgramCandidateStateError(
                    "program candidate comparison missing candidate_manifest_path"
                )
            comparison_candidate_manifest_path = (
                Path(raw_candidate_manifest_path).expanduser().resolve()
            )
            comparison_source_manifest_path = current_manifest_path
        try:
            validated_comparison = (
                validate_program_refinement_candidate_comparison_contract(
                    comparison_path=comparison_path,
                    candidate_manifest_path=comparison_candidate_manifest_path,
                    source_manifest_path=comparison_source_manifest_path,
                )
            )
        except (ProgramRefinementComparisonError, ProgramRefinementError) as exc:
            raise ProgramCandidateStateError(str(exc)) from exc

    if gepa_refinement is not None:
        gepa_identity = _safe_mapping(gepa_refinement.get("source_identity"))
        gepa_role = _identity_role(
            gepa_identity,
            candidate_identity=candidate_identity,
            source_identity=source_identity,
        )
        if gepa_role == "unrelated":
            raise ProgramCandidateStateError(
                "program GEPA refinement identity does not match candidate/source identity"
            )
        gepa_program_hash = (
            source_program_hash if gepa_role == "source" else current_program_hash
        )
        validate_program_refinement_gepa_result_contract(
            gepa_refinement,
            expected_identities=source_or_candidate,
            error_type=ProgramCandidateStateError,
            source_program_hash=gepa_program_hash,
        )

    if promotion_plan is not None:
        try:
            validate_program_promotion_plan_contract(
                promotion_plan,
                expected_identities=[candidate_identity],
                valid_manifest_hashes={current_manifest_hash},
                expected_candidate_manifest_path=current_manifest_path,
                decision_record_sha256=sidecar_hashes.get("decision_record"),
                comparison_sha256=comparison_hash,
            )
        except ProgramPromotionPlanError as exc:
            raise ProgramCandidateStateError(str(exc)) from exc

    if oracle_publication_preflight is not None:
        created_from = _safe_mapping(oracle_publication_preflight.get("created_from"))
        preflight_path = _first_text(created_from.get("preflight_path"))
        try:
            validate_program_oracle_publication_preflight_contract(
                oracle_publication_preflight,
                expected_manifest_path=current_manifest_path,
                expected_manifest_hash=current_manifest_hash,
                preflight_path=Path(preflight_path) if preflight_path else None,
            )
        except ProgramOraclePublicationError as exc:
            raise ProgramCandidateStateError(str(exc)) from exc
        preflight_identity = _safe_mapping(oracle_publication_preflight.get("identity"))
        if not any(
            _identity_exactly_matches(preflight_identity, item)
            for item in source_or_candidate
        ):
            raise ProgramCandidateStateError(
                "Oracle publication preflight identity does not match candidate/source identity"
            )

    if oracle_publication_receipt is not None:
        try:
            validate_program_oracle_publication_receipt_contract(
                oracle_publication_receipt,
                expected_identities=source_or_candidate,
                preflight=oracle_publication_preflight,
                preflight_sha256=sidecar_hashes.get("oracle_publication_preflight"),
            )
        except ProgramOraclePublicationError as exc:
            raise ProgramCandidateStateError(str(exc)) from exc

    if (
        oracle_publication_preflight is not None
        and oracle_publication_receipt is not None
    ):
        if oracle_publication_preflight.get(
            "publication_id"
        ) != oracle_publication_receipt.get("publication_id"):
            raise ProgramCandidateStateError(
                "Oracle publication preflight/receipt publication_id mismatch"
            )

    if export_preflight is not None:
        valid_manifest_hashes = {current_manifest_hash}
        if source_manifest_hash is not None:
            valid_manifest_hashes.add(source_manifest_hash)
        try:
            validate_program_external_authority_export_preflight_contract(
                export_preflight,
                expected_identities=source_or_candidate,
                valid_manifest_hashes=valid_manifest_hashes,
                decision_record_sha256=sidecar_hashes.get("decision_record"),
                comparison_sha256=comparison_hash,
            )
        except ProgramExternalAuthorityExportError as exc:
            raise ProgramCandidateStateError(str(exc)) from exc

    if meta_adjudication_plan is not None:
        valid_manifest_hashes = {current_manifest_hash}
        if source_manifest_hash is not None:
            valid_manifest_hashes.add(source_manifest_hash)
        try:
            validate_program_meta_adjudication_plan_contract(
                meta_adjudication_plan,
                expected_identities=source_or_candidate,
                valid_manifest_hashes=valid_manifest_hashes,
                supplied_sidecar_refs=supplied_sidecar_refs,
                error_type=ProgramCandidateStateError,
            )
        except ProgramMetaAdjudicationError as exc:
            raise ProgramCandidateStateError(str(exc)) from exc

    if activation_packet is not None:
        if activation_packet.get("status") not in {
            "blocked",
            "ready_for_domain_adjudication",
            "ready_for_canonical_binding",
            "ready_for_canonical_binding_verification",
            "ready_for_rollout_preflight",
        }:
            raise ProgramCandidateStateError("activation packet status is unsupported")
        packet_identity = _safe_mapping(activation_packet.get("identity"))
        if not any(
            _identity_exactly_matches(packet_identity, item)
            for item in source_or_candidate
        ):
            raise ProgramCandidateStateError(
                "activation packet identity does not match candidate/source identity"
            )
        effect = _safe_mapping(activation_packet.get("effect"))
        for key in (
            "program_files_mutated",
            "oracle_index_mutated",
            "mlflow_mutated",
            "ak_mutated",
            "external_authority_mutated",
            "production_activation_applied",
        ):
            if effect.get(key) is not False:
                raise ProgramCandidateStateError(
                    f"activation packet must record {key} false"
                )
        non_authority = _safe_mapping(activation_packet.get("non_authority"))
        if non_authority.get("activation_packet_only") is not True:
            raise ProgramCandidateStateError(
                "activation packet must be activation-packet-only"
            )
        _validate_non_authority_false(
            activation_packet,
            label="activation packet",
            keys=(
                "program_activation_applied",
                "automatic_promotion",
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "jury_promotion_authority",
                "mlflow_approval_authority",
                "governance_authority",
                "external_mutation",
            ),
        )
        candidate = _safe_mapping(activation_packet.get("candidate"))
        manifest_ref = _safe_mapping(candidate.get("manifest"))
        if manifest_ref.get("sha256") != current_manifest_hash:
            raise ProgramCandidateStateError(
                "activation packet candidate manifest hash does not match current manifest"
            )
        evidence = _safe_mapping(activation_packet.get("evidence"))
        for key, expected_hash in sidecar_hashes.items():
            if expected_hash is None:
                continue
            ref = evidence.get(key)
            if not isinstance(ref, Mapping):
                raise ProgramCandidateStateError(
                    f"activation packet is missing supplied {key} evidence ref"
                )
            if ref.get("sha256") != expected_hash:
                raise ProgramCandidateStateError(
                    f"activation packet evidence hash does not match supplied {key}"
                )
    return validated_comparison


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
        "example_count": _safe_int(summary.get("total")),
        "status_counts": _safe_mapping(summary.get("status_counts")),
        "sha256": behavior_hash,
    }


def _behavior_episode_summary(
    episode: Mapping[str, Any] | None, episode_hash: str | None
) -> dict[str, Any]:
    if episode is None:
        return {
            "present": False,
            "schema_version": None,
            "status": "insufficient_behavior_evidence",
            "source_count": 0,
            "example_count": 0,
            "status_counts": {},
            "sha256": None,
        }
    summary = _safe_mapping(episode.get("summary"))
    status_counts: dict[str, int] = {}
    raw_counts = summary.get("status_counts")
    if isinstance(raw_counts, Mapping):
        status_counts = {
            str(key): _safe_int(value) for key, value in sorted(raw_counts.items())
        }
    else:
        for key in ("passed", "failed", "error", "degraded"):
            value = _safe_int(summary.get(key))
            if value:
                status_counts[key] = value
    return {
        "present": True,
        "schema_version": episode.get("schema_version"),
        "status": str(summary.get("status") or "unknown"),
        "source_count": _safe_int(summary.get("source_count")),
        "example_count": _safe_int(summary.get("total")),
        "status_counts": status_counts,
        "sha256": episode_hash,
    }


def _runtime_episode_summary(
    runtime_episode: Mapping[str, Any] | None, runtime_episode_hash: str | None
) -> dict[str, Any]:
    if runtime_episode is None:
        return {
            "present": False,
            "schema_version": None,
            "status": "missing",
            "runtime_episode_id": None,
            "contract_mode": None,
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
        "sha256": runtime_episode_hash,
        "source_manifest_sha256": artifact_hashes.get("source_manifest_sha256"),
        "runtime_inputs_sha256": artifact_hashes.get("runtime_inputs_sha256"),
        "behavior_results_sha256": artifact_hashes.get("behavior_results_sha256"),
        "program_runtime_traces_sha256": artifact_hashes.get(
            "program_runtime_traces_sha256"
        ),
        "oracle_evidence_sha256": artifact_hashes.get("oracle_evidence_sha256"),
        "output_file_count": len(_safe_list(runtime_episode.get("output_files"))),
        "evidence_only": True,
        "promotion_authority": False,
        "activation_authority": False,
        "shared_oracle_mutated": False,
    }


def _oracle_readability_summary(
    manifest: Mapping[str, Any], manifest_path: Path
) -> dict[str, Any]:
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
        "ready_for_adjudicator_review": readiness.get("ready_for_adjudicator_review")
        is True,
        "missing_required_evidence": _string_list(
            readiness.get("missing_required_evidence")
        ),
    }


def _decision_summary(decision: Mapping[str, Any] | None) -> dict[str, Any]:
    if decision is None:
        return {"present": False, "status": "missing"}
    return {
        "present": True,
        "schema_version": decision.get("schema_version"),
        "status": decision.get("status"),
        "outcome": decision.get("outcome"),
        "promotion_state_after_decision": decision.get(
            "promotion_state_after_decision"
        ),
        "external_authority_exported": _safe_mapping(
            decision.get("decision_constraints")
        ).get("external_authority_exported")
        is True,
    }


def _jury_results_summary(
    jury_results: Mapping[str, Any] | None,
    candidate_identity: Mapping[str, str | None],
    source_identity: Mapping[str, str | None] | None,
) -> dict[str, Any]:
    if jury_results is None:
        return {"present": False, "status": "missing"}
    role = "unrelated"
    jury_identity = _safe_mapping(jury_results.get("identity"))
    if _identity_exactly_matches(jury_identity, candidate_identity):
        role = "candidate"
    elif source_identity is not None and _identity_exactly_matches(
        jury_identity,
        source_identity,
    ):
        role = "source"
    jury = _safe_mapping(jury_results.get("jury"))
    behavior = _safe_mapping(jury_results.get("behavior_evidence"))
    aggregate = _safe_mapping(jury_results.get("aggregate"))
    interpretation = _safe_mapping(jury_results.get("interpretation"))
    return {
        "present": True,
        "schema_version": jury_results.get("schema_version"),
        "status": jury_results.get("status"),
        "manifest_role": role,
        "selected_juror_count": int(jury.get("selected_juror_count") or 0),
        "selected_perspectives": _string_list(jury.get("selected_perspectives")),
        "provider_backed_model_calls": jury.get("provider_backed_model_calls") is True,
        "behavior_evidence_present": behavior.get("present") is True,
        "aggregate_status": aggregate.get("status"),
        "judgment_counts": _safe_mapping(aggregate.get("judgment_counts")),
        "disagreement_present": aggregate.get("disagreement_present") is True,
        "ready_for_promotion_decision": interpretation.get(
            "ready_for_promotion_decision"
        )
        is True,
        "promotion_authority": False,
    }


def _model_jury_results_summary(
    model_jury_results: Mapping[str, Any] | None,
    candidate_identity: Mapping[str, str | None],
    source_identity: Mapping[str, str | None] | None,
) -> dict[str, Any]:
    if model_jury_results is None:
        return {"present": False, "status": "missing"}
    role = _identity_role(
        _safe_mapping(model_jury_results.get("identity")),
        candidate_identity=candidate_identity,
        source_identity=source_identity,
    )
    jury = _safe_mapping(model_jury_results.get("jury"))
    aggregate = _safe_mapping(model_jury_results.get("aggregate"))
    adjudicator = _safe_mapping(model_jury_results.get("adjudicator"))
    interpretation = _safe_mapping(model_jury_results.get("interpretation"))
    return {
        "present": True,
        "schema_version": model_jury_results.get("schema_version"),
        "status": model_jury_results.get("status"),
        "manifest_role": role,
        "execution_mode": jury.get("execution_mode"),
        "provider_backed_model_calls": jury.get("provider_backed_model_calls") is True,
        "selected_juror_count": _safe_int(jury.get("selected_juror_count")),
        "selected_perspectives": _string_list(jury.get("selected_perspectives")),
        "judgment_counts": _safe_mapping(aggregate.get("judgment_counts")),
        "recommendation": aggregate.get("recommendation"),
        "improvement_request_count": len(
            _safe_list(aggregate.get("unique_improvement_requests"))
        ),
        "adjudicator_repo": adjudicator.get("repo"),
        "ready_for_promotion_decision": interpretation.get(
            "ready_for_promotion_decision"
        )
        is True,
        "promotion_authority": adjudicator.get("promotion_authority") is True,
        "winner_selected": False,
    }


def _comparison_summary(
    comparison: Mapping[str, Any] | None, identity: Mapping[str, str | None]
) -> dict[str, Any]:
    if comparison is None:
        return {"present": False, "status": "missing"}
    role = "unrelated"
    if _identity_exactly_matches(
        _safe_mapping(comparison.get("source_identity")), identity
    ):
        role = "source"
    elif _identity_exactly_matches(
        _safe_mapping(comparison.get("candidate_identity")), identity
    ):
        role = "candidate"
    interpretation = _safe_mapping(comparison.get("interpretation"))
    runtime_comparison = _safe_mapping(comparison.get("runtime_evidence_comparison"))
    runtime_role_summary = _safe_mapping(runtime_comparison.get(role))
    created_from = _safe_mapping(comparison.get("created_from"))
    source_runtime_bound = bool(
        _first_text(
            created_from.get("source_runtime_episode_path"),
            created_from.get("source_runtime_episode_hash"),
        )
    )
    candidate_runtime_bound = bool(
        _first_text(
            created_from.get("candidate_runtime_episode_path"),
            created_from.get("candidate_runtime_episode_hash"),
        )
    )
    runtime_evidence_compared = (
        runtime_comparison.get("compared") is True
        and source_runtime_bound
        and candidate_runtime_bound
    )
    return {
        "present": True,
        "schema_version": comparison.get("schema_version"),
        "status": comparison.get("status"),
        "manifest_role": role,
        "improvement_observed": interpretation.get("improvement_observed") is True,
        "needs_more_evidence": interpretation.get("needs_more_evidence") is True,
        "runtime_evidence_present_for_role": runtime_role_summary.get(
            "runtime_evidence_present"
        )
        is True,
        "runtime_evidence_compared": runtime_evidence_compared,
        "runtime_episode_id": runtime_role_summary.get("runtime_episode_id"),
        "runtime_status": runtime_role_summary.get("runtime_status"),
        "runtime_behavior_status": runtime_role_summary.get("behavior_status"),
        "runtime_artifact_hashes": _safe_mapping(
            runtime_role_summary.get("artifact_hashes")
        ),
        "winner_selected": False,
        "activation_authority": False,
        "promotion_authority": False,
    }


def _gepa_refinement_summary(
    gepa_refinement: Mapping[str, Any] | None,
    *,
    candidate_identity: Mapping[str, str | None],
    source_identity: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    if gepa_refinement is None:
        return {
            "present": False,
            "status": "missing",
            "ready_for_future_candidate_materializer": False,
        }
    evidence_inputs = _safe_mapping(gepa_refinement.get("evidence_inputs"))
    gepa = _safe_mapping(gepa_refinement.get("gepa"))
    gepa_output = _safe_mapping(gepa_refinement.get("gepa_output"))
    readiness = _safe_mapping(gepa_output.get("readiness"))
    role = _identity_role(
        _safe_mapping(gepa_refinement.get("source_identity")),
        candidate_identity=candidate_identity,
        source_identity=source_identity,
    )
    ready_for_materializer = (
        gepa_refinement.get("status") != "gepa_output_unverified"
        and gepa_output.get("manifest_present") is True
        and gepa_output.get("manifest_valid") is True
        and bool(_first_text(gepa_output.get("manifest_sha256")))
        and readiness.get("status") == "optimizer_output_hash_bound_not_candidate"
        and readiness.get("ready_for_future_candidate_materializer") is True
    )
    return {
        "present": True,
        "schema_version": gepa_refinement.get("schema_version"),
        "status": gepa_refinement.get("status"),
        "manifest_role": role,
        "evidence_source": evidence_inputs.get("source"),
        "held_out_validation": evidence_inputs.get("held_out_validation") is True,
        "train_examples_count": _safe_int(evidence_inputs.get("train_examples_count")),
        "validation_examples_count": _safe_int(
            evidence_inputs.get("validation_examples_count")
        ),
        "gepa_attempted": gepa.get("attempted") is True,
        "gepa_status": gepa.get("status"),
        "optimizer_metric": gepa.get("optimizer_metric"),
        "output_manifest_present": gepa_output.get("manifest_present") is True,
        "output_manifest_valid": gepa_output.get("manifest_valid") is True,
        "output_manifest_sha256": gepa_output.get("manifest_sha256"),
        "output_readiness_status": readiness.get("status"),
        "ready_for_future_candidate_materializer": ready_for_materializer,
        "readiness_blockers": _string_list(readiness.get("blockers")),
        "candidate_materialized": False,
        "winner_selected": False,
        "promotion_authority": False,
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
        "missing_required_evidence": _string_list(
            eligibility.get("missing_required_evidence")
        ),
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
        "external_apply_blocking_reasons": _string_list(
            preflight_block.get("external_apply_blocking_reasons")
        ),
        "ak_called": _safe_mapping(preflight.get("effect")).get("ak_called") is True,
        "external_authority_mutated": _safe_mapping(preflight.get("effect")).get(
            "external_authority_mutated"
        )
        is True,
    }


def _meta_adjudication_plan_summary(
    plan: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if plan is None:
        return {"present": False, "status": "missing"}
    sidecars = _safe_mapping(plan.get("sidecars"))
    present_sidecars = sorted(
        key
        for key, value in sidecars.items()
        if isinstance(value, Mapping) and value.get("present") is True
    )
    return {
        "present": True,
        "schema_version": plan.get("schema_version"),
        "status": plan.get("status"),
        "lifecycle_state": plan.get("lifecycle_state"),
        "authority": plan.get("authority"),
        "missing_evidence": _string_list(plan.get("missing_evidence")),
        "next_command_count": len(_safe_list(plan.get("next_commands"))),
        "present_sidecars": present_sidecars,
        "provider_called": _safe_mapping(plan.get("effect")).get("provider_called")
        is True,
        "ak_mutated": _safe_mapping(plan.get("effect")).get("ak_mutated") is True,
        "promotion_authority": _safe_mapping(plan.get("non_authority")).get(
            "promotion_authority"
        )
        is True,
        "activation_authority": _safe_mapping(plan.get("non_authority")).get(
            "activation_authority"
        )
        is True,
    }


def _activation_packet_summary(packet: Mapping[str, Any] | None) -> dict[str, Any]:
    if packet is None:
        return {"present": False, "status": "missing"}
    return {
        "present": True,
        "schema_version": packet.get("schema_version"),
        "status": packet.get("status"),
        "next_required_action": packet.get("next_required_action"),
        "owning_domain": packet.get("owning_domain"),
        "activation_target": packet.get("activation_target"),
        "authority_owner": packet.get("authority_owner"),
        "rollout_owner": packet.get("rollout_owner"),
        "rollback_plan_present": bool(_first_text(packet.get("rollback_plan"))),
        "canonical_binding_ref": packet.get("canonical_binding_ref"),
        "missing_required_evidence": _string_list(
            packet.get("missing_required_evidence")
        ),
        "remaining_activation_blockers": _string_list(
            packet.get("remaining_activation_blockers")
        ),
        "evidence_keys_present": sorted(
            key
            for key, value in _safe_mapping(packet.get("evidence")).items()
            if value is not None
        ),
        "activation_packet_only": _safe_mapping(packet.get("non_authority")).get(
            "activation_packet_only"
        )
        is True,
        "production_activation_applied": _safe_mapping(packet.get("effect")).get(
            "production_activation_applied"
        )
        is True,
        "ak_mutated": _safe_mapping(packet.get("effect")).get("ak_mutated") is True,
        "external_authority_mutated": _safe_mapping(packet.get("effect")).get(
            "external_authority_mutated"
        )
        is True,
    }


def _oracle_publication_preflight_summary(
    preflight: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if preflight is None:
        return {"present": False, "status": "missing"}
    publication = _safe_mapping(preflight.get("publication"))
    checks = _safe_mapping(preflight.get("preflight"))
    effect = _safe_mapping(preflight.get("effect"))
    return {
        "present": True,
        "schema_version": preflight.get("schema_version"),
        "status": preflight.get("status"),
        "publication_id": preflight.get("publication_id"),
        "publication_label": publication.get("publication_label"),
        "publication_label_class": publication.get("publication_label_class"),
        "authority_ref": publication.get("authority_ref"),
        "retention_class": publication.get("retention_class"),
        "ready_for_shared_publication": checks.get("ready_for_shared_publication")
        is True,
        "blocking_reasons": _safe_list(checks.get("blocking_reasons")),
        "shared_oracle_mutated": effect.get("shared_oracle_mutated") is True,
        "evidence_only": True,
    }


def _oracle_publication_receipt_summary(
    receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if receipt is None:
        return {"present": False, "status": "missing"}
    effect = _safe_mapping(receipt.get("effect"))
    publication = _safe_mapping(receipt.get("publication"))
    return {
        "present": True,
        "schema_version": receipt.get("schema_version"),
        "status": receipt.get("status"),
        "publication_id": receipt.get("publication_id"),
        "run_id": receipt.get("run_id"),
        "publication_label": publication.get("publication_label"),
        "publication_label_class": publication.get("publication_label_class"),
        "authority_ref": publication.get("authority_ref"),
        "retention_class": publication.get("retention_class"),
        "shared_oracle_mutated": effect.get("shared_oracle_mutated") is True,
        "ak_called": effect.get("ak_called") is True,
        "governance_mutated": effect.get("governance_mutated") is True,
        "promotion_state_changed": effect.get("promotion_state_changed") is True,
        "evidence_only": True,
    }


def _oracle_report_summary(report: Mapping[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {"present": False, "status": "missing"}
    return {
        "present": True,
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "total_records": int(report.get("total_records") or 0),
        "interpretation_only": _safe_mapping(report.get("non_authority")).get(
            "oracle_interpretation_only"
        )
        is True,
    }


def _generation_gate_summary(preflight: Mapping[str, Any] | None) -> dict[str, Any]:
    if preflight is None:
        return {"present": False, "status": "missing", "generation_allowed": False}
    return {
        "present": True,
        "schema_version": preflight.get("schema_version"),
        "status": preflight.get("status"),
        "generation_allowed": preflight.get("generation_allowed") is True,
        "fail_closed_reasons": _string_list(preflight.get("fail_closed_reasons")),
    }


def _generation_fitness_summary(results: Mapping[str, Any] | None) -> dict[str, Any]:
    if results is None:
        return {
            "present": False,
            "schema_version": None,
            "status": "missing",
            "rendered_state": None,
            "eligible_for_downstream_evidence_review": False,
        }
    eligible = (
        results.get("status") == "fitness_passed"
        and results.get("rendered_state") == "eligible_for_downstream_evidence_review"
    )
    return {
        "present": True,
        "schema_version": results.get("schema_version"),
        "status": results.get("status"),
        "rendered_state": results.get("rendered_state"),
        "eligible_for_downstream_evidence_review": eligible,
        "case_count": len(_safe_list(results.get("cases"))),
    }


def _target_protocol_judgment(
    adjudication: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if adjudication is None:
        return {
            "present": False,
            "judgment": "missing",
            "blocking": True,
            "missing_evidence": ["program_evidence_adjudication.json"],
            "rationale": "target-protocol fidelity has not been adjudicated",
        }
    for item in _safe_list(adjudication.get("role_judgments")):
        role = _safe_mapping(item)
        if role.get("perspective") == "target_protocol_fidelity":
            judgment = str(role.get("judgment") or "unknown")
            return {
                "present": True,
                "judgment": judgment,
                "blocking": judgment != "supports_domain_review",
                "missing_evidence": _string_list(role.get("missing_evidence")),
                "rationale": role.get("rationale"),
            }
    return {
        "present": False,
        "judgment": "missing_target_protocol_fidelity_perspective",
        "blocking": True,
        "missing_evidence": ["target_protocol_fidelity role judgment"],
        "rationale": "program evidence adjudication did not include target_protocol_fidelity",
    }


def _evidence_adjudication_summary(
    adjudication: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if adjudication is None:
        return {"present": False, "status": "missing"}
    aggregate = _safe_mapping(adjudication.get("aggregate"))
    return {
        "present": True,
        "schema_version": adjudication.get("schema_version"),
        "status": adjudication.get("status"),
        "recommendation": aggregate.get("recommendation"),
        "ready_for_domain_decision": aggregate.get("ready_for_domain_decision") is True,
        "blocking_perspectives": _string_list(aggregate.get("blocking_perspectives")),
        "missing_evidence": _string_list(aggregate.get("missing_evidence")),
    }


def _target_fidelity_summary(
    *,
    generation_gate_preflight: Mapping[str, Any] | None,
    generation_fitness_results: Mapping[str, Any] | None,
    program_evidence_adjudication: Mapping[str, Any] | None,
) -> dict[str, Any]:
    gate = _generation_gate_summary(generation_gate_preflight)
    fitness = _generation_fitness_summary(generation_fitness_results)
    adjudication = _evidence_adjudication_summary(program_evidence_adjudication)
    target_judgment = _target_protocol_judgment(program_evidence_adjudication)
    adapter_allowed = (
        fitness["eligible_for_downstream_evidence_review"] is True
        and target_judgment["judgment"] == "supports_domain_review"
    )
    blockers: list[str] = []
    if gate["present"] and gate["generation_allowed"] is not True:
        blockers.append("generation_gate_blocked")
    if not fitness["present"]:
        blockers.append("missing_generation_fitness_results")
    elif fitness["eligible_for_downstream_evidence_review"] is not True:
        blockers.append("generation_fitness_not_review_eligible")
    if target_judgment["judgment"] != "supports_domain_review":
        blockers.append("target_protocol_fidelity_not_supported_by_adjudicator")
    return {
        "generation_gate_preflight": gate,
        "generation_fitness_results": fitness,
        "program_evidence_adjudication": adjudication,
        "target_protocol_fidelity_judgment": target_judgment,
        "downstream_evidence_review_eligible": fitness[
            "eligible_for_downstream_evidence_review"
        ],
        "obsidian_review_adapter_materialization_allowed": adapter_allowed,
        "production_or_domain_activation_allowed": False,
        "canonical_mutation_allowed": False,
        "blockers": blockers,
        "interpretation": (
            "target_fidelity_supported_for_review_only"
            if adapter_allowed
            else "target_fidelity_not_ready_for_review_materialization"
        ),
    }


def _proposal_summary(proposal: Mapping[str, Any] | None) -> dict[str, Any]:
    if proposal is None:
        return {"present": False, "status": "missing"}
    return {
        "present": True,
        "schema_version": proposal.get("schema_version"),
        "status": proposal.get("status"),
        "proposal_id": proposal.get("proposal_id"),
        "proposal_only": _safe_mapping(proposal.get("non_authority")).get(
            "proposal_only"
        )
        is True,
    }


def _overall_status(
    *,
    manifest: Mapping[str, Any],
    review: Mapping[str, Any] | None,
    decision: Mapping[str, Any] | None,
    promotion_plan: Mapping[str, Any] | None,
    export_preflight: Mapping[str, Any] | None,
    activation_packet: Mapping[str, Any] | None,
) -> str:
    promotion_review = _safe_mapping(manifest.get("program_promotion_review"))
    if promotion_review.get("promotion_state") != "not_promoted":
        return "unexpected_promotion_state"
    if activation_packet is not None:
        return "not_promoted_activation_evidence_packet_present"
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
    behavior_present: bool,
    review: Mapping[str, Any] | None,
    decision: Mapping[str, Any] | None,
    jury_results: Mapping[str, Any] | None,
    comparison: Mapping[str, Any] | None,
    export_preflight: Mapping[str, Any] | None,
    activation_packet: Mapping[str, Any] | None,
) -> list[str]:
    steps: list[str] = []
    if not behavior_present:
        steps.append("capture_behavior_evidence")
    if review is None:
        steps.append("build_refined_promotion_review")
    if decision is None:
        steps.append("record_local_adjudicator_decision")
    if jury_results is None:
        steps.append("run_local_jury_sidecar")
    if comparison is None:
        steps.append("compare_candidate_behavior")
    if export_preflight is None:
        steps.append("build_external_authority_export_preflight")
    if activation_packet is None:
        steps.append("build_activation_evidence_packet")
    else:
        next_action = _first_text(activation_packet.get("next_required_action"))
        if next_action:
            steps.append(next_action)
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
    jury_results_path: Path | None = None,
    model_jury_results_path: Path | None = None,
    comparison_path: Path | None = None,
    promotion_plan_path: Path | None = None,
    export_preflight_path: Path | None = None,
    meta_adjudication_plan_path: Path | None = None,
    activation_packet_path: Path | None = None,
    oracle_publication_preflight_path: Path | None = None,
    oracle_publication_receipt_path: Path | None = None,
    generation_gate_preflight_path: Path | None = None,
    generation_fitness_results_path: Path | None = None,
    program_evidence_adjudication_path: Path | None = None,
    gepa_refinement_path: Path | None = None,
    runtime_episode_path: Path | None = None,
) -> dict[str, Any]:
    """Build one local truth-state artifact from existing program sidecars."""

    manifest_input_path = manifest_path.expanduser()
    try:
        candidate_snapshot = snapshot_candidate_artifact_closure(manifest_input_path)
    except (OSError, ValueError) as exc:
        raise ProgramCandidateStateError(
            f"candidate artifact closure is invalid: {exc}"
        ) from exc
    manifest_path = candidate_snapshot.manifest_path
    manifest = candidate_snapshot.manifest
    manifest_hash = candidate_snapshot.manifest_sha256
    if manifest.get("schema_version") != PROGRAM_MANIFEST_SCHEMA:
        raise ProgramCandidateStateError(
            "program manifest schema_version must be " + PROGRAM_MANIFEST_SCHEMA
        )
    if not any(_identity_from_manifest(manifest).values()):
        raise ProgramCandidateStateError(
            "program manifest does not expose request/candidate/assembly/episode/receipt identity"
        )
    try:
        behavior, behavior_path, behavior_hash = load_program_behavior_results(
            manifest,
            manifest_path,
        )
        behavior_episode, behavior_episode_path, behavior_episode_hash = (
            _load_program_behavior_episode(manifest, manifest_path)
        )
    except ProgramRefinementError as exc:
        raise ProgramCandidateStateError(str(exc)) from exc
    _require_loaded_hash_matches_snapshot(
        candidate_snapshot,
        kind="behavior_results",
        loaded_hash=behavior_hash,
        label="program behavior results",
    )
    _require_loaded_hash_matches_snapshot(
        candidate_snapshot,
        kind="behavior_episode",
        loaded_hash=behavior_episode_hash,
        label="program behavior episode",
    )
    candidate_identity = _identity_from_manifest(manifest)
    source_manifest: dict[str, Any] | None = None
    source_identity: dict[str, str | None] | None = None
    source_manifest_hash: str | None = None
    source_manifest_resolved: Path | None = None
    source_behavior_path: Path | None = None
    source_behavior_hash: str | None = None
    source_behavior_episode_path: Path | None = None
    source_behavior_episode_hash: str | None = None
    source_snapshot: CandidateArtifactSnapshot | None = None
    if source_manifest_path is not None:
        source_manifest_input_path = source_manifest_path.expanduser()
        try:
            source_snapshot = snapshot_candidate_artifact_closure(
                source_manifest_input_path
            )
        except (OSError, ValueError) as exc:
            raise ProgramCandidateStateError(
                f"source candidate artifact closure is invalid: {exc}"
            ) from exc
        source_manifest_resolved = source_snapshot.manifest_path
        source_manifest = source_snapshot.manifest
        source_manifest_hash = source_snapshot.manifest_sha256
        if source_manifest.get("schema_version") != PROGRAM_MANIFEST_SCHEMA:
            raise ProgramCandidateStateError(
                "source program manifest schema_version must be "
                + PROGRAM_MANIFEST_SCHEMA
            )
        if not any(_identity_from_manifest(source_manifest).values()):
            raise ProgramCandidateStateError(
                "source program manifest does not expose candidate identity"
            )
        try:
            _source_behavior, source_behavior_path, source_behavior_hash = (
                load_program_behavior_results(source_manifest, source_manifest_resolved)
            )
            (
                _source_behavior_episode,
                source_behavior_episode_path,
                source_behavior_episode_hash,
            ) = _load_program_behavior_episode(
                source_manifest, source_manifest_resolved
            )
        except ProgramRefinementError as exc:
            raise ProgramCandidateStateError(str(exc)) from exc
        _require_loaded_hash_matches_snapshot(
            source_snapshot,
            kind="behavior_results",
            loaded_hash=source_behavior_hash,
            label="source program behavior results",
        )
        _require_loaded_hash_matches_snapshot(
            source_snapshot,
            kind="behavior_episode",
            loaded_hash=source_behavior_episode_hash,
            label="source program behavior episode",
        )
        source_identity = _identity_from_manifest(source_manifest)

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
    jury_results, jury_results_file, jury_results_hash = _load_optional_artifact(
        jury_results_path,
        label="program jury results",
        schema=PROGRAM_JURY_RESULTS_SCHEMA,
    )
    model_jury_results, model_jury_results_file, model_jury_results_hash = (
        _load_optional_artifact(
            model_jury_results_path,
            label="program model jury results",
            schema=PROGRAM_MODEL_JURY_RESULTS_SCHEMA,
        )
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
    meta_adjudication_plan, meta_adjudication_plan_file, meta_adjudication_plan_hash = (
        _load_optional_artifact(
            meta_adjudication_plan_path,
            label="meta-adjudication plan",
            schema=PROGRAM_META_ADJUDICATION_PLAN_SCHEMA,
        )
    )
    activation_packet, activation_packet_file, activation_packet_hash = (
        _load_optional_artifact(
            activation_packet_path,
            label="activation packet",
            schema=ACTIVATION_PACKET_SCHEMA,
        )
    )
    (
        oracle_publication_preflight,
        oracle_publication_preflight_file,
        oracle_publication_preflight_hash,
    ) = _load_optional_artifact(
        oracle_publication_preflight_path,
        label="Oracle publication preflight",
        schema=PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA,
    )
    (
        oracle_publication_receipt,
        oracle_publication_receipt_file,
        oracle_publication_receipt_hash,
    ) = _load_optional_artifact(
        oracle_publication_receipt_path,
        label="Oracle publication receipt",
        schema=PROGRAM_ORACLE_PUBLICATION_RECEIPT_SCHEMA,
    )
    (
        generation_gate_preflight,
        generation_gate_preflight_file,
        generation_gate_preflight_hash,
    ) = _load_optional_artifact(
        generation_gate_preflight_path,
        label="generation gate preflight",
        schema=GEN_GENERATION_GATE_PREFLIGHT_SCHEMA,
    )
    (
        generation_fitness_results,
        generation_fitness_results_file,
        generation_fitness_results_hash,
    ) = _load_optional_artifact(
        generation_fitness_results_path,
        label="generation fitness results",
        schema=GEN_FITNESS_RESULTS_SCHEMA,
    )
    (
        program_evidence_adjudication,
        program_evidence_adjudication_file,
        program_evidence_adjudication_hash,
    ) = _load_optional_artifact(
        program_evidence_adjudication_path,
        label="program evidence adjudication",
        schema=PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA,
    )
    gepa_refinement, gepa_refinement_file, gepa_refinement_hash = (
        _load_optional_artifact(
            gepa_refinement_path,
            label="program GEPA refinement result",
            schema=PROGRAM_REFINEMENT_GEPA_RESULT_SCHEMA,
        )
    )
    runtime_episode, runtime_episode_file, runtime_episode_hash = (
        _load_optional_artifact(
            runtime_episode_path,
            label="program runtime episode",
            schema=PROGRAM_RUNTIME_EPISODE_SCHEMA,
        )
    )

    current_program_hash = next(
        (
            artifact.sha256
            for artifact in candidate_snapshot.artifacts
            if artifact.kind == "program"
        ),
        None,
    )
    source_program_hash = (
        next(
            (
                artifact.sha256
                for artifact in source_snapshot.artifacts
                if artifact.kind == "program"
            ),
            None,
        )
        if source_snapshot is not None
        else None
    )
    activation_sidecar_hashes = {
        "oracle_report": oracle_report_hash,
        "jury_results": jury_results_hash,
        "model_jury_results": model_jury_results_hash,
        "refined_review": review_hash,
        "decision_record": decision_hash,
        "promotion_plan": promotion_plan_hash,
        "candidate_state": None,
        "external_authority_export_preflight": export_preflight_hash,
        "oracle_publication_preflight": oracle_publication_preflight_hash,
        "oracle_publication_receipt": oracle_publication_receipt_hash,
        "canonical_binding_verification": None,
        "generation_fitness_results": generation_fitness_results_hash,
        "program_evidence_adjudication": program_evidence_adjudication_hash,
    }
    supplied_sidecar_refs = {
        key: (path, file_hash)
        for key, path, file_hash in (
            ("oracle_report", oracle_report_file, oracle_report_hash),
            (
                "oracle_publication_preflight",
                oracle_publication_preflight_file,
                oracle_publication_preflight_hash,
            ),
            (
                "oracle_publication_receipt",
                oracle_publication_receipt_file,
                oracle_publication_receipt_hash,
            ),
            ("jury_results", jury_results_file, jury_results_hash),
            ("review", review_file, review_hash),
            ("decision_record", decision_file, decision_hash),
            ("activation_packet", activation_packet_file, activation_packet_hash),
            (
                "generation_gate_preflight",
                generation_gate_preflight_file,
                generation_gate_preflight_hash,
            ),
            (
                "generation_fitness_results",
                generation_fitness_results_file,
                generation_fitness_results_hash,
            ),
            (
                "program_evidence_adjudication",
                program_evidence_adjudication_file,
                program_evidence_adjudication_hash,
            ),
            ("runtime_episode", runtime_episode_file, runtime_episode_hash),
        )
        if path is not None and file_hash is not None
    }

    validated_comparison = _validate_optional_inputs(
        candidate_identity=candidate_identity,
        source_identity=source_identity,
        refinement_proposal=refinement_proposal,
        refinement_proposal_path=refinement_proposal_file,
        refinement_proposal_hash=refinement_proposal_hash,
        review=review,
        review_path=review_file,
        decision=decision,
        jury_results=jury_results,
        model_jury_results=model_jury_results,
        comparison=comparison,
        comparison_path=comparison_file,
        promotion_plan=promotion_plan,
        export_preflight=export_preflight,
        meta_adjudication_plan=meta_adjudication_plan,
        activation_packet=activation_packet,
        oracle_publication_preflight=oracle_publication_preflight,
        oracle_publication_receipt=oracle_publication_receipt,
        gepa_refinement=gepa_refinement,
        current_manifest_path=manifest_path,
        current_manifest_hash=manifest_hash,
        oracle_report_path=oracle_report_file,
        oracle_report_hash=oracle_report_hash,
        current_program_hash=current_program_hash,
        source_manifest_path=source_manifest_resolved,
        source_manifest_hash=source_manifest_hash,
        source_program_hash=source_program_hash,
        behavior_path=behavior_path,
        behavior_hash=behavior_hash,
        behavior_episode_path=behavior_episode_path,
        behavior_episode_hash=behavior_episode_hash,
        source_behavior_path=source_behavior_path,
        source_behavior_hash=source_behavior_hash,
        source_behavior_episode_path=source_behavior_episode_path,
        source_behavior_episode_hash=source_behavior_episode_hash,
        model_jury_results_path=model_jury_results_file,
        model_jury_results_hash=model_jury_results_hash,
        sidecar_hashes=activation_sidecar_hashes,
        comparison_hash=comparison_hash,
        supplied_sidecar_refs=supplied_sidecar_refs,
    )
    validate_program_evidence_adjudication_contract(
        program_evidence_adjudication,
        expected_identity=candidate_identity,
        current_manifest_path=manifest_path,
        current_manifest_hash=manifest_hash,
        behavior_results_hash=behavior_hash,
        behavior_episode_hash=behavior_episode_hash,
        oracle_report_hash=oracle_report_hash,
        activation_packet_hash=activation_packet_hash,
        generation_fitness_results_hash=generation_fitness_results_hash,
        expected_runtime_episode_path=runtime_episode_file,
        expected_runtime_episode_hash=runtime_episode_hash,
        error_type=ProgramCandidateStateError,
    )
    if runtime_episode is not None and runtime_episode_file is not None:
        validate_program_runtime_episode_contract(
            runtime_episode,
            runtime_episode_path=runtime_episode_file,
            expected_manifest_path=manifest_path,
            expected_manifest=manifest,
            expected_manifest_sha256=manifest_hash,
            error_type=ProgramCandidateStateError,
        )
    if validated_comparison is not None:
        comparison = validated_comparison

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
        "behavior_episode_sha256": behavior_episode_hash,
        "execution_episode_sha256": _optional_hash(execution_episode_path),
        "oracle_evidence_sha256": oracle_readability.get("sha256"),
        "oracle_report_sha256": oracle_report_hash,
        "refinement_proposal_sha256": refinement_proposal_hash,
        "review_sha256": review_hash,
        "decision_record_sha256": decision_hash,
        "jury_results_sha256": jury_results_hash,
        "model_jury_results_sha256": model_jury_results_hash,
        "comparison_sha256": comparison_hash,
        "promotion_plan_sha256": promotion_plan_hash,
        "export_preflight_sha256": export_preflight_hash,
        "meta_adjudication_plan_sha256": meta_adjudication_plan_hash,
        "activation_packet_sha256": activation_packet_hash,
        "oracle_publication_preflight_sha256": oracle_publication_preflight_hash,
        "oracle_publication_receipt_sha256": oracle_publication_receipt_hash,
        "generation_gate_preflight_sha256": generation_gate_preflight_hash,
        "generation_fitness_results_sha256": generation_fitness_results_hash,
        "program_evidence_adjudication_sha256": program_evidence_adjudication_hash,
        "gepa_refinement_sha256": gepa_refinement_hash,
        "runtime_episode_sha256": runtime_episode_hash,
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
        activation_packet=activation_packet,
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
            "behavior_episode_path": str(behavior_episode_path)
            if behavior_episode_path is not None and behavior_episode_path.exists()
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
            "jury_results_path": str(jury_results_file)
            if jury_results_file is not None
            else None,
            "model_jury_results_path": str(model_jury_results_file)
            if model_jury_results_file is not None
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
            "meta_adjudication_plan_path": str(meta_adjudication_plan_file)
            if meta_adjudication_plan_file is not None
            else None,
            "activation_packet_path": str(activation_packet_file)
            if activation_packet_file is not None
            else None,
            "oracle_publication_preflight_path": str(oracle_publication_preflight_file)
            if oracle_publication_preflight_file is not None
            else None,
            "oracle_publication_receipt_path": str(oracle_publication_receipt_file)
            if oracle_publication_receipt_file is not None
            else None,
            "generation_gate_preflight_path": str(generation_gate_preflight_file)
            if generation_gate_preflight_file is not None
            else None,
            "generation_fitness_results_path": str(generation_fitness_results_file)
            if generation_fitness_results_file is not None
            else None,
            "program_evidence_adjudication_path": str(
                program_evidence_adjudication_file
            )
            if program_evidence_adjudication_file is not None
            else None,
            "gepa_refinement_path": str(gepa_refinement_file)
            if gepa_refinement_file is not None
            else None,
            "runtime_episode_path": str(runtime_episode_file)
            if runtime_episode_file is not None
            else None,
        },
        "artifact_hashes": artifact_hashes,
        "candidate": {
            "root_path": root_path,
            "artifact_kind": _safe_mapping(manifest.get("candidate_assembly")).get(
                "artifact_kind"
            ),
            "assembly_status": _safe_mapping(manifest.get("candidate_assembly")).get(
                "status"
            ),
            "promotion_state": _safe_mapping(
                manifest.get("program_promotion_review")
            ).get("promotion_state"),
            "candidate_status": _safe_mapping(
                manifest.get("program_promotion_review")
            ).get("candidate_status"),
            "program_gen_source_command": _safe_mapping(manifest.get("request")).get(
                "source_command"
            ),
        },
        "evidence_state": {
            "behavior": _behavior_summary(behavior, behavior_hash),
            "behavior_episode": _behavior_episode_summary(
                behavior_episode,
                behavior_episode_hash,
            ),
            "runtime_episode": _runtime_episode_summary(
                runtime_episode,
                runtime_episode_hash,
            ),
            "execution_episode": {
                "present": execution_episode_path.exists(),
                "path": str(execution_episode_path),
                "sha256": _optional_hash(execution_episode_path),
                "schema_version": _safe_mapping(
                    manifest.get("execution_episode_artifact")
                ).get("schema_version"),
            },
            "oracle_readability": oracle_readability,
            "oracle_report": _oracle_report_summary(oracle_report),
            "oracle_publication_preflight": _oracle_publication_preflight_summary(
                oracle_publication_preflight
            ),
            "oracle_publication_receipt": _oracle_publication_receipt_summary(
                oracle_publication_receipt
            ),
            "refinement_proposal": _proposal_summary(refinement_proposal),
            "optimizer_refinement": _gepa_refinement_summary(
                gepa_refinement,
                candidate_identity=candidate_identity,
                source_identity=source_identity,
            ),
        },
        "target_fidelity_state": _target_fidelity_summary(
            generation_gate_preflight=generation_gate_preflight,
            generation_fitness_results=generation_fitness_results,
            program_evidence_adjudication=program_evidence_adjudication,
        ),
        "promotion_state": {
            "review": _review_summary(review),
            "decision": _decision_summary(decision),
            "jury_results": _jury_results_summary(
                jury_results,
                candidate_identity,
                source_identity,
            ),
            "model_jury_results": _model_jury_results_summary(
                model_jury_results,
                candidate_identity,
                source_identity,
            ),
            "comparison": _comparison_summary(comparison, candidate_identity),
            "promotion_plan": _promotion_plan_summary(promotion_plan),
            "external_authority_export_preflight": _export_preflight_summary(
                export_preflight
            ),
            "meta_adjudication_plan": _meta_adjudication_plan_summary(
                meta_adjudication_plan
            ),
            "activation_packet": _activation_packet_summary(activation_packet),
        },
        "truth_summary": {
            "program_materialized": True,
            "behavior_evidence_present": behavior is not None
            or behavior_episode is not None,
            "oracle_report_present": oracle_report is not None,
            "review_present": review is not None,
            "decision_record_present": decision is not None,
            "jury_results_present": jury_results is not None,
            "model_jury_results_present": model_jury_results is not None,
            "comparison_present": comparison is not None,
            "promotion_plan_present": promotion_plan is not None,
            "external_authority_preflight_present": export_preflight is not None,
            "meta_adjudication_plan_present": meta_adjudication_plan is not None,
            "activation_packet_present": activation_packet is not None,
            "oracle_publication_preflight_present": oracle_publication_preflight
            is not None,
            "oracle_publication_ref_present": oracle_publication_receipt is not None,
            "target_fidelity_evidence_present": generation_fitness_results is not None,
            "target_protocol_adjudication_present": program_evidence_adjudication
            is not None,
            "gepa_refinement_present": gepa_refinement is not None,
            "runtime_episode_present": runtime_episode is not None,
            "gepa_output_ready_for_future_candidate_materializer": _gepa_refinement_summary(
                gepa_refinement,
                candidate_identity=candidate_identity,
                source_identity=source_identity,
            )["ready_for_future_candidate_materializer"],
            "obsidian_review_adapter_materialization_allowed": _target_fidelity_summary(
                generation_gate_preflight=generation_gate_preflight,
                generation_fitness_results=generation_fitness_results,
                program_evidence_adjudication=program_evidence_adjudication,
            )["obsidian_review_adapter_materialization_allowed"],
            "promotion_applied": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "ak_called": False,
            "winner_selected": False,
            "automatic_promotion": False,
            "ready_for_future_apply": False,
            "required_next_steps": _required_next_steps(
                behavior_present=behavior is not None or behavior_episode is not None,
                review=review,
                decision=decision,
                jury_results=jury_results,
                comparison=comparison,
                export_preflight=export_preflight,
                activation_packet=activation_packet,
            ),
        },
        "effect": {
            "local_state_written": False,
            "program_files_mutated": False,
            "sidecar_inputs_mutated": False,
            "oracle_index_mutated": False,
            "ak_called": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "promotion_state_changed": False,
        },
        "shared_oracle_publication": {
            "preflight_present": oracle_publication_preflight is not None,
            "preflight_ready": _safe_mapping(
                _oracle_publication_preflight_summary(oracle_publication_preflight)
            ).get("ready_for_shared_publication")
            is True,
            "publication_id": _safe_mapping(
                _oracle_publication_preflight_summary(oracle_publication_preflight)
            ).get("publication_id")
            or _safe_mapping(
                _oracle_publication_receipt_summary(oracle_publication_receipt)
            ).get("publication_id"),
            "evidence_ref_present": oracle_publication_receipt is not None,
            "evidence_only": True,
            "activation_authority": False,
            "promotion_authority": False,
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
    _require_snapshot_unchanged(candidate_snapshot, label="candidate")
    if source_snapshot is not None:
        _require_snapshot_unchanged(source_snapshot, label="source candidate")
    return payload


def write_program_candidate_state(
    state: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Atomically commit one local state packet through a symlink-safe parent FD."""

    lexical_target = Path(os.path.abspath(out_path.expanduser()))
    try:
        target = prepare_sidecar_output_path(
            lexical_target,
            payload=state,
            artifact_label="candidate state",
            protected_names=_FORBIDDEN_OUTPUT_NAMES,
            payload_artifact_root_policy="allow_named",
            allowed_names_in_protected_roots=("program_candidate_state.json",),
        )
    except ValueError as exc:
        raise ProgramCandidateStateError(str(exc)) from exc
    if target != lexical_target:
        raise ProgramCandidateStateError(
            "candidate state output path must not resolve through symlink components"
        )
    try:
        parent_fd = open_directory_no_symlinks(target.parent, create=True)
    except OSError as exc:
        raise ProgramCandidateStateError(
            f"candidate state output directory could not be opened safely: {exc}"
        ) from exc

    payload = dict(state)
    effect = _safe_mapping(payload.get("effect"))
    effect["local_state_written"] = True
    payload["effect"] = effect
    content = _json_text(payload).encode("utf-8")
    temporary_name = f".{target.name}.{secrets.token_hex(12)}.tmp"
    descriptor = -1
    replaced = False
    try:
        try:
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_fd,
            )
            offset = 0
            while offset < len(content):
                written = os.write(descriptor, content[offset:])
                if written <= 0:
                    raise OSError("candidate state write made no progress")
                offset += written
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(
                temporary_name,
                target.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            replaced = True
        except OSError as exc:
            raise ProgramCandidateStateError(
                f"candidate state failed before atomic replacement: {exc}"
            ) from exc
        try:
            os.fsync(parent_fd)
        except OSError as exc:
            raise ProgramCandidateStateCommitIndeterminateError(
                "candidate state replacement committed but directory durability "
                f"could not be confirmed: {exc}"
            ) from exc
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if not replaced:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except OSError:
                pass
        try:
            os.close(parent_fd)
        except OSError:
            pass
    return payload
