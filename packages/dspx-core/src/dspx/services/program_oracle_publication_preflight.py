# summary: "Builds fail-closed local preflight packets for explicit shared publication of program Oracle evidence."
# read_when:
#   - "Changing Oracle publication eligibility, identity/hash binding, labels, redaction, retention, or publisher custody fields."
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import prepare_sidecar_output_path

from dspx.services.program_oracle_index import (
    PROGRAM_ORACLE_EVIDENCE_SCHEMA,
    validate_program_oracle_evidence_non_authority,
)
from dspx.services.program_oracle_secret_policy import (
    ProgramOracleSecretPolicyError,
    build_onepassword_ref_descriptors,
    validate_publisher_assertion_no_secret,
)
from dspx.services.program_runtime_traces import (
    PROGRAM_RUNTIME_TRACES_SCHEMA,
    validate_program_runtime_traces,
)

PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA = (
    "program-oracle-shared-publication-preflight-v1"
)
PROGRAM_MANIFEST_SCHEMA = "program-candidate-assembly-v1"

EMPIRICAL_LABELS = {
    "local_observed",
    "retained",
    "request_more_evidence",
    "rejected",
}
AUTHORITY_MIRROR_LABELS = {
    "accepted_for_review",
    "promote_decision_recorded",
    "activated",
    "rolled_back",
}
PUBLICATION_LABELS = EMPIRICAL_LABELS | AUTHORITY_MIRROR_LABELS

ELIGIBLE_REDACTION_STATUSES = {"checked", "not_required", "redacted"}
INELIGIBLE_REDACTION_STATUSES = {"unknown", "contains_sensitive_material"}
REDACTION_STATUSES = ELIGIBLE_REDACTION_STATUSES | INELIGIBLE_REDACTION_STATUSES

ELIGIBLE_RETENTION_CLASSES = {
    "ephemeral_review",
    "retained_behavior_memory",
    "activation_evidence_reference",
}
RETENTION_CLASSES = ELIGIBLE_RETENTION_CLASSES | {"do_not_publish"}

TARGETS = {"shared-postgres", "shared_postgres", "postgres_pgvector"}


