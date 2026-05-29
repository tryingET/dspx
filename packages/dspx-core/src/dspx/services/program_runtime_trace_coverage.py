from __future__ import annotations

from typing import Any, Mapping

SOURCE_RECORD_COVERAGE_SCHEMA = "program-runtime-trace-source-coverage-v1"
SourceKey = tuple[str, str | None]


def _source_key(source: Mapping[str, Any]) -> SourceKey:
    split = source.get("split")
    return (str(source.get("path") or ""), str(split) if split is not None else None)


def _call_source_key(record: Mapping[str, Any]) -> SourceKey:
    source = record.get("source")
    return _source_key(source) if isinstance(source, Mapping) else ("", None)


def _record_index(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def source_record_coverage(
    *,
    sources: list[dict[str, Any]],
    module_calls: list[dict[str, Any]],
    final_outputs: list[dict[str, Any]],
    expected_module_ids: list[str],
    program_outputs: list[str],
    non_authority: Mapping[str, bool],
) -> list[dict[str, Any]]:
    coverage: list[dict[str, Any]] = []
    module_indexes_by_source: dict[SourceKey, set[int]] = {}
    final_indexes_by_source: dict[SourceKey, set[int]] = {}
    module_ids_by_record: dict[SourceKey, dict[int, set[str]]] = {}
    final_fields_by_record: dict[SourceKey, dict[int, set[str]]] = {}
    module_counts_by_source: dict[SourceKey, int] = {}
    final_counts_by_source: dict[SourceKey, int] = {}
    expected_modules = set(expected_module_ids)
    expected_outputs = set(program_outputs)
    for call in module_calls:
        key = _call_source_key(call)
        module_counts_by_source[key] = module_counts_by_source.get(key, 0) + 1
        index = _record_index(call.get("example_index"))
        if index is not None:
            module_indexes_by_source.setdefault(key, set()).add(index)
            module_id = str(call.get("module_id") or "")
            if module_id:
                module_ids_by_record.setdefault(key, {}).setdefault(index, set()).add(
                    module_id
                )
    for item in final_outputs:
        key = _call_source_key(item)
        final_counts_by_source[key] = final_counts_by_source.get(key, 0) + 1
        index = _record_index(item.get("example_index"))
        if index is not None:
            final_indexes_by_source.setdefault(key, set()).add(index)
            outputs = item.get("outputs")
            if isinstance(outputs, Mapping):
                fields = {str(field) for field in outputs if str(field)}
                final_fields_by_record.setdefault(key, {}).setdefault(
                    index, set()
                ).update(fields)
    for source in sources:
        key = _source_key(source)
        raw_count = source.get("record_count")
        record_count = raw_count if isinstance(raw_count, int) and raw_count >= 0 else 0
        expected_indexes = set(range(record_count))
        module_indexes = module_indexes_by_source.get(key, set())
        final_indexes = final_indexes_by_source.get(key, set())
        per_record_modules = module_ids_by_record.get(key, {})
        per_record_outputs = final_fields_by_record.get(key, {})
        missing_module_indexes = [
            index
            for index in sorted(expected_indexes)
            if expected_modules - per_record_modules.get(index, set())
        ]
        missing_final_indexes = [
            index
            for index in sorted(expected_indexes)
            if expected_outputs - per_record_outputs.get(index, set())
        ]
        module_gaps = [
            {
                "record_index": index,
                "missing_module_ids": sorted(
                    expected_modules - per_record_modules.get(index, set())
                ),
            }
            for index in missing_module_indexes
        ]
        final_output_gaps = [
            {
                "record_index": index,
                "missing_final_output_fields": sorted(
                    expected_outputs - per_record_outputs.get(index, set())
                ),
            }
            for index in missing_final_indexes
        ]
        if record_count == 0:
            status = "not_applicable_no_records"
        elif missing_final_indexes or missing_module_indexes:
            status = "partial"
        else:
            status = "complete"
        coverage.append(
            {
                "schema_version": SOURCE_RECORD_COVERAGE_SCHEMA,
                "status": status,
                "path": str(source.get("path") or ""),
                "split": source.get("split"),
                "record_count": record_count,
                "expected_module_ids": sorted(expected_modules),
                "program_outputs": list(program_outputs),
                "module_call_count": module_counts_by_source.get(key, 0),
                "final_output_trace_count": final_counts_by_source.get(key, 0),
                "records_with_module_calls": sorted(module_indexes),
                "records_with_final_outputs": sorted(final_indexes),
                "records_with_complete_module_calls": sorted(
                    expected_indexes - set(missing_module_indexes)
                ),
                "records_with_complete_final_outputs": sorted(
                    expected_indexes - set(missing_final_indexes)
                ),
                "missing_module_call_record_indexes": missing_module_indexes,
                "missing_final_output_record_indexes": missing_final_indexes,
                "module_coverage_gaps": module_gaps,
                "final_output_coverage_gaps": final_output_gaps,
                "non_authority": dict(non_authority),
            }
        )
    return coverage


def source_record_coverage_status(
    *, sources: list[dict[str, Any]], coverage: list[dict[str, Any]]
) -> str:
    statuses = {str(item.get("status")) for item in coverage if item.get("status")}
    if not sources:
        return "not_applicable_no_behavior_sources"
    if "partial" in statuses:
        return "partial"
    if statuses == {"not_applicable_no_records"}:
        return "not_applicable_no_records"
    return "complete"


def source_record_coverage_valid(
    *,
    value: object,
    sources: list[dict[str, Any]],
    module_calls: list[dict[str, Any]],
    final_outputs: list[dict[str, Any]],
    expected_module_ids: list[str],
    program_outputs: list[str],
    non_authority: Mapping[str, bool],
) -> bool:
    if not isinstance(value, list):
        return False
    expected = source_record_coverage(
        sources=sources,
        module_calls=module_calls,
        final_outputs=final_outputs,
        expected_module_ids=expected_module_ids,
        program_outputs=program_outputs,
        non_authority=non_authority,
    )
    if len(value) != len(expected):
        return False
    for raw_item, expected_item in zip(value, expected):
        if not isinstance(raw_item, Mapping):
            return False
        item = dict(raw_item)
        if item != expected_item:
            return False
    return True
