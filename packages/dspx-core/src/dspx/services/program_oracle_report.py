# summary: "Loads indexed program Oracle evidence and builds deterministic non-authoritative behavior reports and interpretations."
# read_when:
#   - "Changing program Oracle report records, aggregate counters, interpretation, or local index loading."
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from dspx.coordinates import ExecutionEmbedding
from dspx.coordinates.storage import get_default_index_path, open_coordinate_store
from dspx.services.program_oracle_index import (
    PROGRAM_ORACLE_EVIDENCE_KIND,
    PROGRAM_ORACLE_EVIDENCE_SCHEMA,
    PROGRAM_ORACLE_RUN_KIND,
)
from dspx.services.program_quality_evaluation import (
    normalize_declared_quality_behavior_status,
)

PROGRAM_ORACLE_REPORT_SCHEMA = "program-oracle-evidence-report-v1"
KNOWN_BEHAVIOR_STATUSES = (
    "passed",
    "failed",
    "error",
    "degraded",
    "executed",
    "unknown",
)


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _embedding_backend_identity(
    metadata: Mapping[str, Any], *, expected_dimension: int
) -> dict[str, Any]:
    raw = _safe_mapping(metadata.get("embedding_backend"))
    required = {
        "schema_version",
        "effective_backend",
        "model",
        "semantic_class",
        "semantic_claim",
        "production_semantic_claim_allowed",
    }
    backend = raw.get("effective_backend")
    dimension = raw.get("dimension")
    common_valid = (
        raw.get("schema_version") == "dspx-embedding-backend-identity-v1"
        and required.issubset(raw)
        and isinstance(dimension, int)
        and not isinstance(dimension, bool)
        and dimension > 0
        and dimension == expected_dimension
        and raw.get("production_semantic_claim_allowed") is False
    )
    mock_valid = (
        backend == "mock"
        and raw.get("model") == "sha256-deterministic-test-double-v1"
        and raw.get("semantic_class") == "deterministic_test_double"
        and raw.get("semantic_claim") == "plumbing_only_not_production_semantics"
    )
    model_valid = (
        backend == "sentence-transformers"
        and isinstance(raw.get("model"), str)
        and bool(str(raw.get("model")).strip())
        and raw.get("semantic_class") == "model_backed_semantic_embedding"
        and raw.get("semantic_claim")
        == "model_backed_semantics_not_production_validated"
    )
    if common_valid and (mock_valid or model_valid):
        return raw
    return {
        "schema_version": "dspx-embedding-backend-identity-unknown",
        "effective_backend": "unknown",
        "model": None,
        "dimension": None,
        "semantic_class": "unknown",
        "semantic_claim": "unknown_legacy_or_invalid_backend_identity",
        "production_semantic_claim_allowed": False,
    }


def _embedding_backend_posture(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "status": "no_records",
            "semantic_claim": "no_embedding_evidence",
            "production_semantic_claim_allowed": False,
        }
    identities = {
        (
            str(identity.get("effective_backend") or "unknown"),
            str(identity.get("model") or ""),
            str(identity.get("dimension") or "unknown"),
            str(identity.get("semantic_claim") or "unknown"),
        )
        for record in records
        for identity in [_safe_mapping(record.get("embedding_backend"))]
    }
    if any(identity[0] == "unknown" for identity in identities):
        status = "unknown_backend_identity_fail_closed"
        semantic_claim = "unknown_legacy_or_invalid_backend_identity"
    elif len(identities) != 1:
        status = "mixed_backend_identity_fail_closed"
        semantic_claim = "mixed_embedding_semantics_not_comparable"
    else:
        backend, _, _, claim = next(iter(identities))
        if backend == "mock":
            status = "explicit_mock_plumbing_only"
        else:
            status = "model_backed_not_production_validated"
        semantic_claim = claim
    return {
        "status": status,
        "semantic_claim": semantic_claim,
        "production_semantic_claim_allowed": False,
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _normalize_behavior_status(value: object) -> str:
    text = str(value or "unknown").strip().lower() or "unknown"
    quality_status = normalize_declared_quality_behavior_status(text)
    if quality_status is not None:
        return quality_status
    if text.startswith("degraded"):
        return "degraded"
    if text in KNOWN_BEHAVIOR_STATUSES:
        return text
    return "unknown"


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def _status_counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {status: int(counter.get(status, 0)) for status in KNOWN_BEHAVIOR_STATUSES}


def _metadata_has_expected_shape(metadata: Mapping[str, Any]) -> bool:
    return (
        metadata.get("schema_version") == PROGRAM_ORACLE_EVIDENCE_SCHEMA
        and metadata.get("evidence_kind") == PROGRAM_ORACLE_EVIDENCE_KIND
        and isinstance(metadata.get("identity"), Mapping)
        and isinstance(metadata.get("oracle_facets"), Mapping)
        and isinstance(metadata.get("behavior"), Mapping)
    )


def _index_path_for_report(index_path: Path | None) -> Path:
    return (
        index_path.expanduser() if index_path is not None else get_default_index_path()
    )


def load_program_oracle_evidence_embeddings(
    index_path: Path | None = None,
    *,
    limit: int = 1000,
) -> list[ExecutionEmbedding]:
    """Load valid program-oracle-evidence records from a local CoordinateIndex.

    Missing indexes are treated as empty so report generation stays read-oriented and
    does not create a default repo index just to say there is no program evidence.
    """

    db_path = _index_path_for_report(index_path)
    if not db_path.exists():
        return []
    index = open_coordinate_store(store="sqlite", db_path=db_path)
    embeddings = index.list_all(run_kind=PROGRAM_ORACLE_RUN_KIND, limit=limit)
    return [emb for emb in embeddings if _metadata_has_expected_shape(emb.metadata)]


def _failure_signals(behavior: Mapping[str, Any]) -> list[str]:
    raw_failure_modes = behavior.get("failure_modes")
    if not isinstance(raw_failure_modes, list):
        return []
    signals: list[str] = []
    for raw_failure in raw_failure_modes:
        if not isinstance(raw_failure, Mapping):
            continue
        for signal in _string_list(raw_failure.get("signals")):
            if signal not in signals:
                signals.append(signal)
    return signals


def _source_artifact_kinds(metadata: Mapping[str, Any]) -> list[str]:
    raw_artifacts = metadata.get("source_artifacts")
    if not isinstance(raw_artifacts, list):
        return []
    kinds = {
        str(item.get("kind"))
        for item in raw_artifacts
        if isinstance(item, Mapping) and str(item.get("kind") or "").strip()
    }
    return sorted(kinds)


def _behavior_source_kinds(behavior: Mapping[str, Any]) -> list[str]:
    raw_sources = behavior.get("evaluation_sources")
    if not isinstance(raw_sources, list):
        return []
    kinds = {
        str(source.get("source_kind"))
        for source in raw_sources
        if isinstance(source, Mapping) and str(source.get("source_kind") or "").strip()
    }
    return sorted(kinds)


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _runtime_trace_record(metadata: Mapping[str, Any]) -> dict[str, Any]:
    runtime_traces = _safe_mapping(metadata.get("runtime_traces"))
    coverage = _safe_mapping(runtime_traces.get("coverage"))
    return {
        "status": str(runtime_traces.get("status") or "unknown"),
        "path": runtime_traces.get("path"),
        "content_hash": runtime_traces.get("content_hash"),
        "module_call_count": _safe_int(runtime_traces.get("module_call_count")),
        "final_output_trace_count": _safe_int(
            runtime_traces.get("final_output_trace_count")
        ),
        "coverage_status": str(coverage.get("status") or "unknown"),
        "source_record_coverage_status": str(
            coverage.get("source_record_coverage_status") or "unknown"
        ),
        "missing_module_count": _safe_int(coverage.get("missing_module_count")),
        "missing_final_output_field_count": _safe_int(
            coverage.get("missing_final_output_field_count")
        ),
    }


def _record_from_embedding(embedding: ExecutionEmbedding) -> dict[str, Any]:
    metadata = embedding.metadata
    facets = _safe_mapping(metadata.get("oracle_facets"))
    behavior = _safe_mapping(metadata.get("behavior"))
    summary = _safe_mapping(behavior.get("summary"))
    identity = _safe_mapping(metadata.get("identity"))
    input_fields = _string_list(facets.get("input_fields"))
    if not input_fields:
        input_fields = _string_list(_safe_mapping(metadata.get("io")).get("inputs"))
    output_fields = _string_list(facets.get("output_fields"))
    if not output_fields:
        output_fields = _string_list(_safe_mapping(metadata.get("io")).get("outputs"))
    source_kinds = _string_list(facets.get("behavior_source_kinds"))
    if not source_kinds:
        source_kinds = _behavior_source_kinds(behavior)
    return {
        "run_id": embedding.run_id,
        "embedding_backend": _embedding_backend_identity(
            metadata, expected_dimension=embedding.dimension
        ),
        "identity": identity,
        "behavior_status": _normalize_behavior_status(
            summary.get("status") or facets.get("behavior_status")
        ),
        "task_type": str(facets.get("task_type") or "unknown"),
        "metric": str(facets.get("metric") or "unknown"),
        "input_fields": input_fields,
        "output_fields": output_fields,
        "failure_signals": _failure_signals(behavior),
        "evidence_path": metadata.get("evidence_path") or embedding.source_path,
        "evidence_hash": metadata.get("evidence_hash"),
        "source_artifact_kinds": _source_artifact_kinds(metadata),
        "behavior_source_kinds": source_kinds,
        "runtime_traces": _runtime_trace_record(metadata),
        "evidence_source_count": _safe_mapping(behavior.get("evidence_summary")).get(
            "source_count", facets.get("evidence_source_count")
        ),
        "total_evaluation_count": _safe_mapping(behavior.get("evidence_summary")).get(
            "total", facets.get("total_evaluation_count")
        ),
    }


def summarize_program_oracle_evidence(
    embeddings: list[ExecutionEmbedding],
) -> dict[str, Any]:
    """Summarize indexed program Oracle evidence without making decisions."""

    records = [_record_from_embedding(embedding) for embedding in embeddings]
    behavior_status_counts: Counter[str] = Counter()
    task_type_counts: Counter[str] = Counter()
    metric_counts: Counter[str] = Counter()
    input_field_counts: Counter[str] = Counter()
    output_field_counts: Counter[str] = Counter()
    failure_signal_counts: Counter[str] = Counter()
    behavior_source_kind_counts: Counter[str] = Counter()
    runtime_trace_status_counts: Counter[str] = Counter()
    runtime_trace_coverage_status_counts: Counter[str] = Counter()
    runtime_trace_source_record_coverage_status_counts: Counter[str] = Counter()
    total_evaluation_count = 0
    evidence_source_count = 0
    runtime_trace_module_call_count = 0
    runtime_trace_final_output_trace_count = 0
    embedding_backend_counts: Counter[str] = Counter()
    embedding_semantic_claim_counts: Counter[str] = Counter()

    for record in records:
        embedding_backend = _safe_mapping(record.get("embedding_backend"))
        embedding_backend_counts[
            str(embedding_backend.get("effective_backend") or "unknown")
        ] += 1
        embedding_semantic_claim_counts[
            str(embedding_backend.get("semantic_claim") or "unknown")
        ] += 1
        behavior_status_counts[str(record["behavior_status"])] += 1
        task_type_counts[str(record["task_type"])] += 1
        metric_counts[str(record["metric"])] += 1
        input_field_counts.update(record["input_fields"])
        output_field_counts.update(record["output_fields"])
        failure_signal_counts.update(record["failure_signals"])
        behavior_source_kind_counts.update(record["behavior_source_kinds"])
        runtime_traces = _safe_mapping(record.get("runtime_traces"))
        runtime_trace_status_counts[str(runtime_traces.get("status") or "unknown")] += 1
        runtime_trace_coverage_status_counts[
            str(runtime_traces.get("coverage_status") or "unknown")
        ] += 1
        runtime_trace_source_record_coverage_status_counts[
            str(runtime_traces.get("source_record_coverage_status") or "unknown")
        ] += 1
        total_evaluation_count += int(record.get("total_evaluation_count") or 0)
        evidence_source_count += int(record.get("evidence_source_count") or 0)
        runtime_trace_module_call_count += _safe_int(
            runtime_traces.get("module_call_count")
        )
        runtime_trace_final_output_trace_count += _safe_int(
            runtime_traces.get("final_output_trace_count")
        )

    return {
        "total_records": len(records),
        "behavior_status_counts": _status_counter_payload(behavior_status_counts),
        "task_type_counts": _counter_payload(task_type_counts),
        "metric_counts": _counter_payload(metric_counts),
        "input_field_counts": _counter_payload(input_field_counts),
        "output_field_counts": _counter_payload(output_field_counts),
        "failure_signal_counts": _counter_payload(failure_signal_counts),
        "behavior_source_kind_counts": _counter_payload(behavior_source_kind_counts),
        "runtime_trace_status_counts": _counter_payload(runtime_trace_status_counts),
        "runtime_trace_coverage_status_counts": _counter_payload(
            runtime_trace_coverage_status_counts
        ),
        "runtime_trace_source_record_coverage_status_counts": _counter_payload(
            runtime_trace_source_record_coverage_status_counts
        ),
        "runtime_trace_module_call_count": runtime_trace_module_call_count,
        "runtime_trace_final_output_trace_count": runtime_trace_final_output_trace_count,
        "embedding_backend_counts": _counter_payload(embedding_backend_counts),
        "embedding_semantic_claim_counts": _counter_payload(
            embedding_semantic_claim_counts
        ),
        "embedding_backend_posture": _embedding_backend_posture(records),
        "evidence_source_count": evidence_source_count,
        "total_evaluation_count": total_evaluation_count,
        "records": records,
    }


def _top(counter_payload: Mapping[str, Any]) -> tuple[str, int] | None:
    items = [(str(key), int(value)) for key, value in counter_payload.items()]
    if not items:
        return None
    return sorted(items, key=lambda item: (-item[1], item[0]))[0]


def _build_interpretation(summary: Mapping[str, Any]) -> dict[str, Any]:
    total = int(summary.get("total_records") or 0)
    if total == 0:
        return {
            "summary": "No indexed program Oracle evidence records were found.",
            "notable_patterns": [],
            "bounded_next_questions": [
                "Has program-gen emitted oracle_evidence.json for a run with local behavior evidence?",
                "Was that evidence explicitly indexed into the intended local CoordinateIndex?",
            ],
        }

    status_top = _top(_safe_mapping(summary.get("behavior_status_counts")))
    metric_top = _top(_safe_mapping(summary.get("metric_counts")))
    failure_top = _top(_safe_mapping(summary.get("failure_signal_counts")))
    task_top = _top(_safe_mapping(summary.get("task_type_counts")))

    status_phrase = status_top[0] if status_top is not None else "unknown"
    metric_phrase = metric_top[0] if metric_top is not None else "unknown"
    source_counts = _safe_mapping(summary.get("behavior_source_kind_counts"))
    source_phrase = ", ".join(sorted(source_counts)) if source_counts else "unknown"
    summary_text = (
        f"Indexed program Oracle evidence currently contains {total} program "
        f"record(s) across {summary.get('evidence_source_count', 0)} behavior "
        f"source(s); the most common behavior status is {status_phrase} under "
        f"{metric_phrase} evidence. Sources: {source_phrase}. This is an "
        "evidence-grounded behavior summary and is not live authority. "
        f"Embedding claim posture: "
        f"{_safe_mapping(summary.get('embedding_backend_posture')).get('semantic_claim', 'unknown')}."
    )

    notable_patterns = [
        f"Behavior status distribution: {summary.get('behavior_status_counts')}",
        f"Behavior source distribution: {source_counts}",
    ]
    if task_top is not None:
        notable_patterns.append(
            f"Most common task type: {task_top[0]} ({task_top[1]})."
        )
    if metric_top is not None:
        notable_patterns.append(
            f"Most common metric: {metric_top[0]} ({metric_top[1]})."
        )
    if failure_top is not None and failure_top[1] > 0:
        notable_patterns.append(
            f"Most common failure signal: {failure_top[0]} ({failure_top[1]})."
        )
    else:
        notable_patterns.append(
            "No recurring failure signal was present in these records."
        )

    bounded_next_questions = [
        "Which evidence sources are associated with the observed behavior statuses?",
        "Which input/output fields appear in repeated failure signals?",
        "What additional examples, splits, or traces would make this behavior evidence less narrow?",
    ]
    return {
        "summary": summary_text,
        "notable_patterns": notable_patterns,
        "bounded_next_questions": bounded_next_questions,
    }


def non_authority_flags() -> dict[str, bool]:
    return {
        "oracle_interpretation_only": True,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "governance_authority": False,
        "external_mutation": False,
    }


def build_program_oracle_evidence_report(
    index_path: Path | None = None,
    *,
    limit: int = 1000,
) -> dict[str, Any]:
    """Build a deterministic, non-authoritative report over indexed evidence."""

    db_path = _index_path_for_report(index_path)
    embeddings = load_program_oracle_evidence_embeddings(db_path, limit=limit)
    summary = summarize_program_oracle_evidence(embeddings)
    status = "ok" if summary["total_records"] else "no_program_oracle_evidence"
    return {
        "schema_version": PROGRAM_ORACLE_REPORT_SCHEMA,
        "status": status,
        "index_path": str(db_path),
        "run_kind": PROGRAM_ORACLE_RUN_KIND,
        **summary,
        "interpretation": _build_interpretation(summary),
        "non_authority": non_authority_flags(),
    }
