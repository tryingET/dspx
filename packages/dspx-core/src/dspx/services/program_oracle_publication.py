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
    PROGRAM_ORACLE_PUBLICATION_PREFLIGHT_SCHEMA,
    TARGETS,
)

PROGRAM_ORACLE_PUBLICATION_RECEIPT_SCHEMA = (
    "program-oracle-shared-publication-receipt-v1"
)
PROGRAM_ORACLE_PUBLICATION_RECORD_SCHEMA = "program-oracle-shared-publication-v1"
PROGRAM_ORACLE_PUBLICATION_RUN_KIND = "program-oracle-shared-publication"

_POSTGRES_STORE_NAMES = {
    "postgres",
    "postgres_pgvector",
    "pgvector",
    "shared-postgres",
    "shared_postgres",
}


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


def _validate_preflight_hashes(preflight: Mapping[str, Any]) -> tuple[Path, str]:
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
    return evidence_path, actual_hash


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
    if target_store and target_store not in _POSTGRES_STORE_NAMES:
        raise ProgramOraclePublicationError(
            "explicit shared Oracle publication requires DSPX_ORACLE_STORE=postgres_pgvector"
        )
    try:
        from dspx.coordinates.postgres_store import PostgresPgvectorCoordinateStore

        return PostgresPgvectorCoordinateStore()
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

    publication_id = _required_text(
        preflight.get("publication_id"), field="publication_id"
    )
    evidence_path, evidence_hash = _validate_preflight_hashes(preflight)
    evidence = load_program_oracle_evidence(evidence_path)
    if (
        evidence is None
        or evidence.get("schema_version") != PROGRAM_ORACLE_EVIDENCE_SCHEMA
    ):
        raise ProgramOraclePublicationError(
            "program Oracle evidence schema_version must be "
            + PROGRAM_ORACLE_EVIDENCE_SCHEMA
        )

    embedding = build_program_oracle_evidence_embedding(
        evidence,
        evidence_path=evidence_path,
        evidence_hash=evidence_hash,
    )
    run_id = _publication_run_id(publication_id)
    publication = _safe_mapping(preflight.get("publication"))
    planned_record = _safe_mapping(preflight.get("planned_record"))
    publication_metadata = {
        **embedding.metadata,
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
            "path": str(source),
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
        source_path=str(evidence_path),
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
            "preflight_path": str(source),
            "preflight_sha256": _sha256_file(source),
            "oracle_evidence_path": str(evidence_path),
            "oracle_evidence_sha256": evidence_hash,
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
    effect = _safe_mapping(payload.get("effect"))
    effect["local_receipt_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload
