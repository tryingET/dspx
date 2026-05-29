from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from dspx.services.program_runtime_trace_coverage import (
    source_record_coverage,
    source_record_coverage_status,
    source_record_coverage_valid,
)

PROGRAM_RUNTIME_TRACES_SCHEMA = "program-runtime-traces-v1"
PROGRAM_RUNTIME_MODULE_CALL_SCHEMA = "program-runtime-module-call-v1"
PROGRAM_RUNTIME_FINAL_OUTPUT_SCHEMA = "program-runtime-final-output-v1"

_EFFECT_KEYS = {
    "provider_called",
    "tool_called",
    "custom_import_loaded",
    "network",
    "filesystem_read",
    "filesystem_write",
    "subprocess",
    "external_authority",
}

_NON_AUTHORITY = {
    "runtime_evidence_only": True,
    "oracle_authority": False,
    "ranking_authority": False,
    "promotion_authority": False,
    "activation_authority": False,
    "governance_authority": False,
    "canonical_mutation": False,
    "external_mutation": False,
    "winner_selection": False,
}


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def _stable_hash(payload: Mapping[str, Any] | list[Any]) -> str:
    text = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _string_list_field(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            return None
        out.append(item)
    if len(set(out)) != len(out):
        return None
    return out


def _surfaces(module_surfaces: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = module_surfaces.get("module_surfaces")
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _surface_signature(surface: Mapping[str, Any]) -> dict[str, Any]:
    signature = surface.get("signature")
    return dict(signature) if isinstance(signature, Mapping) else {}


def _surface_effects(surface: Mapping[str, Any]) -> dict[str, bool]:
    raw = surface.get("effects")
    effects = dict(raw) if isinstance(raw, Mapping) else {}
    return {key: bool(effects.get(key, False)) for key in sorted(_EFFECT_KEYS)}


def _trajectory_slots(primitive: str, call: Mapping[str, Any]) -> dict[str, Any]:
    if primitive == "ReAct":
        return {
            "react_steps": _jsonable(call.get("react_steps") or []),
            "react_history": _jsonable(call.get("history") or []),
            "tool_call_intents": [],
            "tool_call_results": [],
            "tool_calls_executed": False,
        }
    if primitive == "ReActV2":
        return {
            "react_v2_steps": _jsonable(call.get("react_v2_steps") or []),
            "react_v2_history": _jsonable(call.get("history") or []),
            "final_submit": _jsonable(call.get("final_submit") or {}),
            "tool_call_intents": [],
            "tool_call_results": [],
            "tool_calls_executed": False,
            "experimental": True,
        }
    if primitive == "ProgramOfThought":
        return {
            "program_of_thought_steps": _jsonable(
                call.get("program_of_thought_steps") or []
            ),
            "generated_code_blocks": _jsonable(call.get("generated_code_blocks") or []),
            "interpreter_results": _jsonable(call.get("interpreter_results") or []),
            "tool_calls_executed": False,
            "sandbox_policy": "empty_python_interpreter_sandbox",
        }
    return {
        "prediction_steps": _jsonable(call.get("prediction_steps") or []),
        "tool_call_intents": [],
        "tool_call_results": [],
        "tool_calls_executed": False,
    }


def _input_linkage(
    *, fields: list[str], inputs: Mapping[str, Any], prior_outputs: set[str]
) -> list[dict[str, Any]]:
    linked: list[dict[str, Any]] = []
    for field in fields:
        present = field in inputs
        declared_available_from_prior_output = field in prior_outputs
        if not present:
            source = "missing"
        elif declared_available_from_prior_output:
            source = "upstream_module_output"
        else:
            source = "program_input"
        linked.append(
            {
                "field": field,
                "source": source,
                "present": present,
                "declared_available_from_prior_output": declared_available_from_prior_output,
            }
        )
    return linked


def _output_linkage(
    *, fields: list[str], outputs: Mapping[str, Any], program_outputs: set[str]
) -> list[dict[str, Any]]:
    return [
        {
            "field": field,
            "source": "module_output",
            "present": field in outputs,
            "delivered_to_final_output": field in program_outputs,
        }
        for field in fields
    ]


def _final_linkage(
    *, outputs: Mapping[str, Any], module_id: str, program_outputs: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "field": field,
            "source_module_id": module_id if field in outputs else None,
            "present": field in outputs,
        }
        for field in program_outputs
    ]


def _with_trace_hash(payload: dict[str, Any]) -> dict[str, Any]:
    hashed = dict(payload)
    hashed["trace_hash"] = _stable_hash(payload)
    return hashed


def _without_trace_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items() if key != "trace_hash"}


def _trace_hash_valid(value: Mapping[str, Any]) -> bool:
    trace_hash = value.get("trace_hash")
    return isinstance(trace_hash, str) and trace_hash == _stable_hash(
        _without_trace_hash(value)
    )


def _mapping_list(value: object) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        items.append({str(key): value for key, value in item.items()})
    return items


def _non_authority_valid(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    payload = dict(value)
    for key, expected in _NON_AUTHORITY.items():
        if payload.get(key) is not expected:
            return False
    return True


def _runtime_policy_valid(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    payload = dict(value)
    false_keys = {
        "tool_binding_allowed",
        "tool_execution_allowed",
        "dspy_tool_materialization_allowed",
        "react_tool_binding_allowed",
        "react_v2_tool_binding_allowed",
        "live_external_retriever_allowed",
        "network_allowed_by_trace_contract",
        "filesystem_mutation_allowed_by_trace_contract",
        "external_authority_mutation_allowed",
    }
    return all(payload.get(key) is False for key in false_keys)


def _effects_safe(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    payload = dict(value)
    forbidden_true = {
        "tool_called",
        "custom_import_loaded",
        "network",
        "filesystem_write",
        "subprocess",
        "external_authority",
    }
    return all(payload.get(key) is False for key in forbidden_true)


def _trajectory_slots_safe(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    payload = dict(value)
    if payload.get("tool_calls_executed") is not False:
        return False
    for key in ("tool_call_intents", "tool_call_results"):
        raw = payload.get(key, [])
        if raw not in ([], None):
            return False
    return True


def validate_program_runtime_traces(payload: Mapping[str, Any]) -> bool:
    """Return whether a runtime-traces artifact satisfies replay semantics.

    This validates the artifact's internal hash chain and safety posture. It is
    intentionally stricter than JSON-shape validation so replay can fail closed
    if trace records are edited, tool execution is implied, or non-authority
    flags drift.
    """

    if payload.get("schema_version") != PROGRAM_RUNTIME_TRACES_SCHEMA:
        return False
    if payload.get("status") not in {
        "runtime_traces_captured",
        "no_runtime_traces_captured",
    }:
        return False
    module_calls = _mapping_list(payload.get("module_calls"))
    final_outputs = _mapping_list(payload.get("final_outputs"))
    if module_calls is None or final_outputs is None:
        return False
    if payload.get("module_call_count") != len(module_calls):
        return False
    if payload.get("final_output_trace_count") != len(final_outputs):
        return False
    has_trace_records = bool(module_calls or final_outputs)
    if payload.get("status") == "runtime_traces_captured" and not has_trace_records:
        return False
    if payload.get("status") == "no_runtime_traces_captured" and has_trace_records:
        return False
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list) or payload.get("source_count") != len(
        raw_sources
    ):
        return False
    sources = [dict(item) for item in raw_sources if isinstance(item, Mapping)]
    if len(sources) != len(raw_sources):
        return False
    # Compatibility: older v1 runtime-trace artifacts did not emit
    # source_record_coverage. New artifacts must match the reconstructed
    # record-level semantics exactly when the field is present.
    if "source_record_coverage" in payload and not source_record_coverage_valid(
        value=payload.get("source_record_coverage"),
        sources=sources,
        module_calls=module_calls,
        final_outputs=final_outputs,
        expected_module_ids=_string_list(
            (payload.get("coverage") or {}).get("expected_module_ids")
            if isinstance(payload.get("coverage"), Mapping)
            else None
        ),
        program_outputs=_string_list(
            (payload.get("coverage") or {}).get("program_outputs")
            if isinstance(payload.get("coverage"), Mapping)
            else None
        ),
        non_authority=_NON_AUTHORITY,
    ):
        return False
    if not _runtime_policy_valid(payload.get("runtime_policy")):
        return False
    if not _non_authority_valid(payload.get("non_authority")):
        return False
    if not _coverage_valid(
        coverage=payload.get("coverage"),
        sources=sources,
        module_calls=module_calls,
        final_outputs=final_outputs,
    ):
        return False
    trace_hashes = payload.get("trace_hashes")
    if not isinstance(trace_hashes, Mapping):
        return False
    if trace_hashes.get("module_calls") != [
        call.get("trace_hash") for call in module_calls
    ]:
        return False
    if trace_hashes.get("final_outputs") != [
        item.get("trace_hash") for item in final_outputs
    ]:
        return False
    for call in module_calls:
        if call.get("schema_version") != PROGRAM_RUNTIME_MODULE_CALL_SCHEMA:
            return False
        if not _trace_hash_valid(call):
            return False
        if not _effects_safe(call.get("effects")):
            return False
        if not _trajectory_slots_safe(call.get("trajectory_slots")):
            return False
        if not _non_authority_valid(call.get("non_authority")):
            return False
        if not isinstance(call.get("input_field_linkage"), list):
            return False
        if not isinstance(call.get("output_field_linkage"), list):
            return False
        if not isinstance(call.get("final_output_linkage"), list):
            return False
    for item in final_outputs:
        if item.get("schema_version") != PROGRAM_RUNTIME_FINAL_OUTPUT_SCHEMA:
            return False
        if not _trace_hash_valid(item):
            return False
        if not _non_authority_valid(item.get("non_authority")):
            return False
        if not isinstance(item.get("final_output_linkage"), list):
            return False
    return True


def _source_descriptor(
    *,
    path: str,
    content_hash: str | None,
    split: str | None,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    summary = payload.get("summary")
    return {
        "path": path,
        "content_hash": content_hash,
        "kind": "dataset_split" if split else "examples",
        "split": split,
        "record_count": len(payload.get("examples") or [])
        if isinstance(payload.get("examples"), list)
        else 0,
        "summary": dict(summary) if isinstance(summary, Mapping) else {},
    }


def _module_calls_from_runtime_trace(
    *,
    record: Mapping[str, Any],
    source: Mapping[str, Any],
    surfaces_by_id: Mapping[str, Mapping[str, Any]],
    program_outputs: list[str],
) -> list[dict[str, Any]]:
    trace = record.get("runtime_trace")
    if not isinstance(trace, Mapping):
        return []
    raw_calls = trace.get("module_calls")
    if not isinstance(raw_calls, list):
        return []
    calls: list[dict[str, Any]] = []
    prior_outputs: set[str] = set()
    for call_index, raw_call in enumerate(raw_calls):
        if not isinstance(raw_call, Mapping):
            continue
        raw_call_map: dict[str, Any] = {
            str(key): value for key, value in raw_call.items()
        }
        module_id = str(raw_call_map.get("module_id") or "")
        surface = dict(surfaces_by_id.get(module_id) or {})
        signature = _surface_signature(surface)
        input_fields = _string_list(signature.get("inputs"))
        output_fields = _string_list(signature.get("outputs"))
        inputs = (
            dict(raw_call_map.get("inputs") or {})
            if isinstance(raw_call_map.get("inputs"), Mapping)
            else {}
        )
        outputs = (
            dict(raw_call_map.get("outputs") or {})
            if isinstance(raw_call_map.get("outputs"), Mapping)
            else {}
        )
        primitive = str(
            surface.get("primitive") or raw_call_map.get("primitive") or "Predict"
        )
        call = {
            "schema_version": PROGRAM_RUNTIME_MODULE_CALL_SCHEMA,
            "source": dict(source),
            "example_index": record.get("index"),
            "call_index": call_index,
            "module_id": module_id,
            "primitive": primitive,
            "status": str(
                raw_call_map.get("status") or record.get("status") or "unknown"
            ),
            "capture_status": "actual_module_call_captured",
            "inputs": _jsonable(inputs),
            "input_field_linkage": _input_linkage(
                fields=input_fields, inputs=inputs, prior_outputs=prior_outputs
            ),
            "outputs": _jsonable(outputs),
            "output_field_linkage": _output_linkage(
                fields=output_fields,
                outputs=outputs,
                program_outputs=set(program_outputs),
            ),
            "final_output_linkage": _final_linkage(
                outputs=outputs, module_id=module_id, program_outputs=program_outputs
            ),
            "trajectory_slots": _trajectory_slots(primitive, raw_call_map),
            "effects": _surface_effects(surface),
            "non_authority": dict(_NON_AUTHORITY),
        }
        calls.append(_with_trace_hash(call))
        prior_outputs.update(str(key) for key in outputs)
    return calls


def _synthetic_single_module_call(
    *,
    record: Mapping[str, Any],
    source: Mapping[str, Any],
    surface: Mapping[str, Any],
    program_outputs: list[str],
) -> dict[str, Any]:
    signature = _surface_signature(surface)
    input_fields = _string_list(signature.get("inputs"))
    output_fields = _string_list(signature.get("outputs"))
    raw_inputs = record.get("inputs")
    raw_outputs = record.get("observed_outputs")
    inputs = dict(raw_inputs) if isinstance(raw_inputs, Mapping) else {}
    outputs = dict(raw_outputs) if isinstance(raw_outputs, Mapping) else {}
    module_id = str(surface.get("module_id") or "generated_module")
    primitive = str(surface.get("primitive") or "Predict")
    call = {
        "schema_version": PROGRAM_RUNTIME_MODULE_CALL_SCHEMA,
        "source": dict(source),
        "example_index": record.get("index"),
        "call_index": 0,
        "module_id": module_id,
        "primitive": primitive,
        "status": str(record.get("status") or "unknown"),
        "capture_status": "actual_single_module_call_reconstructed_from_behavior_result",
        "inputs": _jsonable(
            {field: inputs[field] for field in input_fields if field in inputs}
        ),
        "input_field_linkage": _input_linkage(
            fields=input_fields, inputs=inputs, prior_outputs=set()
        ),
        "outputs": _jsonable(
            {field: outputs[field] for field in output_fields if field in outputs}
        ),
        "output_field_linkage": _output_linkage(
            fields=output_fields, outputs=outputs, program_outputs=set(program_outputs)
        ),
        "final_output_linkage": _final_linkage(
            outputs=outputs, module_id=module_id, program_outputs=program_outputs
        ),
        "trajectory_slots": _trajectory_slots(primitive, {}),
        "effects": _surface_effects(surface),
        "non_authority": dict(_NON_AUTHORITY),
    }
    return _with_trace_hash(call)


def _coverage_summary(
    *,
    surfaces: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    module_calls: list[dict[str, Any]],
    final_outputs: list[dict[str, Any]],
    program_outputs: list[str],
) -> dict[str, Any]:
    expected_module_ids = sorted(
        str(surface.get("module_id") or "")
        for surface in surfaces
        if str(surface.get("module_id") or "")
    )
    captured_module_ids = sorted(
        {
            str(call.get("module_id") or "")
            for call in module_calls
            if str(call.get("module_id") or "")
        }
    )
    final_output_fields: set[str] = set()
    for record in final_outputs:
        outputs = record.get("outputs")
        if isinstance(outputs, Mapping):
            final_output_fields.update(
                str(field) for field in outputs if str(field) in set(program_outputs)
            )
    missing_module_ids = sorted(set(expected_module_ids) - set(captured_module_ids))
    missing_final_output_fields = sorted(set(program_outputs) - final_output_fields)
    record_coverage = source_record_coverage(
        sources=sources,
        module_calls=module_calls,
        final_outputs=final_outputs,
        expected_module_ids=expected_module_ids,
        program_outputs=program_outputs,
        non_authority=_NON_AUTHORITY,
    )
    record_coverage_status = source_record_coverage_status(
        sources=sources, coverage=record_coverage
    )
    if not sources:
        status = "not_applicable_no_behavior_sources"
    elif (
        missing_module_ids
        or missing_final_output_fields
        or record_coverage_status == "partial"
    ):
        status = "partial"
    else:
        status = "complete"
    return {
        "schema_version": "program-runtime-trace-coverage-v1",
        "status": status,
        "source_count": len(sources),
        "expected_module_ids": expected_module_ids,
        "captured_module_ids": captured_module_ids,
        "missing_module_ids": missing_module_ids,
        "program_outputs": list(program_outputs),
        "captured_final_output_fields": sorted(final_output_fields),
        "missing_final_output_fields": missing_final_output_fields,
        "source_record_coverage_status": record_coverage_status,
        "module_call_count": len(module_calls),
        "final_output_trace_count": len(final_outputs),
        "non_authority": dict(_NON_AUTHORITY),
    }


def _coverage_valid(
    *,
    coverage: object,
    sources: list[Any],
    module_calls: list[dict[str, Any]],
    final_outputs: list[dict[str, Any]],
) -> bool:
    if not isinstance(coverage, Mapping):
        return False
    payload = dict(coverage)
    if payload.get("schema_version") != "program-runtime-trace-coverage-v1":
        return False
    if payload.get("status") not in {
        "not_applicable_no_behavior_sources",
        "partial",
        "complete",
    }:
        return False
    if payload.get("source_count") != len(sources):
        return False
    if payload.get("module_call_count") != len(module_calls):
        return False
    if payload.get("final_output_trace_count") != len(final_outputs):
        return False
    if not _non_authority_valid(payload.get("non_authority")):
        return False
    expected_list = _string_list_field(payload.get("expected_module_ids"))
    captured_list = _string_list_field(payload.get("captured_module_ids"))
    missing_list = _string_list_field(payload.get("missing_module_ids"))
    program_outputs_list = _string_list_field(payload.get("program_outputs"))
    captured_outputs_list = _string_list_field(
        payload.get("captured_final_output_fields")
    )
    missing_outputs_list = _string_list_field(
        payload.get("missing_final_output_fields")
    )
    if any(
        item is None
        for item in (
            expected_list,
            captured_list,
            missing_list,
            program_outputs_list,
            captured_outputs_list,
            missing_outputs_list,
        )
    ):
        return False
    expected = set(expected_list or [])
    captured = set(captured_list or [])
    missing = set(missing_list or [])
    if not captured <= expected:
        return False
    if missing != expected - captured:
        return False
    program_outputs = set(program_outputs_list or [])
    captured_outputs = set(captured_outputs_list or [])
    missing_outputs = set(missing_outputs_list or [])
    if not captured_outputs <= program_outputs:
        return False
    if missing_outputs != program_outputs - captured_outputs:
        return False
    source_record_coverage_status = payload.get("source_record_coverage_status")
    if (
        source_record_coverage_status is not None
        and source_record_coverage_status
        not in {
            "not_applicable_no_behavior_sources",
            "not_applicable_no_records",
            "partial",
            "complete",
        }
    ):
        return False
    if not sources:
        return payload.get("status") == "not_applicable_no_behavior_sources"
    if missing or missing_outputs or source_record_coverage_status == "partial":
        return payload.get("status") == "partial"
    return payload.get("status") == "complete"


def _final_output_record(
    *, record: Mapping[str, Any], source: Mapping[str, Any], program_outputs: list[str]
) -> dict[str, Any]:
    raw_outputs = record.get("observed_outputs")
    outputs = dict(raw_outputs) if isinstance(raw_outputs, Mapping) else {}
    payload = {
        "schema_version": PROGRAM_RUNTIME_FINAL_OUTPUT_SCHEMA,
        "source": dict(source),
        "example_index": record.get("index"),
        "status": str(record.get("status") or "unknown"),
        "outputs": _jsonable(outputs),
        "final_output_linkage": [
            {"field": field, "present": field in outputs} for field in program_outputs
        ],
        "non_authority": dict(_NON_AUTHORITY),
    }
    return _with_trace_hash(payload)


def _collect_from_behavior_payload(
    *,
    payload: Mapping[str, Any],
    path: str,
    content_hash: str | None,
    split: str | None,
    surfaces: list[dict[str, Any]],
    program_outputs: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    source = _source_descriptor(
        path=path, content_hash=content_hash, split=split, payload=payload
    )
    surfaces_by_id = {
        str(surface.get("module_id") or ""): surface for surface in surfaces
    }
    records = payload.get("examples")
    if not isinstance(records, list):
        return source, [], []
    module_calls: list[dict[str, Any]] = []
    final_outputs: list[dict[str, Any]] = []
    for raw_record in records:
        if not isinstance(raw_record, Mapping):
            continue
        record = dict(raw_record)
        has_explicit_runtime_trace = isinstance(record.get("runtime_trace"), Mapping)
        traced_calls = _module_calls_from_runtime_trace(
            record=record,
            source=source,
            surfaces_by_id=surfaces_by_id,
            program_outputs=program_outputs,
        )
        if traced_calls:
            module_calls.extend(traced_calls)
        elif len(surfaces) == 1 and not has_explicit_runtime_trace:
            module_calls.append(
                _synthetic_single_module_call(
                    record=record,
                    source=source,
                    surface=surfaces[0],
                    program_outputs=program_outputs,
                )
            )
        final_outputs.append(
            _final_output_record(
                record=record, source=source, program_outputs=program_outputs
            )
        )
    return source, module_calls, final_outputs


def build_program_runtime_traces(
    intent: Any,
    *,
    module_surfaces: Mapping[str, Any],
    behavior_results: Mapping[str, Any] | None = None,
    behavior_results_hash: str | None = None,
    dataset_split_behavior_results: Mapping[str, Mapping[str, Any]] | None = None,
    dataset_split_behavior_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the local runtime trajectory evidence sidecar.

    Runtime traces are evidence-only. They are derived from generated local
    example/dataset harness results and generated pipeline trace fragments when
    available. They do not grant ranking, promotion, activation, governance,
    Oracle, or external mutation authority, and they never bind tools.
    """

    surfaces = _surfaces(module_surfaces)
    program_outputs = [str(item) for item in getattr(intent, "outputs", [])]
    sources: list[dict[str, Any]] = []
    module_calls: list[dict[str, Any]] = []
    final_outputs: list[dict[str, Any]] = []

    if behavior_results is not None:
        source, calls, finals = _collect_from_behavior_payload(
            payload=behavior_results,
            path="behavior_results.json",
            content_hash=behavior_results_hash,
            split=None,
            surfaces=surfaces,
            program_outputs=program_outputs,
        )
        sources.append(source)
        module_calls.extend(calls)
        final_outputs.extend(finals)

    split_payloads = dict(dataset_split_behavior_results or {})
    split_hashes = dict(dataset_split_behavior_hashes or {})
    for split in sorted(split_payloads):
        source, calls, finals = _collect_from_behavior_payload(
            payload=split_payloads[split],
            path=f"behavior_results.{split}.json",
            content_hash=split_hashes.get(split),
            split=split,
            surfaces=surfaces,
            program_outputs=program_outputs,
        )
        sources.append(source)
        module_calls.extend(calls)
        final_outputs.extend(finals)

    status = (
        "runtime_traces_captured"
        if module_calls or final_outputs
        else "no_runtime_traces_captured"
    )
    coverage = _coverage_summary(
        surfaces=surfaces,
        sources=sources,
        module_calls=module_calls,
        final_outputs=final_outputs,
        program_outputs=program_outputs,
    )
    return {
        "schema_version": PROGRAM_RUNTIME_TRACES_SCHEMA,
        "status": status,
        "intent": {
            "name": str(getattr(intent, "name", "")),
            "objective": str(getattr(intent, "objective", "")),
        },
        "sources": sources,
        "source_count": len(sources),
        "module_call_count": len(module_calls),
        "final_output_trace_count": len(final_outputs),
        "module_calls": module_calls,
        "final_outputs": final_outputs,
        "trace_hashes": {
            "module_calls": [str(call.get("trace_hash")) for call in module_calls],
            "final_outputs": [str(item.get("trace_hash")) for item in final_outputs],
        },
        "coverage": coverage,
        "source_record_coverage": source_record_coverage(
            sources=sources,
            module_calls=module_calls,
            final_outputs=final_outputs,
            expected_module_ids=coverage["expected_module_ids"],
            program_outputs=program_outputs,
            non_authority=_NON_AUTHORITY,
        ),
        "runtime_policy": {
            "source": "local_generated_behavior_harnesses_only",
            "provider_calls_may_have_occurred_in_behavior_harness": bool(sources),
            "tool_binding_allowed": False,
            "tool_execution_allowed": False,
            "dspy_tool_materialization_allowed": False,
            "react_tool_binding_allowed": False,
            "react_v2_tool_binding_allowed": False,
            "live_external_retriever_allowed": False,
            "network_allowed_by_trace_contract": False,
            "filesystem_mutation_allowed_by_trace_contract": False,
            "external_authority_mutation_allowed": False,
        },
        "non_authority": dict(_NON_AUTHORITY),
        "notes": [
            "This sidecar records local generated-harness runtime trace evidence only.",
            "Single-module traces are reconstructed from behavior result inputs and observed outputs; generated pipeline traces use explicit runtime trace fragments when available.",
            "ReAct, ReActV2, and ProgramOfThought trajectory slots are present but tool-call lists remain empty and no tools are bound or executed.",
        ],
    }
