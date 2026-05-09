from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from dspx.coordinates import CoordinateStore, ExecutionEmbedding
from dspx.coordinates.embeddings import get_embedding_engine
from dspx.services.program_oracle_secret_policy import (
    ProgramOracleSecretPolicyError,
    build_onepassword_ref_descriptors,
    validate_publisher_assertion_no_secret,
)

ADJUDICATION_TRACE_SCHEMA = "program-adjudication-behavior-trace-v1"
ADJUDICATION_TRACE_PUBLICATION_PREFLIGHT_SCHEMA = (
    "program-adjudication-trace-publication-preflight-v1"
)
ADJUDICATION_TRACE_PUBLICATION_RECEIPT_SCHEMA = (
    "program-adjudication-trace-publication-receipt-v1"
)
ADJUDICATION_TRACE_PUBLICATION_RECORD_SCHEMA = (
    "program-adjudication-trace-shared-publication-v1"
)
ADJUDICATION_TRACE_PUBLICATION_RUN_KIND = "program-adjudication-trace-publication"

EMPIRICAL_LABELS = {
    "adjudication_behavior_trace",
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
REDACTION_STATUSES = ELIGIBLE_REDACTION_STATUSES | {
    "unknown",
    "contains_sensitive_material",
}
ELIGIBLE_RETENTION_CLASSES = {
    "ephemeral_review",
    "retained_behavior_memory",
    "activation_evidence_reference",
}
RETENTION_CLASSES = ELIGIBLE_RETENTION_CLASSES | {"do_not_publish"}
TARGETS = {"shared-postgres", "shared_postgres", "postgres_pgvector"}
_POSTGRES_STORE_NAMES = {"postgres_pgvector", "pgvector"}


class ProgramAdjudicationPublicationError(ValueError):
    """Raised when adjudication trace publication fails closed."""


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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


def _required_text(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProgramAdjudicationPublicationError(f"{field} is required")
    return text


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramAdjudicationPublicationError(
            f"{label} not found: {source}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProgramAdjudicationPublicationError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramAdjudicationPublicationError(
            f"{label} must contain a JSON object: {source}"
        )
    return payload


def _label_class(label: str) -> str:
    if label in EMPIRICAL_LABELS:
        return "empirical"
    if label in AUTHORITY_MIRROR_LABELS:
        return "authority_mirror"
    raise ProgramAdjudicationPublicationError(
        "unknown publication_label: "
        + label
        + "; expected one of "
        + ", ".join(sorted(PUBLICATION_LABELS))
    )


def _validate_redaction_status(value: str) -> None:
    if value not in REDACTION_STATUSES:
        raise ProgramAdjudicationPublicationError(
            "unknown redaction_status: "
            + value
            + "; expected one of "
            + ", ".join(sorted(REDACTION_STATUSES))
        )
    if value not in ELIGIBLE_REDACTION_STATUSES:
        raise ProgramAdjudicationPublicationError(
            "redaction_status is not eligible for shared publication: " + value
        )


def _validate_retention_class(value: str) -> None:
    if value not in RETENTION_CLASSES:
        raise ProgramAdjudicationPublicationError(
            "unknown retention_class: "
            + value
            + "; expected one of "
            + ", ".join(sorted(RETENTION_CLASSES))
        )
    if value == "do_not_publish":
        raise ProgramAdjudicationPublicationError(
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
    return {
        "target": target,
        "target_supported_by_preflight": target in TARGETS,
        "configured_store": store or None,
        "configured_database_url_keys": configured_url_keys,
        "database_url_present": database_url_present,
        "database_url_redacted": "<redacted>" if database_url_present else None,
        "schema": str(os.getenv("DSPX_ORACLE_SCHEMA") or "").strip() or None,
        "connection_attempted": False,
        "shared_write_attempted": False,
    }


def _redact_local_paths(value: object) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text == "path":
                path_text = str(item or "")
                if path_text:
                    redacted["path_sha256"] = _sha256_payload({"path": path_text})
                    redacted["file_name"] = Path(path_text).name
                continue
            redacted[key_text] = _redact_local_paths(item)
        return redacted
    if isinstance(value, list):
        return [_redact_local_paths(item) for item in value]
    return value


def _trace_publication_summary(trace: Mapping[str, Any]) -> dict[str, Any]:
    judging = _safe_mapping(trace.get("judging_behavior"))
    events = [
        str(_safe_mapping(event).get("event"))
        for event in _safe_list(trace.get("trace_events"))
        if _safe_mapping(event).get("event")
    ]
    linked = _safe_mapping(trace.get("linked_artifacts"))
    return {
        "trace_event_names": events,
        "has_program_adjudicator_delegation": bool(
            linked.get("program_adjudicator_delegation")
        ),
        "has_generated_program_adjudicator_decision": bool(
            linked.get("generated_program_adjudicator_decision")
        ),
        "meta_adjudicator_id": judging.get("meta_adjudicator_id"),
        "generated_program_adjudicator_id": judging.get(
            "generated_program_adjudicator_id"
        ),
        "generated_program_decision_outcome": judging.get(
            "generated_program_decision_outcome"
        ),
    }


def _validate_trace(trace: Mapping[str, Any], path: Path) -> None:
    if trace.get("schema_version") != ADJUDICATION_TRACE_SCHEMA:
        raise ProgramAdjudicationPublicationError(
            "adjudication trace schema_version must be " + ADJUDICATION_TRACE_SCHEMA
        )
    if trace.get("status") != "trace_ready_for_publication_preflight":
        raise ProgramAdjudicationPublicationError(
            "adjudication trace status must be trace_ready_for_publication_preflight"
        )
    publication = _safe_mapping(trace.get("oracle_postgres_publication"))
    if publication.get("shared_oracle_write_performed") is not False:
        raise ProgramAdjudicationPublicationError(
            "adjudication trace must not already report shared Oracle writes"
        )
    if publication.get("activation_authority") is not False:
        raise ProgramAdjudicationPublicationError(
            "adjudication trace must not claim activation authority"
        )
    non_authority = _safe_mapping(trace.get("non_authority"))
    for key in (
        "activation_authority",
        "promotion_authority",
        "oracle_authority",
        "governance_authority",
        "external_mutation",
    ):
        if non_authority.get(key) is not False:
            raise ProgramAdjudicationPublicationError(
                f"adjudication trace widens non-authority flag: {key}"
            )
    if not _safe_mapping(trace.get("identity")):
        raise ProgramAdjudicationPublicationError(
            f"adjudication trace identity is required: {path}"
        )


def _expected_publication_id(
    *,
    target: str,
    identity: Mapping[str, Any],
    trace_sha256: str,
    publication_label: str,
    authority_ref: str | None,
    publisher_id: str,
    redaction_status: str,
    retention_class: str,
    publisher_secret_refs: list[dict[str, Any]],
) -> str:
    seed = {
        "schema_version": ADJUDICATION_TRACE_PUBLICATION_PREFLIGHT_SCHEMA,
        "target": target,
        "identity": {key: value for key, value in sorted(identity.items()) if value},
        "trace_sha256": trace_sha256,
        "publication_label": publication_label,
        "authority_ref": authority_ref,
        "publisher_id": publisher_id,
        "redaction_status": redaction_status,
        "retention_class": retention_class,
        "publisher_secret_refs": publisher_secret_refs,
    }
    return "prog-adj-trace-pub-" + _sha256_payload(seed)[:20]


def build_adjudication_trace_publication_preflight(
    *,
    trace_path: Path,
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
    """Build a local preflight packet for shared adjudication-trace publication."""

    resolved_trace_path = trace_path.expanduser().resolve()
    trace = _load_json_object(resolved_trace_path, label="adjudication behavior trace")
    _validate_trace(trace, resolved_trace_path)
    target_name = _required_text(target, field="target")
    if target_name not in TARGETS:
        raise ProgramAdjudicationPublicationError("unsupported target: " + target_name)
    label = _required_text(publication_label, field="publication_label")
    label_class = _label_class(label)
    authority = str(authority_ref or "").strip() or None
    if label_class == "authority_mirror" and authority is None:
        raise ProgramAdjudicationPublicationError(
            "authority_ref is required for authority-mirror publication labels"
        )
    publisher = _required_text(publisher_id, field="publisher_id")
    role = _required_text(publisher_role, field="publisher_role")
    assertion = _required_text(publisher_assertion, field="publisher_assertion")
    try:
        validate_publisher_assertion_no_secret(assertion)
        secret_ref_descriptors = build_onepassword_ref_descriptors(
            publisher_secret_refs
        )
    except ProgramOracleSecretPolicyError as exc:
        raise ProgramAdjudicationPublicationError(str(exc)) from exc
    _validate_redaction_status(redaction_status)
    _validate_retention_class(retention_class)

    trace_sha256 = _sha256_file(resolved_trace_path)
    identity = _safe_mapping(trace.get("identity"))
    publication_id = _expected_publication_id(
        target=target_name,
        identity=identity,
        trace_sha256=trace_sha256,
        publication_label=label,
        authority_ref=authority,
        publisher_id=publisher,
        redaction_status=redaction_status,
        retention_class=retention_class,
        publisher_secret_refs=secret_ref_descriptors,
    )
    publication = {
        "publication_label": label,
        "publication_label_class": label_class,
        "authority_ref_required": label_class == "authority_mirror",
        "authority_ref": authority,
        "authority_ref_kind": "opaque_reference_only" if authority else None,
        "publisher_id": publisher,
        "publisher_role": role,
        "publisher_assertion": assertion,
        "publisher_identity_kind": "declared_not_authenticated",
        "publisher_secret_refs": secret_ref_descriptors,
        "redaction_status": redaction_status,
        "retention_class": retention_class,
    }
    planned_record = {
        **publication,
        "adjudication_trace_sha256": trace_sha256,
        "source_schema_version": trace.get("schema_version"),
        "trace_summary": _trace_publication_summary(trace),
        "non_authority": {
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "governance_authority": False,
            "external_mutation": False,
            "activation_authority": False,
        },
    }
    return {
        "schema_version": ADJUDICATION_TRACE_PUBLICATION_PREFLIGHT_SCHEMA,
        "status": "ready_not_published",
        "publication_id": publication_id,
        "target": _redacted_backend_posture(target_name),
        "identity": identity,
        "created_from": {
            "adjudication_trace_path": str(resolved_trace_path),
            "adjudication_trace_schema_version": trace.get("schema_version"),
        },
        "artifact_hashes": {
            "adjudication_trace_sha256": trace_sha256,
        },
        "publication": publication,
        "preflight": {
            "trace_valid": True,
            "trace_non_authority_valid": True,
            "publication_label_valid": True,
            "authority_ref_requirement_satisfied": True,
            "publisher_fields_present": True,
            "redaction_status_eligible": True,
            "retention_class_eligible": True,
            "ready_for_shared_publication": True,
            "blocking_reasons": [],
        },
        "planned_record": planned_record,
        "idempotency": {
            "same_inputs_same_publication_id": True,
            "publication_id_seed": "target+identity+trace_hash+publication_fields",
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
            "activation_state_changed": False,
        },
        "non_authority": {
            "preflight_only": True,
            "oracle_authority": False,
            "promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
            "winner_selection": False,
            "automatic_promotion": False,
        },
    }


def write_adjudication_trace_publication_preflight(
    preflight: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if (
        preflight.get("schema_version")
        != ADJUDICATION_TRACE_PUBLICATION_PREFLIGHT_SCHEMA
    ):
        raise ProgramAdjudicationPublicationError(
            "adjudication trace publication preflight schema_version is invalid"
        )
    target = out_path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(preflight)
    effect = _safe_mapping(payload.get("effect"))
    effect["local_preflight_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload


def _validate_secret_ref_descriptors(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ProgramAdjudicationPublicationError(
            "publication.publisher_secret_refs must be a list"
        )
    descriptors: list[dict[str, Any]] = []
    for ref in value:
        if not isinstance(ref, Mapping):
            raise ProgramAdjudicationPublicationError(
                "publication.publisher_secret_refs must contain objects"
            )
        descriptor = {str(key): item for key, item in ref.items()}
        if set(descriptor) - {
            "provider",
            "ref_kind",
            "ref_redacted",
            "ref_sha256",
            "sdk_resolution_attempted",
            "secret_value_persisted",
        }:
            raise ProgramAdjudicationPublicationError(
                "publication publisher_secret_refs must not contain resolved values"
            )
        if (
            descriptor.get("provider") != "1password"
            or descriptor.get("ref_kind") != "op_uri"
            or descriptor.get("sdk_resolution_attempted") is not False
            or descriptor.get("secret_value_persisted") is not False
            or not isinstance(descriptor.get("ref_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", str(descriptor.get("ref_sha256")))
            or not str(descriptor.get("ref_redacted") or "").startswith(
                "op://<redacted>/<redacted>/"
            )
        ):
            raise ProgramAdjudicationPublicationError(
                "publication publisher_secret_refs must be redacted 1Password refs"
            )
        descriptors.append(descriptor)
    return descriptors


def _ensure_preflight_publishable(preflight: Mapping[str, Any]) -> None:
    if (
        preflight.get("schema_version")
        != ADJUDICATION_TRACE_PUBLICATION_PREFLIGHT_SCHEMA
    ):
        raise ProgramAdjudicationPublicationError(
            "preflight schema_version must be "
            + ADJUDICATION_TRACE_PUBLICATION_PREFLIGHT_SCHEMA
        )
    if preflight.get("status") != "ready_not_published":
        raise ProgramAdjudicationPublicationError(
            "preflight status must be ready_not_published before shared publication"
        )
    effect = _safe_mapping(preflight.get("effect"))
    if effect.get("shared_oracle_mutated") is not False:
        raise ProgramAdjudicationPublicationError(
            "preflight must prove shared_oracle_mutated is false"
        )
    checks = _safe_mapping(preflight.get("preflight"))
    required_true = (
        "trace_valid",
        "trace_non_authority_valid",
        "publication_label_valid",
        "authority_ref_requirement_satisfied",
        "publisher_fields_present",
        "redaction_status_eligible",
        "retention_class_eligible",
        "ready_for_shared_publication",
    )
    failed = [key for key in required_true if checks.get(key) is not True]
    if failed:
        raise ProgramAdjudicationPublicationError(
            "preflight checks are not publishable: " + ", ".join(failed)
        )
    if checks.get("blocking_reasons") != []:
        raise ProgramAdjudicationPublicationError(
            "preflight blocking_reasons must be empty"
        )


def _validate_preflight_hashes(preflight: Mapping[str, Any]) -> tuple[Path, str]:
    created_from = _safe_mapping(preflight.get("created_from"))
    artifact_hashes = _safe_mapping(preflight.get("artifact_hashes"))
    trace_path = (
        Path(
            _required_text(
                created_from.get("adjudication_trace_path"),
                field="created_from.adjudication_trace_path",
            )
        )
        .expanduser()
        .resolve()
    )
    expected_hash = _required_text(
        artifact_hashes.get("adjudication_trace_sha256"),
        field="artifact_hashes.adjudication_trace_sha256",
    )
    actual_hash = _sha256_file(trace_path)
    if actual_hash != expected_hash:
        raise ProgramAdjudicationPublicationError(
            "adjudication trace hash no longer matches preflight packet"
        )
    return trace_path, actual_hash


def _publication_run_id(publication_id: str) -> str:
    return f"program-adjudication-trace-publication:{publication_id}"


def _redacted_store_posture(
    store: CoordinateStore, target: Mapping[str, Any]
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "target": target.get("target"),
        "backend": str(getattr(store, "backend_name", type(store).__name__)),
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
    return payload


def _open_configured_shared_store() -> CoordinateStore:
    target_store = str(os.getenv("DSPX_ORACLE_STORE") or "").strip().lower()
    if target_store not in _POSTGRES_STORE_NAMES:
        raise ProgramAdjudicationPublicationError(
            "explicit adjudication trace publication requires a configured and available "
            "Postgres/pgvector Oracle backend: set DSPX_ORACLE_STORE=postgres_pgvector"
        )
    database_url = str(
        os.getenv("DSPX_ORACLE_DATABASE_URL")
        or os.getenv("DSPX_ORACLE_POSTGRES_URL")
        or ""
    ).strip()
    if not database_url:
        raise ProgramAdjudicationPublicationError(
            "explicit adjudication trace publication requires a configured and available "
            "Postgres/pgvector Oracle backend: set DSPX_ORACLE_DATABASE_URL or "
            "DSPX_ORACLE_POSTGRES_URL"
        )
    try:
        from dspx.coordinates.postgres_store import PostgresPgvectorCoordinateStore

        return PostgresPgvectorCoordinateStore(database_url=database_url)
    except Exception as exc:
        raise ProgramAdjudicationPublicationError(
            "explicit adjudication trace publication requires a configured and available "
            "Postgres/pgvector Oracle backend"
        ) from exc


def _trace_embedding(
    *,
    trace: Mapping[str, Any],
    trace_path: Path,
    trace_hash: str,
    publication_id: str,
    publication: Mapping[str, Any],
    planned_record: Mapping[str, Any],
    preflight_path: Path,
) -> ExecutionEmbedding:
    identity = _safe_mapping(trace.get("identity"))
    judging = _safe_mapping(trace.get("judging_behavior"))
    events = _safe_list(trace.get("trace_events"))
    linked_artifacts = _redact_local_paths(_safe_mapping(trace.get("linked_artifacts")))
    run_id = _publication_run_id(publication_id)
    engine = get_embedding_engine()
    return engine.embed_execution(
        run_id=run_id,
        input_text=json.dumps(identity, sort_keys=True),
        output_text=json.dumps(judging, sort_keys=True),
        config_text="\n".join(
            [
                f"schema_version={ADJUDICATION_TRACE_PUBLICATION_RECORD_SCHEMA}",
                f"source_schema_version={trace.get('schema_version')}",
                f"publication_label={publication.get('publication_label')}",
                f"retention_class={publication.get('retention_class')}",
                f"non_authority={json.dumps(planned_record.get('non_authority'), sort_keys=True)}",
            ]
        ),
        run_kind=ADJUDICATION_TRACE_PUBLICATION_RUN_KIND,
        provider="program-meta-adjudication",
        template_version=ADJUDICATION_TRACE_PUBLICATION_RECORD_SCHEMA,
        source_path=None,
        metadata={
            "schema_version": ADJUDICATION_TRACE_PUBLICATION_RECORD_SCHEMA,
            "source_schema_version": trace.get("schema_version"),
            "publication_id": publication_id,
            "publication": dict(publication),
            "planned_record": dict(planned_record),
            "publication_label": publication.get("publication_label"),
            "publication_label_class": publication.get("publication_label_class"),
            "authority_ref": publication.get("authority_ref"),
            "retention_class": publication.get("retention_class"),
            "redaction_status": publication.get("redaction_status"),
            "publisher_id": publication.get("publisher_id"),
            "publisher_role": publication.get("publisher_role"),
            "preflight": {
                "file_name": preflight_path.name,
                "sha256": _sha256_file(preflight_path),
                "schema_version": ADJUDICATION_TRACE_PUBLICATION_PREFLIGHT_SCHEMA,
            },
            "artifact_hashes": {"adjudication_trace_sha256": trace_hash},
            "identity": identity,
            "judging_behavior": judging,
            "trace_events": events,
            "linked_artifact_refs": linked_artifacts,
            "non_authority": _safe_mapping(planned_record.get("non_authority")),
            "local_paths_omitted_from_shared_record": True,
            "source_path_hash": _sha256_payload({"path": str(trace_path)}),
        },
    )


def publish_adjudication_trace_preflight(
    *, preflight_path: Path, store: CoordinateStore | None = None
) -> dict[str, Any]:
    """Publish a preflighted adjudication trace to the shared Oracle store."""

    source = preflight_path.expanduser().resolve()
    preflight = _load_json_object(source, label="adjudication trace preflight")
    _ensure_preflight_publishable(preflight)
    target = _safe_mapping(preflight.get("target"))
    target_name = _required_text(target.get("target"), field="target.target")
    if target_name not in TARGETS:
        raise ProgramAdjudicationPublicationError("preflight target is not supported")
    trace_path, trace_hash = _validate_preflight_hashes(preflight)
    trace = _load_json_object(trace_path, label="adjudication behavior trace")
    _validate_trace(trace, trace_path)
    publication = _safe_mapping(preflight.get("publication"))
    planned_record = _safe_mapping(preflight.get("planned_record"))
    secret_refs = _validate_secret_ref_descriptors(
        publication.get("publisher_secret_refs")
    )
    if planned_record.get("publisher_secret_refs") != secret_refs:
        raise ProgramAdjudicationPublicationError(
            "planned_record publisher_secret_refs do not match publication"
        )
    label = _required_text(
        publication.get("publication_label"), field="publication.publication_label"
    )
    expected_label_class = _label_class(label)
    if publication.get("publication_label_class") != expected_label_class:
        raise ProgramAdjudicationPublicationError(
            "publication_label_class does not match publication_label"
        )
    authority_ref = str(publication.get("authority_ref") or "").strip() or None
    publisher_id = _required_text(
        publication.get("publisher_id"), field="publication.publisher_id"
    )
    redaction_status = _required_text(
        publication.get("redaction_status"), field="publication.redaction_status"
    )
    retention_class = _required_text(
        publication.get("retention_class"), field="publication.retention_class"
    )
    publication_id = _expected_publication_id(
        target=target_name,
        identity=_safe_mapping(preflight.get("identity")),
        trace_sha256=trace_hash,
        publication_label=label,
        authority_ref=authority_ref,
        publisher_id=publisher_id,
        redaction_status=redaction_status,
        retention_class=retention_class,
        publisher_secret_refs=secret_refs,
    )
    if preflight.get("publication_id") != publication_id:
        raise ProgramAdjudicationPublicationError(
            "publication_id does not match recomputed idempotency key"
        )
    embedding = _trace_embedding(
        trace=trace,
        trace_path=trace_path,
        trace_hash=trace_hash,
        publication_id=publication_id,
        publication=publication,
        planned_record=planned_record,
        preflight_path=source,
    )
    shared_store = store or _open_configured_shared_store()
    try:
        upserted = shared_store.upsert(embedding)
    except Exception as exc:
        raise ProgramAdjudicationPublicationError(
            "shared Oracle adjudication trace upsert failed"
        ) from exc
    if upserted is not True:
        raise ProgramAdjudicationPublicationError(
            "shared Oracle adjudication trace upsert failed"
        )
    return {
        "schema_version": ADJUDICATION_TRACE_PUBLICATION_RECEIPT_SCHEMA,
        "status": "published",
        "publication_id": publication_id,
        "run_id": _publication_run_id(publication_id),
        "target": _redacted_store_posture(shared_store, target),
        "source": {
            "preflight_file": source.name,
            "preflight_sha256": _sha256_file(source),
            "adjudication_trace_file": trace_path.name,
            "adjudication_trace_sha256": trace_hash,
            "local_paths_omitted_from_shared_record": True,
        },
        "identity": _safe_mapping(preflight.get("identity")),
        "publication": publication,
        "record": {
            "schema_version": ADJUDICATION_TRACE_PUBLICATION_RECORD_SCHEMA,
            "run_kind": ADJUDICATION_TRACE_PUBLICATION_RUN_KIND,
            "template_version": ADJUDICATION_TRACE_PUBLICATION_RECORD_SCHEMA,
            "provider": "program-meta-adjudication",
            "publication_label": publication.get("publication_label"),
            "publication_label_class": publication.get("publication_label_class"),
            "retention_class": publication.get("retention_class"),
            "redaction_status": publication.get("redaction_status"),
            "authority_ref": publication.get("authority_ref"),
            "non_authority": _safe_mapping(planned_record.get("non_authority")),
        },
        "idempotency": {
            "publication_id": publication_id,
            "run_id": _publication_run_id(publication_id),
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
            "activation_state_changed": False,
        },
        "non_authority": {
            "oracle_authority": False,
            "promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
            "agent_kernel_mutation": False,
            "winner_selection": False,
            "automatic_promotion": False,
        },
        "notes": [
            "This receipt records an explicit shared Oracle empirical adjudication-trace publication.",
            "Oracle remains empirical memory and does not approve promotion or activation.",
            "Authority-mirror labels mirror the supplied authority_ref only.",
        ],
    }


def write_adjudication_trace_publication_receipt(
    receipt: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if receipt.get("schema_version") != ADJUDICATION_TRACE_PUBLICATION_RECEIPT_SCHEMA:
        raise ProgramAdjudicationPublicationError(
            "adjudication trace publication receipt schema_version is invalid"
        )
    target = out_path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(receipt)
    effect = _safe_mapping(payload.get("effect"))
    effect["local_receipt_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload
