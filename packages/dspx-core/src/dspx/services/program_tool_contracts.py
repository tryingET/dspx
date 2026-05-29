from __future__ import annotations

from typing import Any, Mapping

from dspx.contract_scalars import contract_bool

PROGRAM_TOOL_CONTRACTS_SCHEMA = "program-tool-contracts-v1"
PROGRAM_TOOL_CONTRACT_SCHEMA = "program-tool-contract-v1"

_EFFECT_CLASSES = {
    "pure",
    "read",
    "mutate",
    "network",
    "filesystem",
    "subprocess",
    "external_authority",
}

_NON_AUTHORITY = {
    "tool_contracts_only": True,
    "runtime_binding_authority": False,
    "tool_execution_authority": False,
    "oracle_authority": False,
    "ranking_authority": False,
    "promotion_authority": False,
    "activation_authority": False,
    "governance_authority": False,
    "canonical_mutation": False,
    "external_mutation": False,
}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _schema(value: object, *, fields: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    field_names = _string_list(fields)
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {name: {"type": "string"} for name in field_names},
        "required": field_names,
    }


def _allowlists(value: object) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, Mapping) else {}
    return {
        "tool_ids": _string_list(payload.get("tool_ids")),
        "network_hosts": _string_list(payload.get("network_hosts")),
        "filesystem_paths": _string_list(payload.get("filesystem_paths")),
        "imports": _string_list(payload.get("imports")),
        "environment_variables": _string_list(payload.get("environment_variables")),
    }


def _timeout_policy(value: object) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, Mapping) else {}
    raw_timeout = payload.get("timeout_seconds", payload.get("max_seconds", 1))
    if isinstance(raw_timeout, bool):
        timeout_seconds = 1.0
    else:
        try:
            timeout_seconds = float(raw_timeout)
        except (TypeError, ValueError):
            timeout_seconds = 1.0
    if timeout_seconds <= 0:
        timeout_seconds = 1.0
    return {
        "timeout_seconds": timeout_seconds,
        "retry_policy": str(payload.get("retry_policy") or "none"),
        "fail_closed": contract_bool(
            payload.get("fail_closed"),
            default=True,
            label="tool contract timeout_policy.fail_closed",
        ),
    }


def _redaction_policy(value: object) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, Mapping) else {}
    return {
        "redact_inputs": _string_list(payload.get("redact_inputs")),
        "redact_outputs": _string_list(payload.get("redact_outputs")),
        "redact_secrets": contract_bool(
            payload.get("redact_secrets"),
            default=True,
            label="tool contract redaction_policy.redact_secrets",
        ),
        "persist_redacted_only": contract_bool(
            payload.get("persist_redacted_only"),
            default=True,
            label="tool contract redaction_policy.persist_redacted_only",
        ),
    }


def _effect_class(value: object, *, tool_id: str) -> str:
    effect_class = str(value or "pure").strip().lower()
    if effect_class not in _EFFECT_CLASSES:
        allowed = sorted(_EFFECT_CLASSES)
        raise ValueError(
            f"tool contract {tool_id!r} effect_class must be one of {allowed}"
        )
    return effect_class


def _tool_contract(declaration: Mapping[str, Any]) -> dict[str, Any]:
    tool_id = str(declaration.get("id") or declaration.get("name") or "").strip()
    effect_class = _effect_class(declaration.get("effect_class"), tool_id=tool_id)
    return {
        "schema_version": PROGRAM_TOOL_CONTRACT_SCHEMA,
        "tool_id": tool_id,
        "name": str(declaration.get("name") or tool_id),
        "status": "descriptor_only_not_bound_or_executed",
        "args_schema": _schema(
            declaration.get("args_schema"), fields=declaration.get("inputs")
        ),
        "return_schema": _schema(
            declaration.get("return_schema"), fields=declaration.get("outputs")
        ),
        "effect_class": effect_class,
        "allowlists": _allowlists(declaration.get("allowlists")),
        "timeout_policy": _timeout_policy(declaration.get("timeout_policy")),
        "redaction_policy": _redaction_policy(declaration.get("redaction_policy")),
        "dry_run_mutation_posture": {
            "dry_run_required": True,
            "declared_mutation_allowed": contract_bool(
                declaration.get("mutation_allowed"),
                default=effect_class == "mutate",
                label=f"tool contract {tool_id!r} mutation_allowed",
            ),
            "mutation_allowed_in_generated_program": False,
            "network_allowed_in_generated_program": False,
            "filesystem_allowed_in_generated_program": False,
            "subprocess_allowed_in_generated_program": False,
            "posture": "descriptor_only_no_runtime_effects",
        },
        "generated_adapter": {
            "exists": False,
            "content_hash": None,
            "provenance": None,
        },
        "non_authority": dict(_NON_AUTHORITY),
    }


def build_program_tool_contracts(intent: Any) -> dict[str, Any]:
    """Build descriptor-only external tool contracts for a generated program.

    This sidecar is the explicit contract layer that must exist before any future
    generated adapter or ``dspy.Tool`` materialization. It never binds, imports,
    executes, dry-runs, or mutates external systems by itself.
    """

    declarations = list(
        dict(getattr(intent, "capabilities", {}) or {}).get("declarations") or []
    )
    tool_declarations = [
        dict(item)
        for item in declarations
        if isinstance(item, Mapping) and item.get("kind") == "tool"
    ]
    contracts = [_tool_contract(item) for item in tool_declarations]
    return {
        "schema_version": PROGRAM_TOOL_CONTRACTS_SCHEMA,
        "status": "descriptor_only_no_tool_binding",
        "tool_contract_count": len(contracts),
        "contracts": contracts,
        "runtime_policy": {
            "dspy_tool_materialization_allowed": False,
            "tool_execution_allowed": False,
            "generated_adapters_allowed": False,
            "network_allowed": False,
            "filesystem_allowed": False,
            "subprocess_allowed": False,
            "mutation_allowed": False,
            "fail_closed_without_explicit_future_adapter": True,
        },
        "non_authority": dict(_NON_AUTHORITY),
        "notes": [
            "Tool contracts are descriptor-only and hash-bound evidence for future safe adapters.",
            "This sidecar does not enable dspy.Tool, ReAct tools, custom imports, live retrievers, network access, filesystem access, subprocesses, or external authority mutation.",
            "Future generated adapters must record adapter hashes/provenance and remain replay-checked before any runtime effect is allowed.",
        ],
    }
