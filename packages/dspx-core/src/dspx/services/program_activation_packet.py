from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import prepare_sidecar_output_path
from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES
from dspx.services.program_jury_result_validation import (
    validate_program_jury_results_contract,
)
from dspx.services.program_model_jury_validation import (
    PROGRAM_MODEL_JURY_RESULTS_SCHEMA,
    validate_program_model_jury_results_contract,
)
from dspx.services.program_oracle_publication_preflight import (
    AUTHORITY_MIRROR_LABELS,
    ELIGIBLE_REDACTION_STATUSES,
    ELIGIBLE_RETENTION_CLASSES,
    EMPIRICAL_LABELS,
    PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA,
    TARGETS,
)

ACTIVATION_PACKET_SCHEMA = "generated-cognition-program-production-activation-packet-v1"
TRANSITION_TYPE = "generated-cognition-program.production_activation"
GOVERNANCE_BOUNDARY_REF = (
    "~/ai-society/holdingco/governance-kernel/docs/core/definitions/"
    "generated-dspy-program-promotion-governance.md"
)
TRANSITION_PASSPORT_REF = (
    "~/ai-society/holdingco/governance-kernel/docs/core/definitions/"
    "transition-passports/generated-cognition-program-production-activation.md"
)

_EXPECTED_SCHEMAS = {
    "oracle_report": "program-oracle-evidence-report-v1",
    "jury_results": "program-jury-results-v2",
    "model_jury_results": PROGRAM_MODEL_JURY_RESULTS_SCHEMA,
    "refined_review": "program-promotion-review-refined-v1",
    "decision_record": "program-promotion-decision-record-v1",
    "promotion_plan": "program-promotion-plan-v1",
    "oracle_publication_preflight": "program-oracle-shared-publication-preflight-v1",
    "oracle_publication_receipt": "program-oracle-shared-publication-receipt-v1",
    "candidate_state": "program-candidate-state-v1",
    "obsidian_review_adapter_receipt": "dspy-pdf-transition-review-adapter-receipt-v1",
    "canonical_binding_verification": "program-canonical-binding-verification-v1",
    "external_authority_export_preflight": "program-external-authority-export-preflight-v1",
}

CANONICAL_BINDING_VERIFICATION_SCHEMA = "program-canonical-binding-verification-v1"
_AK_DECISION_REF_RE = re.compile(r"^ak://decision/(?P<id>[0-9]+)#accepted$")

_ACTIVATION_PACKET_PROTECTED_OUTPUT_NAMES = {
    *PROTECTED_PROGRAM_ARTIFACT_NAMES,
    "promotion_decision_record.json",
    "promotion_plan.json",
    "jury_results.json",
    "model_jury_results.json",
}

_NON_AUTHORITY = {
    "activation_packet_only": True,
    "program_activation_applied": False,
    "automatic_promotion": False,
    "oracle_ranking": False,
    "oracle_pruning": False,
    "oracle_promotion": False,
    "jury_promotion_authority": False,
    "mlflow_approval_authority": False,
    "governance_authority": False,
    "external_mutation": False,
}

_EFFECT = {
    "activation_packet_written": True,
    "program_files_mutated": False,
    "oracle_index_mutated": False,
    "mlflow_mutated": False,
    "ak_mutated": False,
    "external_authority_mutated": False,
    "production_activation_applied": False,
}


class ProgramActivationPacketError(ValueError):
    """Raised when activation packet inputs are malformed."""


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramActivationPacketError(f"{label} not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramActivationPacketError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramActivationPacketError(
            f"{label} must contain a JSON object: {source}"
        )
    return payload


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


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


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


def _manifest_surfaces(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    surfaces: list[dict[str, Any]] = []
    for surface in _safe_list(candidate.get("surfaces")):
        if isinstance(surface, Mapping):
            surfaces.append({str(key): item for key, item in surface.items()})
    return surfaces


def _artifact_ref(
    path: Path | None, *, schema_version: str | None = None
) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return None
    return {
        "path": str(resolved),
        "sha256": _sha256_file(resolved),
        **({"schema_version": schema_version} if schema_version else {}),
    }


def _load_optional_artifact(
    path: Path | None,
    *,
    label: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if path is None:
        return None, None
    payload = _load_json_object(path, label=label)
    expected_schema = _EXPECTED_SCHEMAS[label]
    if payload.get("schema_version") != expected_schema:
        raise ProgramActivationPacketError(
            f"{label} schema_version must be {expected_schema}"
        )
    return payload, _artifact_ref(path, schema_version=expected_schema)


def _validate_non_authority_false(
    payload: Mapping[str, Any], *, label: str, keys: tuple[str, ...]
) -> None:
    non_authority = _safe_mapping(payload.get("non_authority"))
    invalid = [key for key in keys if non_authority.get(key) is not False]
    if invalid:
        raise ProgramActivationPacketError(
            f"{label} widens non-authority flags: " + ", ".join(invalid)
        )


def _identity_mismatch(
    candidate_identity: Mapping[str, Any],
    artifact_identity: Mapping[str, Any],
) -> list[str]:
    mismatched: list[str] = []
    for key, candidate_value in candidate_identity.items():
        artifact_value = artifact_identity.get(key)
        if artifact_value in {None, ""} or candidate_value in {None, ""}:
            continue
        if str(artifact_value) != str(candidate_value):
            mismatched.append(key)
    return mismatched


def _missing_identity_keys(
    candidate_identity: Mapping[str, Any],
    artifact_identity: Mapping[str, Any],
) -> list[str]:
    return [
        key
        for key, candidate_value in candidate_identity.items()
        if candidate_value not in {None, ""}
        and artifact_identity.get(key) in {None, ""}
    ]


def _validate_artifact_identity(
    candidate_identity: Mapping[str, Any],
    artifact: Mapping[str, Any] | None,
    *,
    label: str,
) -> None:
    if artifact is None:
        return
    artifact_identity = _safe_mapping(artifact.get("identity"))
    if not artifact_identity:
        raise ProgramActivationPacketError(f"{label} missing identity object")
    missing = _missing_identity_keys(candidate_identity, artifact_identity)
    if missing:
        raise ProgramActivationPacketError(
            f"{label} identity is incomplete for candidate identity: "
            + ", ".join(missing)
        )
    mismatched = _identity_mismatch(candidate_identity, artifact_identity)
    if mismatched:
        raise ProgramActivationPacketError(
            f"{label} identity does not match candidate identity: "
            + ", ".join(mismatched)
        )


def _declared_behavior_result_hashes(manifest: Mapping[str, Any]) -> dict[str, str]:
    request = _safe_mapping(manifest.get("request"))
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    behavior_results = _safe_mapping(execution_episode.get("behavior_results"))
    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    receipt_evidence = _safe_mapping(receipt_bundle.get("evidence"))
    hashes: dict[str, str] = {}
    for label, value in (
        ("request.behavior_results_hash", request.get("behavior_results_hash")),
        (
            "execution_episode.behavior_results.content_hash",
            behavior_results.get("content_hash"),
        ),
        (
            "receipt_bundle.evidence.behavior_results_hash",
            receipt_evidence.get("behavior_results_hash"),
        ),
    ):
        text = _first_text(value)
        if text:
            hashes[label] = text
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    for surface in _safe_list(candidate.get("surfaces")):
        if (
            not isinstance(surface, Mapping)
            or surface.get("kind") != "behavior_results"
        ):
            continue
        text = _first_text(surface.get("content_hash"))
        if text:
            hashes["candidate_assembly.surfaces.behavior_results.content_hash"] = text
    return hashes


def _declared_behavior_episode_hashes(manifest: Mapping[str, Any]) -> dict[str, str]:
    request = _safe_mapping(manifest.get("request"))
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    orchestration = _safe_mapping(execution_episode.get("behavior_orchestration"))
    episode_artifact = _safe_mapping(manifest.get("behavior_episode_artifact"))
    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    receipt_evidence = _safe_mapping(receipt_bundle.get("evidence"))
    hashes: dict[str, str] = {}
    for label, value in (
        ("request.behavior_episode_hash", request.get("behavior_episode_hash")),
        (
            "execution_episode.behavior_orchestration.result_hash",
            orchestration.get("result_hash"),
        ),
        (
            "manifest.behavior_episode_artifact.content_hash",
            episode_artifact.get("content_hash"),
        ),
        (
            "receipt_bundle.evidence.behavior_episode_hash",
            receipt_evidence.get("behavior_episode_hash"),
        ),
    ):
        text = _first_text(value)
        if text:
            hashes[label] = text
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    for surface in _safe_list(candidate.get("surfaces")):
        if (
            not isinstance(surface, Mapping)
            or surface.get("kind") != "behavior_episode"
        ):
            continue
        text = _first_text(surface.get("content_hash"))
        if text:
            hashes["candidate_assembly.surfaces.behavior_episode.content_hash"] = text
    return hashes


def _validate_declared_hashes(
    *,
    actual_hash: str,
    declared_hashes: Mapping[str, str],
    label: str,
) -> None:
    mismatched = [
        name
        for name, declared_hash in declared_hashes.items()
        if declared_hash != actual_hash
    ]
    if mismatched:
        raise ProgramActivationPacketError(
            f"{label} hash does not match manifest declaration(s): "
            + ", ".join(sorted(mismatched))
        )


def _behavior_refs(root: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for name, schema, declared_hashes in (
        (
            "behavior_results.json",
            "program-behavior-results-v1",
            _declared_behavior_result_hashes(manifest),
        ),
        (
            "behavior_episode.json",
            "program-behavior-episode-v1",
            _declared_behavior_episode_hashes(manifest),
        ),
    ):
        path = root / name
        if not path.exists():
            continue
        payload = _load_json_object(path, label=name)
        if payload.get("schema_version") != schema:
            raise ProgramActivationPacketError(
                f"{name} schema_version must be {schema}"
            )
        actual_hash = _sha256_file(path)
        _validate_declared_hashes(
            actual_hash=actual_hash,
            declared_hashes=declared_hashes,
            label=name,
        )
        ref = _artifact_ref(path, schema_version=schema)
        if ref is not None:
            refs.append(ref)
    return refs


def _receipt_ref(manifest_path: Path) -> dict[str, Any] | None:
    return _artifact_ref(
        Path(str(manifest_path.expanduser().resolve()) + ".meta.json"),
        schema_version="dspx-run-receipt-v1",
    )


def _decision_outcome(decision_record: Mapping[str, Any] | None) -> str | None:
    if decision_record is None:
        return None
    outcome = str(decision_record.get("outcome") or "").strip()
    return outcome or None


def _decision_record_ref(path: Path | None) -> dict[str, Any] | None:
    return _artifact_ref(path, schema_version="program-promotion-decision-record-v1")


def _validate_decision_authority_owner(
    decision_record: Mapping[str, Any] | None, *, authority_owner: str
) -> None:
    if decision_record is None:
        return
    decided_by = str(decision_record.get("decided_by") or "").strip()
    if decided_by != authority_owner:
        raise ProgramActivationPacketError(
            "decision_record decided_by must match activation authority_owner"
        )


def _validate_jury_results_artifact_binding(
    jury_results: Mapping[str, Any],
    *,
    manifest_path: Path,
    manifest_hash: str,
) -> None:
    validate_program_jury_results_contract(
        jury_results,
        valid_manifest_refs={manifest_path: manifest_hash},
        label="jury_results",
        error_type=ProgramActivationPacketError,
        outside_root_message="outside the activation manifest root",
        manifest_mismatch_message=(
            "jury_results manifest sha256 does not match activation manifest"
        ),
    )


def _validate_activation_evidence_boundaries(
    *,
    manifest_path: Path,
    manifest_hash: str,
    jury_results: Mapping[str, Any] | None,
    model_jury_results: Mapping[str, Any] | None,
    refined_review: Mapping[str, Any] | None,
    decision_record: Mapping[str, Any] | None,
    promotion_plan: Mapping[str, Any] | None,
) -> None:
    if jury_results is not None:
        _validate_jury_results_artifact_binding(
            jury_results,
            manifest_path=manifest_path,
            manifest_hash=manifest_hash,
        )
    if model_jury_results is not None:
        validate_program_model_jury_results_contract(
            model_jury_results,
            label="model_jury_results",
            error_type=ProgramActivationPacketError,
        )
    if refined_review is not None:
        _validate_non_authority_false(
            refined_review,
            label="refined_review",
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
    if decision_record is not None:
        _validate_non_authority_false(
            decision_record,
            label="decision_record",
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
    if promotion_plan is not None:
        _validate_non_authority_false(
            promotion_plan,
            label="promotion_plan",
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


def _validate_redacted_database_url_posture(
    target: Mapping[str, Any], *, label: str
) -> None:
    if any(
        key in target
        for key in (
            "database_url",
            "database_url_raw",
            "postgres_url",
            "postgres_url_raw",
        )
    ):
        raise ProgramActivationPacketError(
            f"{label} target must not include raw database URL fields"
        )
    if target.get("database_url_present") is True:
        redacted = str(target.get("database_url_redacted") or "").strip()
        if not redacted:
            raise ProgramActivationPacketError(
                f"{label} target.database_url_redacted is required"
            )
        if "://" in redacted and "@" in redacted and ":<redacted>@" not in redacted:
            raise ProgramActivationPacketError(
                f"{label} target.database_url_redacted must not expose secret-bearing credentials"
            )
        lowered = redacted.lower()
        if any(marker in lowered for marker in ("super-secret", "password=", "token=")):
            raise ProgramActivationPacketError(
                f"{label} target.database_url_redacted must not expose secret values"
            )


def _validate_oracle_publication_target_posture(target: Mapping[str, Any]) -> None:
    if not target:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt target posture is required"
        )
    if not str(target.get("backend") or "").strip():
        raise ProgramActivationPacketError(
            "oracle_publication_receipt target.backend is required"
        )
    if target.get("connection_attempted") is not True:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt target.connection_attempted must be true"
        )
    if target.get("shared_write_attempted") is not True:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt target.shared_write_attempted must be true"
        )
    _validate_redacted_database_url_posture(target, label="oracle_publication_receipt")


def _validate_oracle_publication_preflight_target_posture(
    target: Mapping[str, Any],
) -> str:
    if not target:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight target posture is required"
        )
    target_name = str(target.get("target") or "").strip()
    if target_name not in TARGETS:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight target must be a supported shared Oracle target"
        )
    if target.get("target_supported_by_preflight") is not True:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight target_supported_by_preflight must be true"
        )
    if target.get("connection_attempted") is not False:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight target.connection_attempted must be false"
        )
    if target.get("shared_write_attempted") is not False:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight target.shared_write_attempted must be false"
        )
    _validate_redacted_database_url_posture(
        target, label="oracle_publication_preflight"
    )
    return target_name


def _validate_oracle_publication_receipt_source_lineage(
    *,
    source: Mapping[str, Any],
    preflight: Mapping[str, Any] | None,
    preflight_ref: Mapping[str, Any] | None,
) -> None:
    if source.get("local_paths_omitted_from_shared_record") is not True:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt must omit local paths from shared record"
        )
    for key in (
        "preflight_file",
        "preflight_sha256",
        "oracle_evidence_file",
        "oracle_evidence_sha256",
    ):
        if not str(source.get(key) or "").strip():
            raise ProgramActivationPacketError(
                f"oracle_publication_receipt source.{key} is required"
            )
    if preflight is None:
        return
    preflight_hash = str((preflight_ref or {}).get("sha256") or "").strip()
    if preflight_hash and source.get("preflight_sha256") != preflight_hash:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt source.preflight_sha256 does not match supplied preflight"
        )
    preflight_hashes = _safe_mapping(preflight.get("artifact_hashes"))
    if source.get("oracle_evidence_sha256") != preflight_hashes.get(
        "oracle_evidence_sha256"
    ):
        raise ProgramActivationPacketError(
            "oracle_publication_receipt source.oracle_evidence_sha256 does not match supplied preflight"
        )


