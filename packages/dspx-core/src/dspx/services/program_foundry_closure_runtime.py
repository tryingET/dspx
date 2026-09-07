"""Frozen current pure Oracle reducers; AST differential tests guard producer drift."""

import ipaddress
import math
import re
from urllib.parse import urlsplit, urlunsplit
from typing import Any, Mapping

if __package__:
    from dspx.services.program_foundry_closure_io import (
        Rejected,
        closed,
        equal,
        require,
    )
else:
    from program_foundry_closure_io import Rejected, closed, equal, require  # ty: ignore[unresolved-import]

PROGRAM_ORACLE_EVIDENCE_SCHEMA = "program-oracle-evidence-v1"


def model_name(value: object) -> None:
    require(
        isinstance(value, str)
        and 0 < len(value) <= 256
        and value == value.strip()
        and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value),
        "runtime_provider_model",
    )


def provider(value: dict) -> dict:
    """Validate local runtime records, never authenticate provider responses."""
    if value.get("status") == "unavailable":
        closed(value, {"status", "error"})
        error = closed(value["error"], {"type", "message"})
        require(
            all(isinstance(x, str) for x in error.values()), "runtime_provider_error"
        )
        return {
            "provider": "unavailable",
            "provider_family": "unavailable",
            "model": None,
            "effect_contract": "dspx-provider-effect-v1",
            "runtime": {"configuration_status": "unavailable"},
        }
    closed(value, {"status", "metadata", "effect_evidence"})
    equal(value["status"], "configured", "runtime_provider_status")
    metadata = value["metadata"]
    if "schema_version" in metadata:
        raise Rejected("runtime_provider_profile_unsupported", "unsupported")
    closed(
        metadata,
        {
            "provider",
            "model",
            "model_type",
            "typed_contract",
            "capabilities",
            "runtime",
        },
    )
    kind, model = metadata["provider"], metadata["model"]
    require(kind in {"stub", "openai-compatible"}, "runtime_provider_kind")
    model_name(model)
    equal(metadata["model_type"], "text")
    equal(metadata["typed_contract"], "typed_lm")
    equal(
        metadata["capabilities"],
        {
            "supports_tools": False,
            "code_exec": False,
            "json_mode": False,
            "multi_turn": True,
            "structured_output_format": "none",
            "supports_vision": False,
            "supports_audio": False,
        },
        "runtime_provider_capabilities",
    )
    runtime = closed(
        metadata["runtime"], {"provider_kind", "base_endpoint", "effective_timeout"}
    )
    equal(runtime["provider_kind"], kind, "runtime_provider_kind")
    if kind == "stub":
        equal(model, "stub/echo")
        equal(runtime["base_endpoint"], None)
        equal(runtime["effective_timeout"], None)
    else:
        base, timeout = runtime["base_endpoint"], runtime["effective_timeout"]
        require(
            isinstance(base, str)
            and base == base.strip()
            and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in base),
            "runtime_provider_endpoint",
        )
        parsed = urlsplit(base)
        host, port = parsed.hostname, parsed.port
        require(host is not None and "%" not in host, "runtime_provider_endpoint")
        address = ipaddress.ip_address(host)
        path = parsed.path
        parts = path.strip("/").split("/") if path.strip("/") else []
        require(
            parsed.scheme == "http"
            and address.is_loopback
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and port != 0
            and "\\" not in path
            and "%" not in path
            and "//" not in path
            and all(
                re.fullmatch(r"[A-Za-z0-9_~-]+(?:\.[A-Za-z0-9_~-]+)*", p) for p in parts
            )
            and [p.lower() for p in parts[-2:]] != ["chat", "completions"],
            "runtime_provider_endpoint",
        )
        netloc = (
            f"[{address.compressed}]" if address.version == 6 else address.compressed
        )
        if port is not None:
            netloc += f":{port}"
        equal(
            base,
            urlunsplit(
                ("http", netloc, "/" + "/".join(parts) if parts else "", "", "")
            ),
            "runtime_provider_endpoint",
        )
        require(
            type(timeout) in {int, float} and math.isfinite(timeout) and timeout > 0,
            "runtime_provider_timeout",
        )
    effect = closed(
        value["effect_evidence"],
        {
            "schema_version",
            "attempt_total",
            "attempts_truncated",
            "terminal_effect",
            "attempts",
        },
    )
    equal(effect["schema_version"], "dspx-provider-effect-evidence-v1")
    attempts, total, truncated = (
        effect["attempts"],
        effect["attempt_total"],
        effect["attempts_truncated"],
    )
    require(
        isinstance(attempts, list)
        and len(attempts) <= 64
        and type(total) is int
        and total >= len(attempts)
        and type(truncated) is bool
        and truncated == (total > len(attempts))
        and (not truncated or len(attempts) == 64),
        "runtime_provider_attempt_counts",
    )
    dispositions = {
        "preflight_rejected",
        "completed_success",
        "completed_failure",
        "effect_indeterminate",
    }
    for index, attempt in enumerate(attempts):
        closed(
            attempt,
            {
                "provider_kind",
                "requested_model",
                "observed_model",
                "dispatch_count",
                "effect_disposition",
            },
        )
        equal(attempt["provider_kind"], kind)
        equal(attempt["requested_model"], model)
        if attempt["observed_model"] is not None:
            model_name(attempt["observed_model"])
        disposition = attempt["effect_disposition"]
        require(disposition in dispositions, "runtime_provider_disposition")
        equal(
            attempt["dispatch_count"], 0 if disposition == "preflight_rejected" else 1
        )
        if disposition == "completed_success":
            equal(attempt["observed_model"], model, "runtime_provider_success_model")
        require(
            disposition != "effect_indeterminate" or index == len(attempts) - 1,
            "runtime_provider_indeterminate_position",
        )
    equal(
        effect["terminal_effect"],
        attempts[-1]["effect_disposition"] if attempts else None,
        "runtime_provider_terminal",
    )
    require(
        (total == 0) == (effect["terminal_effect"] is None), "runtime_provider_terminal"
    )
    return {
        "provider": kind,
        "provider_family": kind,
        "model": model,
        "effect_contract": "dspx-provider-effect-v1",
        "runtime": runtime,
    }


def _safe_mapping(value: object) -> dict[str, Any]:
    return (
        {str(key): item for key, item in value.items()}
        if isinstance(value, Mapping)
        else {}
    )


def _runtime_trace_summary(
    runtime_traces: Mapping[str, Any], *, content_hash: str
) -> dict[str, Any]:
    coverage = _safe_mapping(runtime_traces.get("coverage"))
    return {
        "schema_version": runtime_traces.get("schema_version"),
        "path": "program_runtime_traces.json",
        "content_hash": content_hash,
        "status": runtime_traces.get("status"),
        "source_count": runtime_traces.get("source_count"),
        "module_call_count": runtime_traces.get("module_call_count"),
        "final_output_trace_count": runtime_traces.get("final_output_trace_count"),
        "coverage": {
            "schema_version": coverage.get("schema_version"),
            "status": coverage.get("status"),
            "source_record_coverage_status": coverage.get(
                "source_record_coverage_status"
            ),
        },
        "non_authority": _safe_mapping(runtime_traces.get("non_authority")),
    }


def _oracle_evidence(
    *,
    manifest_identity: Mapping[str, str | None],
    runtime_episode_id: str,
    behavior_results: Mapping[str, Any],
    behavior_results_hash: str,
    runtime_traces: Mapping[str, Any],
    runtime_traces_hash: str,
    inputs_hash: str,
    contract_mode: str,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    intent = _safe_mapping(manifest.get("intent"))
    raw_summary = behavior_results.get("summary")
    summary = _safe_mapping(raw_summary)
    raw_inputs = behavior_results.get("input_fields")
    raw_outputs = behavior_results.get("output_fields")
    input_fields = (
        [str(item) for item in raw_inputs] if isinstance(raw_inputs, list) else []
    )
    output_fields = (
        [str(item) for item in raw_outputs] if isinstance(raw_outputs, list) else []
    )
    status = str(summary.get("status") or "unknown")
    failure_modes: list[dict[str, Any]] = []
    if status not in {
        "executed",
        "executed_quality_passed",
        "executed_valid_review_only",
        "passed",
    }:
        failure_modes.append(
            {
                "index": 0,
                "status": status,
                "signals": [str(item) for item in behavior_results.get("notes") or []]
                if isinstance(behavior_results.get("notes"), list)
                else [],
                "mismatched_outputs": [],
                "missing_observed_outputs": [],
            }
        )
    identity = {key: value for key, value in manifest_identity.items() if value}
    identity["runtime_episode_id"] = runtime_episode_id
    runtime_trace_summary = _runtime_trace_summary(
        runtime_traces, content_hash=runtime_traces_hash
    )
    runtime_trace_coverage = _safe_mapping(runtime_trace_summary.get("coverage"))
    oracle_facets = {
        "task_type": str(intent.get("task_type") or "single_module"),
        "metric": f"runtime_episode:{contract_mode}",
        "input_fields": input_fields,
        "output_fields": output_fields,
        "behavior_status": status,
        "status_counts": _safe_mapping(summary.get("status_counts")),
        "has_examples": True,
        "example_count": 1,
        "has_dataset_splits": False,
        "dataset_split_count": 0,
        "evidence_source_count": 1,
        "behavior_source_kinds": ["runtime_inputs"],
        "total_evaluation_count": 1,
        "failure_mode_count": len(failure_modes),
        "has_failures": bool(failure_modes),
        "runtime_episode_id": runtime_episode_id,
        "contract_mode": contract_mode,
        "runtime_trace_status": runtime_trace_summary.get("status"),
        "runtime_trace_coverage_status": runtime_trace_coverage.get("status"),
        "runtime_trace_source_record_coverage_status": runtime_trace_coverage.get(
            "source_record_coverage_status"
        ),
        "runtime_trace_module_call_count": runtime_trace_summary.get(
            "module_call_count"
        ),
        "runtime_trace_final_output_trace_count": runtime_trace_summary.get(
            "final_output_trace_count"
        ),
    }
    objective = str(
        intent.get("objective")
        or _safe_mapping(behavior_results.get("intent")).get("objective")
        or ""
    )
    oracle_text = "\n".join(
        [
            "schema_version=program-oracle-evidence-v1",
            "evidence_kind=program_execution_episode",
            f"intent.name={intent.get('name') or behavior_results.get('intent_name') or ''}",
            f"intent.objective={objective}",
            f"intent.task_type={oracle_facets['task_type']}",
            f"intent.metric={oracle_facets['metric']}",
            "io.inputs=" + ",".join(input_fields),
            "io.outputs=" + ",".join(output_fields),
            f"identity.runtime_episode_id={runtime_episode_id}",
            f"identity.candidate_id={identity.get('candidate_id')}",
            f"identity.assembly_id={identity.get('assembly_id')}",
            f"behavior.status={status}",
            "behavior.source_kinds=runtime_inputs",
            "behavior.example_count=1",
            f"runtime_traces.status={oracle_facets.get('runtime_trace_status')}",
            f"runtime_traces.coverage_status={oracle_facets.get('runtime_trace_coverage_status')}",
            f"runtime_traces.source_record_coverage_status={oracle_facets.get('runtime_trace_source_record_coverage_status')}",
            f"runtime_traces.module_call_count={oracle_facets.get('runtime_trace_module_call_count')}",
            f"runtime_traces.final_output_trace_count={oracle_facets.get('runtime_trace_final_output_trace_count')}",
            "authority=oracle_readability_only_non_authoritative; oracle_ranking=false; "
            "oracle_pruning=false; oracle_promotion=false; governance_authority=false; external_mutation=false",
        ]
    )
    return {
        "schema_version": PROGRAM_ORACLE_EVIDENCE_SCHEMA,
        "evidence_kind": "program_execution_episode",
        "authority": "oracle_readability_only_non_authoritative",
        "non_authority": {
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "governance_authority": False,
            "external_mutation": False,
        },
        "identity": identity,
        "intent": {
            "name": intent.get("name") or behavior_results.get("intent_name"),
            "objective": objective,
            "task_type": oracle_facets["task_type"],
            "metric": oracle_facets["metric"],
            "constraints": list(
                intent.get("constraints")
                or _safe_mapping(behavior_results.get("intent")).get("constraints")
                or []
            ),
        },
        "io": {"inputs": input_fields, "outputs": output_fields},
        "behavior": {
            "result_path": "behavior_results.json",
            "result_hash": behavior_results_hash,
            "summary": dict(summary),
            "statuses": _safe_mapping(summary.get("status_counts")),
            "example_count": 1,
            "evaluation_sources": [
                {
                    "kind": "runtime_inputs",
                    "source_kind": "runtime_inputs",
                    "input_artifact_path": "runtime_inputs.json",
                    "input_artifact_hash": inputs_hash,
                    "behavior_results_path": "behavior_results.json",
                    "behavior_results_hash": behavior_results_hash,
                }
            ],
            "evidence_summary": dict(summary),
            "source_statuses": [status],
            "failure_modes": failure_modes,
        },
        "runtime_traces": runtime_trace_summary,
        "oracle_facets": oracle_facets,
        "oracle_text": oracle_text,
        "source_artifacts": [
            {
                "kind": "runtime_inputs",
                "path": "runtime_inputs.json",
                "content_hash": inputs_hash,
                "source_kind": "runtime_inputs",
            },
            {
                "kind": "behavior_results",
                "path": "behavior_results.json",
                "content_hash": behavior_results_hash,
                "source_kind": "runtime_inputs",
            },
            {
                "kind": "runtime_traces",
                "path": "program_runtime_traces.json",
                "content_hash": runtime_traces_hash,
            },
        ],
    }
