from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import prepare_sidecar_output_path
from dspx.services.program_evidence_adjudication_validation import (
    validate_program_evidence_adjudication_contract,
)
from dspx.services.program_jury_result_validation import (
    PROGRAM_JURY_RESULTS_SCHEMA,
    validate_program_jury_results_contract,
)
from dspx.services.program_model_jury_validation import (
    PROGRAM_MODEL_JURY_RESULTS_SCHEMA,
    validate_program_model_jury_results_contract,
)
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
PROGRAM_META_ADJUDICATION_PLAN_SCHEMA = "program-meta-adjudication-plan-v1"
PROGRAM_EXTERNAL_AUTHORITY_EXPORT_PREFLIGHT_SCHEMA = (
    "program-external-authority-export-preflight-v1"
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
    non_authority = _safe_mapping(payload.get("non_authority"))
    invalid = [key for key in keys if non_authority.get(key) is not False]
    if invalid:
        raise ProgramCandidateStateError(
            f"{label} widens non-authority flags: " + ", ".join(invalid)
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
    review: Mapping[str, Any] | None,
    decision: Mapping[str, Any] | None,
    jury_results: Mapping[str, Any] | None,
    model_jury_results: Mapping[str, Any] | None,
    comparison: Mapping[str, Any] | None,
    promotion_plan: Mapping[str, Any] | None,
    export_preflight: Mapping[str, Any] | None,
    meta_adjudication_plan: Mapping[str, Any] | None,
    activation_packet: Mapping[str, Any] | None,
    oracle_publication_receipt: Mapping[str, Any] | None,
    gepa_refinement: Mapping[str, Any] | None,
    current_manifest_path: Path,
    current_manifest_hash: str,
    source_manifest_path: Path | None,
    source_manifest_hash: str | None,
    behavior_hash: str | None,
    behavior_episode_hash: str | None,
    sidecar_hashes: Mapping[str, str | None],
    comparison_hash: str | None,
    supplied_sidecar_refs: Mapping[str, tuple[Path, str]],
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
        if not any(
            _identity_exactly_matches(review_identity, item)
            for item in source_or_candidate
        ):
            raise ProgramCandidateStateError(
                "refined promotion review identity does not match candidate/source identity: "
                + ", ".join(
                    _identity_mismatch_keys(review_identity, candidate_identity)
                )
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
        if not any(
            _identity_exactly_matches(decision_identity, item)
            for item in source_or_candidate
        ):
            raise ProgramCandidateStateError(
                "program promotion decision record identity does not match candidate/source identity: "
                + ", ".join(
                    _identity_mismatch_keys(decision_identity, candidate_identity)
                )
            )

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

    if gepa_refinement is not None:
        _validate_non_authority_false(
            gepa_refinement,
            label="program GEPA refinement result",
            keys=(
                "automatic_promotion",
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "winner_selection",
                "external_authority_export",
                "governance_authority",
                "external_mutation",
            ),
        )
        effect = _safe_mapping(gepa_refinement.get("effect"))
        if effect.get("local_gepa_candidate_generated") is not False:
            raise ProgramCandidateStateError(
                "program GEPA refinement result must not claim local candidate generation"
            )
        if effect.get("source_program_files_mutated") is not False:
            raise ProgramCandidateStateError(
                "program GEPA refinement result must record source_program_files_mutated false"
            )
        if gepa_refinement.get("candidate") is not None:
            raise ProgramCandidateStateError(
                "program GEPA refinement result must keep candidate null"
            )
        gepa_identity = _safe_mapping(gepa_refinement.get("source_identity"))
        if (
            _identity_role(
                gepa_identity,
                candidate_identity=candidate_identity,
                source_identity=source_identity,
            )
            == "unrelated"
        ):
            raise ProgramCandidateStateError(
                "program GEPA refinement identity does not match candidate/source identity"
            )
        gepa_output = _safe_mapping(gepa_refinement.get("gepa_output"))
        readiness = _safe_mapping(gepa_output.get("readiness"))
        readiness_claim = readiness.get("ready_for_future_candidate_materializer")
        if readiness_claim is True:
            if gepa_refinement.get("status") == "gepa_output_unverified":
                raise ProgramCandidateStateError(
                    "program GEPA refinement readiness conflicts with unverified status"
                )
            if gepa_output.get("manifest_present") is not True:
                raise ProgramCandidateStateError(
                    "program GEPA refinement readiness requires manifest_present true"
                )
            if gepa_output.get("manifest_valid") is not True:
                raise ProgramCandidateStateError(
                    "program GEPA refinement readiness requires manifest_valid true"
                )
            if not _first_text(gepa_output.get("manifest_sha256")):
                raise ProgramCandidateStateError(
                    "program GEPA refinement readiness requires manifest_sha256"
                )
            if readiness.get("status") != "optimizer_output_hash_bound_not_candidate":
                raise ProgramCandidateStateError(
                    "program GEPA refinement readiness status must be optimizer_output_hash_bound_not_candidate"
                )

    if promotion_plan is not None:
        if promotion_plan.get("status") != "planned_not_applied":
            raise ProgramCandidateStateError(
                "program promotion plan must have status planned_not_applied"
            )
        if (
            _safe_mapping(promotion_plan.get("eligibility")).get("allowed_for_apply")
            is not False
        ):
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

    if oracle_publication_receipt is not None:
        if oracle_publication_receipt.get("status") != "published":
            raise ProgramCandidateStateError(
                "Oracle publication receipt status must be published"
            )
        effect = _safe_mapping(oracle_publication_receipt.get("effect"))
        if effect.get("shared_oracle_mutated") is not True:
            raise ProgramCandidateStateError(
                "Oracle publication receipt must record shared_oracle_mutated true"
            )
        forbidden_true = {
            "ak_called": "Oracle publication receipt must not record AK mutation",
            "governance_mutated": "Oracle publication receipt must not record governance mutation",
            "mlflow_mutated": "Oracle publication receipt must not record MLflow mutation",
            "program_files_mutated": "Oracle publication receipt must not record program file mutation",
            "promotion_state_changed": "Oracle publication receipt must not record promotion state changes",
        }
        for key, message in forbidden_true.items():
            if effect.get(key) is not False:
                raise ProgramCandidateStateError(message)
        _validate_non_authority_false(
            oracle_publication_receipt,
            label="Oracle publication receipt",
            keys=(
                "oracle_authority",
                "promotion_authority",
                "governance_authority",
                "agent_kernel_mutation",
                "winner_selection",
                "automatic_promotion",
            ),
        )
        receipt_identity = _safe_mapping(oracle_publication_receipt.get("identity"))
        if not any(
            _identity_exactly_matches(receipt_identity, item)
            for item in source_or_candidate
        ):
            raise ProgramCandidateStateError(
                "Oracle publication receipt identity does not match candidate/source identity"
            )

    if export_preflight is not None:
        if export_preflight.get("status") not in {
            "ready_not_applied",
            "incomplete_preflight",
        }:
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
        if not any(
            _identity_exactly_matches(preflight_identity, item)
            for item in source_or_candidate
        ):
            raise ProgramCandidateStateError(
                "external authority export preflight identity does not match candidate/source identity"
            )
        _validate_export_preflight_artifact_hashes(
            export_preflight,
            current_manifest_hash=current_manifest_hash,
            source_manifest_hash=source_manifest_hash,
            decision_hash=sidecar_hashes.get("decision_record"),
            comparison_hash=comparison_hash,
        )

    if meta_adjudication_plan is not None:
        if meta_adjudication_plan.get("status") != "planned_not_executed":
            raise ProgramCandidateStateError(
                "meta-adjudication plan must be planned_not_executed"
            )
        if (
            meta_adjudication_plan.get("lifecycle_state")
            != "meta_adjudication_plan_ready"
        ):
            raise ProgramCandidateStateError(
                "meta-adjudication plan lifecycle_state must be meta_adjudication_plan_ready"
            )
        _validate_non_authority_false(
            meta_adjudication_plan,
            label="meta-adjudication plan",
            keys=(
                "activation_authority",
                "promotion_authority",
                "oracle_authority",
                "governance_authority",
                "external_authority",
                "external_mutation",
            ),
        )
        effect = _safe_mapping(meta_adjudication_plan.get("effect"))
        for key in (
            "candidate_files_mutated",
            "canonical_target_mutated",
            "ak_mutated",
            "governance_mutated",
            "oracle_index_mutated",
            "shared_oracle_mutated",
            "provider_called",
        ):
            if effect.get(key) is not False:
                raise ProgramCandidateStateError(
                    f"meta-adjudication plan must record {key} false"
                )
        meta_identity = _safe_mapping(meta_adjudication_plan.get("identity"))
        if not any(
            _identity_exactly_matches(meta_identity, item)
            for item in source_or_candidate
        ):
            raise ProgramCandidateStateError(
                "meta-adjudication plan identity does not match candidate/source identity"
            )
        meta_manifest = _safe_mapping(meta_adjudication_plan.get("manifest"))
        valid_manifest_hashes = {current_manifest_hash}
        if source_manifest_hash is not None:
            valid_manifest_hashes.add(source_manifest_hash)
        if meta_manifest.get("sha256") not in valid_manifest_hashes:
            raise ProgramCandidateStateError(
                "meta-adjudication plan manifest sha256 does not match candidate/source manifest"
            )
        _validate_meta_adjudication_plan_sidecar_freshness(
            meta_adjudication_plan,
            supplied_sidecar_refs=supplied_sidecar_refs,
        )

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
    return {
        "present": True,
        "schema_version": comparison.get("schema_version"),
        "status": comparison.get("status"),
        "manifest_role": role,
        "improvement_observed": interpretation.get("improvement_observed") is True,
        "needs_more_evidence": interpretation.get("needs_more_evidence") is True,
        "winner_selected": False,
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
    oracle_publication_receipt_path: Path | None = None,
    generation_gate_preflight_path: Path | None = None,
    generation_fitness_results_path: Path | None = None,
    program_evidence_adjudication_path: Path | None = None,
    gepa_refinement_path: Path | None = None,
) -> dict[str, Any]:
    """Build one local truth-state artifact from existing program sidecars."""

    manifest_path = manifest_path.expanduser().resolve()
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

    manifest_hash = _sha256_file(manifest_path)
    activation_sidecar_hashes = {
        "oracle_report": oracle_report_hash,
        "jury_results": jury_results_hash,
        "model_jury_results": model_jury_results_hash,
        "refined_review": review_hash,
        "decision_record": decision_hash,
        "promotion_plan": promotion_plan_hash,
        "candidate_state": None,
        "external_authority_export_preflight": export_preflight_hash,
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
        )
        if path is not None and file_hash is not None
    }

    _validate_optional_inputs(
        candidate_identity=candidate_identity,
        source_identity=source_identity,
        review=review,
        decision=decision,
        jury_results=jury_results,
        model_jury_results=model_jury_results,
        comparison=comparison,
        promotion_plan=promotion_plan,
        export_preflight=export_preflight,
        meta_adjudication_plan=meta_adjudication_plan,
        activation_packet=activation_packet,
        oracle_publication_receipt=oracle_publication_receipt,
        gepa_refinement=gepa_refinement,
        current_manifest_path=manifest_path,
        current_manifest_hash=manifest_hash,
        source_manifest_path=source_manifest_resolved,
        source_manifest_hash=source_manifest_hash,
        behavior_hash=behavior_hash,
        behavior_episode_hash=behavior_episode_hash,
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
        error_type=ProgramCandidateStateError,
    )

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
        "oracle_publication_receipt_sha256": oracle_publication_receipt_hash,
        "generation_gate_preflight_sha256": generation_gate_preflight_hash,
        "generation_fitness_results_sha256": generation_fitness_results_hash,
        "program_evidence_adjudication_sha256": program_evidence_adjudication_hash,
        "gepa_refinement_sha256": gepa_refinement_hash,
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
            "oracle_publication_ref_present": oracle_publication_receipt is not None,
            "target_fidelity_evidence_present": generation_fitness_results is not None,
            "target_protocol_adjudication_present": program_evidence_adjudication
            is not None,
            "gepa_refinement_present": gepa_refinement is not None,
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
            "local_state_written": out_path is not None,
            "program_files_mutated": False,
            "sidecar_inputs_mutated": False,
            "oracle_index_mutated": False,
            "ak_called": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "promotion_state_changed": False,
        },
        "shared_oracle_publication": {
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
    return payload


def write_program_candidate_state(
    state: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Write the local candidate state sidecar."""

    try:
        target = prepare_sidecar_output_path(
            out_path,
            payload=state,
            artifact_label="candidate state",
            protected_names=_FORBIDDEN_OUTPUT_NAMES,
            payload_artifact_root_policy="allow_named",
            allowed_names_in_protected_roots=("program_candidate_state.json",),
        )
    except ValueError as exc:
        raise ProgramCandidateStateError(str(exc)) from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    effect = _safe_mapping(payload.get("effect"))
    effect["local_state_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload
