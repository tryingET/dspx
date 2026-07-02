from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from dspx.coordinates import CoordinateStore
from dspx.services.artifact_boundary import prepare_sidecar_output_path
from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES
from dspx.services.program_oracle_index import (
    PROGRAM_ORACLE_EVIDENCE_SCHEMA,
    build_program_oracle_evidence_embedding,
    load_program_oracle_evidence,
)
from dspx.services.program_oracle_publication_preflight import (
    AUTHORITY_MIRROR_LABELS,
    ELIGIBLE_REDACTION_STATUSES,
    ELIGIBLE_RETENTION_CLASSES,
    EMPIRICAL_LABELS,
    PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA,
    TARGETS,
)
from dspx.services.program_oracle_secret_policy import (
    ProgramOracleSecretPolicyError,
    validate_publisher_assertion_no_secret,
)

PROGRAM_ORACLE_PUBLICATION_RECEIPT_SCHEMA = (
    "program-oracle-shared-publication-receipt-v1"
)
PROGRAM_ORACLE_PUBLICATION_RECORD_SCHEMA = "program-oracle-shared-publication-v1"
PROGRAM_ORACLE_PUBLICATION_RUN_KIND = "program-oracle-shared-publication"

_POSTGRES_STORE_NAMES = {
    "postgres_pgvector",
    "pgvector",
}

_PUBLICATION_RECEIPT_PROTECTED_OUTPUT_NAMES = PROTECTED_PROGRAM_ARTIFACT_NAMES | {
    "oracle_publication_preflight.json",
    "oracle_publication_receipt.json",
}

_REQUIRED_FALSE_PUBLICATION_NON_AUTHORITY_FLAGS = (
    "oracle_ranking",
    "oracle_pruning",
    "oracle_promotion",
    "governance_authority",
    "external_mutation",
)


class ProgramOraclePublicationError(ValueError):
    """Raised when explicit shared Oracle publication fails closed."""


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramOraclePublicationError(f"{label} not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramOraclePublicationError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramOraclePublicationError(
            f"{label} must contain a JSON object: {source}"
        )
    return payload


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


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


def _required_text(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProgramOraclePublicationError(f"{field} is required")
    return text


def _validate_publisher_secret_ref_descriptors(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ProgramOraclePublicationError(
            "publication.publisher_secret_refs must be a list"
        )
    allowed_keys = {
        "provider",
        "ref_kind",
        "ref_redacted",
        "ref_sha256",
        "sdk_resolution_attempted",
        "secret_value_persisted",
    }
    descriptors: list[dict[str, Any]] = []
    for index, ref in enumerate(value):
        if not isinstance(ref, Mapping):
            raise ProgramOraclePublicationError(
                f"publication.publisher_secret_refs[{index}] must be an object"
            )
        descriptor = {str(key): item for key, item in ref.items()}
        extra_keys = sorted(set(descriptor) - allowed_keys)
        if extra_keys:
            raise ProgramOraclePublicationError(
                "publication publisher_secret_refs must not contain resolved secret values or extra fields: "
                + ", ".join(extra_keys)
            )
        ref_sha256 = descriptor.get("ref_sha256")
        ref_redacted = descriptor.get("ref_redacted")
        if (
            descriptor.get("provider") != "1password"
            or descriptor.get("ref_kind") != "op_uri"
            or descriptor.get("sdk_resolution_attempted") is not False
            or descriptor.get("secret_value_persisted") is not False
            or not isinstance(ref_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", ref_sha256)
            or not isinstance(ref_redacted, str)
            or not ref_redacted.startswith("op://<redacted>/<redacted>/")
        ):
            raise ProgramOraclePublicationError(
                "publication publisher_secret_refs must be redacted 1Password refs"
            )
        descriptors.append(descriptor)
    return descriptors


def _ensure_preflight_passed(
    preflight: Mapping[str, Any], preflight_path: Path
) -> None:
    if preflight.get("schema_version") != PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA:
        raise ProgramOraclePublicationError(
            "preflight schema_version must be "
            + PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA
            + f": {preflight_path}"
        )
    if preflight.get("status") != "ready_not_published":
        raise ProgramOraclePublicationError(
            "preflight status must be ready_not_published before shared publication"
        )

    effect = _safe_mapping(preflight.get("effect"))
    if effect.get("shared_oracle_mutated") is not False:
        raise ProgramOraclePublicationError(
            "preflight must prove shared_oracle_mutated is false"
        )
    if (
        effect.get("ak_called") is not False
        or effect.get("governance_mutated") is not False
    ):
        raise ProgramOraclePublicationError(
            "preflight must prove AK/governance were not mutated"
        )

    checks = _safe_mapping(preflight.get("preflight"))
    required_true = (
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
    failed = [key for key in required_true if checks.get(key) is not True]
    if failed:
        raise ProgramOraclePublicationError(
            "preflight checks are not publishable: " + ", ".join(failed)
        )
    blocking = checks.get("blocking_reasons")
    if blocking != []:
        raise ProgramOraclePublicationError(
            "preflight blocking_reasons must be empty before shared publication"
        )


def _resolve_candidate_relative_path(
    candidate_root: Path, relative_path: str, *, label: str
) -> Path:
    if Path(relative_path).is_absolute():
        raise ProgramOraclePublicationError(
            f"{label} must be relative to candidate root"
        )
    root = candidate_root.resolve()
    resolved = (root / relative_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProgramOraclePublicationError(
            f"{label} must stay within candidate root"
        ) from exc
    return resolved


def _validate_preflight_hashes(
    preflight: Mapping[str, Any],
) -> tuple[Path, Path, dict[str, str]]:
    created_from = _safe_mapping(preflight.get("created_from"))
    artifact_hashes = _safe_mapping(preflight.get("artifact_hashes"))
    evidence_path = (
        Path(
            _required_text(
                created_from.get("oracle_evidence_path"),
                field="created_from.oracle_evidence_path",
            )
        )
        .expanduser()
        .resolve()
    )
    expected_hash = _required_text(
        artifact_hashes.get("oracle_evidence_sha256"),
        field="artifact_hashes.oracle_evidence_sha256",
    )
    actual_hash = _sha256_file(evidence_path)
    if actual_hash != expected_hash:
        raise ProgramOraclePublicationError(
            "program Oracle evidence hash no longer matches preflight packet"
        )
    manifest_path = (
        Path(
            _required_text(
                created_from.get("manifest_path"), field="created_from.manifest_path"
            )
        )
        .expanduser()
        .resolve()
    )
    expected_manifest_hash = _required_text(
        artifact_hashes.get("manifest_sha256"), field="artifact_hashes.manifest_sha256"
    )
    if _sha256_file(manifest_path) != expected_manifest_hash:
        raise ProgramOraclePublicationError(
            "program manifest hash no longer matches preflight packet"
        )
    runtime_traces_path_text = _required_text(
        created_from.get("runtime_traces_path"),
        field="created_from.runtime_traces_path",
    )
    runtime_traces_path = Path(runtime_traces_path_text).expanduser().resolve()
    expected_runtime_traces_hash = _required_text(
        artifact_hashes.get("runtime_traces_sha256"),
        field="artifact_hashes.runtime_traces_sha256",
    )
    if _sha256_file(runtime_traces_path) != expected_runtime_traces_hash:
        raise ProgramOraclePublicationError(
            "program runtime traces hash no longer matches preflight packet"
        )
    return (
        evidence_path,
        manifest_path,
        {
            "manifest_sha256": expected_manifest_hash,
            "oracle_evidence_sha256": actual_hash,
            "runtime_traces_sha256": expected_runtime_traces_hash,
        },
    )


def _validate_runtime_trace_preflight_binding(
    *,
    preflight: Mapping[str, Any],
    evidence: Mapping[str, Any],
    manifest_path: Path,
    artifact_hashes: Mapping[str, str],
) -> None:
    evidence_summary = _safe_mapping(evidence.get("runtime_traces"))
    evidence_path = _required_text(
        evidence_summary.get("path"), field="evidence.runtime_traces.path"
    )
    evidence_hash = _required_text(
        evidence_summary.get("content_hash"),
        field="evidence.runtime_traces.content_hash",
    )
    if evidence_hash != artifact_hashes.get("runtime_traces_sha256"):
        raise ProgramOraclePublicationError(
            "preflight runtime traces hash does not match program Oracle evidence summary"
        )
    expected_runtime_path = _resolve_candidate_relative_path(
        manifest_path.parent,
        evidence_path,
        label="evidence.runtime_traces.path",
    )
    created_from = _safe_mapping(preflight.get("created_from"))
    runtime_traces_path = (
        Path(
            _required_text(
                created_from.get("runtime_traces_path"),
                field="created_from.runtime_traces_path",
            )
        )
        .expanduser()
        .resolve()
    )
    if runtime_traces_path != expected_runtime_path:
        raise ProgramOraclePublicationError(
            "preflight runtime traces path does not match program Oracle evidence summary"
        )


def _expected_publication_id(
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


def _validate_publication_contract(
    *,
    preflight: Mapping[str, Any],
    target_name: str,
    evidence: Mapping[str, Any],
    evidence_identity: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    preflight_identity = _safe_mapping(preflight.get("identity"))
    if preflight_identity != dict(evidence_identity):
        raise ProgramOraclePublicationError(
            "preflight identity does not match program Oracle evidence identity"
        )

    publication = _safe_mapping(preflight.get("publication"))
    label = _required_text(
        publication.get("publication_label"), field="publication.publication_label"
    )
    if label not in EMPIRICAL_LABELS | AUTHORITY_MIRROR_LABELS:
        raise ProgramOraclePublicationError(
            "publication_label is not eligible for shared publication"
        )
    expected_label_class = (
        "authority_mirror" if label in AUTHORITY_MIRROR_LABELS else "empirical"
    )
    if publication.get("publication_label_class") != expected_label_class:
        raise ProgramOraclePublicationError(
            "publication_label_class does not match publication_label"
        )
    authority_ref = str(publication.get("authority_ref") or "").strip() or None
    if expected_label_class == "authority_mirror" and authority_ref is None:
        raise ProgramOraclePublicationError(
            "authority_ref is required for authority-mirror publication labels"
        )
    publisher_id = _required_text(
        publication.get("publisher_id"), field="publication.publisher_id"
    )
    publisher_role = _required_text(
        publication.get("publisher_role"), field="publication.publisher_role"
    )
    publisher_assertion = _required_text(
        publication.get("publisher_assertion"), field="publication.publisher_assertion"
    )
    try:
        validate_publisher_assertion_no_secret(publisher_assertion)
    except ProgramOracleSecretPolicyError as exc:
        raise ProgramOraclePublicationError(str(exc)) from exc
    redaction_status = _required_text(
        publication.get("redaction_status"), field="publication.redaction_status"
    )
    if redaction_status not in ELIGIBLE_REDACTION_STATUSES:
        raise ProgramOraclePublicationError(
            "publication.redaction_status is not eligible for shared publication"
        )
    retention_class = _required_text(
        publication.get("retention_class"), field="publication.retention_class"
    )
    if retention_class not in ELIGIBLE_RETENTION_CLASSES:
        raise ProgramOraclePublicationError(
            "publication.retention_class is not eligible for shared publication"
        )

    planned_record = _safe_mapping(preflight.get("planned_record"))
    secret_refs = _validate_publisher_secret_ref_descriptors(
        publication.get("publisher_secret_refs")
    )

    expected_planned = {
        "candidate_id": evidence_identity.get("candidate_id"),
        "assembly_id": evidence_identity.get("assembly_id"),
        "receipt_bundle_id": evidence_identity.get("receipt_bundle_id"),
        "publication_label": label,
        "publication_label_class": expected_label_class,
        "publisher_id": publisher_id,
        "publisher_role": publisher_role,
        "authority_ref": authority_ref,
        "redaction_status": redaction_status,
        "retention_class": retention_class,
        "publisher_secret_refs": secret_refs,
        "oracle_evidence_sha256": artifact_hashes["oracle_evidence_sha256"],
        "manifest_sha256": artifact_hashes["manifest_sha256"],
        "runtime_traces_sha256": artifact_hashes["runtime_traces_sha256"],
        "runtime_traces": _runtime_trace_publication_summary(
            _safe_mapping(evidence.get("runtime_traces"))
        ),
    }
    mismatched = [
        key
        for key, expected in expected_planned.items()
        if planned_record.get(key) != expected
    ]
    if mismatched:
        raise ProgramOraclePublicationError(
            "planned_record does not match validated publication fields: "
            + ", ".join(sorted(mismatched))
        )
    non_authority = _safe_mapping(planned_record.get("non_authority"))
    invalid = [
        key
        for key in _REQUIRED_FALSE_PUBLICATION_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid:
        raise ProgramOraclePublicationError(
            "planned_record non_authority flags must be false: " + ", ".join(invalid)
        )

    expected_publication_id = _expected_publication_id(
        target=target_name,
        identity=evidence_identity,
        artifact_hashes=artifact_hashes,
        publication_label=label,
        authority_ref=authority_ref,
        publisher_id=publisher_id,
        publisher_role=publisher_role,
        publisher_assertion=publisher_assertion,
        redaction_status=redaction_status,
        retention_class=retention_class,
        publisher_secret_refs=secret_refs,
    )
    actual_publication_id = _required_text(
        preflight.get("publication_id"), field="publication_id"
    )
    if actual_publication_id != expected_publication_id:
        raise ProgramOraclePublicationError(
            "publication_id does not match recomputed idempotency key"
        )
    return expected_publication_id, publication, planned_record


def validate_program_oracle_publication_preflight_contract(
    preflight: Mapping[str, Any],
    *,
    expected_manifest_path: Path,
    expected_manifest_hash: str,
    preflight_path: Path | None = None,
) -> None:
    """Validate a program Oracle publication preflight without shared mutation."""

    source = preflight_path or Path("<program-oracle-publication-preflight>")
    _ensure_preflight_passed(preflight, source)
    target = _safe_mapping(preflight.get("target"))
    target_name = _validate_publication_preflight_target_posture(target)
    evidence_path, manifest_path, artifact_hashes = _validate_preflight_hashes(
        preflight
    )
    if manifest_path != expected_manifest_path.expanduser().resolve():
        raise ProgramOraclePublicationError(
            "preflight manifest path does not match current manifest"
        )
    if artifact_hashes.get("manifest_sha256") != expected_manifest_hash:
        raise ProgramOraclePublicationError(
            "preflight manifest hash does not match current manifest"
        )
    evidence = load_program_oracle_evidence(evidence_path)
    if (
        evidence is None
        or evidence.get("schema_version") != PROGRAM_ORACLE_EVIDENCE_SCHEMA
    ):
        raise ProgramOraclePublicationError(
            "program Oracle evidence schema_version must be "
            + PROGRAM_ORACLE_EVIDENCE_SCHEMA
        )
    _validate_runtime_trace_preflight_binding(
        preflight=preflight,
        evidence=evidence,
        manifest_path=manifest_path,
        artifact_hashes=artifact_hashes,
    )
    expected_publication_id, _publication, _planned_record = (
        _validate_publication_contract(
            preflight=preflight,
            target_name=target_name,
            evidence=evidence,
            evidence_identity=_safe_mapping(evidence.get("identity")),
            artifact_hashes=artifact_hashes,
        )
    )
    idempotency = _safe_mapping(preflight.get("idempotency"))
    expected_idempotency = {
        "publication_id": expected_publication_id,
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
        raise ProgramOraclePublicationError(
            "preflight idempotency contract mismatch: "
            + ", ".join(mismatched_idempotency)
        )
    effect = _safe_mapping(preflight.get("effect"))
    for key in (
        "mlflow_mutated",
        "program_files_mutated",
        "promotion_state_changed",
    ):
        if effect.get(key) is not False:
            raise ProgramOraclePublicationError(f"preflight must prove {key} is false")
    non_authority = _safe_mapping(preflight.get("non_authority"))
    invalid_non_authority = [
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
    if invalid_non_authority:
        raise ProgramOraclePublicationError(
            "preflight widens non-authority flags: " + ", ".join(invalid_non_authority)
        )


def _receipt_identity_matches(
    actual: Mapping[str, Any], expected: Mapping[str, Any]
) -> bool:
    if not actual:
        return False
    for key, expected_value in expected.items():
        if expected_value in {None, ""}:
            continue
        if str(actual.get(key) or "") != str(expected_value):
            return False
    return True


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
        raise ProgramOraclePublicationError(
            f"{label} target must not include raw database URL fields"
        )
    if target.get("database_url_present") is True:
        redacted = str(target.get("database_url_redacted") or "").strip()
        if not redacted:
            raise ProgramOraclePublicationError(
                f"{label} target.database_url_redacted is required"
            )
        if "://" in redacted and "@" in redacted and ":<redacted>@" not in redacted:
            raise ProgramOraclePublicationError(
                f"{label} target.database_url_redacted must not expose secret-bearing credentials"
            )
        lowered = redacted.lower()
        if any(marker in lowered for marker in ("super-secret", "password=", "token=")):
            raise ProgramOraclePublicationError(
                f"{label} target.database_url_redacted must not expose secret values"
            )


def _validate_publication_preflight_target_posture(target: Mapping[str, Any]) -> str:
    if not target:
        raise ProgramOraclePublicationError("preflight target posture is required")
    target_name = _required_text(target.get("target"), field="target.target")
    if target_name not in TARGETS:
        raise ProgramOraclePublicationError("preflight target is not supported")
    if target.get("target_supported_by_preflight") is not True:
        raise ProgramOraclePublicationError(
            "preflight target_supported_by_preflight must be true"
        )
    if target.get("connection_attempted") is not False:
        raise ProgramOraclePublicationError(
            "preflight target.connection_attempted must be false"
        )
    if target.get("shared_write_attempted") is not False:
        raise ProgramOraclePublicationError(
            "preflight target.shared_write_attempted must be false"
        )
    _validate_redacted_database_url_posture(target, label="preflight")
    return target_name


def _validate_publication_receipt_target_posture(target: Mapping[str, Any]) -> None:
    if not target:
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt target posture is required"
        )
    if not str(target.get("backend") or "").strip():
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt target.backend is required"
        )
    if target.get("connection_attempted") is not True:
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt target.connection_attempted must be true"
        )
    if target.get("shared_write_attempted") is not True:
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt target.shared_write_attempted must be true"
        )
    _validate_redacted_database_url_posture(target, label="oracle_publication_receipt")


def validate_program_oracle_publication_receipt_contract(
    receipt: Mapping[str, Any],
    *,
    expected_identities: Iterable[Mapping[str, Any]] = (),
    preflight: Mapping[str, Any] | None = None,
    preflight_sha256: str | None = None,
) -> None:
    """Validate a shared Oracle publication receipt before downstream consumption."""

    if receipt.get("schema_version") != PROGRAM_ORACLE_PUBLICATION_RECEIPT_SCHEMA:
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt schema_version must be "
            + PROGRAM_ORACLE_PUBLICATION_RECEIPT_SCHEMA
        )
    if receipt.get("status") != "published":
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt status must be published"
        )

    identity = _safe_mapping(receipt.get("identity"))
    expected_identity_list = tuple(expected_identities)
    if expected_identity_list and not any(
        _receipt_identity_matches(identity, expected)
        for expected in expected_identity_list
    ):
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt identity does not match expected candidate/source identity"
        )

    publication_id = _required_text(
        receipt.get("publication_id"), field="oracle_publication_receipt.publication_id"
    )
    run_id = _required_text(
        receipt.get("run_id"), field="oracle_publication_receipt.run_id"
    )
    expected_run_id = _publication_run_id(publication_id)
    if run_id != expected_run_id:
        raise ProgramOraclePublicationError(
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
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt idempotency contract mismatch: "
            + ", ".join(mismatched_idempotency)
        )

    publication = _safe_mapping(receipt.get("publication"))
    record = _safe_mapping(receipt.get("record"))
    if preflight is not None:
        if preflight.get("publication_id") != publication_id:
            raise ProgramOraclePublicationError(
                "oracle_publication_receipt publication_id mismatch with supplied preflight"
            )
        if publication != _safe_mapping(preflight.get("publication")):
            raise ProgramOraclePublicationError(
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
            raise ProgramOraclePublicationError(
                "oracle_publication_receipt record does not match supplied preflight planned_record: "
                + ", ".join(sorted(mismatched_preflight_record))
            )

    expected_record = {
        "schema_version": PROGRAM_ORACLE_PUBLICATION_RECORD_SCHEMA,
        "run_kind": PROGRAM_ORACLE_PUBLICATION_RUN_KIND,
        "template_version": PROGRAM_ORACLE_PUBLICATION_RECORD_SCHEMA,
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
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt record does not match publication fields: "
            + ", ".join(sorted(mismatched_record))
        )
    record_non_authority = _safe_mapping(record.get("non_authority"))
    record_widened = [
        key
        for key in _REQUIRED_FALSE_PUBLICATION_NON_AUTHORITY_FLAGS
        if record_non_authority.get(key) is not False
    ]
    if record_widened:
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt record widens non-authority flags: "
            + ", ".join(record_widened)
        )

    _validate_publication_receipt_target_posture(_safe_mapping(receipt.get("target")))

    source = _safe_mapping(receipt.get("source"))
    if source.get("local_paths_omitted_from_shared_record") is not True:
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt must omit local paths from shared record"
        )
    for key in (
        "preflight_file",
        "preflight_sha256",
        "oracle_evidence_file",
        "oracle_evidence_sha256",
    ):
        if not str(source.get(key) or "").strip():
            raise ProgramOraclePublicationError(
                f"oracle_publication_receipt source.{key} is required"
            )
    if preflight_sha256 and source.get("preflight_sha256") != preflight_sha256:
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt source.preflight_sha256 does not match supplied preflight"
        )
    if preflight is not None:
        preflight_hashes = _safe_mapping(preflight.get("artifact_hashes"))
        if source.get("oracle_evidence_sha256") != preflight_hashes.get(
            "oracle_evidence_sha256"
        ):
            raise ProgramOraclePublicationError(
                "oracle_publication_receipt source.oracle_evidence_sha256 does not match supplied preflight"
            )

    effect = _safe_mapping(receipt.get("effect"))
    if effect.get("shared_oracle_mutated") is not True:
        raise ProgramOraclePublicationError(
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
            raise ProgramOraclePublicationError(
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
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt widens non-authority flags: "
            + ", ".join(invalid)
        )


def _publication_run_id(publication_id: str) -> str:
    return f"program-oracle-publication:{publication_id}"


def _redacted_store_posture(
    store: CoordinateStore, target: Mapping[str, Any]
) -> dict[str, Any]:
    backend = str(getattr(store, "backend_name", type(store).__name__))
    payload: dict[str, Any] = {
        "target": target.get("target"),
        "backend": backend,
        "database_url_present": bool(target.get("database_url_present")),
        "database_url_redacted": target.get("database_url_redacted"),
        "schema": target.get("schema"),
        "connection_attempted": True,
        "shared_write_attempted": True,
    }
    redacted_url = getattr(store, "redacted_database_url", None)
    if redacted_url:
        payload["database_url_redacted"] = redacted_url
        payload["database_url_present"] = True
    db_path = getattr(store, "db_path", None)
    if db_path is not None:
        payload["store_path"] = str(db_path)
    return payload


def _open_configured_shared_store() -> CoordinateStore:
    target_store = str(os.getenv("DSPX_ORACLE_STORE") or "").strip().lower()
    if target_store not in _POSTGRES_STORE_NAMES:
        raise ProgramOraclePublicationError(
            "explicit shared Oracle publication requires a configured and available "
            "Postgres/pgvector Oracle backend: set DSPX_ORACLE_STORE=postgres_pgvector"
        )
    database_url = str(
        os.getenv("DSPX_ORACLE_DATABASE_URL")
        or os.getenv("DSPX_ORACLE_POSTGRES_URL")
        or ""
    ).strip()
    if not database_url:
        raise ProgramOraclePublicationError(
            "explicit shared Oracle publication requires a configured and available "
            "Postgres/pgvector Oracle backend: set DSPX_ORACLE_DATABASE_URL or "
            "DSPX_ORACLE_POSTGRES_URL"
        )
    try:
        from dspx.coordinates.postgres_store import PostgresPgvectorCoordinateStore

        return PostgresPgvectorCoordinateStore(database_url=database_url)
    except Exception as exc:
        raise ProgramOraclePublicationError(
            "explicit shared Oracle publication requires a configured and available "
            "Postgres/pgvector Oracle backend"
        ) from exc


def program_oracle_publication_input_paths(preflight_path: Path) -> tuple[Path, ...]:
    """Return local input paths a program Oracle publication receipt must not overwrite."""

    source = preflight_path.expanduser().resolve()
    preflight = _load_json_object(source, label="program Oracle publication preflight")
    _ensure_preflight_passed(preflight, source)
    evidence_path, manifest_path, _artifact_hashes = _validate_preflight_hashes(
        preflight
    )
    created_from = _safe_mapping(preflight.get("created_from"))
    runtime_traces_path = (
        Path(
            _required_text(
                created_from.get("runtime_traces_path"),
                field="created_from.runtime_traces_path",
            )
        )
        .expanduser()
        .resolve()
    )
    return (source, manifest_path, evidence_path, runtime_traces_path)


def prepare_program_oracle_publication_receipt_output_path(
    out_path: Path,
    *,
    preflight_path: Path,
    protected_input_paths: Iterable[Path] | None = None,
) -> Path:
    """Validate a local receipt output path before shared publication is attempted."""

    protected_paths = tuple(
        protected_input_paths
        if protected_input_paths is not None
        else program_oracle_publication_input_paths(preflight_path)
    )
    manifest_roots = tuple(
        path.parent for path in protected_paths if path.name == "manifest.json"
    )
    try:
        return prepare_sidecar_output_path(
            out_path,
            payload={},
            artifact_label="program Oracle publication receipt",
            protected_names=_PUBLICATION_RECEIPT_PROTECTED_OUTPUT_NAMES,
            payload_artifact_root_policy="ignore",
            extra_protected_paths=protected_paths,
            extra_protected_roots=manifest_roots,
        )
    except ValueError as exc:
        raise ProgramOraclePublicationError(str(exc)) from exc


def publish_program_oracle_preflight(
    *,
    preflight_path: Path,
    store: CoordinateStore | None = None,
) -> dict[str, Any]:
    """Publish one preflighted program Oracle evidence record to a shared store.

    This is explicit shared publication only: it writes one coordinate record to the
    configured shared Oracle store and returns a receipt. It does not mutate AK,
    governance, MLflow, generated program files, or activation/promotion state.
    """

    source = preflight_path.expanduser().resolve()
    preflight = _load_json_object(source, label="program Oracle publication preflight")
    _ensure_preflight_passed(preflight, source)
    target = _safe_mapping(preflight.get("target"))
    target_name = _required_text(target.get("target"), field="target.target")
    if target_name not in TARGETS:
        raise ProgramOraclePublicationError("preflight target is not supported")

    evidence_path, manifest_path, artifact_hashes = _validate_preflight_hashes(
        preflight
    )
    evidence_hash = artifact_hashes["oracle_evidence_sha256"]
    evidence = load_program_oracle_evidence(evidence_path)
    if (
        evidence is None
        or evidence.get("schema_version") != PROGRAM_ORACLE_EVIDENCE_SCHEMA
    ):
        raise ProgramOraclePublicationError(
            "program Oracle evidence schema_version must be "
            + PROGRAM_ORACLE_EVIDENCE_SCHEMA
        )

    _validate_runtime_trace_preflight_binding(
        preflight=preflight,
        evidence=evidence,
        manifest_path=manifest_path,
        artifact_hashes=artifact_hashes,
    )
    evidence_identity = _safe_mapping(evidence.get("identity"))
    publication_id, publication, planned_record = _validate_publication_contract(
        preflight=preflight,
        target_name=target_name,
        evidence=evidence,
        evidence_identity=evidence_identity,
        artifact_hashes=artifact_hashes,
    )
    embedding = build_program_oracle_evidence_embedding(
        evidence,
        evidence_path=evidence_path,
        evidence_hash=evidence_hash,
    )
    run_id = _publication_run_id(publication_id)
    base_metadata = dict(embedding.metadata)
    base_metadata.pop("evidence_path", None)
    publication_metadata = {
        **base_metadata,
        "schema_version": PROGRAM_ORACLE_PUBLICATION_RECORD_SCHEMA,
        "source_schema_version": PROGRAM_ORACLE_EVIDENCE_SCHEMA,
        "publication_id": publication_id,
        "publication": publication,
        "planned_record": planned_record,
        "publication_label": publication.get("publication_label"),
        "publication_label_class": publication.get("publication_label_class"),
        "authority_ref": publication.get("authority_ref"),
        "authority_ref_kind": publication.get("authority_ref_kind"),
        "retention_class": publication.get("retention_class"),
        "redaction_status": publication.get("redaction_status"),
        "publisher_id": publication.get("publisher_id"),
        "publisher_role": publication.get("publisher_role"),
        "preflight": {
            "file_name": source.name,
            "sha256": _sha256_file(source),
            "schema_version": preflight.get("schema_version"),
        },
        "artifact_hashes": _safe_mapping(preflight.get("artifact_hashes")),
        "identity": _safe_mapping(preflight.get("identity")),
        "non_authority": _safe_mapping(planned_record.get("non_authority")),
    }
    publication_embedding = replace(
        embedding,
        run_id=run_id,
        run_kind=PROGRAM_ORACLE_PUBLICATION_RUN_KIND,
        provider="program-gen",
        template_version=PROGRAM_ORACLE_PUBLICATION_RECORD_SCHEMA,
        source_path=None,
        metadata=publication_metadata,
    )

    shared_store = store or _open_configured_shared_store()
    try:
        upserted = shared_store.upsert(publication_embedding)
    except Exception as exc:
        raise ProgramOraclePublicationError(
            "shared Oracle publication upsert failed"
        ) from exc
    if upserted is not True:
        raise ProgramOraclePublicationError("shared Oracle publication upsert failed")

    return {
        "schema_version": PROGRAM_ORACLE_PUBLICATION_RECEIPT_SCHEMA,
        "status": "published",
        "publication_id": publication_id,
        "run_id": run_id,
        "target": _redacted_store_posture(shared_store, target),
        "source": {
            "preflight_file": source.name,
            "preflight_sha256": _sha256_file(source),
            "oracle_evidence_file": evidence_path.name,
            "oracle_evidence_sha256": evidence_hash,
            "local_paths_omitted_from_shared_record": True,
        },
        "identity": _safe_mapping(preflight.get("identity")),
        "publication": publication,
        "record": {
            "schema_version": PROGRAM_ORACLE_PUBLICATION_RECORD_SCHEMA,
            "run_kind": PROGRAM_ORACLE_PUBLICATION_RUN_KIND,
            "template_version": PROGRAM_ORACLE_PUBLICATION_RECORD_SCHEMA,
            "provider": "program-gen",
            "publication_label": publication.get("publication_label"),
            "publication_label_class": publication.get("publication_label_class"),
            "retention_class": publication.get("retention_class"),
            "redaction_status": publication.get("redaction_status"),
            "authority_ref": publication.get("authority_ref"),
            "non_authority": _safe_mapping(planned_record.get("non_authority")),
        },
        "idempotency": {
            "publication_id": publication_id,
            "run_id": run_id,
            "upsert_semantics": "same run_id replaces equivalent shared coordinate record",
            "safe_to_retry": True,
        },
        "effect": {
            "local_receipt_written": False,
            "oracle_index_mutated": False,
            "shared_oracle_mutated": True,
            "ak_called": False,
            "governance_mutated": False,
            "mlflow_mutated": False,
            "program_files_mutated": False,
            "promotion_state_changed": False,
        },
        "non_authority": {
            "oracle_authority": False,
            "promotion_authority": False,
            "governance_authority": False,
            "agent_kernel_mutation": False,
            "winner_selection": False,
            "automatic_promotion": False,
        },
        "notes": [
            "This receipt records an explicit shared Oracle empirical publication.",
            "Oracle remains empirical memory and does not approve promotion or activation.",
            "Authority-mirror labels mirror the supplied authority_ref only.",
        ],
    }


def write_program_oracle_publication_receipt(
    receipt: Mapping[str, Any],
    out_path: Path,
    *,
    extra_protected_paths: Iterable[Path] = (),
    extra_protected_roots: Iterable[Path] = (),
) -> dict[str, Any]:
    """Write a local receipt for an explicit shared Oracle publication."""

    payload = dict(receipt)
    if payload.get("schema_version") != PROGRAM_ORACLE_PUBLICATION_RECEIPT_SCHEMA:
        raise ProgramOraclePublicationError(
            "program Oracle publication receipt schema_version is invalid"
        )
    try:
        target = prepare_sidecar_output_path(
            out_path,
            payload=payload,
            artifact_label="program Oracle publication receipt",
            protected_names=_PUBLICATION_RECEIPT_PROTECTED_OUTPUT_NAMES,
            payload_artifact_root_policy="ignore",
            extra_protected_paths=extra_protected_paths,
            extra_protected_roots=extra_protected_roots,
        )
    except ValueError as exc:
        raise ProgramOraclePublicationError(str(exc)) from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    effect = _safe_mapping(payload.get("effect"))
    effect["local_receipt_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload
