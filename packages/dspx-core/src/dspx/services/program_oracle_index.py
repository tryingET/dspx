from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from dspx.coordinates import (
    EmbeddingEngine,
    ExecutionEmbedding,
    get_embedding_engine,
    open_coordinate_store,
)

PROGRAM_ORACLE_EVIDENCE_SCHEMA = "program-oracle-evidence-v1"
PROGRAM_ORACLE_EVIDENCE_KIND = "program_execution_episode"
PROGRAM_ORACLE_AUTHORITY = "oracle_readability_only_non_authoritative"
PROGRAM_ORACLE_RUN_KIND = "program-oracle-evidence"
PROGRAM_ORACLE_PROVIDER = "program-gen"

_REQUIRED_FALSE_NON_AUTHORITY_FLAGS = (
    "oracle_ranking",
    "oracle_pruning",
    "oracle_promotion",
    "governance_authority",
    "external_mutation",
)


def iter_program_oracle_evidence_files(
    path: Path, *, limit: int | None = None
) -> Iterable[Path]:
    """Yield candidate program oracle evidence files below a path."""

    root = path.expanduser().resolve()
    if root.is_file():
        candidates = [root] if root.name == "oracle_evidence.json" else []
    elif root.exists():
        candidates = sorted(root.rglob("oracle_evidence.json"))
    else:
        candidates = []
    if limit is not None and limit >= 0:
        candidates = candidates[:limit]
    yield from candidates


def load_program_oracle_evidence(path: Path) -> dict[str, Any] | None:
    """Load a program-oracle-evidence-v1 JSON object, or None for other schemas."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("program Oracle evidence must be a JSON object")
    if payload.get("schema_version") != PROGRAM_ORACLE_EVIDENCE_SCHEMA:
        return None
    return payload


def validate_program_oracle_evidence_non_authority(payload: Mapping[str, Any]) -> None:
    """Fail unless the evidence explicitly preserves the non-authority boundary."""

    if payload.get("evidence_kind") != PROGRAM_ORACLE_EVIDENCE_KIND:
        raise ValueError("program Oracle evidence has unexpected evidence_kind")
    if payload.get("authority") != PROGRAM_ORACLE_AUTHORITY:
        raise ValueError(
            "program Oracle evidence authority is not readability-only non-authoritative"
        )
    non_authority = payload.get("non_authority")
    if not isinstance(non_authority, Mapping):
        raise ValueError("program Oracle evidence missing non_authority object")
    invalid = [
        key
        for key in _REQUIRED_FALSE_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid:
        raise ValueError(
            "program Oracle evidence non_authority flags must be false: "
            + ", ".join(invalid)
        )


def _json_compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = payload.get("identity")
    if not isinstance(raw, Mapping):
        raise ValueError("program Oracle evidence missing identity object")
    identity = dict(raw)
    if not identity.get("receipt_bundle_id") and not identity.get("episode_id"):
        raise ValueError(
            "program Oracle evidence identity requires receipt_bundle_id or episode_id"
        )
    return identity


def _run_id(identity: Mapping[str, Any]) -> str:
    receipt_bundle_id = str(identity.get("receipt_bundle_id") or "").strip()
    if receipt_bundle_id:
        return f"program-oracle-evidence:{receipt_bundle_id}"
    return f"program-oracle-evidence:{identity['episode_id']}"


def _mapping_or_empty(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _behavior_output_text(behavior: Mapping[str, Any]) -> str:
    summary = _mapping_or_empty(behavior.get("summary"))
    statuses = _mapping_or_empty(behavior.get("statuses"))
    raw_failure_modes = behavior.get("failure_modes")
    failure_modes = raw_failure_modes if isinstance(raw_failure_modes, list) else []
    parts = [
        f"behavior_status={summary.get('status', 'unknown')}",
        f"summary={_json_compact(summary)}",
        f"statuses={_json_compact(statuses)}",
    ]
    if failure_modes:
        compact_failures = []
        for raw_failure in failure_modes[:10]:
            if isinstance(raw_failure, Mapping):
                compact_failures.append(
                    {
                        "index": raw_failure.get("index"),
                        "status": raw_failure.get("status"),
                        "signals": raw_failure.get("signals") or [],
                        "mismatched_outputs": raw_failure.get("mismatched_outputs")
                        or [],
                        "missing_observed_outputs": raw_failure.get(
                            "missing_observed_outputs"
                        )
                        or [],
                    }
                )
        parts.append(f"failure_modes={_json_compact(compact_failures)}")
    return "\n".join(parts)


def _config_text(payload: Mapping[str, Any]) -> str:
    oracle_facets = _mapping_or_empty(payload.get("oracle_facets"))
    intent = _mapping_or_empty(payload.get("intent"))
    io = _mapping_or_empty(payload.get("io"))
    non_authority = _mapping_or_empty(payload.get("non_authority"))
    return "\n".join(
        [
            f"schema_version={payload.get('schema_version')}",
            f"evidence_kind={payload.get('evidence_kind')}",
            f"task_type={oracle_facets.get('task_type') or intent.get('task_type')}",
            f"metric={oracle_facets.get('metric') or intent.get('metric')}",
            f"input_fields={_json_compact(io.get('inputs') or oracle_facets.get('input_fields') or [])}",
            f"output_fields={_json_compact(io.get('outputs') or oracle_facets.get('output_fields') or [])}",
            f"authority={payload.get('authority')}",
            f"non_authority={_json_compact(non_authority)}",
        ]
    )


def build_program_oracle_evidence_embedding(
    payload: Mapping[str, Any],
    *,
    evidence_path: Path,
    evidence_hash: str,
    engine: EmbeddingEngine | None = None,
) -> ExecutionEmbedding:
    """Map program-oracle-evidence-v1 into the existing ExecutionEmbedding contract."""

    validate_program_oracle_evidence_non_authority(payload)
    identity = _identity(payload)
    behavior = _mapping_or_empty(payload.get("behavior"))
    oracle_text = str(payload.get("oracle_text") or "").strip()
    if not oracle_text:
        raise ValueError("program Oracle evidence missing oracle_text")
    metadata = {
        "identity": identity,
        "oracle_facets": _mapping_or_empty(payload.get("oracle_facets")),
        "behavior": behavior,
        "source_artifacts": list(payload.get("source_artifacts") or []),
        "non_authority": _mapping_or_empty(payload.get("non_authority")),
        "authority": payload.get("authority"),
        "schema_version": payload.get("schema_version"),
        "evidence_kind": payload.get("evidence_kind"),
        "evidence_path": str(evidence_path),
        "evidence_hash": evidence_hash,
        "intent": _mapping_or_empty(payload.get("intent")),
        "io": _mapping_or_empty(payload.get("io")),
    }
    embedding_engine = engine or get_embedding_engine()
    return embedding_engine.embed_execution(
        run_id=_run_id(identity),
        input_text=oracle_text,
        output_text=_behavior_output_text(behavior),
        config_text=_config_text(payload),
        run_kind=PROGRAM_ORACLE_RUN_KIND,
        provider=PROGRAM_ORACLE_PROVIDER,
        template_version=PROGRAM_ORACLE_EVIDENCE_SCHEMA,
        source_path=str(evidence_path),
        metadata=metadata,
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index_program_oracle_evidence_path(
    path: Path,
    *,
    index_path: Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Index program-gen Oracle-readable evidence into a local CoordinateIndex.

    Program evidence indexing is candidate-local by contract. Shared publication
    has its own explicit publish path, so ambient ``DSPX_ORACLE_STORE`` must not
    redirect this local indexing helper into a shared backend.
    """

    engine = get_embedding_engine()
    index = open_coordinate_store(store="sqlite", db_path=index_path)
    scanned = 0
    indexed = 0
    skipped = 0
    errors = 0
    error_details: list[dict[str, Any]] = []

    for evidence_file in iter_program_oracle_evidence_files(path, limit=limit):
        scanned += 1
        try:
            evidence = load_program_oracle_evidence(evidence_file)
            if evidence is None:
                skipped += 1
                continue
            evidence_hash = _sha256_file(evidence_file)
            embedding = build_program_oracle_evidence_embedding(
                evidence,
                evidence_path=evidence_file,
                evidence_hash=evidence_hash,
                engine=engine,
            )
            if index.upsert(embedding):
                indexed += 1
            else:
                errors += 1
                error_details.append(
                    {
                        "path": str(evidence_file),
                        "error": "coordinate index upsert failed",
                    }
                )
        except Exception as exc:
            errors += 1
            error_details.append(
                {
                    "path": str(evidence_file),
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
            )

    resolved_index_path = getattr(index, "db_path", index_path or "")

    return {
        "scanned": scanned,
        "indexed": indexed,
        "skipped": skipped,
        "errors": errors,
        "error_details": error_details,
        "index_path": str(resolved_index_path),
        "index_stats": index.stats(),
        "backend": engine.backend,
        "dimension": engine.dimension,
        "non_authority_confirmed": errors == 0,
    }