class ProgramOraclePublicationPreflightError(ValueError):
    """Raised when program Oracle shared publication preflight fails closed."""


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramOraclePublicationPreflightError(
            f"{label} not found: {source}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProgramOraclePublicationPreflightError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramOraclePublicationPreflightError(
            f"{label} must contain a JSON object: {source}"
        )
    return payload


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _required_text(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProgramOraclePublicationPreflightError(f"{field} is required")
    return text


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _runtime_trace_publication_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    coverage = _safe_mapping(summary.get("coverage"))
    return {
        "path": summary.get("path"),
        "content_hash": summary.get("content_hash"),
        "status": summary.get("status"),
        "source_count": summary.get("source_count"),
        "module_call_count": summary.get("module_call_count"),
        "final_output_trace_count": summary.get("final_output_trace_count"),
        "coverage_status": coverage.get("status"),
        "source_record_coverage_status": coverage.get("source_record_coverage_status"),
        "non_authority": _safe_mapping(summary.get("non_authority")),
    }


def _source_artifact_hash(
    source_artifacts: object, *, kind: str, path: str
) -> str | None:
    if not isinstance(source_artifacts, list):
        return None
    for artifact in source_artifacts:
        if not isinstance(artifact, Mapping):
            continue
        item = _safe_mapping(artifact)
        if item.get("kind") == kind and item.get("path") == path:
            value = item.get("content_hash")
            return value if isinstance(value, str) and value else None
    return None


def _resolve_candidate_relative_path(
    candidate_root: Path, relative_path: str, *, label: str
) -> Path:
    if Path(relative_path).is_absolute():
        raise ProgramOraclePublicationPreflightError(
            f"{label} must be relative to the candidate root"
        )
    root = candidate_root.resolve()
    resolved = (root / relative_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProgramOraclePublicationPreflightError(
            f"{label} must stay within the candidate root"
        ) from exc
    return resolved


def _runtime_trace_expected_publication_summary(
    *,
    summary_path: str,
    expected_hash: str,
    runtime_traces: Mapping[str, Any],
) -> dict[str, Any]:
    coverage = _safe_mapping(runtime_traces.get("coverage"))
    return {
        "path": summary_path,
        "content_hash": expected_hash,
        "status": runtime_traces.get("status"),
        "source_count": runtime_traces.get("source_count"),
        "module_call_count": runtime_traces.get("module_call_count"),
        "final_output_trace_count": runtime_traces.get("final_output_trace_count"),
        "coverage_status": coverage.get("status"),
        "source_record_coverage_status": coverage.get("source_record_coverage_status"),
        "non_authority": _safe_mapping(runtime_traces.get("non_authority")),
    }


def _validate_runtime_trace_summary(
    oracle_evidence: Mapping[str, Any], candidate_root: Path
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    raw_summary = oracle_evidence.get("runtime_traces")
    if not isinstance(raw_summary, Mapping):
        raise ProgramOraclePublicationPreflightError(
            "program Oracle evidence must include runtime_traces summary for shared publication"
        )
    summary = dict(raw_summary)
    if "module_calls" in summary or "final_outputs" in summary:
        raise ProgramOraclePublicationPreflightError(
            "program Oracle evidence runtime_traces summary must not include raw trace records"
        )
    relative_path = str(summary.get("path") or "").strip()
    expected_hash = str(summary.get("content_hash") or "").strip()
    if not relative_path or not expected_hash:
        raise ProgramOraclePublicationPreflightError(
            "program Oracle evidence runtime_traces summary requires path and content_hash"
        )
    source_hash = _source_artifact_hash(
        oracle_evidence.get("source_artifacts"),
        kind="runtime_traces",
        path=relative_path,
    )
    if source_hash != expected_hash:
        raise ProgramOraclePublicationPreflightError(
            "program Oracle evidence runtime_traces source_artifacts hash does not match summary"
        )
    runtime_traces_path = _resolve_candidate_relative_path(
        candidate_root,
        relative_path,
        label="program Oracle evidence runtime_traces path",
    )
    runtime_traces = _load_json_object(
        runtime_traces_path, label="program runtime traces"
    )
    if runtime_traces.get("schema_version") != PROGRAM_RUNTIME_TRACES_SCHEMA:
        raise ProgramOraclePublicationPreflightError(
            "program runtime traces schema_version must be "
            + PROGRAM_RUNTIME_TRACES_SCHEMA
        )
    actual_hash = _sha256_file(runtime_traces_path)
    if actual_hash != expected_hash:
        raise ProgramOraclePublicationPreflightError(
            "program runtime traces hash does not match Oracle evidence summary"
        )
    if not validate_program_runtime_traces(runtime_traces):
        raise ProgramOraclePublicationPreflightError(
            "program runtime traces failed replay-semantic validation"
        )
    publication_summary = _runtime_trace_publication_summary(summary)
    expected_summary = _runtime_trace_expected_publication_summary(
        summary_path=relative_path,
        expected_hash=expected_hash,
        runtime_traces=runtime_traces,
    )
    mismatched = [
        key
        for key, expected in expected_summary.items()
        if publication_summary.get(key) != expected
    ]
    if mismatched:
        raise ProgramOraclePublicationPreflightError(
            "program Oracle evidence runtime_traces summary does not match artifact: "
            + ", ".join(sorted(mismatched))
        )
    return runtime_traces_path, runtime_traces, publication_summary


def _manifest_identity(manifest: Mapping[str, Any]) -> dict[str, str | None]:
    request = _safe_mapping(manifest.get("request"))
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    execution = _safe_mapping(manifest.get("execution_episode"))
    receipt = _safe_mapping(manifest.get("receipt_bundle"))
    return {
        "request_id": _first_text(
            request.get("request_id"),
            candidate.get("request_id"),
            execution.get("request_id"),
            receipt.get("request_id"),
        ),
        "candidate_id": _first_text(
            candidate.get("candidate_id"),
            execution.get("candidate_id"),
            receipt.get("candidate_id"),
        ),
        "assembly_id": _first_text(
            candidate.get("assembly_id"),
            execution.get("assembly_id"),
            receipt.get("assembly_id"),
        ),
        "episode_id": _first_text(
            execution.get("episode_id"),
            receipt.get("episode_id"),
        ),
        "receipt_bundle_id": _first_text(receipt.get("receipt_bundle_id")),
    }


def _validate_manifest(manifest: Mapping[str, Any], path: Path) -> None:
    if manifest.get("schema_version") != PROGRAM_MANIFEST_SCHEMA:
        raise ProgramOraclePublicationPreflightError(
            f"program manifest schema_version must be {PROGRAM_MANIFEST_SCHEMA}: {path}"
        )
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    if candidate.get("artifact_kind") != "program":
        raise ProgramOraclePublicationPreflightError(
            f"program manifest artifact_kind must be program: {path}"
        )
    if not any(_manifest_identity(manifest).values()):
        raise ProgramOraclePublicationPreflightError(
            "program manifest does not expose request/candidate/assembly/episode/receipt identity"
        )


def _artifact_path(
    manifest: Mapping[str, Any], manifest_path: Path, *keys: str
) -> Path:
    root = manifest_path.parent
    for key in keys:
        value = _safe_mapping(manifest.get(key)).get("path")
        if value:
            candidate = Path(str(value))
            return candidate if candidate.is_absolute() else root / candidate
    execution = _safe_mapping(manifest.get("execution_episode"))
    value = _safe_mapping(execution.get("oracle_evidence")).get("path")
    if value:
        candidate = Path(str(value))
        return candidate if candidate.is_absolute() else root / candidate
    return root / "oracle_evidence.json"


def _assert_identity_compatible(
    *,
    evidence_identity: Mapping[str, Any],
    manifest_identity: Mapping[str, str | None],
) -> None:
    mismatches = [
        key
        for key, expected in manifest_identity.items()
        if expected
        and evidence_identity.get(key)
        and evidence_identity.get(key) != expected
    ]
    if mismatches:
        raise ProgramOraclePublicationPreflightError(
            "program Oracle evidence identity does not match manifest identity: "
            + ", ".join(sorted(mismatches))
        )
    missing = [
        key
        for key, expected in manifest_identity.items()
        if expected and not evidence_identity.get(key)
    ]
    if missing:
        raise ProgramOraclePublicationPreflightError(
            "program Oracle evidence identity is missing manifest identity fields: "
            + ", ".join(sorted(missing))
        )


def _label_class(label: str) -> str:
    if label in EMPIRICAL_LABELS:
        return "empirical"
    if label in AUTHORITY_MIRROR_LABELS:
        return "authority_mirror"
    raise ProgramOraclePublicationPreflightError(
        "unknown publication_label: "
        + label
        + "; expected one of "
        + ", ".join(sorted(PUBLICATION_LABELS))
    )


def _validate_redaction_status(value: str) -> None:
    if value not in REDACTION_STATUSES:
        raise ProgramOraclePublicationPreflightError(
            "unknown redaction_status: "
            + value
            + "; expected one of "
            + ", ".join(sorted(REDACTION_STATUSES))
        )
    if value in INELIGIBLE_REDACTION_STATUSES:
        raise ProgramOraclePublicationPreflightError(
            "redaction_status is not eligible for shared publication: " + value
        )


def _validate_retention_class(value: str) -> None:
    if value not in RETENTION_CLASSES:
        raise ProgramOraclePublicationPreflightError(
            "unknown retention_class: "
            + value
            + "; expected one of "
            + ", ".join(sorted(RETENTION_CLASSES))
        )
    if value == "do_not_publish":
        raise ProgramOraclePublicationPreflightError(
            "retention_class do_not_publish is not eligible for shared publication"
        )


def _redacted_backend_posture(target: str) -> dict[str, Any]:
    store = str(os.getenv("DSPX_ORACLE_STORE") or "").strip()
    configured_url_keys = [
        key
        for key in ("DSPX_ORACLE_DATABASE_URL", "DSPX_ORACLE_POSTGRES_URL")
        if str(os.getenv(key) or "").strip()
    ]
    database_url_present = bool(configured_url_keys)
    schema = str(os.getenv("DSPX_ORACLE_SCHEMA") or "").strip() or None
    return {
        "target": target,
        "target_supported_by_preflight": target in TARGETS,
        "configured_store": store or None,
        "configured_database_url_keys": configured_url_keys,
        "database_url_present": database_url_present,
        "database_url_redacted": "<redacted>" if database_url_present else None,
        "schema": schema,
        "connection_attempted": False,
        "shared_write_attempted": False,
    }


def _idempotency_key(
    *,
    target: str,
    identity: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
    publication_label: str,
    authority_ref: str | None,
    publisher_id: str,
    publisher_role: str,
    publisher_assertion: str,
    redaction_status: str,
    retention_class: str,
    publisher_secret_refs: list[dict[str, Any]] | None = None,
) -> str:
    seed = {
        "schema_version": PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA,
        "target": target,
        "identity": {key: value for key, value in sorted(identity.items()) if value},
        "artifact_hashes": dict(sorted(artifact_hashes.items())),
        "publication_label": publication_label,
        "authority_ref": authority_ref,
        "publisher_id": publisher_id,
        "publisher_role": publisher_role,
        "publisher_assertion": publisher_assertion,
        "redaction_status": redaction_status,
        "retention_class": retention_class,
        "publisher_secret_refs": publisher_secret_refs or [],
    }
    return "prog-oracle-pub-" + _sha256_payload(seed)[:20]


def build_program_oracle_publication_preflight(
    *,
    manifest_path: Path,
    target: str,
    publication_label: str,
    publisher_id: str,
    publisher_role: str,
    publisher_assertion: str,
    redaction_status: str,
    retention_class: str,
    authority_ref: str | None = None,
    publisher_secret_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Build a local shared-Oracle publication preflight packet without shared writes."""

    manifest_file = manifest_path.expanduser().resolve()
    normalized_target = _required_text(target, field="target")
    if normalized_target not in TARGETS:
        raise ProgramOraclePublicationPreflightError(
            "unknown target: "
            + normalized_target
            + "; expected one of "
            + ", ".join(sorted(TARGETS))
        )
    normalized_label = _required_text(publication_label, field="publication_label")
    label_class = _label_class(normalized_label)
    normalized_authority_ref = str(authority_ref or "").strip() or None
    if label_class == "authority_mirror" and normalized_authority_ref is None:
        raise ProgramOraclePublicationPreflightError(
            "authority_ref is required for authority-mirror publication labels"
        )
    normalized_publisher_id = _required_text(publisher_id, field="publisher_id")
    normalized_publisher_role = _required_text(publisher_role, field="publisher_role")
    normalized_publisher_assertion = _required_text(
        publisher_assertion, field="publisher_assertion"
    )
    try:
        validate_publisher_assertion_no_secret(normalized_publisher_assertion)
        normalized_secret_refs = build_onepassword_ref_descriptors(
            publisher_secret_refs
        )
    except ProgramOracleSecretPolicyError as exc:
        raise ProgramOraclePublicationPreflightError(str(exc)) from exc
    normalized_redaction_status = _required_text(
        redaction_status, field="redaction_status"
    )
    _validate_redaction_status(normalized_redaction_status)
    normalized_retention_class = _required_text(
        retention_class, field="retention_class"
    )
    _validate_retention_class(normalized_retention_class)

    manifest = _load_json_object(manifest_file, label="program manifest")
    _validate_manifest(manifest, manifest_file)
    identity = _manifest_identity(manifest)
    manifest_hash = _sha256_file(manifest_file)

    oracle_evidence_file = (
        _artifact_path(
            manifest,
            manifest_file,
            "oracle_evidence",
            "oracle_readability",
        )
        .expanduser()
        .resolve()
    )
    oracle_evidence = _load_json_object(
        oracle_evidence_file, label="program Oracle evidence"
    )
    if oracle_evidence.get("schema_version") != PROGRAM_ORACLE_EVIDENCE_SCHEMA:
        raise ProgramOraclePublicationPreflightError(
            "program Oracle evidence schema_version must be "
            + PROGRAM_ORACLE_EVIDENCE_SCHEMA
        )
    try:
        validate_program_oracle_evidence_non_authority(oracle_evidence)
    except ValueError as exc:
        raise ProgramOraclePublicationPreflightError(str(exc)) from exc
    _assert_identity_compatible(
        evidence_identity=_safe_mapping(oracle_evidence.get("identity")),
        manifest_identity=identity,
    )
    oracle_evidence_hash = _sha256_file(oracle_evidence_file)
    (
        runtime_traces_file,
        runtime_traces_payload,
        runtime_trace_summary,
    ) = _validate_runtime_trace_summary(oracle_evidence, manifest_file.parent)
    runtime_traces_hash = _sha256_file(runtime_traces_file)
    artifact_hashes = {
        "manifest_sha256": manifest_hash,
        "oracle_evidence_sha256": oracle_evidence_hash,
        "runtime_traces_sha256": runtime_traces_hash,
    }
    publication_id = _idempotency_key(
        target=normalized_target,
        identity=identity,
        artifact_hashes=artifact_hashes,
        publication_label=normalized_label,
        authority_ref=normalized_authority_ref,
        publisher_id=normalized_publisher_id,
        publisher_role=normalized_publisher_role,
        publisher_assertion=normalized_publisher_assertion,
        redaction_status=normalized_redaction_status,
        retention_class=normalized_retention_class,
        publisher_secret_refs=normalized_secret_refs,
    )

    return {
        "schema_version": PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA,
        "status": "ready_not_published",
        "publication_id": publication_id,
        "target": _redacted_backend_posture(normalized_target),
        "created_from": {
            "manifest_path": str(manifest_file),
            "manifest_schema_version": manifest.get("schema_version"),
            "oracle_evidence_path": str(oracle_evidence_file),
            "oracle_evidence_schema_version": oracle_evidence.get("schema_version"),
            "runtime_traces_path": str(runtime_traces_file),
            "runtime_traces_schema_version": runtime_traces_payload.get(
                "schema_version"
            ),
        },
        "identity": identity,
        "artifact_hashes": artifact_hashes,
        "publication": {
            "publication_label": normalized_label,
            "publication_label_class": label_class,
            "authority_ref": normalized_authority_ref,
            "authority_ref_required": label_class == "authority_mirror",
            "authority_ref_kind": "opaque_reference_only"
            if normalized_authority_ref
            else None,
            "publisher_id": normalized_publisher_id,
            "publisher_role": normalized_publisher_role,
            "publisher_assertion": normalized_publisher_assertion,
            "publisher_secret_refs": normalized_secret_refs,
            "publisher_secret_ref_policy": "1password_refs_only_values_never_persisted",
            "publisher_identity_kind": "declared_not_authenticated",
            "redaction_status": normalized_redaction_status,
            "redaction_status_kind": "declared_custody_assertion_not_dlp_proof",
            "retention_class": normalized_retention_class,
            "retraction_supported_by_future_record": True,
        },
        "preflight": {
            "manifest_valid": True,
            "oracle_evidence_present": True,
            "oracle_evidence_non_authority_valid": True,
            "identity_matches_manifest": True,
            "runtime_trace_summary_valid": True,
            "runtime_trace_hash_match": True,
            "runtime_trace_semantics_valid": True,
            "publication_label_valid": True,
            "authority_ref_requirement_satisfied": True,
            "publisher_fields_present": True,
            "redaction_status_eligible": True,
            "retention_class_eligible": True,
            "ready_for_shared_publication": True,
            "ready_for_shared_publication_reason": "preflight_passed_publish_requires_explicit_shared_backend",
            "blocking_reasons": [],
        },
        "idempotency": {
            "publication_id": publication_id,
            "safe_to_recompute": True,
            "same_inputs_same_publication_id": True,
            "shared_duplicate_check_performed": False,
            "shared_duplicate_check_reason": "No shared backend was contacted.",
        },
        "planned_record": {
            "schema_version": "program-oracle-shared-publication-v1",
            "source_schema_version": PROGRAM_ORACLE_EVIDENCE_SCHEMA,
            "candidate_id": identity.get("candidate_id"),
            "assembly_id": identity.get("assembly_id"),
            "receipt_bundle_id": identity.get("receipt_bundle_id"),
            "oracle_evidence_sha256": oracle_evidence_hash,
            "manifest_sha256": manifest_hash,
            "runtime_traces_sha256": runtime_traces_hash,
            "runtime_traces": runtime_trace_summary,
            "publication_label": normalized_label,
            "publication_label_class": label_class,
            "publisher_id": normalized_publisher_id,
            "publisher_role": normalized_publisher_role,
            "publisher_secret_refs": normalized_secret_refs,
            "publisher_secret_ref_policy": "1password_refs_only_values_never_persisted",
            "publisher_identity_kind": "declared_not_authenticated",
            "authority_ref": normalized_authority_ref,
            "authority_ref_kind": "opaque_reference_only"
            if normalized_authority_ref
            else None,
            "redaction_status": normalized_redaction_status,
            "retention_class": normalized_retention_class,
            "non_authority": {
                "oracle_ranking": False,
                "oracle_pruning": False,
                "oracle_promotion": False,
                "governance_authority": False,
                "external_mutation": False,
            },
        },
        "effect": {
            "local_preflight_written": False,
            "oracle_index_mutated": False,
            "shared_oracle_mutated": False,
            "ak_called": False,
            "governance_mutated": False,
            "mlflow_mutated": False,
            "program_files_mutated": False,
            "promotion_state_changed": False,
        },
        "non_authority": {
            "preflight_only": True,
            "planned_not_published": True,
            "oracle_authority": False,
            "promotion_authority": False,
            "governance_authority": False,
            "agent_kernel_mutation": False,
            "winner_selection": False,
            "automatic_promotion": False,
        },
        "notes": [
            "This packet is a local shared-Oracle publication preflight only.",
            "No shared Oracle backend was contacted or mutated.",
            "Publisher identity is declared custody context, not authenticated authority.",
            "The publish command must perform shared backend checks and emit a publication receipt.",
        ],
    }


def write_program_oracle_publication_preflight(
    packet: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    """Write a local shared-Oracle publication preflight packet."""

    payload = dict(packet)
    target = prepare_sidecar_output_path(
        out_path,
        payload=payload,
        artifact_label="program Oracle publication preflight",
        payload_artifact_root_policy="ignore",
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if payload.get("schema_version") != PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA:
        raise ProgramOraclePublicationPreflightError(
            "program Oracle publication preflight schema_version is invalid"
        )
    effect = _safe_mapping(payload.get("effect"))
    effect["local_preflight_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload
