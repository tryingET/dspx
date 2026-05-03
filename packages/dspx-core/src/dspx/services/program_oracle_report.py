from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from dspx.coordinates import ExecutionEmbedding
from dspx.coordinates.storage import CoordinateIndex, get_default_index_path
from dspx.services.program_oracle_index import (
    PROGRAM_ORACLE_EVIDENCE_KIND,
    PROGRAM_ORACLE_EVIDENCE_SCHEMA,
    PROGRAM_ORACLE_RUN_KIND,
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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _normalize_behavior_status(value: object) -> str:
    text = str(value or "unknown").strip().lower() or "unknown"
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
    index = CoordinateIndex(db_path=db_path)
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
        "identity": identity,
        "behavior_status": _normalize_behavior_status(
            facets.get("behavior_status") or summary.get("status")
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
    total_evaluation_count = 0
    evidence_source_count = 0

    for record in records:
        behavior_status_counts[str(record["behavior_status"])] += 1
        task_type_counts[str(record["task_type"])] += 1
        metric_counts[str(record["metric"])] += 1
        input_field_counts.update(record["input_fields"])
        output_field_counts.update(record["output_fields"])
        failure_signal_counts.update(record["failure_signals"])
        behavior_source_kind_counts.update(record["behavior_source_kinds"])
        total_evaluation_count += int(record.get("total_evaluation_count") or 0)
        evidence_source_count += int(record.get("evidence_source_count") or 0)

    return {
        "total_records": len(records),
        "behavior_status_counts": _status_counter_payload(behavior_status_counts),
        "task_type_counts": _counter_payload(task_type_counts),
        "metric_counts": _counter_payload(metric_counts),
        "input_field_counts": _counter_payload(input_field_counts),
        "output_field_counts": _counter_payload(output_field_counts),
        "failure_signal_counts": _counter_payload(failure_signal_counts),
        "behavior_source_kind_counts": _counter_payload(behavior_source_kind_counts),
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
        "evidence-grounded behavior summary and is not live authority."
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
