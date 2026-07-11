# summary: "Builds local preflight packets for publishing pi-autoresearch empirical evidence to shared Oracle storage."
# read_when:
#   - "Changing autoresearch packet validation, publication labels, custody fields, or idempotency."

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_oracle_publication_preflight import (
    AUTHORITY_MIRROR_LABELS,
    ELIGIBLE_RETENTION_CLASSES,
    EMPIRICAL_LABELS,
    INELIGIBLE_REDACTION_STATUSES,
    REDACTION_STATUSES,
    RETENTION_CLASSES,
    TARGETS,
)
from dspx.services.program_oracle_secret_policy import (
    ProgramOracleSecretPolicyError,
    build_onepassword_ref_descriptors,
    validate_publisher_assertion_no_secret,
)

AUTORESEARCH_ORACLE_EVIDENCE_PACKET_SCHEMA = "autoresearch.oracle_evidence.v1"
AUTORESEARCH_ORACLE_EVIDENCE_RECORD_SCHEMA = (
    "autoresearch.campaign_run.oracle_evidence.v1"
)
AUTORESEARCH_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA = (
    "autoresearch-oracle-shared-publication-preflight-v1"
)

PUBLICATION_LABELS = EMPIRICAL_LABELS | AUTHORITY_MIRROR_LABELS
_REQUIRED_TARGET_KINDS = {
    "dspx_oracle",
    "empirical_memory",
    "evidence",
    "adapter_source",
}
_REQUIRED_RECORD_FIELDS = (
    "campaign",
    "metricName",
    "metricUnit",
    "direction",
    "runStatus",
    "runKind",
    "empiricalDecisionClass",
    "metric",
    "timestamp",
    "description",
    "checks",
)


