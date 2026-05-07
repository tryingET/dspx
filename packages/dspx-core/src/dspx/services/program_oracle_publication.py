from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from dspx.coordinates import CoordinateStore
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

PROGRAM_ORACLE_PUBLICATION_RECEIPT_SCHEMA = (
    "program-oracle-shared-publication-receipt-v1"
)
PROGRAM_ORACLE_PUBLICATION_RECORD_SCHEMA = "program-oracle-shared-publication-v1"
PROGRAM_ORACLE_PUBLICATION_RUN_KIND = "program-oracle-shared-publication"

_POSTGRES_STORE_NAMES = {
    "postgres_pgvector",
    "pgvector",
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


def _required_text(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProgramOraclePublicationError(f"{field} is required")
    return text


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
        "publication_label_valid",
        "authority_ref_requirement_satisfied",
        "publisher_fields_present",
        "redaction_status_eligible",
        "retention_class_eligible",
    )
    failed = [key for key in required_true if checks.get(key) is not True]
    if failed:
        raise ProgramOraclePublicationError(
            "preflight checks are not publishable: " + ", ".join(failed)
        )
    blocking = checks.get("blocking_reasons")
    if blocking != ["shared_publication_not_implemented"]:
        raise ProgramOraclePublicationError(
            "preflight blocking_reasons must only contain shared_publication_not_implemented"
        )


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
    return (
        evidence_path,
        manifest_path,
        {
            "manifest_sha256": expected_manifest_hash,
            "oracle_evidence_sha256": actual_hash,
        },
    )


def _expected_publication_id(
    *,
    target: str,
    identity: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
    publication_label: str,
    authority_ref: str | None,
    publisher_id: str,
    redaction_status: str,
    retention_class: str,
) -> str:
    seed = {
        "schema_version": PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA,
        "target": target,
        "identity": {key: value for key, value in sorted(identity.items()) if value},
        "artifact_hashes": dict(sorted(artifact_hashes.items())),
        "publication_label": publication_label,
        "authority_ref": authority_ref,
        "publisher_id": publisher_id,
        "redaction_status": redaction_status,
        "retention_class": retention_class,
    }
    return "prog-oracle-pub-" + _sha256_payload(seed)[:20]


def _validate_publication_contract(
    *,
    preflight: Mapping[str, Any],
    target_name: str,
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
    _required_text(
        publication.get("publisher_assertion"), field="publication.publisher_assertion"
    )
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
    expected_planned = {
        "publication_label": label,
        "publication_label_class": expected_label_class,
        "publisher_id": publisher_id,
        "publisher_role": publisher_role,
        "authority_ref": authority_ref,
        "redaction_status": redaction_status,
        "retention_class": retention_class,
        "oracle_evidence_sha256": artifact_hashes["oracle_evidence_sha256"],
        "manifest_sha256": artifact_hashes["manifest_sha256"],
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
        redaction_status=redaction_status,
        retention_class=retention_class,
    )
    actual_publication_id = _required_text(
        preflight.get("publication_id"), field="publication_id"
    )
    if actual_publication_id != expected_publication_id:
        raise ProgramOraclePublicationError(
            "publication_id does not match recomputed idempotency key"
        )
    return expected_publication_id, publication, planned_record


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

    evidence_path, _manifest_path, artifact_hashes = _validate_preflight_hashes(
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

    evidence_identity = _safe_mapping(evidence.get("identity"))
    publication_id, publication, planned_record = _validate_publication_contract(
        preflight=preflight,
        target_name=target_name,
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
    receipt: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    """Write a local receipt for an explicit shared Oracle publication."""

    target = out_path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(receipt)
    if payload.get("schema_version") != PROGRAM_ORACLE_PUBLICATION_RECEIPT_SCHEMA:
        raise ProgramOraclePublicationError(
            "program Oracle publication receipt schema_version is invalid"
        )
    effect = _safe_mapping(payload.get("effect"))
    effect["local_receipt_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload
