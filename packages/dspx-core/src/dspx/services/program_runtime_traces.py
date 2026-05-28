from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

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
        traced_calls = _module_calls_from_runtime_trace(
            record=record,
            source=source,
            surfaces_by_id=surfaces_by_id,
            program_outputs=program_outputs,
        )
        if traced_calls:
            module_calls.extend(traced_calls)
        elif len(surfaces) == 1:
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
