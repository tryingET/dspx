from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from dspx.cache import sha256_text
from dspx.services.program_contracts import sanitize_ident
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


def _schema_property_is_bounded(schema: object, *, depth: int = 0) -> bool:
    if not isinstance(schema, Mapping) or not schema:
        return False
    payload: dict[str, Any] = {str(key): item for key, item in schema.items()}
    if depth > 3:
        return False
    schema_type = payload.get("type")
    if schema_type in {"string", "number", "integer", "boolean", "null"}:
        allowed_keys = {"type", "enum", "const", "description", "format"}
        if set(payload) - allowed_keys:
            return False
        enum = payload.get("enum")
        if enum is not None and not isinstance(enum, list):
            return False
        return True
    if schema_type == "array":
        allowed_keys = {"type", "items", "minItems", "maxItems", "description"}
        if set(payload) - allowed_keys:
            return False
        if not _schema_property_is_bounded(payload.get("items"), depth=depth + 1):
            return False
        for key in ["minItems", "maxItems"]:
            value = payload.get(key)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int)
            ):
                return False
        return True
    if schema_type == "object":
        return _schema_is_bounded(payload, depth=depth + 1)
    return False


def _schema_is_bounded(schema: Mapping[str, Any], *, depth: int = 0) -> bool:
    if schema.get("type") != "object":
        return False
    if schema.get("additionalProperties") is not False:
        return False
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, Mapping) or not isinstance(required, list):
        return False
    property_names = {str(key) for key in properties}
    required_names = {item for item in required if isinstance(item, str)}
    if len(required_names) != len(required) or not required_names <= property_names:
        return False
    return all(
        isinstance(raw_property, Mapping)
        and _schema_property_is_bounded(raw_property, depth=depth)
        for raw_property in properties.values()
    )


def _adapter_blueprint_hash_bound(blueprint: Mapping[str, Any]) -> bool:
    source = blueprint.get("source_preview")
    source_hash = blueprint.get("source_hash")
    return (
        isinstance(source, str)
        and bool(source_hash)
        and sha256_text(source) == source_hash
    )


def _schema_required_fields(schema: Mapping[str, Any]) -> list[str]:
    required = schema.get("required")
    if not isinstance(required, list):
        return []
    return sorted(str(item) for item in required if isinstance(item, str))


def _adapter_dry_run_expected_result(
    *, tool_id: str, args_schema: Mapping[str, Any], return_schema: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": "program-tool-adapter-dry-run-v1",
        "tool_id": tool_id,
        "status": "validated_not_executed",
        "args_fields": _schema_required_fields(args_schema),
        "return_fields": _schema_required_fields(return_schema),
        "return_validated": True,
        "effects": {
            "tool_called": False,
            "dspy_tool_bound": False,
            "network": False,
            "filesystem": False,
            "subprocess": False,
            "external_authority_mutated": False,
        },
    }


def _adapter_source(
    *,
    tool_id: str,
    effect_class: str,
    args_schema: Mapping[str, Any],
    return_schema: Mapping[str, Any],
) -> str:
    return "\n".join(
        [
            f"# DSPx generated dspy.Tool adapter source for {tool_id}",
            "# Materialized for review/hash binding only; not imported or bound by program-gen.",
            f"TOOL_ID = {tool_id!r}",
            f"EFFECT_CLASS = {effect_class!r}",
            f"ARGS_SCHEMA = {dict(args_schema)!r}",
            f"RETURN_SCHEMA = {dict(return_schema)!r}",
            "EXECUTION_ALLOWED = False",
            "DSPY_TOOL_BINDING_ALLOWED = False",
            "IMPORTED_BY_GENERATED_PROGRAM = False",
            "def _type_matches(value, expected):",
            "    if expected == 'string':",
            "        return isinstance(value, str)",
            "    if expected == 'boolean':",
            "        return isinstance(value, bool)",
            "    if expected == 'integer':",
            "        return isinstance(value, int) and not isinstance(value, bool)",
            "    if expected == 'number':",
            "        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)",
            "    if expected == 'array':",
            "        return isinstance(value, list)",
            "    if expected == 'object':",
            "        return isinstance(value, dict)",
            "    if expected == 'null':",
            "        return value is None",
            "    return False",
            "def _validate_value(schema, value, label):",
            "    expected = schema.get('type')",
            "    if 'const' in schema and value != schema.get('const'):",
            "        raise ValueError(f'{label} does not match schema const')",
            "    enum = schema.get('enum')",
            "    if enum is not None and value not in enum:",
            "        raise ValueError(f'{label} does not match schema enum')",
            "    if not _type_matches(value, expected):",
            "        raise TypeError(f'{label} does not match schema type')",
            "    if expected == 'object':",
            "        _validate_object(schema, value, label)",
            "    if expected == 'array':",
            "        min_items = schema.get('minItems')",
            "        if isinstance(min_items, int) and len(value) < min_items:",
            "            raise ValueError(f'{label} has fewer items than schema minItems')",
            "        max_items = schema.get('maxItems')",
            "        if isinstance(max_items, int) and len(value) > max_items:",
            "            raise ValueError(f'{label} has more items than schema maxItems')",
            "        item_schema = schema.get('items')",
            "        if isinstance(item_schema, dict):",
            "            for index, item in enumerate(value):",
            "                _validate_value(item_schema, item, f'{label}[{index}]')",
            "    return value",
            "def _validate_object(schema, payload, label):",
            "    if not isinstance(payload, dict):",
            "        raise TypeError(f'{label} payload must be a dict')",
            "    properties = schema.get('properties', {})",
            "    missing = [name for name in schema.get('required', []) if name not in payload]",
            "    if missing:",
            "        raise ValueError(f'missing required {label} fields: {missing}')",
            "    if schema.get('additionalProperties') is False:",
            "        extra = sorted(set(payload) - set(properties))",
            "        if extra:",
            "            raise ValueError(f'unexpected {label} fields: {extra}')",
            "    for name, field_schema in properties.items():",
            "        if name in payload:",
            "            _validate_value(field_schema, payload[name], f'{label} field {name!r}')",
            "    return dict(payload)",
            "def validate_args(payload):",
            "    return _validate_object(ARGS_SCHEMA, payload, 'tool args')",
            "def validate_return(payload):",
            "    return _validate_object(RETURN_SCHEMA, payload, 'tool return')",
            "def adapter_dry_run(payload, expected_return=None):",
            "    validated = validate_args(payload)",
            "    validated_return = None if expected_return is None else validate_return(expected_return)",
            "    return {",
            "        'schema_version': 'program-tool-adapter-dry-run-v1',",
            "        'tool_id': TOOL_ID,",
            "        'status': 'validated_not_executed',",
            "        'args_fields': sorted(validated),",
            "        'return_fields': [] if validated_return is None else sorted(validated_return),",
            "        'return_validated': validated_return is not None,",
            "        'effects': {",
            "            'tool_called': False,",
            "            'dspy_tool_bound': False,",
            "            'network': False,",
            "            'filesystem': False,",
            "            'subprocess': False,",
            "            'external_authority_mutated': False,",
            "        },",
            "    }",
            "def adapter(payload):",
            "    validate_args(payload)",
            "    raise RuntimeError('DSPx generated tool adapter is materialized but not execution-enabled')",
            "",
        ]
    )


def _adapter_blueprint(*, tool_id: str, effect_class: str) -> dict[str, Any]:
    source = "\n".join(
        [
            f"# DSPx generated future dspy.Tool adapter blueprint for {tool_id}",
            "# Not executable in this slice; recorded for review/provenance only.",
            f"TOOL_ID = {tool_id!r}",
            f"EFFECT_CLASS = {effect_class!r}",
            "EXECUTION_ALLOWED = False",
            "DSPY_TOOL_BINDING_ALLOWED = False",
            "def adapter(*args, **kwargs):",
            "    raise RuntimeError('DSPx tool adapter blueprint is not executable')",
            "",
        ]
    )
    return {
        "schema_version": "program-tool-adapter-blueprint-v1",
        "status": "blueprint_recorded_not_executable"
        if effect_class == "pure"
        else "blocked_non_pure_effect_class",
        "tool_id": tool_id,
        "effect_class": effect_class,
        "source_hash": sha256_text(source),
        "source_preview": source,
        "execution_allowed": False,
        "dspy_tool_binding_allowed": False,
    }


def _tool_contract(declaration: Mapping[str, Any]) -> dict[str, Any]:
    tool_id = str(declaration.get("id") or declaration.get("name") or "").strip()
    effect_class = _effect_class(declaration.get("effect_class"), tool_id=tool_id)
    args_schema = _schema(
        declaration.get("args_schema"), fields=declaration.get("inputs")
    )
    return_schema = _schema(
        declaration.get("return_schema"), fields=declaration.get("outputs")
    )
    adapter_source = _adapter_source(
        tool_id=tool_id,
        effect_class=effect_class,
        args_schema=args_schema,
        return_schema=return_schema,
    )
    return {
        "schema_version": PROGRAM_TOOL_CONTRACT_SCHEMA,
        "tool_id": tool_id,
        "name": str(declaration.get("name") or tool_id),
        "status": "descriptor_only_not_bound_or_executed",
        "args_schema": args_schema,
        "return_schema": return_schema,
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
            "source_hash": sha256_text(adapter_source),
            "source_preview": adapter_source,
            "execution_allowed": False,
            "dspy_tool_binding_allowed": False,
            "imported_by_generated_program": False,
        },
        "generated_adapter_blueprint": _adapter_blueprint(
            tool_id=tool_id, effect_class=effect_class
        ),
        "generated_adapter_policy": {
            "schema_version": "program-tool-generated-adapter-policy-v1",
            "status": "adapter_not_generated",
            "adapter_kind": "future_dspy_tool_adapter",
            "required_before_enablement": [
                "adapter source hash and provenance must be recorded",
                "tool input/output schemas must be enforced at adapter boundary",
                "timeout and redaction policy must be enforced before tool call",
                "effect class and allowlists must be checked before tool call",
                "runtime trace must record dry-run/tool-call posture without secrets",
                "receipt replay must verify adapter hash and trace consistency",
            ],
            "execution_allowed": False,
            "dspy_tool_binding_allowed": False,
        },
        "non_authority": dict(_NON_AUTHORITY),
    }


def _declared_react_v2_modules(intent: Any) -> list[dict[str, Any]]:
    topology = dict(getattr(intent, "topology", {}) or {})
    modules = topology.get("modules")
    if not isinstance(modules, list):
        return []
    return [
        dict(module)
        for module in modules
        if isinstance(module, Mapping)
        and str(module.get("primitive") or "") == "ReActV2"
    ]


def _react_v2_tool_readiness(
    *, intent: Any, contracts: list[dict[str, Any]]
) -> dict[str, Any]:
    modules = _declared_react_v2_modules(intent)
    options = dict(getattr(intent, "options", {}) or {})
    requested = bool(modules) or bool(
        options.get("enable_react_v2_materialization")
        or options.get("react_v2_materialization")
    )
    declared_tool_ids = [contract["tool_id"] for contract in contracts]
    module_tool_refs: list[str] = []
    for module in modules:
        react = module.get("react") if isinstance(module.get("react"), Mapping) else {}
        raw_tools = module.get(
            "tools", react.get("tools") if isinstance(react, Mapping) else []
        )
        if isinstance(raw_tools, list):
            module_tool_refs.extend(
                str(item) for item in raw_tools if str(item).strip()
            )
        raw_declared_refs = (
            react.get("declared_tool_refs") if isinstance(react, Mapping) else []
        )
        if isinstance(raw_declared_refs, list):
            module_tool_refs.extend(
                str(item) for item in raw_declared_refs if str(item).strip()
            )
    referenced_tool_ids = sorted(set(module_tool_refs))
    contracts_by_id = {
        str(contract.get("tool_id") or ""): contract for contract in contracts
    }
    missing_contracts = sorted(set(module_tool_refs) - set(declared_tool_ids))
    referenced_contracts = [
        contracts_by_id[tool_id]
        for tool_id in referenced_tool_ids
        if tool_id in contracts_by_id
    ]
    non_pure_refs = sorted(
        str(contract.get("tool_id") or "")
        for contract in referenced_contracts
        if str(contract.get("effect_class") or "") != "pure"
    )
    schema_unready_refs = sorted(
        str(contract.get("tool_id") or "")
        for contract in referenced_contracts
        if not _schema_is_bounded(dict(contract.get("args_schema") or {}))
        or not _schema_is_bounded(dict(contract.get("return_schema") or {}))
    )
    blueprint_unready_refs = sorted(
        str(contract.get("tool_id") or "")
        for contract in referenced_contracts
        if not isinstance(contract.get("generated_adapter_blueprint"), Mapping)
        or contract["generated_adapter_blueprint"].get("status")
        != "blueprint_recorded_not_executable"
        or not _adapter_blueprint_hash_bound(
            dict(contract.get("generated_adapter_blueprint") or {})
        )
    )
    replay_policy_unready_refs = sorted(
        str(contract.get("tool_id") or "")
        for contract in referenced_contracts
        if not isinstance(contract.get("generated_adapter_policy"), Mapping)
        or "receipt replay must verify adapter hash and trace consistency"
        not in contract["generated_adapter_policy"].get(
            "required_before_enablement", []
        )
    )
    adapter_blockers = [
        "generated_adapter.exists is false for every tool contract",
        "program_generated_policy still forbids dspy.Tool materialization",
        "runtime_policy.dspy_tool_materialization_allowed is false",
        "tool execution receipt/replay adapter hashes are not present",
    ]
    if missing_contracts:
        adapter_blockers.append(
            f"ReActV2 module tool refs missing descriptor contracts: {missing_contracts}"
        )
    if non_pure_refs:
        adapter_blockers.append(
            f"ReActV2 module tool refs are not pure-effect contracts: {non_pure_refs}"
        )
    if schema_unready_refs:
        adapter_blockers.append(
            f"ReActV2 module tool refs missing bounded args/return schemas: {schema_unready_refs}"
        )
    if blueprint_unready_refs:
        adapter_blockers.append(
            f"ReActV2 module tool refs missing hash-bound non-executable adapter blueprints: {blueprint_unready_refs}"
        )
    if replay_policy_unready_refs:
        adapter_blockers.append(
            f"ReActV2 module tool refs missing replay-policy preconditions: {replay_policy_unready_refs}"
        )
    if requested and not contracts and module_tool_refs:
        adapter_blockers.append("ReActV2 requested tools but no tool contracts exist")
    adapter_materialization_ready = bool(referenced_tool_ids) and not (
        missing_contracts
        or non_pure_refs
        or schema_unready_refs
        or blueprint_unready_refs
        or replay_policy_unready_refs
    )
    pure_tool_preflight = {
        "referenced_tool_ids": referenced_tool_ids,
        "missing_tool_contracts": missing_contracts,
        "non_pure_tool_refs": non_pure_refs,
        "schema_unready_tool_refs": schema_unready_refs,
        "blueprint_unready_tool_refs": blueprint_unready_refs,
        "replay_policy_unready_tool_refs": replay_policy_unready_refs,
        "all_referenced_tools_have_pure_contracts": bool(referenced_tool_ids)
        and not missing_contracts
        and not non_pure_refs,
        "all_referenced_tool_schemas_bounded": bool(referenced_tool_ids)
        and not schema_unready_refs
        and not missing_contracts,
        "all_referenced_adapter_blueprints_hash_bound": bool(referenced_tool_ids)
        and not blueprint_unready_refs
        and not missing_contracts,
        "all_referenced_tools_have_replay_policy_preconditions": bool(
            referenced_tool_ids
        )
        and not replay_policy_unready_refs
        and not missing_contracts,
        "ready_for_tool_adapter_materialization": adapter_materialization_ready,
        "materialization_status": "ready_for_generated_adapter_materialization"
        if adapter_materialization_ready
        else "blocked_until_pure_contracts_schemas_blueprints_and_replay_policy",
    }
    return {
        "schema_version": "program-react-v2-tool-readiness-v1",
        "react_v2_requested": requested,
        "react_v2_module_count": len(modules),
        "declared_tool_contract_count": len(contracts),
        "declared_tool_ids": declared_tool_ids,
        "react_v2_module_tool_refs": module_tool_refs,
        "missing_tool_contracts": missing_contracts,
        "pure_tool_adapter_preflight": pure_tool_preflight,
        "ready_for_react_v2_no_tool_materialization": requested
        and not module_tool_refs,
        "ready_for_react_v2_tool_binding": False,
        "status": "blocked_until_generated_tool_adapter_policy"
        if requested and (contracts or module_tool_refs)
        else "not_requested_or_no_tool_need",
        "production_readiness_blockers": adapter_blockers
        if requested and (contracts or module_tool_refs)
        else [],
        "next_actions": [
            "Keep ReActV2 tools=[] for materialization until generated tool adapters are policy-approved.",
            "For every desired tool, declare a descriptor-only tool capability with schemas, effect class, allowlists, timeout, redaction, and mutation posture.",
            "Land generated dspy.Tool adapter policy with adapter hashes/provenance and replay checks before enabling tool binding.",
        ],
        "effect": {
            "tool_called": False,
            "dspy_tool_bound": False,
            "network": False,
            "filesystem_write": False,
            "subprocess": False,
            "external_authority_mutated": False,
        },
    }


def materialize_program_tool_adapter_blueprints(
    payload: Mapping[str, Any], root: Path
) -> dict[str, Any]:
    """Write non-executable tool adapter blueprint/source files into a candidate dir.

    These files are provenance/review artifacts only. They are not imported, bound
    to ``dspy.Tool``, or executed by generated programs.
    """

    updated = dict(payload)
    contracts: list[dict[str, Any]] = []
    used_artifact_paths: dict[str, str] = {}
    adapter_dir = root / "tool_adapters"
    for raw_contract in payload.get("contracts") or []:
        if not isinstance(raw_contract, Mapping):
            continue
        contract = dict(raw_contract)
        blueprint = dict(contract.get("generated_adapter_blueprint") or {})
        generated_adapter = dict(contract.get("generated_adapter") or {})
        tool_id = str(contract.get("tool_id") or blueprint.get("tool_id") or "tool")
        adapter_dir.mkdir(parents=True, exist_ok=True)
        sanitized_tool_id = sanitize_ident(tool_id, fallback="tool")
        if blueprint.get("status") == "blueprint_recorded_not_executable":
            blueprint_filename = f"{sanitized_tool_id}_adapter_blueprint.py"
            blueprint_artifact_path = f"tool_adapters/{blueprint_filename}"
            prior_tool_id = used_artifact_paths.setdefault(
                blueprint_artifact_path, tool_id
            )
            if prior_tool_id != tool_id:
                raise ValueError(
                    "tool adapter artifact path collision after sanitization: "
                    f"{prior_tool_id!r} and {tool_id!r} -> {blueprint_artifact_path}"
                )
            blueprint_path = adapter_dir / blueprint_filename
            blueprint_source = str(blueprint.get("source_preview") or "")
            blueprint_path.write_text(blueprint_source, encoding="utf-8")
            blueprint["artifact"] = {
                "path": blueprint_artifact_path,
                "content_hash": sha256_text(blueprint_source),
                "executable": False,
                "imported_by_generated_program": False,
            }
        if (
            blueprint.get("status") == "blueprint_recorded_not_executable"
            and generated_adapter.get("execution_allowed") is False
            and generated_adapter.get("dspy_tool_binding_allowed") is False
        ):
            adapter_filename = f"{sanitized_tool_id}_adapter.py"
            adapter_artifact_path = f"tool_adapters/{adapter_filename}"
            prior_tool_id = used_artifact_paths.setdefault(
                adapter_artifact_path, tool_id
            )
            if prior_tool_id != tool_id:
                raise ValueError(
                    "tool adapter artifact path collision after sanitization: "
                    f"{prior_tool_id!r} and {tool_id!r} -> {adapter_artifact_path}"
                )
            adapter_path = adapter_dir / adapter_filename
            adapter_source = str(generated_adapter.get("source_preview") or "")
            compile(adapter_source, f"tool_adapters/{adapter_filename}", "exec")
            adapter_path.write_text(adapter_source, encoding="utf-8")
            adapter_hash = sha256_text(adapter_source)
            generated_adapter.update(
                {
                    "exists": True,
                    "content_hash": adapter_hash,
                    "source_hash": adapter_hash,
                    "artifact": {
                        "path": adapter_artifact_path,
                        "content_hash": adapter_hash,
                        "executable": False,
                        "imported_by_generated_program": False,
                    },
                    "provenance": {
                        "source": "program_tool_contracts.generated_adapter.source_preview",
                        "materialized_by": "program-gen",
                        "status": "materialized_not_bound_not_executed",
                    },
                    "validation": {
                        "schema_version": "program-tool-generated-adapter-validation-v1",
                        "status": "validated_not_bound_not_executed",
                        "source_compiles": True,
                        "constants_match_contract": True,
                        "source_hash_matches_artifact": True,
                        "dry_run_supported": True,
                        "dry_run_expected_result": _adapter_dry_run_expected_result(
                            tool_id=tool_id,
                            args_schema=dict(contract.get("args_schema") or {}),
                            return_schema=dict(contract.get("return_schema") or {}),
                        ),
                        "execution_allowed": False,
                        "dspy_tool_binding_allowed": False,
                        "imported_by_generated_program": False,
                    },
                }
            )
        policy_for_adapter = dict(contract.get("generated_adapter_policy") or {})
        if generated_adapter.get("exists") is True:
            policy_for_adapter["status"] = "adapter_source_materialized_not_bound"
            policy_for_adapter["source_hash_bound"] = True
            policy_for_adapter["artifact_hash_bound"] = True
            policy_for_adapter["execution_allowed"] = False
            policy_for_adapter["dspy_tool_binding_allowed"] = False
        contract["generated_adapter_blueprint"] = blueprint
        contract["generated_adapter"] = generated_adapter
        contract["generated_adapter_policy"] = policy_for_adapter
        contracts.append(contract)
    updated["contracts"] = contracts
    policy = dict(updated.get("tool_adapter_policy") or {})
    artifact_count = sum(
        1
        for contract in contracts
        if isinstance(contract.get("generated_adapter_blueprint"), Mapping)
        and isinstance(contract["generated_adapter_blueprint"].get("artifact"), Mapping)
    )
    generated_adapter_count = sum(
        1
        for contract in contracts
        if isinstance(contract.get("generated_adapter"), Mapping)
        and contract["generated_adapter"].get("exists") is True
        and isinstance(contract["generated_adapter"].get("artifact"), Mapping)
    )
    if artifact_count or generated_adapter_count:
        policy["status"] = "adapter_source_artifacts_written_not_bound"
        policy["adapter_blueprint_artifact_count"] = artifact_count
        policy["generated_adapter_count"] = generated_adapter_count
        policy["all_adapters_hash_bound"] = generated_adapter_count > 0
        policy["dspy_tool_binding_allowed"] = False
        policy["tool_execution_allowed"] = False
        updated["tool_adapter_policy"] = policy
    return updated


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
    blueprint_count = sum(
        1
        for contract in contracts
        if contract["generated_adapter_blueprint"]["status"]
        == "blueprint_recorded_not_executable"
    )
    return {
        "schema_version": PROGRAM_TOOL_CONTRACTS_SCHEMA,
        "status": "descriptor_only_no_tool_binding",
        "tool_contract_count": len(contracts),
        "contracts": contracts,
        "tool_adapter_policy": {
            "schema_version": "program-tool-adapter-policy-v1",
            "status": "adapter_blueprints_recorded_not_executable"
            if blueprint_count
            else "no_generated_adapters_present",
            "generated_adapter_count": 0,
            "adapter_blueprint_count": blueprint_count,
            "all_adapters_hash_bound": False,
            "all_adapters_replay_checked": False,
            "dspy_tool_binding_allowed": False,
            "tool_execution_allowed": False,
            "next_required_slice": "generate_hash_bound_dspy_tool_adapters_with_replay_visible_traces",
        },
        "react_v2_tool_readiness": _react_v2_tool_readiness(
            intent=intent, contracts=contracts
        ),
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