def _validate_oracle_publication_receipt(
    identity: Mapping[str, Any],
    receipt: Mapping[str, Any] | None,
    *,
    preflight: Mapping[str, Any] | None = None,
    preflight_ref: Mapping[str, Any] | None = None,
) -> None:
    if receipt is None:
        return
    if receipt.get("status") != "published":
        raise ProgramActivationPacketError(
            "oracle_publication_receipt status must be published"
        )
    _validate_artifact_identity(
        identity,
        receipt,
        label="oracle_publication_receipt",
    )
    publication_id = str(receipt.get("publication_id") or "").strip()
    run_id = str(receipt.get("run_id") or "").strip()
    if not publication_id:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt publication_id is required"
        )
    expected_run_id = f"program-oracle-publication:{publication_id}"
    if run_id != expected_run_id:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt run_id must match publication_id"
        )

    idempotency = _safe_mapping(receipt.get("idempotency"))
    expected_idempotency = {
        "publication_id": publication_id,
        "run_id": run_id,
        "safe_to_retry": True,
    }
    mismatched_idempotency = [
        key
        for key, expected in expected_idempotency.items()
        if idempotency.get(key) != expected
    ]
    if mismatched_idempotency:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt idempotency contract mismatch: "
            + ", ".join(mismatched_idempotency)
        )

    publication = _safe_mapping(receipt.get("publication"))
    record = _safe_mapping(receipt.get("record"))
    if preflight is not None:
        preflight_publication = _safe_mapping(preflight.get("publication"))
        if publication != preflight_publication:
            raise ProgramActivationPacketError(
                "oracle_publication_receipt publication does not match supplied preflight"
            )
        preflight_record = _safe_mapping(preflight.get("planned_record"))
        expected_preflight_record = {
            "schema_version": preflight_record.get("schema_version"),
            "publication_label": preflight_record.get("publication_label"),
            "publication_label_class": preflight_record.get("publication_label_class"),
            "retention_class": preflight_record.get("retention_class"),
            "redaction_status": preflight_record.get("redaction_status"),
            "authority_ref": preflight_record.get("authority_ref"),
            "non_authority": preflight_record.get("non_authority"),
        }
        mismatched_preflight_record = [
            key
            for key, expected in expected_preflight_record.items()
            if record.get(key) != expected
        ]
        if mismatched_preflight_record:
            raise ProgramActivationPacketError(
                "oracle_publication_receipt record does not match supplied preflight planned_record: "
                + ", ".join(sorted(mismatched_preflight_record))
            )
    expected_record = {
        "schema_version": "program-oracle-shared-publication-v1",
        "run_kind": "program-oracle-shared-publication",
        "template_version": "program-oracle-shared-publication-v1",
        "provider": "program-gen",
        "publication_label": publication.get("publication_label"),
        "publication_label_class": publication.get("publication_label_class"),
        "retention_class": publication.get("retention_class"),
        "redaction_status": publication.get("redaction_status"),
        "authority_ref": publication.get("authority_ref"),
    }
    mismatched_record = [
        key for key, expected in expected_record.items() if record.get(key) != expected
    ]
    if mismatched_record:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt record does not match publication fields: "
            + ", ".join(sorted(mismatched_record))
        )
    _validate_non_authority_false(
        record,
        label="oracle_publication_receipt record",
        keys=(
            "oracle_ranking",
            "oracle_pruning",
            "oracle_promotion",
            "governance_authority",
            "external_mutation",
        ),
    )

    _validate_oracle_publication_target_posture(_safe_mapping(receipt.get("target")))

    _validate_oracle_publication_receipt_source_lineage(
        source=_safe_mapping(receipt.get("source")),
        preflight=preflight,
        preflight_ref=preflight_ref,
    )

    effect = _safe_mapping(receipt.get("effect"))
    if effect.get("shared_oracle_mutated") is not True:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt must record shared_oracle_mutated true"
        )
    for key in (
        "ak_called",
        "governance_mutated",
        "mlflow_mutated",
        "program_files_mutated",
        "promotion_state_changed",
    ):
        if effect.get(key) is not False:
            raise ProgramActivationPacketError(
                f"oracle_publication_receipt must record {key} false"
            )
    non_authority = _safe_mapping(receipt.get("non_authority"))
    invalid = [
        key
        for key in (
            "oracle_authority",
            "promotion_authority",
            "governance_authority",
            "agent_kernel_mutation",
            "winner_selection",
            "automatic_promotion",
        )
        if non_authority.get(key) is not False
    ]
    if invalid:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt widens non-authority flags: "
            + ", ".join(invalid)
        )


def _parse_ak_decision_ref(canonical_binding_ref: str) -> int:
    match = _AK_DECISION_REF_RE.fullmatch(str(canonical_binding_ref or "").strip())
    if match is None:
        raise ProgramActivationPacketError(
            "canonical_binding_ref must match ak://decision/<id>#accepted"
        )
    return int(match.group("id"))


def _ak_decision_payload(envelope: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = envelope.get("decision")
    if isinstance(decision, Mapping):
        return decision
    return envelope


def _validate_canonical_binding_verification(
    *,
    verification: Mapping[str, Any] | None,
    canonical_binding_ref: str | None,
    decision_record_ref: Mapping[str, Any] | None,
) -> None:
    if verification is None:
        return
    if not str(canonical_binding_ref or "").strip():
        raise ProgramActivationPacketError(
            "canonical_binding_verification requires canonical_binding_ref"
        )
    if verification.get("status") != "verified":
        raise ProgramActivationPacketError(
            "canonical_binding_verification status must be verified"
        )
    if verification.get("canonical_binding_ref") != canonical_binding_ref:
        raise ProgramActivationPacketError(
            "canonical_binding_verification canonical_binding_ref does not match"
        )
    if verification.get("binding_kind") != "ak_decision":
        raise ProgramActivationPacketError(
            "canonical_binding_verification binding_kind must be ak_decision"
        )
    if verification.get("ak_decision_outcome") != "accepted":
        raise ProgramActivationPacketError(
            "canonical_binding_verification ak_decision_outcome must be accepted"
        )
    if verification.get("ak_decision_state") not in {"adr_recorded", "unblocked"}:
        raise ProgramActivationPacketError(
            "canonical_binding_verification ak_decision_state must be adr_recorded or unblocked"
        )
    if decision_record_ref is not None:
        expected_hash = _strip_sha256_prefix(decision_record_ref.get("sha256"))
        actual_hash = _strip_sha256_prefix(verification.get("decision_record_sha256"))
        if expected_hash and not actual_hash:
            raise ProgramActivationPacketError(
                "canonical_binding_verification decision_record_sha256 is required"
            )
        if expected_hash and actual_hash != expected_hash:
            raise ProgramActivationPacketError(
                "canonical_binding_verification decision_record_sha256 does not match"
            )


def _canonical_binding_verified(verification: Mapping[str, Any] | None) -> bool:
    return (
        verification is not None
        and verification.get("schema_version") == CANONICAL_BINDING_VERIFICATION_SCHEMA
        and verification.get("status") == "verified"
    )


def _canonical_binding_created_from(
    decision_record_path: Path, decision_record: Mapping[str, Any]
) -> dict[str, Any]:
    created_from = _safe_mapping(decision_record.get("created_from"))
    result: dict[str, Any] = {"decision_record_path": str(decision_record_path)}
    refined_review_path_text = _first_text(created_from.get("refined_review_path"))
    if refined_review_path_text is None:
        return result
    refined_review_path = Path(refined_review_path_text).expanduser().resolve()
    result["refined_review_path"] = str(refined_review_path)
    try:
        refined_review = _load_json_object(refined_review_path, label="refined_review")
    except ProgramActivationPacketError:
        return result
    review_created_from = _safe_mapping(refined_review.get("created_from"))
    manifest_path_text = _first_text(review_created_from.get("manifest_path"))
    if manifest_path_text is not None:
        result["manifest_path"] = str(Path(manifest_path_text).expanduser().resolve())
    return result


def build_canonical_binding_verification(
    *,
    canonical_binding_ref: str,
    decision_record_path: Path,
    ak_bin: Path | str = "ak",
    ak_db: Path | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    normalized_ref = str(canonical_binding_ref or "").strip()
    decision_id = _parse_ak_decision_ref(normalized_ref)
    decision_record_path = decision_record_path.expanduser().resolve()
    decision_record = _load_json_object(decision_record_path, label="decision_record")
    if decision_record.get("schema_version") != "program-promotion-decision-record-v1":
        raise ProgramActivationPacketError(
            "decision_record schema_version must be program-promotion-decision-record-v1"
        )
    created_from = _safe_mapping(decision_record.get("created_from"))
    if created_from.get("ak_decision_ref") != normalized_ref:
        raise ProgramActivationPacketError(
            "decision_record created_from.ak_decision_ref must match canonical_binding_ref"
        )
    if decision_record.get("outcome") != "promote":
        raise ProgramActivationPacketError("decision_record outcome must be promote")

    command = [
        str(Path(ak_bin).expanduser()),
        "decision",
        "get",
        str(decision_id),
        "-F",
        "json",
    ]
    if ak_db is not None:
        command.extend(["--db", str(ak_db.expanduser())])
    try:
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise ProgramActivationPacketError(
            f"canonical binding verification could not read AK decision {decision_id}: {exc}"
        ) from exc
    if proc.returncode != 0:
        raise ProgramActivationPacketError(
            "canonical binding verification AK lookup failed: " + proc.stderr.strip()
        )
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProgramActivationPacketError(
            "canonical binding verification AK lookup did not return JSON"
        ) from exc
    if not isinstance(envelope, Mapping):
        raise ProgramActivationPacketError(
            "canonical binding verification AK lookup must return a JSON object"
        )
    decision = _ak_decision_payload(envelope)
    if int(decision.get("id") or -1) != decision_id:
        raise ProgramActivationPacketError("AK decision id does not match binding ref")
    if decision.get("outcome") != "accepted":
        raise ProgramActivationPacketError("AK decision outcome must be accepted")
    if decision.get("state") not in {"adr_recorded", "unblocked"}:
        raise ProgramActivationPacketError(
            "AK decision state must be adr_recorded or unblocked"
        )
    if decision.get("adr_ref") != created_from.get("decision_doc"):
        raise ProgramActivationPacketError(
            "AK decision adr_ref must match decision_record created_from.decision_doc"
        )

    return {
        "schema_version": CANONICAL_BINDING_VERIFICATION_SCHEMA,
        "status": "verified",
        "canonical_binding_ref": normalized_ref,
        "binding_kind": "ak_decision",
        "decision_id": decision_id,
        "created_from": _canonical_binding_created_from(
            decision_record_path, decision_record
        ),
        "decision_record": _decision_record_ref(decision_record_path),
        "decision_record_sha256": _sha256_file(decision_record_path),
        "ak_decision_state": decision.get("state"),
        "ak_decision_outcome": decision.get("outcome"),
        "ak_decision_title": decision.get("title"),
        "ak_decision_rfc_ref": decision.get("rfc_ref"),
        "ak_decision_adr_ref": decision.get("adr_ref"),
        "ak_decision_evidence_ref": decision.get("evidence_ref"),
        "authority_owner": decision_record.get("decided_by"),
        "effect": {
            "ak_read_only": True,
            "ak_mutated": False,
            "program_files_mutated": False,
            "external_authority_mutated": False,
            "production_activation_applied": False,
        },
        "non_authority": {
            "binding_verification_only": True,
            "production_activation_authority": False,
            "rollout_preflight_authority": False,
            "external_mutation": False,
        },
    }


def write_canonical_binding_verification(
    verification: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    payload = dict(verification)
    try:
        out_path = prepare_sidecar_output_path(
            out_path,
            payload=payload,
            artifact_label="canonical binding verification",
            protected_names=_ACTIVATION_PACKET_PROTECTED_OUTPUT_NAMES,
            payload_artifact_root_policy="forbid",
        )
    except ValueError as exc:
        raise ProgramActivationPacketError(str(exc)) from exc
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def _validate_oracle_report_identity(
    identity: Mapping[str, Any], oracle_report: Mapping[str, Any] | None
) -> None:
    if oracle_report is None:
        return
    records = _safe_list(oracle_report.get("records"))
    for record in records:
        if not isinstance(record, Mapping):
            continue
        record_identity = _safe_mapping(record.get("identity"))
        if not record_identity:
            continue
        if _missing_identity_keys(identity, record_identity):
            continue
        if not _identity_mismatch(identity, record_identity):
            return
    raise ProgramActivationPacketError(
        "oracle_report does not contain a record matching candidate identity"
    )


def _validate_oracle_publication_preflight(
    identity: Mapping[str, Any], preflight_packet: Mapping[str, Any] | None
) -> None:
    if preflight_packet is None:
        return
    if preflight_packet.get("status") != "ready_not_published":
        raise ProgramActivationPacketError(
            "oracle_publication_preflight status must be ready_not_published"
        )
    preflight_identity = _safe_mapping(preflight_packet.get("identity"))
    if not preflight_identity:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight missing identity object"
        )
    if preflight_identity != dict(identity):
        raise ProgramActivationPacketError(
            "oracle_publication_preflight identity does not match candidate identity"
        )

    checks = _safe_mapping(preflight_packet.get("preflight"))
    required_ready_checks = (
        "manifest_valid",
        "oracle_evidence_present",
        "oracle_evidence_non_authority_valid",
        "identity_matches_manifest",
        "runtime_trace_summary_valid",
        "runtime_trace_hash_match",
        "runtime_trace_semantics_valid",
        "publication_label_valid",
        "authority_ref_requirement_satisfied",
        "publisher_fields_present",
        "redaction_status_eligible",
        "retention_class_eligible",
        "ready_for_shared_publication",
    )
    failed_checks = [
        key for key in required_ready_checks if checks.get(key) is not True
    ]
    if failed_checks:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight readiness checks must be true: "
            + ", ".join(failed_checks)
        )
    if checks.get("blocking_reasons") != []:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight blocking_reasons must be empty"
        )

    effect = _safe_mapping(preflight_packet.get("effect"))
    for key in (
        "shared_oracle_mutated",
        "ak_called",
        "governance_mutated",
        "mlflow_mutated",
        "program_files_mutated",
        "promotion_state_changed",
    ):
        if effect.get(key) is not False:
            raise ProgramActivationPacketError(
                f"oracle_publication_preflight must record {key} false"
            )
    _validate_non_authority_false(
        preflight_packet,
        label="oracle_publication_preflight",
        keys=(
            "oracle_authority",
            "promotion_authority",
            "governance_authority",
            "agent_kernel_mutation",
            "winner_selection",
            "automatic_promotion",
        ),
    )

    publication_id = str(preflight_packet.get("publication_id") or "").strip()
    if not publication_id:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight publication_id is required"
        )
    idempotency = _safe_mapping(preflight_packet.get("idempotency"))
    expected_idempotency = {
        "publication_id": publication_id,
        "safe_to_recompute": True,
        "same_inputs_same_publication_id": True,
        "shared_duplicate_check_performed": False,
    }
    mismatched_idempotency = [
        key
        for key, expected in expected_idempotency.items()
        if idempotency.get(key) != expected
    ]
    if mismatched_idempotency:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight idempotency contract mismatch: "
            + ", ".join(mismatched_idempotency)
        )

    target_name = _validate_oracle_publication_preflight_target_posture(
        _safe_mapping(preflight_packet.get("target"))
    )
    artifact_hashes = _safe_mapping(preflight_packet.get("artifact_hashes"))
    required_hashes = (
        "manifest_sha256",
        "oracle_evidence_sha256",
        "runtime_traces_sha256",
    )
    missing_hashes = [
        key
        for key in required_hashes
        if not str(artifact_hashes.get(key) or "").strip()
    ]
    if missing_hashes:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight artifact_hashes missing required hashes: "
            + ", ".join(missing_hashes)
        )

    publication = _safe_mapping(preflight_packet.get("publication"))
    label = str(publication.get("publication_label") or "").strip()
    if label not in EMPIRICAL_LABELS | AUTHORITY_MIRROR_LABELS:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight publication_label is not eligible"
        )
    expected_label_class = (
        "authority_mirror" if label in AUTHORITY_MIRROR_LABELS else "empirical"
    )
    authority_ref = str(publication.get("authority_ref") or "").strip() or None
    expected_publication = {
        "publication_label_class": expected_label_class,
        "authority_ref": authority_ref,
        "authority_ref_required": expected_label_class == "authority_mirror",
        "authority_ref_kind": "opaque_reference_only" if authority_ref else None,
        "publisher_secret_ref_policy": "1password_refs_only_values_never_persisted",
        "publisher_identity_kind": "declared_not_authenticated",
        "redaction_status_kind": "declared_custody_assertion_not_dlp_proof",
        "retraction_supported_by_future_record": True,
    }
    mismatched_publication = [
        key
        for key, expected in expected_publication.items()
        if publication.get(key) != expected
    ]
    if mismatched_publication:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight publication contract mismatch: "
            + ", ".join(sorted(mismatched_publication))
        )
    if expected_label_class == "authority_mirror" and authority_ref is None:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight authority_ref is required for authority-mirror labels"
        )
    publisher_id = str(publication.get("publisher_id") or "").strip()
    if not publisher_id:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight publication.publisher_id is required"
        )
    if not str(publication.get("publisher_role") or "").strip():
        raise ProgramActivationPacketError(
            "oracle_publication_preflight publication.publisher_role is required"
        )
    if not str(publication.get("publisher_assertion") or "").strip():
        raise ProgramActivationPacketError(
            "oracle_publication_preflight publication.publisher_assertion is required"
        )
    redaction_status = str(publication.get("redaction_status") or "").strip()
    if redaction_status not in ELIGIBLE_REDACTION_STATUSES:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight redaction_status is not eligible"
        )
    retention_class = str(publication.get("retention_class") or "").strip()
    if retention_class not in ELIGIBLE_RETENTION_CLASSES:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight retention_class is not eligible"
        )
    publisher_secret_refs = _safe_list(publication.get("publisher_secret_refs"))
    if any(
        not isinstance(item, Mapping) or item.get("secret_value_persisted") is not False
        for item in publisher_secret_refs
    ):
        raise ProgramActivationPacketError(
            "oracle_publication_preflight publisher_secret_refs must be descriptors without persisted secret values"
        )
    expected_publication_id = (
        "prog-oracle-pub-"
        + _sha256_payload(
            {
                "schema_version": PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA,
                "target": target_name,
                "identity": {
                    key: value for key, value in sorted(identity.items()) if value
                },
                "artifact_hashes": dict(sorted(artifact_hashes.items())),
                "publication_label": label,
                "authority_ref": authority_ref,
                "publisher_id": publisher_id,
                "redaction_status": redaction_status,
                "retention_class": retention_class,
                "publisher_secret_refs": publisher_secret_refs,
            }
        )[:20]
    )
    if publication_id != expected_publication_id:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight publication_id does not match recomputed idempotency key"
        )

    planned_record = _safe_mapping(preflight_packet.get("planned_record"))
    expected_planned = {
        "candidate_id": identity.get("candidate_id"),
        "assembly_id": identity.get("assembly_id"),
        "receipt_bundle_id": identity.get("receipt_bundle_id"),
        "oracle_evidence_sha256": artifact_hashes.get("oracle_evidence_sha256"),
        "manifest_sha256": artifact_hashes.get("manifest_sha256"),
        "runtime_traces_sha256": artifact_hashes.get("runtime_traces_sha256"),
        "publication_label": publication.get("publication_label"),
        "publication_label_class": publication.get("publication_label_class"),
        "publisher_id": publication.get("publisher_id"),
        "publisher_role": publication.get("publisher_role"),
        "publisher_secret_refs": publication.get("publisher_secret_refs"),
        "authority_ref": publication.get("authority_ref"),
        "authority_ref_kind": publication.get("authority_ref_kind"),
        "redaction_status": publication.get("redaction_status"),
        "retention_class": publication.get("retention_class"),
    }
    mismatched_planned = [
        key
        for key, expected in expected_planned.items()
        if planned_record.get(key) != expected
    ]
    if mismatched_planned:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight planned_record does not match validated "
            "preflight fields: " + ", ".join(sorted(mismatched_planned))
        )
    runtime_traces = _safe_mapping(planned_record.get("runtime_traces"))
    if not runtime_traces:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight planned_record missing runtime_traces"
        )
    _validate_non_authority_false(
        runtime_traces,
        label="oracle_publication_preflight planned_record runtime_traces",
        keys=(
            "activation_authority",
            "canonical_mutation",
            "external_mutation",
            "governance_authority",
            "oracle_authority",
            "promotion_authority",
            "ranking_authority",
            "winner_selection",
        ),
    )
    _validate_non_authority_false(
        planned_record,
        label="oracle_publication_preflight planned_record",
        keys=(
            "oracle_ranking",
            "oracle_pruning",
            "oracle_promotion",
            "governance_authority",
            "external_mutation",
        ),
    )


def _oracle_publication_preflight_ref(
    preflight_ref: dict[str, Any] | None,
    preflight_packet: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if preflight_ref is None or preflight_packet is None:
        return None
    publication = _safe_mapping(preflight_packet.get("publication"))
    checks = _safe_mapping(preflight_packet.get("preflight"))
    effect = _safe_mapping(preflight_packet.get("effect"))
    return {
        **preflight_ref,
        "publication_id": preflight_packet.get("publication_id"),
        "publication_label": publication.get("publication_label"),
        "publication_label_class": publication.get("publication_label_class"),
        "authority_ref": publication.get("authority_ref"),
        "retention_class": publication.get("retention_class"),
        "ready_for_shared_publication": checks.get("ready_for_shared_publication")
        is True,
        "runtime_trace_semantics_valid": checks.get("runtime_trace_semantics_valid")
        is True,
        "runtime_trace_hash_match": checks.get("runtime_trace_hash_match") is True,
        "blocking_reasons": _safe_list(checks.get("blocking_reasons")),
        "preflight_only": True,
        "activation_authority": False,
        "promotion_authority": False,
        "shared_oracle_mutated": effect.get("shared_oracle_mutated") is True,
    }


def _oracle_publication_ref(
    receipt_ref: dict[str, Any] | None,
    receipt: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if receipt_ref is None or receipt is None:
        return None
    publication = _safe_mapping(receipt.get("publication"))
    effect = _safe_mapping(receipt.get("effect"))
    return {
        **receipt_ref,
        "publication_id": receipt.get("publication_id"),
        "run_id": receipt.get("run_id"),
        "publication_label": publication.get("publication_label"),
        "publication_label_class": publication.get("publication_label_class"),
        "authority_ref": publication.get("authority_ref"),
        "retention_class": publication.get("retention_class"),
        "evidence_only": True,
        "activation_authority": False,
        "promotion_authority": False,
        "shared_oracle_mutated": effect.get("shared_oracle_mutated") is True,
    }


def _strip_sha256_prefix(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text.removeprefix("sha256:")


def _candidate_state_publication_refs(
    candidate_state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if candidate_state is None:
        return {
            "candidate_state_present": False,
            "preflight_present": False,
            "preflight_publication_id": None,
            "receipt_present": False,
            "receipt_publication_id": None,
        }
    evidence = _safe_mapping(candidate_state.get("evidence_state"))
    shared = _safe_mapping(candidate_state.get("shared_oracle_publication"))
    state_preflight = _safe_mapping(evidence.get("oracle_publication_preflight"))
    state_receipt = _safe_mapping(evidence.get("oracle_publication_receipt"))
    return {
        "candidate_state_present": True,
        "preflight_present": state_preflight.get("present") is True
        or shared.get("preflight_present") is True,
        "preflight_ready": shared.get("preflight_ready") is True,
        "preflight_publication_id": state_preflight.get("publication_id"),
        "receipt_present": state_receipt.get("present") is True
        or shared.get("evidence_ref_present") is True,
        "receipt_publication_id": state_receipt.get("publication_id"),
    }


def _oracle_publication_alignment_summary(
    *,
    candidate_state: Mapping[str, Any] | None,
    oracle_publication_preflight: Mapping[str, Any] | None,
    oracle_publication_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    candidate_refs = _candidate_state_publication_refs(candidate_state)
    preflight_publication_id = (
        oracle_publication_preflight.get("publication_id")
        if oracle_publication_preflight is not None
        else None
    )
    receipt_publication_id = (
        oracle_publication_receipt.get("publication_id")
        if oracle_publication_receipt is not None
        else None
    )
    supplied_ids = [
        value for value in (preflight_publication_id, receipt_publication_id) if value
    ]
    candidate_ids = [
        value
        for value in (
            candidate_refs.get("preflight_publication_id"),
            candidate_refs.get("receipt_publication_id"),
        )
        if value
    ]
    unique_ids = set(supplied_ids + candidate_ids)
    return {
        "candidate_state_present": candidate_refs["candidate_state_present"],
        "candidate_state_preflight_present": candidate_refs["preflight_present"],
        "candidate_state_receipt_present": candidate_refs["receipt_present"],
        "preflight_ref_supplied": oracle_publication_preflight is not None,
        "receipt_ref_supplied": oracle_publication_receipt is not None,
        "preflight_publication_id": preflight_publication_id,
        "receipt_publication_id": receipt_publication_id,
        "candidate_state_preflight_publication_id": candidate_refs.get(
            "preflight_publication_id"
        ),
        "candidate_state_receipt_publication_id": candidate_refs.get(
            "receipt_publication_id"
        ),
        "publication_ids_aligned": len(unique_ids) <= 1,
        "evidence_only": True,
        "activation_authority": False,
        "promotion_authority": False,
    }


def _validate_export_preflight_artifact_hashes(
    export_preflight: Mapping[str, Any],
    *,
    manifest_path: Path,
    decision_record_path: Path | None,
) -> None:
    artifact_hashes = _safe_mapping(export_preflight.get("artifact_hashes"))
    manifest_hash = _sha256_file(manifest_path)
    if artifact_hashes.get("manifest_sha256") != manifest_hash:
        raise ProgramActivationPacketError(
            "external authority export preflight manifest_sha256 does not match current manifest"
        )
    if decision_record_path is not None:
        decision_hash = _sha256_file(decision_record_path)
        if artifact_hashes.get("decision_record_sha256") != decision_hash:
            raise ProgramActivationPacketError(
                "external authority export preflight decision_record_sha256 does not match supplied decision record"
            )
    planned_payload = _safe_mapping(export_preflight.get("planned_payload"))
    refs_by_kind: dict[str, Mapping[str, Any]] = {}
    for ref in _safe_list(planned_payload.get("evidence_refs")):
        if not isinstance(ref, Mapping):
            raise ProgramActivationPacketError(
                "external authority export preflight evidence refs must be objects"
            )
        kind = _first_text(ref.get("kind"))
        raw_path = _first_text(ref.get("path"))
        expected_hash = _first_text(ref.get("sha256"))
        if kind is None or raw_path is None or expected_hash is None:
            raise ProgramActivationPacketError(
                "external authority export preflight evidence refs must include kind, path, and sha256"
            )
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise ProgramActivationPacketError(
                f"external authority export preflight evidence ref is missing: {path}"
            )
        actual_hash = _sha256_file(path)
        if actual_hash != expected_hash:
            raise ProgramActivationPacketError(
                "external authority export preflight evidence ref hash mismatch: "
                f"{path}"
            )
        refs_by_kind[kind] = ref
        if ref.get("kind") == "program_manifest" and actual_hash != manifest_hash:
            raise ProgramActivationPacketError(
                "external authority export preflight program_manifest ref does not match current manifest"
            )

    expected_refs = {
        "program_manifest": artifact_hashes.get("manifest_sha256"),
        "promotion_decision_record": artifact_hashes.get("decision_record_sha256"),
        "candidate_comparison": artifact_hashes.get("comparison_sha256"),
    }
    if export_preflight.get("status") == "ready_not_applied":
        for kind, expected_hash in expected_refs.items():
            if expected_hash is None or kind not in refs_by_kind:
                raise ProgramActivationPacketError(
                    f"external authority export preflight is missing {kind} evidence ref"
                )
    for kind, expected_hash in expected_refs.items():
        if expected_hash is None or kind not in refs_by_kind:
            continue
        if refs_by_kind[kind].get("sha256") != expected_hash:
            raise ProgramActivationPacketError(
                f"external authority export preflight {kind} evidence ref hash mismatch"
            )


def _validate_external_authority_export_preflight(
    candidate_identity: Mapping[str, Any],
    export_preflight: Mapping[str, Any] | None,
    *,
    manifest_path: Path,
    decision_record_path: Path | None,
) -> None:
    if export_preflight is None:
        return
    if export_preflight.get("status") not in {
        "ready_not_applied",
        "incomplete_preflight",
    }:
        raise ProgramActivationPacketError(
            "external authority export preflight status must be ready_not_applied or incomplete_preflight"
        )
    _validate_artifact_identity(
        candidate_identity,
        export_preflight,
        label="external_authority_export_preflight",
    )
    preflight = _safe_mapping(export_preflight.get("preflight"))
    if preflight.get("ready_for_future_apply") is not False:
        raise ProgramActivationPacketError(
            "external authority export preflight must keep ready_for_future_apply false"
        )
    if preflight.get("external_mutation_requested") is not False:
        raise ProgramActivationPacketError(
            "external authority export preflight must record external_mutation_requested false"
        )
    target = _safe_mapping(export_preflight.get("target"))
    if target.get("mutation_supported") is not False:
        raise ProgramActivationPacketError(
            "external authority export preflight target must keep mutation_supported false"
        )
    if target.get("apply_command_available") is not False:
        raise ProgramActivationPacketError(
            "external authority export preflight target must keep apply_command_available false"
        )
    effect = _safe_mapping(export_preflight.get("effect"))
    for key in (
        "external_authority_mutated",
        "ak_called",
        "governance_mutated",
        "program_files_mutated",
        "promotion_state_changed",
    ):
        if effect.get(key) is not False:
            raise ProgramActivationPacketError(
                f"external authority export preflight must record {key} false"
            )
    non_authority = _safe_mapping(export_preflight.get("non_authority"))
    if non_authority.get("preflight_only") is not True:
        raise ProgramActivationPacketError(
            "external authority export preflight must be preflight-only"
        )
    if non_authority.get("planned_not_exported") is not True:
        raise ProgramActivationPacketError(
            "external authority export preflight must be planned_not_exported"
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
    _validate_export_preflight_artifact_hashes(
        export_preflight,
        manifest_path=manifest_path,
        decision_record_path=decision_record_path,
    )


def _external_authority_export_preflight_ref(
    artifact_ref: Mapping[str, Any] | None,
    export_preflight: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if artifact_ref is None or export_preflight is None:
        return None
    target = _safe_mapping(export_preflight.get("target"))
    preflight = _safe_mapping(export_preflight.get("preflight"))
    return {
        **dict(artifact_ref),
        "status": export_preflight.get("status"),
        "export_id": export_preflight.get("export_id"),
        "target_system": target.get("system"),
        "target_contract": target.get("target_contract"),
        "external_ref": target.get("external_ref"),
        "ready_for_future_apply": preflight.get("ready_for_future_apply") is True,
        "blocking_reasons": _safe_list(preflight.get("blocking_reasons")),
        "external_apply_blocking_reasons": _safe_list(
            preflight.get("external_apply_blocking_reasons")
        ),
        "preflight_only": _safe_mapping(export_preflight.get("non_authority")).get(
            "preflight_only"
        )
        is True,
        "planned_not_exported": _safe_mapping(
            export_preflight.get("non_authority")
        ).get("planned_not_exported")
        is True,
    }


def _validate_candidate_state_publication_alignment(
    *,
    candidate_state: Mapping[str, Any] | None,
    oracle_publication_preflight: Mapping[str, Any] | None,
    oracle_publication_receipt: Mapping[str, Any] | None,
) -> None:
    if (
        oracle_publication_preflight is not None
        and oracle_publication_receipt is not None
        and oracle_publication_preflight.get("publication_id")
        != oracle_publication_receipt.get("publication_id")
    ):
        raise ProgramActivationPacketError(
            "oracle_publication_preflight/receipt publication_id mismatch"
        )
    if candidate_state is None:
        return
    evidence = _safe_mapping(candidate_state.get("evidence_state"))
    shared = _safe_mapping(candidate_state.get("shared_oracle_publication"))
    state_preflight = _safe_mapping(evidence.get("oracle_publication_preflight"))
    state_receipt = _safe_mapping(evidence.get("oracle_publication_receipt"))

    state_preflight_present = state_preflight.get("present") is True
    shared_preflight_present = shared.get("preflight_present") is True
    if oracle_publication_preflight is None:
        if state_preflight_present or shared_preflight_present:
            raise ProgramActivationPacketError(
                "candidate_state references oracle_publication_preflight but activation packet omitted it"
            )
    else:
        if not state_preflight_present or not shared_preflight_present:
            raise ProgramActivationPacketError(
                "candidate_state must include supplied oracle_publication_preflight"
            )
        if state_preflight.get("publication_id") != oracle_publication_preflight.get(
            "publication_id"
        ):
            raise ProgramActivationPacketError(
                "candidate_state oracle_publication_preflight publication_id does not match supplied preflight"
            )
        if shared.get("preflight_ready") is not True:
            raise ProgramActivationPacketError(
                "candidate_state shared_oracle_publication.preflight_ready must be true"
            )

    state_receipt_present = state_receipt.get("present") is True
    shared_receipt_present = shared.get("evidence_ref_present") is True
    if oracle_publication_receipt is None:
        if state_receipt_present or shared_receipt_present:
            raise ProgramActivationPacketError(
                "candidate_state references oracle_publication_receipt but activation packet omitted it"
            )
    else:
        if not state_receipt_present or not shared_receipt_present:
            raise ProgramActivationPacketError(
                "candidate_state must include supplied oracle_publication_receipt"
            )
        if state_receipt.get("publication_id") != oracle_publication_receipt.get(
            "publication_id"
        ):
            raise ProgramActivationPacketError(
                "candidate_state oracle_publication_receipt publication_id does not match supplied receipt"
            )


def _validate_candidate_state(
    identity: Mapping[str, Any], candidate_state: Mapping[str, Any] | None
) -> None:
    if candidate_state is None:
        return
    state_identity = _safe_mapping(candidate_state.get("candidate_identity"))
    if not state_identity:
        raise ProgramActivationPacketError("candidate_state missing candidate_identity")
    mismatched = _identity_mismatch(identity, state_identity)
    if mismatched:
        raise ProgramActivationPacketError(
            "candidate_state identity does not match candidate identity: "
            + ", ".join(mismatched)
        )
    _validate_non_authority_false(
        candidate_state,
        label="candidate_state",
        keys=(
            "agent_kernel_mutation",
            "apply_promotion",
            "automatic_promotion",
            "external_apply",
            "governance_authority",
            "oracle_authority",
            "promotion_authority",
            "winner_selection",
        ),
    )
    target_fidelity = _safe_mapping(candidate_state.get("target_fidelity_state"))
    if target_fidelity:
        if target_fidelity.get("production_or_domain_activation_allowed") is not False:
            raise ProgramActivationPacketError(
                "candidate_state target_fidelity_state must record "
                "production_or_domain_activation_allowed false"
            )
        if target_fidelity.get("canonical_mutation_allowed") is not False:
            raise ProgramActivationPacketError(
                "candidate_state target_fidelity_state must record "
                "canonical_mutation_allowed false"
            )
        judgment = _safe_mapping(
            target_fidelity.get("target_protocol_fidelity_judgment")
        )
        if judgment.get("present") is not True:
            raise ProgramActivationPacketError(
                "candidate_state target_fidelity_state must include present "
                "target_protocol_fidelity_judgment"
            )
        if judgment.get("blocking") is not False:
            raise ProgramActivationPacketError(
                "candidate_state target_protocol_fidelity_judgment must record "
                "blocking false"
            )
        if judgment.get("judgment") != "supports_domain_review":
            raise ProgramActivationPacketError(
                "candidate_state target_protocol_fidelity_judgment must be "
                "supports_domain_review"
            )


def _validate_obsidian_review_adapter_receipt(
    receipt: Mapping[str, Any] | None,
    *,
    candidate_state_ref: Mapping[str, Any] | None,
) -> None:
    if receipt is None:
        return
    if receipt.get("status") != "materialized":
        raise ProgramActivationPacketError(
            "obsidian_review_adapter_receipt status must be materialized"
        )
    for key in (
        "canonical_mutation_performed",
        "wiki_mutation_performed",
        "atlas_mutation_performed",
        "zotero_mutation_performed",
        "source_package_mutation_performed",
        "puzzle_register_mutation_performed",
        "external_mutation_performed",
    ):
        if receipt.get(key) is not False:
            raise ProgramActivationPacketError(
                f"obsidian_review_adapter_receipt must record {key} false"
            )
    if receipt.get("obsidian_review_adapter_materialization_allowed") is not True:
        raise ProgramActivationPacketError(
            "obsidian_review_adapter_receipt must record "
            "obsidian_review_adapter_materialization_allowed true"
        )
    if candidate_state_ref is not None:
        expected = _strip_sha256_prefix(candidate_state_ref.get("sha256"))
        actual = _strip_sha256_prefix(receipt.get("program_candidate_state_hash"))
        if expected and not actual:
            raise ProgramActivationPacketError(
                "obsidian_review_adapter_receipt program_candidate_state_hash is required"
            )
        if expected and actual != expected:
            raise ProgramActivationPacketError(
                "obsidian_review_adapter_receipt program_candidate_state_hash "
                "does not match candidate_state"
            )


def _target_review_admission(
    *,
    candidate_state: Mapping[str, Any] | None,
    candidate_state_ref: dict[str, Any] | None,
    obsidian_receipt: Mapping[str, Any] | None,
    obsidian_receipt_ref: dict[str, Any] | None,
) -> dict[str, Any]:
    target_fidelity = _safe_mapping(
        (candidate_state or {}).get("target_fidelity_state")
    )
    target_judgment = _safe_mapping(
        target_fidelity.get("target_protocol_fidelity_judgment")
    )
    blockers: list[str] = []
    if candidate_state is None:
        blockers.append("target_aware_candidate_state_missing")
    elif target_fidelity:
        if (
            target_fidelity.get("obsidian_review_adapter_materialization_allowed")
            is not True
        ):
            blockers.append("obsidian_review_adapter_materialization_not_allowed")
        if target_fidelity.get("production_or_domain_activation_allowed") is not False:
            blockers.append("candidate_state_does_not_deny_domain_activation")
        if target_fidelity.get("canonical_mutation_allowed") is not False:
            blockers.append("candidate_state_does_not_deny_canonical_mutation")
        if target_judgment.get("present") is not True:
            blockers.append("target_protocol_fidelity_judgment_missing")
        if target_judgment.get("blocking") is not False:
            blockers.append("target_protocol_fidelity_judgment_blocking")
        if target_judgment.get("judgment") != "supports_domain_review":
            blockers.append("target_protocol_fidelity_judgment_not_supported")
    else:
        blockers.append("target_fidelity_state_missing")
    if obsidian_receipt is None:
        blockers.append("obsidian_review_adapter_receipt_missing")

    return {
        "candidate_state": candidate_state_ref,
        "obsidian_review_adapter_receipt": obsidian_receipt_ref,
        "target_protocol_fidelity_judgment": target_judgment.get("judgment"),
        "review_adapter_materialization_allowed": target_fidelity.get(
            "obsidian_review_adapter_materialization_allowed"
        )
        is True,
        "review_packet_materialized": obsidian_receipt is not None,
        "review_only": True,
        "production_activation_authority": False,
        "canonical_mutation_authority": False,
        "canonical_mutation_allowed": target_fidelity.get("canonical_mutation_allowed")
        is True,
        "status": "review_admitted" if not blockers else "blocked",
        "blockers": blockers,
    }


def _remaining_activation_blockers(
    *,
    behavior_refs: list[dict[str, Any]],
    oracle_report: Mapping[str, Any] | None,
    jury_results: Mapping[str, Any] | None,
    model_jury_results: Mapping[str, Any] | None,
    refined_review: Mapping[str, Any] | None,
    decision_record: Mapping[str, Any] | None,
    canonical_binding_ref: str | None,
    canonical_binding_verification: Mapping[str, Any] | None,
    rollout_owner: str | None,
    rollback_plan: str | None,
    require_obsidian_review_adapter: bool,
    target_review_admission: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not behavior_refs:
        blockers.append("behavior_evidence")
    if oracle_report is None:
        blockers.append("oracle_report")
    if jury_results is None and model_jury_results is None:
        blockers.append("jury_evidence")
    if refined_review is None:
        blockers.append("refined_promotion_review")
    if require_obsidian_review_adapter:
        blockers.extend(
            str(item) for item in _safe_list(target_review_admission.get("blockers"))
        )
    if decision_record is None:
        blockers.append("domain_decision_record")
    elif _decision_outcome(decision_record) != "promote":
        blockers.append("decision_outcome_not_promote")
    if not str(canonical_binding_ref or "").strip():
        blockers.append("canonical_binding_ref")
    elif not _canonical_binding_verified(canonical_binding_verification):
        blockers.append("canonical_binding_verification")
    if not str(rollout_owner or "").strip():
        blockers.append("rollout_owner")
    if not str(rollback_plan or "").strip():
        blockers.append("rollback_plan")
    return list(dict.fromkeys(blockers))


def _status_and_missing(
    *,
    behavior_refs: list[dict[str, Any]],
    oracle_report: Mapping[str, Any] | None,
    jury_results: Mapping[str, Any] | None,
    model_jury_results: Mapping[str, Any] | None,
    refined_review: Mapping[str, Any] | None,
    decision_record: Mapping[str, Any] | None,
    canonical_binding_ref: str | None,
    canonical_binding_verification: Mapping[str, Any] | None,
    rollout_owner: str | None,
    rollback_plan: str | None,
    require_obsidian_review_adapter: bool,
    target_review_admission: Mapping[str, Any],
) -> tuple[str, list[str], str]:
    missing: list[str] = []
    if not behavior_refs:
        missing.append("behavior_evidence")
    if oracle_report is None:
        missing.append("oracle_report")
    if jury_results is None and model_jury_results is None:
        missing.append("jury_evidence")
    if refined_review is None:
        missing.append("refined_promotion_review")
    if require_obsidian_review_adapter:
        missing.extend(
            str(item) for item in _safe_list(target_review_admission.get("blockers"))
        )
    if not str(rollout_owner or "").strip():
        missing.append("rollout_owner")
    if not str(rollback_plan or "").strip():
        missing.append("rollback_plan")
    if missing:
        return "blocked", missing, "collect_missing_evidence"

    outcome = _decision_outcome(decision_record)
    if decision_record is None:
        return "ready_for_domain_adjudication", [], "record_domain_decision"
    if outcome != "promote":
        return "blocked", ["decision_outcome_not_promote"], "resolve_decision_outcome"
    if not str(canonical_binding_ref or "").strip():
        return (
            "ready_for_canonical_binding",
            [],
            "bind_decision_into_ak_or_current_authority",
        )
    if not _canonical_binding_verified(canonical_binding_verification):
        return (
            "ready_for_canonical_binding_verification",
            [],
            "verify_canonical_binding_ref_before_rollout_preflight",
        )
    return "ready_for_rollout_preflight", [], "run_owner_approved_rollout_preflight"


def build_generated_program_activation_packet(
    *,
    manifest_path: Path,
    owning_domain: str,
    activation_target: str,
    authority_owner: str,
    oracle_report_path: Path | None = None,
    jury_results_path: Path | None = None,
    model_jury_results_path: Path | None = None,
    review_path: Path | None = None,
    decision_record_path: Path | None = None,
    promotion_plan_path: Path | None = None,
    oracle_publication_preflight_path: Path | None = None,
    oracle_publication_receipt_path: Path | None = None,
    candidate_state_path: Path | None = None,
    external_authority_export_preflight_path: Path | None = None,
    obsidian_review_adapter_receipt_path: Path | None = None,
    canonical_binding_verification_path: Path | None = None,
    require_obsidian_review_adapter: bool = False,
    canonical_binding_ref: str | None = None,
    rollout_owner: str | None = None,
    rollback_plan: str | None = None,
) -> dict[str, Any]:
    """Build a non-authoritative activation evidence packet for domain review."""

    normalized_owning_domain = str(owning_domain or "").strip()
    normalized_activation_target = str(activation_target or "").strip()
    normalized_authority_owner = str(authority_owner or "").strip()
    if not normalized_owning_domain:
        raise ProgramActivationPacketError("activation packet requires owning_domain")
    if not normalized_activation_target:
        raise ProgramActivationPacketError(
            "activation packet requires activation_target"
        )
    if not normalized_authority_owner:
        raise ProgramActivationPacketError("activation packet requires authority_owner")

    manifest_path = manifest_path.expanduser().resolve()
    manifest = _load_json_object(manifest_path, label="program manifest")
    if manifest.get("schema_version") != "program-candidate-assembly-v1":
        raise ProgramActivationPacketError(
            "program manifest schema_version must be program-candidate-assembly-v1"
        )
    manifest_ref = _artifact_ref(
        manifest_path, schema_version="program-candidate-assembly-v1"
    )
    assert manifest_ref is not None
    root = manifest_path.parent
    identity = _identity_from_manifest(manifest)

    oracle_report, oracle_ref = _load_optional_artifact(
        oracle_report_path,
        label="oracle_report",
    )
    jury_results, jury_ref = _load_optional_artifact(
        jury_results_path,
        label="jury_results",
    )
    model_jury_results, model_jury_ref = _load_optional_artifact(
        model_jury_results_path,
        label="model_jury_results",
    )
    refined_review, review_ref = _load_optional_artifact(
        review_path,
        label="refined_review",
    )
    decision_record, decision_ref = _load_optional_artifact(
        decision_record_path,
        label="decision_record",
    )
    promotion_plan, promotion_plan_ref = _load_optional_artifact(
        promotion_plan_path,
        label="promotion_plan",
    )
    oracle_publication_preflight, oracle_publication_preflight_ref = (
        _load_optional_artifact(
            oracle_publication_preflight_path,
            label="oracle_publication_preflight",
        )
    )
    oracle_publication_receipt, oracle_publication_receipt_ref = (
        _load_optional_artifact(
            oracle_publication_receipt_path,
            label="oracle_publication_receipt",
        )
    )
    candidate_state, candidate_state_ref = _load_optional_artifact(
        candidate_state_path,
        label="candidate_state",
    )
    external_authority_export_preflight, external_authority_export_preflight_ref = (
        _load_optional_artifact(
            external_authority_export_preflight_path,
            label="external_authority_export_preflight",
        )
    )
    obsidian_review_adapter_receipt, obsidian_review_adapter_receipt_ref = (
        _load_optional_artifact(
            obsidian_review_adapter_receipt_path,
            label="obsidian_review_adapter_receipt",
        )
    )
    canonical_binding_verification, canonical_binding_verification_ref = (
        _load_optional_artifact(
            canonical_binding_verification_path,
            label="canonical_binding_verification",
        )
    )

    _validate_artifact_identity(identity, jury_results, label="jury_results")
    _validate_artifact_identity(
        identity, model_jury_results, label="model_jury_results"
    )
    _validate_artifact_identity(identity, refined_review, label="refined_review")
    _validate_artifact_identity(identity, decision_record, label="decision_record")
    _validate_artifact_identity(identity, promotion_plan, label="promotion_plan")
    _validate_activation_evidence_boundaries(
        manifest_path=manifest_path,
        manifest_hash=str(manifest_ref["sha256"]),
        jury_results=jury_results,
        model_jury_results=model_jury_results,
        refined_review=refined_review,
        decision_record=decision_record,
        promotion_plan=promotion_plan,
    )
    _validate_decision_authority_owner(
        decision_record,
        authority_owner=normalized_authority_owner,
    )
    _validate_oracle_report_identity(identity, oracle_report)
    _validate_oracle_publication_preflight(identity, oracle_publication_preflight)
    _validate_oracle_publication_receipt(
        identity,
        oracle_publication_receipt,
        preflight=oracle_publication_preflight,
        preflight_ref=oracle_publication_preflight_ref,
    )
    _validate_candidate_state(identity, candidate_state)
    _validate_external_authority_export_preflight(
        identity,
        external_authority_export_preflight,
        manifest_path=manifest_path,
        decision_record_path=decision_record_path,
    )
    _validate_candidate_state_publication_alignment(
        candidate_state=candidate_state,
        oracle_publication_preflight=oracle_publication_preflight,
        oracle_publication_receipt=oracle_publication_receipt,
    )
    decision_ref_for_binding = (
        _decision_record_ref(decision_record_path)
        if decision_record_path is not None
        else None
    )
    _validate_canonical_binding_verification(
        verification=canonical_binding_verification,
        canonical_binding_ref=canonical_binding_ref,
        decision_record_ref=decision_ref_for_binding,
    )
    _validate_obsidian_review_adapter_receipt(
        obsidian_review_adapter_receipt,
        candidate_state_ref=candidate_state_ref,
    )

    behavior_refs = _behavior_refs(root, manifest)
    receipt = _receipt_ref(manifest_path)
    target_review_admission = _target_review_admission(
        candidate_state=candidate_state,
        candidate_state_ref=candidate_state_ref,
        obsidian_receipt=obsidian_review_adapter_receipt,
        obsidian_receipt_ref=obsidian_review_adapter_receipt_ref,
    )
    status, missing, next_action = _status_and_missing(
        behavior_refs=behavior_refs,
        oracle_report=oracle_report,
        jury_results=jury_results,
        model_jury_results=model_jury_results,
        refined_review=refined_review,
        decision_record=decision_record,
        canonical_binding_ref=canonical_binding_ref,
        canonical_binding_verification=canonical_binding_verification,
        rollout_owner=rollout_owner,
        rollback_plan=rollback_plan,
        require_obsidian_review_adapter=require_obsidian_review_adapter,
        target_review_admission=target_review_admission,
    )
    remaining_activation_blockers = _remaining_activation_blockers(
        behavior_refs=behavior_refs,
        oracle_report=oracle_report,
        jury_results=jury_results,
        model_jury_results=model_jury_results,
        refined_review=refined_review,
        decision_record=decision_record,
        canonical_binding_ref=canonical_binding_ref,
        canonical_binding_verification=canonical_binding_verification,
        rollout_owner=rollout_owner,
        rollback_plan=rollback_plan,
        require_obsidian_review_adapter=require_obsidian_review_adapter,
        target_review_admission=target_review_admission,
    )

    return {
        "schema_version": ACTIVATION_PACKET_SCHEMA,
        "transition_type": TRANSITION_TYPE,
        "status": status,
        "status_kind": "advisory_evidence_packet_status_not_authority_state",
        "next_required_action": next_action,
        "governance_boundary_ref": GOVERNANCE_BOUNDARY_REF,
        "transition_passport_ref": TRANSITION_PASSPORT_REF,
        "owning_domain": normalized_owning_domain,
        "activation_target": normalized_activation_target,
        "authority_owner": normalized_authority_owner,
        "rollout_owner": str(rollout_owner or "").strip() or None,
        "rollback_plan": str(rollback_plan or "").strip() or None,
        "canonical_binding_ref": str(canonical_binding_ref or "").strip() or None,
        "identity": identity,
        "candidate": {
            "manifest": manifest_ref,
            "receipt": receipt,
            "surface_count": len(_manifest_surfaces(manifest)),
            "surfaces": _manifest_surfaces(manifest),
        },
        "evidence": {
            "behavior": behavior_refs,
            "oracle_report": oracle_ref,
            "jury_results": jury_ref,
            "model_jury_results": model_jury_ref,
            "refined_review": review_ref,
            "decision_record": decision_ref,
            "promotion_plan": promotion_plan_ref,
            "oracle_publication_preflight": _oracle_publication_preflight_ref(
                oracle_publication_preflight_ref,
                oracle_publication_preflight,
            ),
            "oracle_publication_receipt": _oracle_publication_ref(
                oracle_publication_receipt_ref,
                oracle_publication_receipt,
            ),
            "candidate_state": candidate_state_ref,
            "external_authority_export_preflight": _external_authority_export_preflight_ref(
                external_authority_export_preflight_ref,
                external_authority_export_preflight,
            ),
            "obsidian_review_adapter_receipt": obsidian_review_adapter_receipt_ref,
            "canonical_binding_verification": canonical_binding_verification_ref,
        },
        "evidence_alignment": {
            "oracle_publication": _oracle_publication_alignment_summary(
                candidate_state=candidate_state,
                oracle_publication_preflight=oracle_publication_preflight,
                oracle_publication_receipt=oracle_publication_receipt,
            )
        },
        "target_review_admission": target_review_admission,
        "decision": {
            "outcome": _decision_outcome(decision_record),
            "promotion_state_after_decision": (decision_record or {}).get(
                "promotion_state_after_decision"
            )
            if decision_record is not None
            else None,
            "decided_by": (decision_record or {}).get("decided_by")
            if decision_record is not None
            else None,
        },
        "missing_required_evidence": missing,
        "remaining_activation_blockers": remaining_activation_blockers,
        "boundary_checks": {
            "mlflow_approval_authority": False,
            "oracle_promotion_authority": False,
            "oracle_publication_activation_authority": False,
            "jury_promotion_authority": False,
            "dspx_activation_authority": False,
            "requires_domain_governing_body": True,
            "requires_rollout_owner_before_rollout": True,
            "requires_rollback_plan_before_rollout": True,
            "requires_canonical_binding_before_rollout": True,
            "requires_obsidian_review_adapter_when_requested": require_obsidian_review_adapter,
        },
        "effect": dict(_EFFECT),
        "non_authority": dict(_NON_AUTHORITY),
        "notes": [
            "This packet is generated-program activation evidence only.",
            "It does not activate, deploy, promote, mutate AK, mutate governance, mutate MLflow, or mutate Oracle indexes.",
            "The owning domain or delegated governing body remains the judging authority for concrete activation.",
        ],
    }


def write_generated_program_activation_packet(
    packet: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Write an activation evidence packet without mutating source artifacts."""

    payload = dict(packet)
    try:
        out_path = prepare_sidecar_output_path(
            out_path,
            payload=payload,
            artifact_label="activation packet",
            protected_names=_ACTIVATION_PACKET_PROTECTED_OUTPUT_NAMES,
            payload_artifact_root_policy="forbid",
        )
    except ValueError as exc:
        raise ProgramActivationPacketError(str(exc)) from exc
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