class AutoresearchOraclePublicationPreflightError(ValueError):
    """Raised when autoresearch Oracle publication preflight fails closed."""


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AutoresearchOraclePublicationPreflightError(
            f"{label} not found: {source}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise AutoresearchOraclePublicationPreflightError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise AutoresearchOraclePublicationPreflightError(
            f"{label} must contain a JSON object: {source}"
        )
    return payload


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _required_text(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AutoresearchOraclePublicationPreflightError(f"{field} is required")
    return text


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _label_class(label: str) -> str:
    if label in EMPIRICAL_LABELS:
        return "empirical"
    if label in AUTHORITY_MIRROR_LABELS:
        return "authority_mirror"
    raise AutoresearchOraclePublicationPreflightError(
        "unknown publication_label: "
        + label
        + "; expected one of "
        + ", ".join(sorted(PUBLICATION_LABELS))
    )


def _validate_redaction_status(value: str) -> None:
    if value not in REDACTION_STATUSES:
        raise AutoresearchOraclePublicationPreflightError(
            "unknown redaction_status: "
            + value
            + "; expected one of "
            + ", ".join(sorted(REDACTION_STATUSES))
        )
    if value in INELIGIBLE_REDACTION_STATUSES:
        raise AutoresearchOraclePublicationPreflightError(
            "redaction_status is not eligible for shared publication: " + value
        )


def _validate_retention_class(value: str) -> None:
    if value not in RETENTION_CLASSES:
        raise AutoresearchOraclePublicationPreflightError(
            "unknown retention_class: "
            + value
            + "; expected one of "
            + ", ".join(sorted(RETENTION_CLASSES))
        )
    if value not in ELIGIBLE_RETENTION_CLASSES:
        raise AutoresearchOraclePublicationPreflightError(
            "retention_class is not eligible for shared publication: " + value
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


def _validate_source_packet(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    if packet.get("packetKind") != AUTORESEARCH_ORACLE_EVIDENCE_PACKET_SCHEMA:
        raise AutoresearchOraclePublicationPreflightError(
            "autoresearch packetKind must be "
            + AUTORESEARCH_ORACLE_EVIDENCE_PACKET_SCHEMA
        )
    if packet.get("adapterContractVersion") != 1:
        raise AutoresearchOraclePublicationPreflightError(
            "autoresearch adapterContractVersion must be 1"
        )
    target_kinds = packet.get("targetKinds")
    if not isinstance(target_kinds, list) or not _REQUIRED_TARGET_KINDS.issubset(
        {str(item) for item in target_kinds}
    ):
        raise AutoresearchOraclePublicationPreflightError(
            "autoresearch targetKinds must include dspx_oracle, empirical_memory, evidence, and adapter_source"
        )
    source_artifacts = _safe_mapping(packet.get("sourceArtifacts"))
    if source_artifacts.get("closeoutPacketKind") != "autoresearch.closeout.v1":
        raise AutoresearchOraclePublicationPreflightError(
            "autoresearch sourceArtifacts.closeoutPacketKind must be autoresearch.closeout.v1"
        )
    _required_text(
        source_artifacts.get("receiptPath"), field="sourceArtifacts.receiptPath"
    )
    for field in ("adapterBoundary", "evidenceBoundary", "authorityBoundary"):
        _required_text(packet.get(field), field=field)

    publication_preflight = _safe_mapping(packet.get("publicationPreflight"))
    if publication_preflight.get("status") != "ready_for_dspx_owner_review":
        raise AutoresearchOraclePublicationPreflightError(
            "autoresearch publicationPreflight.status must be ready_for_dspx_owner_review"
        )
    if publication_preflight.get("target") != "dspx_oracle_postgres_pgvector":
        raise AutoresearchOraclePublicationPreflightError(
            "autoresearch publicationPreflight.target must be dspx_oracle_postgres_pgvector"
        )
    if publication_preflight.get("blockedReasons") != []:
        raise AutoresearchOraclePublicationPreflightError(
            "autoresearch publicationPreflight.blockedReasons must be empty"
        )
    for field in (
        "sharedOracleMutated",
        "localCoordinatesDbMigrated",
        "canonicalAuthorityMutated",
    ):
        if publication_preflight.get(field) is not False:
            raise AutoresearchOraclePublicationPreflightError(
                f"autoresearch publicationPreflight.{field} must be false"
            )
    records = packet.get("records")
    if not isinstance(records, list):
        raise AutoresearchOraclePublicationPreflightError(
            "autoresearch records must be an array"
        )
    if not records:
        raise AutoresearchOraclePublicationPreflightError(
            "autoresearch records must contain at least one Oracle-ready record"
        )
    normalized_records: list[dict[str, Any]] = []
    seen_record_ids: set[str] = set()
    for index, value in enumerate(records):
        if not isinstance(value, Mapping):
            raise AutoresearchOraclePublicationPreflightError(
                f"autoresearch records[{index}] must be an object"
            )
        record = {str(key): item for key, item in value.items()}
        if record.get("recordKind") != AUTORESEARCH_ORACLE_EVIDENCE_RECORD_SCHEMA:
            raise AutoresearchOraclePublicationPreflightError(
                f"autoresearch records[{index}].recordKind must be "
                + AUTORESEARCH_ORACLE_EVIDENCE_RECORD_SCHEMA
            )
        record_id = _required_text(
            record.get("recordId"), field=f"records[{index}].recordId"
        )
        if record_id in seen_record_ids:
            raise AutoresearchOraclePublicationPreflightError(
                f"autoresearch records[{index}].recordId is duplicated"
            )
        seen_record_ids.add(record_id)
        _required_text(record.get("oracleText"), field=f"records[{index}].oracleText")
        for field in _REQUIRED_RECORD_FIELDS:
            _required_text(record.get(field), field=f"records[{index}].{field}")
        if record.get("nonAuthority") is not True:
            raise AutoresearchOraclePublicationPreflightError(
                f"autoresearch records[{index}].nonAuthority must be true"
            )
        source_refs = _safe_mapping(record.get("sourceRefs"))
        if source_refs.get("closeoutPacketKind") != "autoresearch.closeout.v1":
            raise AutoresearchOraclePublicationPreflightError(
                "autoresearch records["
                + str(index)
                + "].sourceRefs.closeoutPacketKind must be autoresearch.closeout.v1"
            )
        _required_text(
            source_refs.get("receiptPath"),
            field=f"records[{index}].sourceRefs.receiptPath",
        )
        normalized_records.append(record)
    return normalized_records


def _idempotency_key(
    *,
    target: str,
    packet_hash: str,
    record_hashes: Mapping[str, str],
    publication_label: str,
    authority_ref: str | None,
    publisher_id: str,
    redaction_status: str,
    retention_class: str,
    publisher_secret_refs: list[dict[str, Any]] | None = None,
) -> str:
    seed = {
        "schema_version": AUTORESEARCH_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA,
        "target": target,
        "packet_hash": packet_hash,
        "record_hashes": dict(sorted(record_hashes.items())),
        "publication_label": publication_label,
        "authority_ref": authority_ref,
        "publisher_id": publisher_id,
        "redaction_status": redaction_status,
        "retention_class": retention_class,
        "publisher_secret_refs": publisher_secret_refs or [],
    }
    return "autoresearch-oracle-pub-" + _sha256_payload(seed)[:20]


def build_autoresearch_oracle_publication_preflight(
    *,
    packet_path: Path,
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
    """Build a local preflight packet for pi-autoresearch Oracle evidence."""

    source_packet_file = packet_path.expanduser().resolve()
    normalized_target = _required_text(target, field="target")
    if normalized_target not in TARGETS:
        raise AutoresearchOraclePublicationPreflightError(
            "unknown target: "
            + normalized_target
            + "; expected one of "
            + ", ".join(sorted(TARGETS))
        )
    normalized_label = _required_text(publication_label, field="publication_label")
    label_class = _label_class(normalized_label)
    normalized_authority_ref = str(authority_ref or "").strip() or None
    if label_class == "authority_mirror" and normalized_authority_ref is None:
        raise AutoresearchOraclePublicationPreflightError(
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
        raise AutoresearchOraclePublicationPreflightError(str(exc)) from exc
    normalized_redaction_status = _required_text(
        redaction_status, field="redaction_status"
    )
    _validate_redaction_status(normalized_redaction_status)
    normalized_retention_class = _required_text(
        retention_class, field="retention_class"
    )
    _validate_retention_class(normalized_retention_class)

    packet = _load_json_object(source_packet_file, label="autoresearch Oracle packet")
    records = _validate_source_packet(packet)
    packet_hash = _sha256_file(source_packet_file)
    record_hashes = {
        str(record["recordId"]): _sha256_payload(record) for record in records
    }
    publication_id = _idempotency_key(
        target=normalized_target,
        packet_hash=packet_hash,
        record_hashes=record_hashes,
        publication_label=normalized_label,
        authority_ref=normalized_authority_ref,
        publisher_id=normalized_publisher_id,
        redaction_status=normalized_redaction_status,
        retention_class=normalized_retention_class,
        publisher_secret_refs=normalized_secret_refs,
    )
    record_ids = [str(record["recordId"]) for record in records]

    return {
        "schema_version": AUTORESEARCH_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA,
        "status": "ready_not_published",
        "publication_id": publication_id,
        "target": _redacted_backend_posture(normalized_target),
        "created_from": {
            "packet_file": source_packet_file.name,
            "packet_kind": packet.get("packetKind"),
            "adapter_contract_version": packet.get("adapterContractVersion"),
            "cwd_present": bool(str(packet.get("cwd") or "").strip()),
            "campaign": packet.get("campaign"),
            "source_artifacts": {
                "closeout_packet_kind": _safe_mapping(
                    packet.get("sourceArtifacts")
                ).get("closeoutPacketKind"),
                "receipt_path_present": bool(
                    str(
                        _safe_mapping(packet.get("sourceArtifacts")).get("receiptPath")
                        or ""
                    ).strip()
                ),
            },
            "local_paths_redacted": True,
        },
        "source_packet_hashes": {
            "packet_sha256": packet_hash,
            "record_sha256_by_record_id": record_hashes,
        },
        "records": {
            "record_count": len(records),
            "record_ids": record_ids,
            "record_kind": AUTORESEARCH_ORACLE_EVIDENCE_RECORD_SCHEMA,
        },
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
            "packet_valid": True,
            "records_present": True,
            "record_non_authority_valid": True,
            "publication_label_valid": True,
            "authority_ref_requirement_satisfied": True,
            "publisher_fields_present": True,
            "redaction_status_eligible": True,
            "retention_class_eligible": True,
            "ready_for_shared_publication": False,
            "ready_for_shared_publication_reason": (
                "autoresearch_adapter_preflight_only_no_shared_write"
            ),
            "blocking_reasons": ["autoresearch_adapter_preflight_only"],
        },
        "idempotency": {
            "publication_id": publication_id,
            "safe_to_recompute": True,
            "same_inputs_same_publication_id": True,
            "shared_duplicate_check_performed": False,
            "shared_duplicate_check_reason": "No shared backend was contacted.",
        },
        "planned_record": {
            "schema_version": "autoresearch-oracle-shared-publication-v1",
            "source_schema_version": AUTORESEARCH_ORACLE_EVIDENCE_PACKET_SCHEMA,
            "packet_sha256": packet_hash,
            "record_count": len(records),
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
            "This packet is a local DSPx-owner preflight over pi-autoresearch evidence.",
            "No shared Oracle backend was contacted or mutated.",
            "pi-autoresearch evidence is empirical memory input only, not authority.",
            "Publisher identity is declared custody context, not authenticated authority.",
        ],
    }


def write_autoresearch_oracle_publication_preflight(
    packet: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    """Write a local autoresearch shared-Oracle publication preflight packet."""

    target = out_path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(packet)
    if (
        payload.get("schema_version")
        != AUTORESEARCH_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA
    ):
        raise AutoresearchOraclePublicationPreflightError(
            "autoresearch preflight schema_version is invalid"
        )
    effect = _safe_mapping(payload.get("effect"))
    effect["local_preflight_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload
