from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from dspx.cache import make_key
from dspx.run_receipts import (
    EXECUTION_REPLAY_POLICY_VERSION,
    RUN_RECEIPT_VERSION,
    canonical_replay_identity_hash,
    current_execution_replay_runtime_identity,
    load_run_receipt,
)
from dspx.services.program_contracts import sanitize_ident
from dspx.services.program_evidence_closure import (
    collect_candidate_artifact_declarations,
    validate_candidate_artifact_closure,
)
from dspx.services.program_runtime_traces import validate_program_runtime_traces


_REQUIRED_FIELDS: tuple[str, ...] = (
    "receipt_version",
    "created_at",
    "run_kind",
    "provider",
    "output_path",
    "hash",
    "template_version",
    "cache_key",
    "cache_file",
    "cache_enabled",
    "replay_inputs",
)

_RUN_KIND_TO_CACHE_KIND: dict[str, str] = {
    "signature-gen": "signature",
    "signature-refine": "signature",
    "module-gen": "module",
    "program-gen": "program",
    "program-runtime": "program-runtime",
    "codegen": "codegen",
}

_REQUIRED_REPLAY_INPUTS: dict[str, tuple[str, ...]] = {
    "signature-gen": ("prompt", "template_version", "options"),
    "signature-refine": (
        "prompt",
        "template_version",
        "attempts",
        "non_interactive",
        "wrap_script",
        "feedback",
        "constraints",
    ),
    "module-gen": (
        "name",
        "description",
        "inputs",
        "outputs",
        "use_signature",
        "template_version",
    ),
    "program-gen": ("intent",),
    "program-runtime": (
        "candidate_manifest_path",
        "candidate_manifest_sha256",
        "candidate_receipt_path",
        "candidate_receipt_sha256",
        "runtime_inputs_sha256",
        "replay_fixture_path",
        "replay_fixture_sha256",
        "contract_mode",
        "skip_oracle_index",
        "publication_preflight_requested",
        "expected_episode",
    ),
    "codegen": ("spec", "language", "template_version", "options"),
}


_ISSUE_RECEIPT_NOT_FOUND = "receipt_not_found"
_ISSUE_RECEIPT_INVALID_JSON_OBJECT = "receipt_invalid_json_object"
_ISSUE_RECEIPT_MISSING_REQUIRED_FIELD = "receipt_missing_required_field"
_ISSUE_RECEIPT_UNSUPPORTED_VERSION = "receipt_unsupported_version"
_ISSUE_RECEIPT_UNSUPPORTED_RUN_KIND = "receipt_unsupported_run_kind"
_ISSUE_RECEIPT_INVALID_OUTPUT_PATH = "receipt_invalid_output_path"
_ISSUE_RECEIPT_INVALID_HASH = "receipt_invalid_hash"
_ISSUE_RECEIPT_INVALID_CACHE_KEY = "receipt_invalid_cache_key"
_ISSUE_RECEIPT_INVALID_CACHE_FILE = "receipt_invalid_cache_file"
_ISSUE_RECEIPT_INVALID_CACHE_ENABLED = "receipt_invalid_cache_enabled"
_ISSUE_RECEIPT_INVALID_REPLAY_INPUTS = "receipt_invalid_replay_inputs"
_ISSUE_RECEIPT_REPLAY_INPUTS_MISSING_KEYS = "receipt_replay_inputs_missing_keys"
_ISSUE_OUTPUT_MISSING = "output_missing"
_ISSUE_OUTPUT_HASH_MISMATCH = "output_hash_mismatch"
_ISSUE_CACHE_LINKAGE_BASENAME_MISMATCH = "cache_linkage_basename_mismatch"
_ISSUE_CACHE_LINKAGE_KIND_MISMATCH = "cache_linkage_kind_mismatch"
_ISSUE_CACHE_KEY_RECOMPUTE_UNSUPPORTED = "cache_key_recompute_unsupported"
_ISSUE_CACHE_KEY_MISMATCH = "cache_key_mismatch"
_ISSUE_CACHE_FILE_MISSING = "cache_file_missing"
_ISSUE_CACHE_FILE_INVALID_JSON_OBJECT = "cache_file_invalid_json_object"
_ISSUE_CACHE_CODE_MISSING = "cache_code_missing"
_ISSUE_CACHE_CODE_HASH_MISMATCH = "cache_code_hash_mismatch"
_ISSUE_PROGRAM_MANIFEST_INVALID_JSON_OBJECT = "program_manifest_invalid_json_object"
_ISSUE_PROGRAM_EVIDENCE_ARTIFACT_MISSING = "program_evidence_artifact_missing"
_ISSUE_PROGRAM_EVIDENCE_HASH_MISMATCH = "program_evidence_hash_mismatch"
_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH = "program_evidence_declaration_mismatch"
_ISSUE_EXECUTION_REPLAY_UNSUPPORTED_KIND = "execution_replay_unsupported_kind"
_ISSUE_EXECUTION_REPLAY_UNSUPPORTED_PROVIDER = "execution_replay_unsupported_provider"
_ISSUE_EXECUTION_REPLAY_UNSUPPORTED_INPUTS = "execution_replay_unsupported_inputs"
_ISSUE_EXECUTION_REPLAY_POLICY_MISSING = "execution_replay_policy_missing"
_ISSUE_EXECUTION_REPLAY_UNSUPPORTED_EFFECTS = "execution_replay_unsupported_effects"
_ISSUE_EXECUTION_REPLAY_IDENTITY_DRIFT = "execution_replay_identity_drift"
_ISSUE_EXECUTION_REPLAY_PROCESS_FAILED = "execution_replay_process_failed"
_ISSUE_EXECUTION_REPLAY_UNEXPECTED_EFFECT = "execution_replay_unexpected_effect"
_ISSUE_EXECUTION_REPLAY_OUTPUT_INVALID = "execution_replay_output_invalid"
_ISSUE_EXECUTION_REPLAY_OUTPUT_EXISTS = "execution_replay_output_exists"
_ISSUE_EXECUTION_REPLAY_OUTPUT_HASH_MISMATCH = "execution_replay_output_hash_mismatch"
_ISSUE_EXECUTION_REPLAY_WRITE_FAILED = "execution_replay_write_failed"

_EXECUTION_REPLAY_KIND = "signature-gen"
_EXECUTION_REPLAY_PROVIDER = "stub"
_EXECUTION_REPLAY_STRATEGY = "signature-gen-local-reexecution"
_EXECUTION_REPLAY_EFFECTS: dict[str, bool] = {
    "network_access_requested": False,
    "network_isolation_enforced": False,
    "provider_call": False,
    "mlflow": False,
    "subprocess": True,
    "temporary_filesystem": True,
    "external_filesystem_access_requested": False,
    "external_filesystem_isolation_enforced": False,
    "source_artifact_write": False,
    "shared_oracle": False,
    "external_authority_mutation_requested": False,
    "explicit_replay_output_write": True,
}
_EXECUTION_REPLAY_SIGNATURE_OPTION_KEYS = {
    "class_name",
    "constraints",
    "feedback",
    "inputs",
    "max_attempts",
    "outputs",
}


ValidationIssue = tuple[str, str]


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _schema_required_fields(schema: Mapping[str, Any]) -> list[str]:
    required = schema.get("required")
    if not isinstance(required, list):
        return []
    return sorted(str(item) for item in required if isinstance(item, str))


def _expected_tool_adapter_dry_run_result(
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


def _generated_tool_adapter_dry_run_valid(
    source: str,
    *,
    tool_id: str,
    args_schema: Mapping[str, Any],
    return_schema: Mapping[str, Any],
    expected_result: Mapping[str, Any],
) -> bool:
    """Validate the adapter dry-run receipt contract without executing source.

    Replay verification must never execute generated candidate artifacts. The dry-run
    contract is therefore checked by comparing the recorded expected result against
    the bounded schema-derived shape and by requiring the source to declare the dry
    run and disabled adapter entrypoints. Full source safety is enforced separately
    by ``_generated_tool_adapter_source_semantic_valid``.
    """

    try:
        tree = ast.parse(source, filename="tool_adapter.py")
    except SyntaxError:
        return False
    function_names = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    if {"adapter_dry_run", "adapter"} - function_names:
        return False
    expected = _expected_tool_adapter_dry_run_result(
        tool_id=tool_id,
        args_schema=args_schema,
        return_schema=return_schema,
    )
    if dict(expected_result) != expected:
        return False
    effects = expected_result.get("effects")
    return isinstance(effects, Mapping) and all(
        value is False for value in effects.values()
    )


def _runtime_trace_tool_intents_match_contracts(
    traces_payload: Mapping[str, Any],
    tool_payload: Mapping[str, Any],
    module_surfaces_payload: Mapping[str, Any] | None = None,
) -> bool:
    contracts_by_id: dict[str, Mapping[str, Any]] = {}
    for raw_contract in _as_list(tool_payload.get("contracts")):
        if not isinstance(raw_contract, Mapping):
            return False
        tool_id = str(raw_contract.get("tool_id") or "")
        if not tool_id:
            return False
        contracts_by_id[tool_id] = raw_contract

    surface_refs_by_module: dict[str, list[str]] = {}
    if module_surfaces_payload is not None:
        for raw_surface in _as_list(module_surfaces_payload.get("module_surfaces")):
            if not isinstance(raw_surface, Mapping):
                return False
            module_id = str(raw_surface.get("module_id") or "")
            if not module_id:
                return False
            primitive = str(raw_surface.get("primitive") or "")
            react = raw_surface.get("react")
            if primitive in {"ReAct", "ReActV2"}:
                if not isinstance(react, Mapping):
                    return False
                surface_refs_by_module[module_id] = sorted(
                    str(item)
                    for item in _as_list(react.get("declared_tool_refs"))
                    if str(item).strip()
                )
            else:
                surface_refs_by_module[module_id] = []

    for raw_call in _as_list(traces_payload.get("module_calls")):
        if not isinstance(raw_call, Mapping):
            return False
        slots = raw_call.get("trajectory_slots")
        if not isinstance(slots, Mapping):
            return False
        tool_refs = slots.get("tool_refs")
        declared_refs = []
        if isinstance(tool_refs, Mapping):
            declared_refs = [
                str(item)
                for item in _as_list(tool_refs.get("declared_tool_refs"))
                if str(item).strip()
            ]
        module_id = str(raw_call.get("module_id") or "")
        if module_surfaces_payload is not None:
            if module_id not in surface_refs_by_module:
                return False
            if sorted(declared_refs) != surface_refs_by_module[module_id]:
                return False
        raw_intents = slots.get("tool_call_intents", [])
        if raw_intents in (None, []):
            if declared_refs:
                return False
            continue
        if not isinstance(raw_intents, list):
            return False
        intent_ids: list[str] = []
        for raw_intent in raw_intents:
            if not isinstance(raw_intent, Mapping):
                return False
            tool_id = str(raw_intent.get("tool_id") or "")
            intent_ids.append(tool_id)
            contract = contracts_by_id.get(tool_id)
            if contract is None:
                return False
            if str(contract.get("effect_class") or "") != "pure":
                return False
            generated_adapter = _as_dict(contract.get("generated_adapter"))
            validation = _as_dict(generated_adapter.get("validation"))
            generated_adapter_policy = _as_dict(
                contract.get("generated_adapter_policy")
            )
            if generated_adapter.get("exists") is not True:
                return False
            if validation.get("dry_run_supported") is not True:
                return False
            if not isinstance(validation.get("dry_run_expected_result"), Mapping):
                return False
            if generated_adapter_policy.get("source_hash_bound") is not True:
                return False
            if generated_adapter_policy.get("artifact_hash_bound") is not True:
                return False
            for key in ("tool_call_executed", "dspy_tool_bound", "result_recorded"):
                if raw_intent.get(key) is not False:
                    return False
        if sorted(intent_ids) != sorted(set(declared_refs)):
            return False
    return True


def _react_v2_readiness_matches_surfaces_and_contracts(
    tool_payload: Mapping[str, Any], module_surfaces_payload: Mapping[str, Any]
) -> bool:
    readiness = tool_payload.get("react_v2_tool_readiness")
    if not isinstance(readiness, Mapping):
        return False
    preflight = readiness.get("pure_tool_adapter_preflight")
    if not isinstance(preflight, Mapping):
        return False

    contract_ids: list[str] = []
    contracts_by_id: dict[str, Mapping[str, Any]] = {}
    for raw_contract in _as_list(tool_payload.get("contracts")):
        if not isinstance(raw_contract, Mapping):
            return False
        tool_id = str(raw_contract.get("tool_id") or "")
        if not tool_id:
            return False
        contract_ids.append(tool_id)
        contracts_by_id[tool_id] = raw_contract

    surface_refs: list[str] = []
    react_v2_module_count = 0
    for raw_surface in _as_list(module_surfaces_payload.get("module_surfaces")):
        if not isinstance(raw_surface, Mapping):
            return False
        if str(raw_surface.get("primitive") or "") != "ReActV2":
            continue
        react_v2_module_count += 1
        react = raw_surface.get("react")
        if not isinstance(react, Mapping):
            return False
        surface_refs.extend(
            str(item)
            for item in _as_list(react.get("declared_tool_refs"))
            if str(item).strip()
        )

    referenced_tool_ids = sorted(set(surface_refs))
    missing_contracts = sorted(set(surface_refs) - set(contract_ids))
    if sorted(_as_list(readiness.get("declared_tool_ids"))) != sorted(contract_ids):
        return False
    if readiness.get("react_v2_module_count") != react_v2_module_count:
        return False
    if sorted(_as_list(readiness.get("react_v2_module_tool_refs"))) != sorted(
        surface_refs
    ):
        return False
    if sorted(_as_list(readiness.get("missing_tool_contracts"))) != missing_contracts:
        return False
    if sorted(_as_list(preflight.get("referenced_tool_ids"))) != referenced_tool_ids:
        return False
    if readiness.get("ready_for_react_v2_tool_binding") is not False:
        return False
    if referenced_tool_ids:
        if preflight.get("ready_for_tool_adapter_materialization") is not True:
            return False
        for tool_id in referenced_tool_ids:
            contract = contracts_by_id.get(tool_id)
            if contract is None or str(contract.get("effect_class") or "") != "pure":
                return False
            generated_adapter = _as_dict(contract.get("generated_adapter"))
            validation = _as_dict(generated_adapter.get("validation"))
            if generated_adapter.get("exists") is not True:
                return False
            if validation.get("dry_run_supported") is not True:
                return False
    return True


def _generated_tool_adapter_source_semantic_valid(
    source: str,
    *,
    tool_id: str,
    effect_class: str,
    args_schema: Mapping[str, Any],
    return_schema: Mapping[str, Any],
) -> bool:
    try:
        tree = ast.parse(source, filename="tool_adapter.py")
    except SyntaxError:
        return False
    constants: dict[str, Any] = {}
    required_functions = {
        "_type_matches",
        "_validate_value",
        "_validate_object",
        "validate_args",
        "validate_return",
        "adapter_dry_run",
        "adapter",
    }
    seen_functions: set[str] = set()
    allowed_constants = {
        "TOOL_ID",
        "EFFECT_CLASS",
        "ARGS_SCHEMA",
        "RETURN_SCHEMA",
        "EXECUTION_ALLOWED",
        "DSPY_TOOL_BINDING_ALLOWED",
        "IMPORTED_BY_GENERATED_PROGRAM",
    }
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            seen_functions.add(node.name)
            if node.name not in required_functions:
                return False
            if node.decorator_list:
                return False
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if not isinstance(target, ast.Name) or target.id not in allowed_constants:
                return False
            try:
                constants[target.id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                return False
            continue
        return False
    if not required_functions <= seen_functions:
        return False
    if constants.get("TOOL_ID") != tool_id:
        return False
    if constants.get("EFFECT_CLASS") != effect_class:
        return False
    if constants.get("ARGS_SCHEMA") != dict(args_schema):
        return False
    if constants.get("RETURN_SCHEMA") != dict(return_schema):
        return False
    if constants.get("EXECUTION_ALLOWED") is not False:
        return False
    if constants.get("DSPY_TOOL_BINDING_ALLOWED") is not False:
        return False
    if constants.get("IMPORTED_BY_GENERATED_PROGRAM") is not False:
        return False
    allowed_call_names = {
        "RuntimeError",
        "TypeError",
        "ValueError",
        "_type_matches",
        "_validate_object",
        "_validate_value",
        "dict",
        "enumerate",
        "isinstance",
        "len",
        "set",
        "sorted",
        "validate_args",
        "validate_return",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id not in allowed_call_names:
                    return False
            elif isinstance(func, ast.Attribute):
                if func.attr not in {"get", "items"}:
                    return False
            else:
                return False
    return True


def _program_runtime_outcomes_semantic_valid(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("schema_version") != "program-runtime-outcomes-v1":
        return False
    if payload.get("status") != "outcome_contracts_declared":
        return False
    outcomes = payload.get("outcomes")
    if not isinstance(outcomes, list):
        return False
    if payload.get("module_outcome_count") != len(outcomes):
        return False
    policy = payload.get("runtime_policy")
    if not isinstance(policy, Mapping):
        return False
    for key in [
        "materialization_executed_modules",
        "records_actual_runtime_trace",
        "tool_binding_allowed",
        "live_external_retriever_allowed",
        "network_allowed",
        "filesystem_access_allowed",
    ]:
        if policy.get(key) is not False:
            return False
    if policy.get("react_v2_tools_require_program_tool_contracts") is not True:
        return False
    for raw_outcome in outcomes:
        if not isinstance(raw_outcome, Mapping):
            return False
        outcome = dict(raw_outcome)
        if outcome.get("status") != "outcome_contract_declared_not_runtime_trace":
            return False
        if not isinstance(outcome.get("module_id"), str) or not outcome.get(
            "module_id"
        ):
            return False
        if not isinstance(outcome.get("primitive"), str) or not outcome.get(
            "primitive"
        ):
            return False
        signature = outcome.get("signature")
        if not isinstance(signature, Mapping):
            return False
        outputs = signature.get("outputs")
        if not isinstance(outputs, list):
            return False
        if outcome.get("final_outputs") != outputs:
            return False
        effects = outcome.get("effects")
        if not isinstance(effects, Mapping):
            return False
        for key in [
            "tool_called",
            "custom_import_loaded",
            "network",
            "filesystem_write",
            "subprocess",
            "external_authority",
        ]:
            if effects.get(key) is not False:
                return False
        if not isinstance(outcome.get("trace_contract"), Mapping):
            return False
        trace_contract = dict(outcome["trace_contract"])
        if outcome.get("primitive") in {"ReAct", "ReActV2"}:
            tool_refs = trace_contract.get("tool_refs")
            if not isinstance(tool_refs, Mapping):
                return False
            if tool_refs.get("tool_binding_allowed") is not False:
                return False
            if tool_refs.get("tool_binding_status") != "declared_refs_only_not_bound":
                return False
            if tool_refs.get("executable_tools") != []:
                return False
    return True


def _program_module_surfaces_semantic_valid(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("schema_version") != "program-module-surfaces-v1":
        return False
    surfaces = payload.get("module_surfaces")
    if not isinstance(surfaces, list):
        return False
    if payload.get("module_surface_count") != len(surfaces):
        return False
    for raw_surface in surfaces:
        if not isinstance(raw_surface, Mapping):
            return False
        surface = dict(raw_surface)
        if surface.get("schema_version") != "program-module-surface-v1":
            return False
        if not isinstance(surface.get("module_id"), str) or not surface.get(
            "module_id"
        ):
            return False
        if not isinstance(surface.get("primitive"), str) or not surface.get(
            "primitive"
        ):
            return False
        signature = surface.get("signature")
        if not isinstance(signature, Mapping):
            return False
        if not isinstance(signature.get("inputs"), list) or not isinstance(
            signature.get("outputs"), list
        ):
            return False
        effects = surface.get("effects")
        if not isinstance(effects, Mapping):
            return False
        for key in [
            "tool_called",
            "custom_import_loaded",
            "network",
            "filesystem_write",
            "subprocess",
            "external_authority",
        ]:
            if effects.get(key) is not False:
                return False
        stage = surface.get("stage")
        if stage is not None:
            if not isinstance(stage, Mapping):
                return False
            if set(stage) - {"role", "metadata_source"}:
                return False
            if not isinstance(stage.get("role"), str) or not stage.get("role"):
                return False
            if stage.get("metadata_source") != "program_intent_topology_module.role":
                return False
        react = surface.get("react")
        if isinstance(react, Mapping):
            if react.get("tool_binding_allowed", False) is not False:
                return False
            if (
                react.get("tool_binding_status", "declared_refs_only_not_bound")
                != "declared_refs_only_not_bound"
            ):
                return False
        retriever = surface.get("retriever")
        if isinstance(retriever, Mapping) and retriever.get("mode") not in {
            "inline_corpus",
            "local_corpus_snapshot",
        }:
            return False
    return True


def _infer_output_path_from_meta(meta_path: Path) -> Path | None:
    suffix = ".meta.json"
    name = meta_path.name
    if name.endswith(suffix):
        return meta_path.parent / name[: -len(suffix)]
    return None


def _resolve_path(
    raw_path: str,
    *,
    meta_path: Path,
    output_hint: bool = False,
    allow_external_absolute: bool = False,
) -> Path:
    """Resolve a receipt-supplied path, confining it under the meta_path root."""
    from dspx.security import confine_path

    root = meta_path.parent.resolve()
    p = Path(raw_path).expanduser()
    if p.is_absolute() and allow_external_absolute:
        resolved_absolute = p.resolve()
        allowed_roots = [root]
        try:
            from dspx.cache import cache_dir

            allowed_roots.append(cache_dir().resolve())
        except Exception:
            pass
        for allowed_root in allowed_roots:
            try:
                resolved_absolute.relative_to(allowed_root)
                return resolved_absolute
            except ValueError:
                continue
        raise ValueError(
            f"receipt path escapes allowed receipt/cache roots: {raw_path}"
        )

    candidates: list[Path] = [confine_path(root, p)]

    if output_hint:
        inferred = _infer_output_path_from_meta(meta_path)
        if inferred is not None:
            confined_inferred = confine_path(root, inferred)
            if confined_inferred not in candidates:
                candidates.append(confined_inferred)

    for cand in candidates:
        if cand.exists():
            return cand

    # Stable fallback for diagnostics: prefer the receipt-relative interpretation.
    return candidates[0]


def _exclusive_write_confined(root: Path, target: Path, payload: bytes) -> int:
    """Create one file through no-follow directory descriptors below ``root``."""
    if os.name != "posix" or not all(
        hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")
    ):
        raise OSError("secure receipt-local output creation is unavailable")
    relative = target.relative_to(root)
    if not relative.parts:
        raise OSError("refusing to replace replay root")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    parent_fd = os.dup(root_fd)
    os.close(root_fd)
    try:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        for component in relative.parts[:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_fd
        file_fd = os.open(
            relative.parts[-1],
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        try:
            with os.fdopen(file_fd, "wb", closefd=False) as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
        finally:
            os.close(file_fd)
    finally:
        os.close(parent_fd)
    return len(payload)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(64 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def _nested_dict(root: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = root
    for key in keys:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(key)
    return dict(current) if isinstance(current, Mapping) else {}


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _add_error(
    report: dict[str, Any],
    *,
    code: str,
    message: str,
    check: str | None = None,
) -> None:
    errors = report.get("errors")
    if not isinstance(errors, list):
        errors = []
        report["errors"] = errors
    errors.append(message)

    error_codes = report.get("error_codes")
    if not isinstance(error_codes, list):
        error_codes = []
        report["error_codes"] = error_codes
    if code not in error_codes:
        error_codes.append(code)

    error_details = report.get("error_details")
    if not isinstance(error_details, list):
        error_details = []
        report["error_details"] = error_details
    detail: dict[str, str] = {"code": code, "message": message}
    if check is not None:
        detail["check"] = check
    error_details.append(detail)


def _validate_receipt(receipt: Mapping[str, Any]) -> list[ValidationIssue]:
    errors: list[ValidationIssue] = []

    for key in _REQUIRED_FIELDS:
        if key not in receipt:
            errors.append(
                (
                    _ISSUE_RECEIPT_MISSING_REQUIRED_FIELD,
                    f"missing required field: {key}",
                )
            )

    if errors:
        return errors

    if str(receipt.get("receipt_version") or "") != RUN_RECEIPT_VERSION:
        errors.append(
            (
                _ISSUE_RECEIPT_UNSUPPORTED_VERSION,
                f"unsupported receipt_version: {receipt.get('receipt_version')!r}",
            )
        )

    run_kind = str(receipt.get("run_kind") or "")
    if run_kind not in _RUN_KIND_TO_CACHE_KIND:
        errors.append(
            (_ISSUE_RECEIPT_UNSUPPORTED_RUN_KIND, f"unsupported run_kind: {run_kind!r}")
        )

    if (
        not isinstance(receipt.get("output_path"), str)
        or not str(receipt.get("output_path")).strip()
    ):
        errors.append(
            (
                _ISSUE_RECEIPT_INVALID_OUTPUT_PATH,
                "field output_path must be a non-empty string",
            )
        )

    if not isinstance(receipt.get("hash"), str) or not str(receipt.get("hash")).strip():
        errors.append(
            (_ISSUE_RECEIPT_INVALID_HASH, "field hash must be a non-empty string")
        )

    if (
        not isinstance(receipt.get("cache_key"), str)
        or not str(receipt.get("cache_key")).strip()
    ):
        errors.append(
            (
                _ISSUE_RECEIPT_INVALID_CACHE_KEY,
                "field cache_key must be a non-empty string",
            )
        )

    if (
        not isinstance(receipt.get("cache_file"), str)
        or not str(receipt.get("cache_file")).strip()
    ):
        errors.append(
            (
                _ISSUE_RECEIPT_INVALID_CACHE_FILE,
                "field cache_file must be a non-empty string",
            )
        )

    if not isinstance(receipt.get("cache_enabled"), bool):
        errors.append(
            (_ISSUE_RECEIPT_INVALID_CACHE_ENABLED, "field cache_enabled must be bool")
        )

    replay_inputs = receipt.get("replay_inputs")
    if not isinstance(replay_inputs, Mapping):
        errors.append(
            (
                _ISSUE_RECEIPT_INVALID_REPLAY_INPUTS,
                "field replay_inputs must be an object",
            )
        )
    else:
        required_inputs = _REQUIRED_REPLAY_INPUTS.get(run_kind, ())
        missing_inputs = [k for k in required_inputs if k not in replay_inputs]
        if missing_inputs:
            errors.append(
                (
                    _ISSUE_RECEIPT_REPLAY_INPUTS_MISSING_KEYS,
                    "replay_inputs missing required keys: "
                    + ", ".join(sorted(missing_inputs)),
                )
            )

    return errors


def _program_evidence_declarations(
    *, manifest: Mapping[str, Any], receipt: Mapping[str, Any]
) -> list[dict[str, Any]]:
    declarations_by_kind: dict[str, list[dict[str, str]]] = {}

    def add(kind: str, *, path: object, content_hash: object, source: str) -> None:
        path_text = _optional_str(path)
        hash_text = _optional_str(content_hash)
        if path_text is None or hash_text is None:
            return
        declarations_by_kind.setdefault(kind, []).append(
            {
                "source": source,
                "path": path_text,
                "content_hash": hash_text,
            }
        )

    execution_episode_artifact = _nested_dict(manifest, "execution_episode_artifact")
    add(
        "execution_episode",
        path=execution_episode_artifact.get("path"),
        content_hash=execution_episode_artifact.get("content_hash"),
        source="manifest.execution_episode_artifact",
    )
    behavior_episode_artifact = _nested_dict(manifest, "behavior_episode_artifact")
    add(
        "behavior_episode",
        path=behavior_episode_artifact.get("path"),
        content_hash=behavior_episode_artifact.get("content_hash"),
        source="manifest.behavior_episode_artifact",
    )
    dataset_manifest_artifact = _nested_dict(manifest, "dataset_manifest_artifact")
    add(
        "dataset_manifest",
        path=dataset_manifest_artifact.get("path"),
        content_hash=dataset_manifest_artifact.get("content_hash"),
        source="manifest.dataset_manifest_artifact",
    )
    dataset_split_evidence = _nested_dict(manifest, "dataset_split_evidence")
    split_artifacts = _nested_dict(dataset_split_evidence, "split_artifacts")
    for split in ("train", "validation", "test"):
        split_payload = _as_dict(split_artifacts.get(split))
        add(
            f"dataset_split_{split}",
            path=split_payload.get("split_path"),
            content_hash=split_payload.get("split_hash"),
            source=f"manifest.dataset_split_evidence.{split}.split_hash",
        )
        add(
            f"dataset_split_harness_{split}",
            path=split_payload.get("eval_harness"),
            content_hash=split_payload.get("eval_harness_hash"),
            source=f"manifest.dataset_split_evidence.{split}.eval_harness_hash",
        )
        add(
            f"dataset_split_behavior_results_{split}",
            path=split_payload.get("behavior_results_path"),
            content_hash=split_payload.get("behavior_results_hash"),
            source=f"manifest.dataset_split_evidence.{split}.behavior_results_hash",
        )

    execution_episode = _nested_dict(manifest, "execution_episode")
    behavior_results = _nested_dict(execution_episode, "behavior_results")
    add(
        "behavior_results",
        path=behavior_results.get("path"),
        content_hash=behavior_results.get("content_hash"),
        source="manifest.execution_episode.behavior_results",
    )
    oracle_evidence = _nested_dict(execution_episode, "oracle_evidence")
    add(
        "oracle_evidence",
        path=oracle_evidence.get("path"),
        content_hash=oracle_evidence.get("content_hash"),
        source="manifest.execution_episode.oracle_evidence",
    )

    try:
        candidate_declarations = collect_candidate_artifact_declarations(manifest)
    except ValueError:
        candidate_declarations = ()
    for declaration in candidate_declarations:
        add(
            declaration.kind,
            path=declaration.path,
            content_hash=declaration.sha256,
            source=("manifest.candidate_assembly.surfaces." + declaration.kind),
        )

    contract_verification_artifact = _nested_dict(
        manifest, "program_architecture_contract_verification_artifact"
    )
    add(
        "contract_verification",
        path=contract_verification_artifact.get("path"),
        content_hash=contract_verification_artifact.get("content_hash"),
        source="manifest.program_architecture_contract_verification_artifact.content_hash",
    )

    evidence = _nested_dict(manifest, "receipt_bundle", "evidence")
    add(
        "module_surfaces",
        path=evidence.get("module_surfaces_path") or "module_surfaces.json",
        content_hash=evidence.get("module_surfaces_hash"),
        source="manifest.receipt_bundle.evidence.module_surfaces_hash",
    )
    add(
        "runtime_outcomes",
        path=evidence.get("runtime_outcomes_path") or "program_runtime_outcomes.json",
        content_hash=evidence.get("runtime_outcomes_hash"),
        source="manifest.receipt_bundle.evidence.runtime_outcomes_hash",
    )
    add(
        "runtime_traces",
        path=evidence.get("runtime_traces_path") or "program_runtime_traces.json",
        content_hash=evidence.get("runtime_traces_hash"),
        source="manifest.receipt_bundle.evidence.runtime_traces_hash",
    )
    add(
        "tool_contracts",
        path=evidence.get("tool_contracts_path") or "program_tool_contracts.json",
        content_hash=evidence.get("tool_contracts_hash"),
        source="manifest.receipt_bundle.evidence.tool_contracts_hash",
    )
    add(
        "capability_registry",
        path=evidence.get("capability_registry_path")
        or "program_capability_registry.json",
        content_hash=evidence.get("capability_registry_hash"),
        source="manifest.receipt_bundle.evidence.capability_registry_hash",
    )
    add(
        "generated_module_policy",
        path=evidence.get("generated_module_policy_path")
        or "generated_module_policy.json",
        content_hash=evidence.get("generated_module_policy_hash"),
        source="manifest.receipt_bundle.evidence.generated_module_policy_hash",
    )
    add(
        "intent_normalization",
        path=evidence.get("intent_normalization_path") or "intent_normalization.json",
        content_hash=evidence.get("intent_normalization_hash"),
        source="manifest.receipt_bundle.evidence.intent_normalization_hash",
    )
    add(
        "execution_episode",
        path=evidence.get("execution_episode_path") or "execution_episode.json",
        content_hash=evidence.get("execution_episode_hash"),
        source="manifest.receipt_bundle.evidence.execution_episode_hash",
    )
    add(
        "behavior_results",
        path="behavior_results.json",
        content_hash=evidence.get("behavior_results_hash"),
        source="manifest.receipt_bundle.evidence.behavior_results_hash",
    )
    add(
        "behavior_episode",
        path=evidence.get("behavior_episode_path") or "behavior_episode.json",
        content_hash=evidence.get("behavior_episode_hash"),
        source="manifest.receipt_bundle.evidence.behavior_episode_hash",
    )
    add(
        "oracle_evidence",
        path=evidence.get("oracle_evidence_path") or "oracle_evidence.json",
        content_hash=evidence.get("oracle_evidence_hash"),
        source="manifest.receipt_bundle.evidence.oracle_evidence_hash",
    )
    add(
        "dataset_manifest",
        path="dataset_manifest.json",
        content_hash=evidence.get("dataset_manifest_hash"),
        source="manifest.receipt_bundle.evidence.dataset_manifest_hash",
    )
    receipt_dataset = _nested_dict(evidence, "dataset")
    receipt_split_artifacts = _nested_dict(receipt_dataset, "split_artifacts")
    for split in ("train", "validation", "test"):
        split_payload = _as_dict(receipt_split_artifacts.get(split))
        add(
            f"dataset_split_{split}",
            path=split_payload.get("split_path"),
            content_hash=split_payload.get("split_hash"),
            source=f"manifest.receipt_bundle.evidence.dataset.{split}.split_hash",
        )
        add(
            f"dataset_split_harness_{split}",
            path=split_payload.get("eval_harness"),
            content_hash=split_payload.get("eval_harness_hash"),
            source=f"manifest.receipt_bundle.evidence.dataset.{split}.eval_harness_hash",
        )
        add(
            f"dataset_split_behavior_results_{split}",
            path=split_payload.get("behavior_results_path"),
            content_hash=split_payload.get("behavior_results_hash"),
            source=f"manifest.receipt_bundle.evidence.dataset.{split}.behavior_results_hash",
        )

    surface_hashes = _nested_dict(
        manifest, "receipt_bundle", "evidence", "surface_hashes"
    )
    add(
        "module_surfaces",
        path="module_surfaces.json",
        content_hash=surface_hashes.get("module_surfaces.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.module_surfaces.json",
    )
    add(
        "runtime_outcomes",
        path="program_runtime_outcomes.json",
        content_hash=surface_hashes.get("program_runtime_outcomes.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.program_runtime_outcomes.json",
    )
    add(
        "runtime_traces",
        path="program_runtime_traces.json",
        content_hash=surface_hashes.get("program_runtime_traces.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.program_runtime_traces.json",
    )
    add(
        "tool_contracts",
        path="program_tool_contracts.json",
        content_hash=surface_hashes.get("program_tool_contracts.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.program_tool_contracts.json",
    )
    add(
        "capability_registry",
        path="program_capability_registry.json",
        content_hash=surface_hashes.get("program_capability_registry.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.program_capability_registry.json",
    )
    add(
        "generated_module_policy",
        path="generated_module_policy.json",
        content_hash=surface_hashes.get("generated_module_policy.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.generated_module_policy.json",
    )
    add(
        "intent_normalization",
        path="intent_normalization.json",
        content_hash=surface_hashes.get("intent_normalization.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.intent_normalization.json",
    )
    add(
        "execution_episode",
        path="execution_episode.json",
        content_hash=surface_hashes.get("execution_episode.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.execution_episode.json",
    )
    add(
        "behavior_results",
        path="behavior_results.json",
        content_hash=surface_hashes.get("behavior_results.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.behavior_results.json",
    )
    add(
        "behavior_episode",
        path="behavior_episode.json",
        content_hash=surface_hashes.get("behavior_episode.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.behavior_episode.json",
    )
    add(
        "oracle_evidence",
        path="oracle_evidence.json",
        content_hash=surface_hashes.get("oracle_evidence.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.oracle_evidence.json",
    )
    add(
        "dataset_manifest",
        path="dataset_manifest.json",
        content_hash=surface_hashes.get("dataset_manifest.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.dataset_manifest.json",
    )
    for split in ("train", "validation", "test"):
        add(
            f"dataset_split_{split}",
            path=f"splits/{split}.jsonl",
            content_hash=surface_hashes.get(f"splits/{split}.jsonl"),
            source=(
                f"manifest.receipt_bundle.evidence.surface_hashes.splits/{split}.jsonl"
            ),
        )
        add(
            f"dataset_split_harness_{split}",
            path=f"eval_{split}.py",
            content_hash=surface_hashes.get(f"eval_{split}.py"),
            source=(f"manifest.receipt_bundle.evidence.surface_hashes.eval_{split}.py"),
        )
        add(
            f"dataset_split_behavior_results_{split}",
            path=f"behavior_results.{split}.json",
            content_hash=surface_hashes.get(f"behavior_results.{split}.json"),
            source=(
                "manifest.receipt_bundle.evidence.surface_hashes."
                f"behavior_results.{split}.json"
            ),
        )

    run_summary = _as_dict(receipt.get("run_summary"))
    add(
        "module_surfaces",
        path=run_summary.get("module_surfaces_path") or "module_surfaces.json",
        content_hash=run_summary.get("module_surfaces_hash"),
        source="receipt.run_summary.module_surfaces_hash",
    )
    add(
        "runtime_outcomes",
        path=run_summary.get("runtime_outcomes_path")
        or "program_runtime_outcomes.json",
        content_hash=run_summary.get("runtime_outcomes_hash"),
        source="receipt.run_summary.runtime_outcomes_hash",
    )
    add(
        "runtime_traces",
        path=run_summary.get("runtime_traces_path") or "program_runtime_traces.json",
        content_hash=run_summary.get("runtime_traces_hash"),
        source="receipt.run_summary.runtime_traces_hash",
    )
    add(
        "tool_contracts",
        path=run_summary.get("tool_contracts_path") or "program_tool_contracts.json",
        content_hash=run_summary.get("tool_contracts_hash"),
        source="receipt.run_summary.tool_contracts_hash",
    )
    add(
        "capability_registry",
        path=run_summary.get("capability_registry_path")
        or "program_capability_registry.json",
        content_hash=run_summary.get("capability_registry_hash"),
        source="receipt.run_summary.capability_registry_hash",
    )
    add(
        "generated_module_policy",
        path=run_summary.get("generated_module_policy_path")
        or "generated_module_policy.json",
        content_hash=run_summary.get("generated_module_policy_hash"),
        source="receipt.run_summary.generated_module_policy_hash",
    )
    add(
        "intent_normalization",
        path=run_summary.get("intent_normalization_path")
        or "intent_normalization.json",
        content_hash=run_summary.get("intent_normalization_hash"),
        source="receipt.run_summary.intent_normalization_hash",
    )
    add(
        "execution_episode",
        path=run_summary.get("execution_episode_path") or "execution_episode.json",
        content_hash=run_summary.get("execution_episode_hash"),
        source="receipt.run_summary.execution_episode_hash",
    )
    add(
        "behavior_results",
        path="behavior_results.json",
        content_hash=run_summary.get("behavior_results_hash"),
        source="receipt.run_summary.behavior_results_hash",
    )
    add(
        "behavior_episode",
        path=run_summary.get("behavior_episode_path") or "behavior_episode.json",
        content_hash=run_summary.get("behavior_episode_hash"),
        source="receipt.run_summary.behavior_episode_hash",
    )
    add(
        "oracle_evidence",
        path="oracle_evidence.json",
        content_hash=run_summary.get("oracle_evidence_hash"),
        source="receipt.run_summary.oracle_evidence_hash",
    )
    add(
        "dataset_manifest",
        path=run_summary.get("dataset_manifest_path") or "dataset_manifest.json",
        content_hash=run_summary.get("dataset_manifest_hash"),
        source="receipt.run_summary.dataset_manifest_hash",
    )
    summary_dataset = _nested_dict(run_summary, "dataset_split_evidence")
    summary_split_artifacts = _nested_dict(summary_dataset, "split_artifacts")
    for split in ("train", "validation", "test"):
        split_payload = _as_dict(summary_split_artifacts.get(split))
        add(
            f"dataset_split_{split}",
            path=split_payload.get("split_path"),
            content_hash=split_payload.get("split_hash"),
            source=f"receipt.run_summary.dataset_split_evidence.{split}.split_hash",
        )
        add(
            f"dataset_split_harness_{split}",
            path=split_payload.get("eval_harness"),
            content_hash=split_payload.get("eval_harness_hash"),
            source=f"receipt.run_summary.dataset_split_evidence.{split}.eval_harness_hash",
        )
        add(
            f"dataset_split_behavior_results_{split}",
            path=split_payload.get("behavior_results_path"),
            content_hash=split_payload.get("behavior_results_hash"),
            source=(
                "receipt.run_summary.dataset_split_evidence."
                f"{split}.behavior_results_hash"
            ),
        )

    receipt_behavior_episode = _nested_dict(
        receipt, "program_behavior_episode_artifact"
    )
    add(
        "behavior_episode",
        path=receipt_behavior_episode.get("path"),
        content_hash=receipt_behavior_episode.get("content_hash"),
        source="receipt.program_behavior_episode_artifact",
    )

    grouped: list[dict[str, Any]] = []
    for kind in sorted(declarations_by_kind):
        declarations = declarations_by_kind[kind]
        grouped.append(
            {
                "kind": kind,
                "path": declarations[0]["path"],
                "content_hash": declarations[0]["content_hash"],
                "declarations": declarations,
            }
        )
    return grouped


def _missing_behavior_episode_declarations(
    *, manifest: Mapping[str, Any], receipt: Mapping[str, Any]
) -> list[str]:
    artifact = _nested_dict(manifest, "behavior_episode_artifact")
    surfaces = _as_list(_nested_dict(manifest, "candidate_assembly").get("surfaces"))
    episode_surfaces = [
        item
        for item in surfaces
        if isinstance(item, Mapping) and item.get("kind") == "behavior_episode"
    ]
    evidence = _nested_dict(manifest, "receipt_bundle", "evidence")
    surface_hashes = _nested_dict(evidence, "surface_hashes")
    run_summary = _as_dict(receipt.get("run_summary"))
    receipt_artifact = _nested_dict(receipt, "program_behavior_episode_artifact")
    episode_expected = bool(
        artifact
        or episode_surfaces
        or evidence.get("behavior_episode_path")
        or evidence.get("behavior_episode_hash")
        or surface_hashes.get("behavior_episode.json")
        or run_summary.get("behavior_episode_path")
        or run_summary.get("behavior_episode_hash")
        or receipt_artifact
    )
    if not episode_expected:
        return []

    missing: list[str] = []
    requirements = {
        "manifest.behavior_episode_artifact": (
            artifact.get("path"),
            artifact.get("content_hash"),
        ),
        "manifest.candidate_assembly.surfaces.behavior_episode": (
            episode_surfaces[0].get("path") if len(episode_surfaces) == 1 else None,
            episode_surfaces[0].get("content_hash")
            if len(episode_surfaces) == 1
            else None,
        ),
        "manifest.receipt_bundle.evidence.behavior_episode": (
            evidence.get("behavior_episode_path"),
            evidence.get("behavior_episode_hash"),
        ),
        "manifest.receipt_bundle.evidence.surface_hashes.behavior_episode.json": (
            "behavior_episode.json",
            surface_hashes.get("behavior_episode.json"),
        ),
        "receipt.run_summary.behavior_episode": (
            run_summary.get("behavior_episode_path"),
            run_summary.get("behavior_episode_hash"),
        ),
        "receipt.program_behavior_episode_artifact": (
            receipt_artifact.get("path"),
            receipt_artifact.get("content_hash"),
        ),
    }
    for source, (path, content_hash) in requirements.items():
        if not isinstance(path, str) or not path.strip():
            missing.append(source + ".path")
        if not isinstance(content_hash, str) or not content_hash.strip():
            missing.append(source + ".content_hash")
    return missing


def _check_program_evidence_artifacts(
    *,
    report: dict[str, Any],
    meta_path: Path,
    output_path: Path,
    receipt: Mapping[str, Any],
) -> None:
    if str(receipt.get("run_kind") or "") != "program-gen":
        return

    checks: dict[str, bool] = report["checks"]
    manifest = _load_json_object(output_path)
    checks["program_manifest_json_object"] = manifest is not None
    if manifest is None:
        _add_error(
            report,
            code=_ISSUE_PROGRAM_MANIFEST_INVALID_JSON_OBJECT,
            message=f"program manifest is not a JSON object: {output_path}",
            check="program_manifest_json_object",
        )
        return

    episode_declarations_check = "program_behavior_episode_declarations_complete"
    missing_episode_declarations = _missing_behavior_episode_declarations(
        manifest=manifest, receipt=receipt
    )
    checks[episode_declarations_check] = not missing_episode_declarations
    if missing_episode_declarations:
        _add_error(
            report,
            code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
            message=(
                "program behavior episode declarations are incomplete: "
                + ", ".join(missing_episode_declarations)
            ),
            check=episode_declarations_check,
        )

    closure_check = "program_candidate_artifact_closure_valid"
    try:
        closure = validate_candidate_artifact_closure(
            manifest, manifest_path=output_path
        )
        checks[closure_check] = True
        report["program_candidate_artifact_closure"] = [
            {"kind": item.kind, "path": str(item.path), "sha256": item.sha256}
            for item in closure
        ]
    except ValueError as exc:
        checks[closure_check] = False
        _add_error(
            report,
            code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
            message=str(exc),
            check=closure_check,
        )

    declarations = _program_evidence_declarations(manifest=manifest, receipt=receipt)
    report["program_evidence_artifacts"] = declarations
    if not declarations:
        checks["program_evidence_artifacts_declared"] = False
        return
    checks["program_evidence_artifacts_declared"] = True

    payloads_by_kind: dict[str, dict[str, Any]] = {}

    for declaration in declarations:
        kind = declaration["kind"]
        artifact_path = _resolve_path(str(declaration["path"]), meta_path=meta_path)
        expected_hash = str(declaration["content_hash"])
        source_declarations = [
            item
            for item in _as_list(declaration.get("declarations"))
            if isinstance(item, Mapping)
        ]
        declared_paths = {
            str(item["path"])
            for item in source_declarations
            if isinstance(item.get("path"), str)
        }
        declared_hashes = {
            str(item["content_hash"])
            for item in source_declarations
            if isinstance(item.get("content_hash"), str)
        }
        exists_check = f"program_{kind}_exists"
        hash_check = f"program_{kind}_hash_match"
        declaration_check = f"program_{kind}_declaration_consistent"
        checks[declaration_check] = (
            len(declared_paths) <= 1 and len(declared_hashes) <= 1
        )
        if not checks[declaration_check]:
            _add_error(
                report,
                code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                message=(
                    f"program evidence declaration mismatch for {kind}: "
                    f"paths={sorted(declared_paths)} hashes={sorted(declared_hashes)}"
                ),
                check=declaration_check,
            )
        artifact_exists = artifact_path.exists() and artifact_path.is_file()
        checks[exists_check] = artifact_exists
        if not artifact_exists:
            _add_error(
                report,
                code=_ISSUE_PROGRAM_EVIDENCE_ARTIFACT_MISSING,
                message=f"program evidence artifact missing: {artifact_path}",
                check=exists_check,
            )
            continue
        actual_hash = _sha256_file(artifact_path)
        report[f"program_{kind}_path"] = str(artifact_path)
        report[f"program_{kind}_hash"] = actual_hash
        checks[hash_check] = actual_hash == expected_hash
        if actual_hash != expected_hash:
            _add_error(
                report,
                code=_ISSUE_PROGRAM_EVIDENCE_HASH_MISMATCH,
                message=(
                    f"program evidence hash mismatch for {kind}: "
                    f"expected={expected_hash} actual={actual_hash}"
                ),
                check=hash_check,
            )
        if kind == "module_surfaces":
            surfaces_payload = _load_json_object(artifact_path)
            if isinstance(surfaces_payload, dict):
                payloads_by_kind["module_surfaces"] = surfaces_payload
            semantic_check = "program_module_surfaces_semantic_valid"
            checks[semantic_check] = _program_module_surfaces_semantic_valid(
                surfaces_payload
            )
            if not checks[semantic_check]:
                _add_error(
                    report,
                    code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                    message=f"program module surfaces semantic check failed: {artifact_path}",
                    check=semantic_check,
                )
        if kind == "runtime_outcomes":
            outcomes_payload = _load_json_object(artifact_path)
            semantic_check = "program_runtime_outcomes_semantic_valid"
            checks[semantic_check] = _program_runtime_outcomes_semantic_valid(
                outcomes_payload
            )
            if not checks[semantic_check]:
                _add_error(
                    report,
                    code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                    message=f"program runtime outcomes semantic check failed: {artifact_path}",
                    check=semantic_check,
                )
        if kind == "runtime_traces":
            traces_payload = _load_json_object(artifact_path)
            if isinstance(traces_payload, dict):
                payloads_by_kind["runtime_traces"] = traces_payload
            semantic_check = "program_runtime_traces_semantic_valid"
            checks[semantic_check] = isinstance(
                traces_payload, dict
            ) and validate_program_runtime_traces(traces_payload)
            if not checks[semantic_check]:
                _add_error(
                    report,
                    code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                    message=f"program runtime traces semantic check failed: {artifact_path}",
                    check=semantic_check,
                )
        if kind == "tool_contracts":
            tool_payload = _load_json_object(artifact_path)
            if isinstance(tool_payload, dict):
                payloads_by_kind["tool_contracts"] = tool_payload
            runtime_policy = (
                tool_payload.get("runtime_policy")
                if isinstance(tool_payload, dict)
                else None
            )
            readiness = (
                tool_payload.get("react_v2_tool_readiness")
                if isinstance(tool_payload, dict)
                else None
            )
            preflight = (
                readiness.get("pure_tool_adapter_preflight")
                if isinstance(readiness, Mapping)
                else None
            )
            preflight_ready = (
                isinstance(preflight, Mapping)
                and preflight.get("ready_for_tool_adapter_materialization") is True
            )
            preflight_map = dict(preflight) if isinstance(preflight, Mapping) else {}
            preflight_ready_valid = (not preflight_ready) or (
                preflight_map.get("all_referenced_tools_have_pure_contracts") is True
                and preflight_map.get("all_referenced_tool_schemas_bounded") is True
                and preflight_map.get("all_referenced_adapter_blueprints_hash_bound")
                is True
                and preflight_map.get(
                    "all_referenced_tools_have_replay_policy_preconditions"
                )
                is True
                and preflight_map.get("materialization_status")
                == "ready_for_generated_adapter_materialization"
            )
            semantic_check = "program_tool_contracts_semantic_valid"
            checks[semantic_check] = (
                isinstance(tool_payload, dict)
                and tool_payload.get("schema_version") == "program-tool-contracts-v1"
                and tool_payload.get("status") == "descriptor_only_no_tool_binding"
                and isinstance(tool_payload.get("contracts"), list)
                and isinstance(runtime_policy, dict)
                and runtime_policy.get("tool_execution_allowed") is False
                and isinstance(tool_payload.get("tool_adapter_policy"), dict)
                and tool_payload["tool_adapter_policy"].get("schema_version")
                == "program-tool-adapter-policy-v1"
                and tool_payload["tool_adapter_policy"].get("status")
                in {
                    "no_generated_adapters_present",
                    "adapter_blueprints_recorded_not_executable",
                    "adapter_source_artifacts_written_not_bound",
                }
                and tool_payload["tool_adapter_policy"].get("dspy_tool_binding_allowed")
                is False
                and tool_payload["tool_adapter_policy"].get("tool_execution_allowed")
                is False
                and (
                    int(
                        tool_payload["tool_adapter_policy"].get(
                            "generated_adapter_count"
                        )
                        or 0
                    )
                    == 0
                    or tool_payload["tool_adapter_policy"].get(
                        "all_adapters_hash_bound"
                    )
                    is True
                )
                and isinstance(readiness, Mapping)
                and readiness.get("ready_for_react_v2_tool_binding") is False
                and isinstance(readiness.get("effect"), Mapping)
                and readiness["effect"].get("tool_called") is False
                and readiness["effect"].get("dspy_tool_bound") is False
                and readiness["effect"].get("network") is False
                and readiness["effect"].get("subprocess") is False
                and isinstance(preflight, Mapping)
                and preflight_ready_valid
            )
            adapter_artifact_check = "program_tool_adapter_artifacts_valid"
            adapter_artifacts_valid = True
            blueprint_check = "program_tool_adapter_blueprints_valid"
            blueprint_valid = True
            generated_adapter_count = 0
            blueprint_artifact_count = 0
            if isinstance(tool_payload, dict):
                for raw_contract in _as_list(tool_payload.get("contracts")):
                    if not isinstance(raw_contract, Mapping):
                        continue
                    contract = dict(raw_contract)
                    generated_adapter_policy = _as_dict(
                        contract.get("generated_adapter_policy")
                    )
                    generated_adapter = _as_dict(contract.get("generated_adapter"))
                    adapter_validation = _as_dict(generated_adapter.get("validation"))
                    adapter_artifact = _as_dict(generated_adapter.get("artifact"))
                    adapter_provenance = _as_dict(generated_adapter.get("provenance"))
                    tool_id = str(contract.get("tool_id") or "")
                    adapter_source_preview = generated_adapter.get("source_preview")
                    if isinstance(adapter_source_preview, str):
                        adapter_source_preview_hash = hashlib.sha256(
                            adapter_source_preview.encode("utf-8")
                        ).hexdigest()
                        if adapter_source_preview_hash != generated_adapter.get(
                            "source_hash"
                        ):
                            adapter_artifacts_valid = False
                    if generated_adapter.get("exists") is True:
                        generated_adapter_count += 1
                        adapter_rel = str(adapter_artifact.get("path") or "")
                        adapter_hash = str(adapter_artifact.get("content_hash") or "")
                        expected_adapter_rel = f"tool_adapters/{sanitize_ident(tool_id, fallback='tool')}_adapter.py"
                        adapter_path: Path | None = None
                        if adapter_rel != expected_adapter_rel:
                            adapter_artifacts_valid = False
                        if not adapter_rel or not adapter_hash:
                            adapter_artifacts_valid = False
                        else:
                            adapter_path = _resolve_path(
                                adapter_rel, meta_path=meta_path
                            )
                            if (
                                not adapter_path.exists()
                                or not adapter_path.is_file()
                                or _sha256_file(adapter_path) != adapter_hash
                            ):
                                adapter_artifacts_valid = False
                        if (
                            adapter_path is not None
                            and adapter_path.exists()
                            and adapter_path.is_file()
                        ):
                            try:
                                adapter_source = adapter_path.read_text(
                                    encoding="utf-8"
                                )
                            except OSError:
                                adapter_artifacts_valid = False
                            else:
                                args_schema = _as_dict(contract.get("args_schema"))
                                return_schema = _as_dict(contract.get("return_schema"))
                                if not _generated_tool_adapter_source_semantic_valid(
                                    adapter_source,
                                    tool_id=tool_id,
                                    effect_class=str(
                                        contract.get("effect_class") or ""
                                    ),
                                    args_schema=args_schema,
                                    return_schema=return_schema,
                                ):
                                    adapter_artifacts_valid = False
                                if not _generated_tool_adapter_dry_run_valid(
                                    adapter_source,
                                    tool_id=tool_id,
                                    args_schema=args_schema,
                                    return_schema=return_schema,
                                    expected_result=_as_dict(
                                        adapter_validation.get(
                                            "dry_run_expected_result"
                                        )
                                    ),
                                ):
                                    adapter_artifacts_valid = False
                        if adapter_provenance != {
                            "source": "program_tool_contracts.generated_adapter.source_preview",
                            "materialized_by": "program-gen",
                            "status": "materialized_not_bound_not_executed",
                        }:
                            adapter_artifacts_valid = False
                        if generated_adapter.get(
                            "source_hash"
                        ) != generated_adapter.get("content_hash"):
                            adapter_artifacts_valid = False
                        if adapter_validation.get("schema_version") != (
                            "program-tool-generated-adapter-validation-v1"
                        ):
                            adapter_artifacts_valid = False
                        if adapter_validation.get("status") != (
                            "validated_not_bound_not_executed"
                        ):
                            adapter_artifacts_valid = False
                        for key in [
                            "source_compiles",
                            "constants_match_contract",
                            "source_hash_matches_artifact",
                            "dry_run_supported",
                        ]:
                            if adapter_validation.get(key) is not True:
                                adapter_artifacts_valid = False
                        for key in [
                            "execution_allowed",
                            "dspy_tool_binding_allowed",
                            "imported_by_generated_program",
                        ]:
                            if adapter_validation.get(key) is not False:
                                adapter_artifacts_valid = False
                        required_before_enablement = set(
                            _as_list(
                                generated_adapter_policy.get(
                                    "required_before_enablement"
                                )
                            )
                        )
                        required_policy_items = {
                            "adapter source hash and provenance must be recorded",
                            "tool input/output schemas must be enforced at adapter boundary",
                            "timeout and redaction policy must be enforced before tool call",
                            "effect class and allowlists must be checked before tool call",
                            "runtime trace must record dry-run/tool-call posture without secrets",
                            "receipt replay must verify adapter hash and trace consistency",
                        }
                        if generated_adapter_policy.get("schema_version") != (
                            "program-tool-generated-adapter-policy-v1"
                        ):
                            adapter_artifacts_valid = False
                        if generated_adapter_policy.get("adapter_kind") != (
                            "future_dspy_tool_adapter"
                        ):
                            adapter_artifacts_valid = False
                        if not required_policy_items <= required_before_enablement:
                            adapter_artifacts_valid = False
                        if generated_adapter_policy.get("status") != (
                            "adapter_source_materialized_not_bound"
                        ):
                            adapter_artifacts_valid = False
                        if (
                            generated_adapter_policy.get("source_hash_bound")
                            is not True
                        ):
                            adapter_artifacts_valid = False
                        if (
                            generated_adapter_policy.get("artifact_hash_bound")
                            is not True
                        ):
                            adapter_artifacts_valid = False
                        if (
                            generated_adapter_policy.get("execution_allowed")
                            is not False
                        ):
                            adapter_artifacts_valid = False
                        if (
                            generated_adapter_policy.get("dspy_tool_binding_allowed")
                            is not False
                        ):
                            adapter_artifacts_valid = False
                        if generated_adapter.get("execution_allowed") is not False:
                            adapter_artifacts_valid = False
                        if (
                            generated_adapter.get("dspy_tool_binding_allowed")
                            is not False
                        ):
                            adapter_artifacts_valid = False
                        if (
                            generated_adapter.get("imported_by_generated_program")
                            is not False
                        ):
                            adapter_artifacts_valid = False
                        if adapter_artifact.get("executable") is not False:
                            adapter_artifacts_valid = False
                        if (
                            adapter_artifact.get("imported_by_generated_program")
                            is not False
                        ):
                            adapter_artifacts_valid = False
                    blueprint = _as_dict(contract.get("generated_adapter_blueprint"))
                    blueprint_source_preview = blueprint.get("source_preview")
                    if isinstance(blueprint_source_preview, str):
                        blueprint_source_preview_hash = hashlib.sha256(
                            blueprint_source_preview.encode("utf-8")
                        ).hexdigest()
                        if blueprint_source_preview_hash != blueprint.get(
                            "source_hash"
                        ):
                            blueprint_valid = False
                    artifact = _as_dict(blueprint.get("artifact"))
                    if not artifact:
                        if (
                            blueprint.get("status")
                            == "blueprint_recorded_not_executable"
                        ):
                            blueprint_valid = False
                        continue
                    artifact_rel = str(artifact.get("path") or "")
                    artifact_hash = str(artifact.get("content_hash") or "")
                    expected_blueprint_rel = f"tool_adapters/{sanitize_ident(str(contract.get('tool_id') or ''), fallback='tool')}_adapter_blueprint.py"
                    if artifact_rel != expected_blueprint_rel:
                        blueprint_valid = False
                    blueprint_artifact_count += 1
                    if not artifact_rel or not artifact_hash:
                        blueprint_valid = False
                        continue
                    blueprint_path = _resolve_path(artifact_rel, meta_path=meta_path)
                    if not blueprint_path.exists() or not blueprint_path.is_file():
                        blueprint_valid = False
                        continue
                    if _sha256_file(blueprint_path) != artifact_hash:
                        blueprint_valid = False
                    if artifact.get("executable") is not False:
                        blueprint_valid = False
                    if artifact.get("imported_by_generated_program") is not False:
                        blueprint_valid = False
                tool_adapter_policy = _as_dict(tool_payload.get("tool_adapter_policy"))
                if (
                    int(tool_adapter_policy.get("generated_adapter_count") or 0)
                    != generated_adapter_count
                ):
                    adapter_artifacts_valid = False
                if (
                    int(
                        tool_adapter_policy.get("adapter_blueprint_artifact_count") or 0
                    )
                    != blueprint_artifact_count
                ):
                    blueprint_valid = False
                if (
                    generated_adapter_count > 0
                    and tool_adapter_policy.get("all_adapters_hash_bound") is not True
                ):
                    adapter_artifacts_valid = False
            checks[adapter_artifact_check] = adapter_artifacts_valid
            checks[blueprint_check] = blueprint_valid
            if not checks[semantic_check]:
                _add_error(
                    report,
                    code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                    message=f"program tool contracts semantic check failed: {artifact_path}",
                    check=semantic_check,
                )
            if not checks[adapter_artifact_check]:
                _add_error(
                    report,
                    code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                    message=f"program tool adapter artifact check failed: {artifact_path}",
                    check=adapter_artifact_check,
                )
            if not checks[blueprint_check]:
                _add_error(
                    report,
                    code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                    message=f"program tool adapter blueprint check failed: {artifact_path}",
                    check=blueprint_check,
                )
        if kind == "capability_registry":
            registry_payload = _load_json_object(artifact_path)
            custom_readiness = (
                registry_payload.get("custom_module_readiness")
                if isinstance(registry_payload, dict)
                else None
            )
            retriever_readiness = (
                registry_payload.get("external_retriever_readiness")
                if isinstance(registry_payload, dict)
                else None
            )
            semantic_check = "program_capability_registry_semantic_valid"
            checks[semantic_check] = (
                isinstance(registry_payload, dict)
                and registry_payload.get("schema_version")
                == "program-capability-registry-v1"
                and registry_payload.get("status")
                == "descriptor_only_no_runtime_binding"
                and isinstance(custom_readiness, dict)
                and custom_readiness.get("imports_enabled") is False
                and custom_readiness.get("custom_module_execution_allowed") is False
                and isinstance(retriever_readiness, dict)
                and retriever_readiness.get("live_retrievers_enabled") is False
                and retriever_readiness.get("external_retriever_execution_allowed")
                is False
            )
            if not checks[semantic_check]:
                _add_error(
                    report,
                    code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                    message=f"program capability registry semantic check failed: {artifact_path}",
                    check=semantic_check,
                )
        if kind == "contract_verification":
            verification_payload = _load_json_object(artifact_path)
            gate = (
                verification_payload.get("materialization_gate")
                if isinstance(verification_payload, dict)
                else None
            )
            semantic_check = "program_contract_verification_semantic_valid"
            checks[semantic_check] = (
                isinstance(verification_payload, dict)
                and verification_payload.get("schema_version")
                == "program-architecture-contract-verification-v1"
                and verification_payload.get("status") == "verified_contract_intent"
                and verification_payload.get(
                    "materialization_allowed_by_contract_verification"
                )
                is True
                and isinstance(gate, dict)
                and gate.get("status")
                == "verified_for_explicit_program_gen_materialization"
                and gate.get("allows_live_tools") is False
                and gate.get("allows_custom_imports") is False
                and gate.get("allows_external_retrievers") is False
            )
            if not checks[semantic_check]:
                _add_error(
                    report,
                    code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                    message=f"program contract verification semantic check failed: {artifact_path}",
                    check=semantic_check,
                )
        if kind == "generated_module_policy":
            policy_payload = _load_json_object(artifact_path)
            semantic_check = "program_generated_module_policy_semantic_valid"
            policy_effects = (
                policy_payload.get("effects")
                if isinstance(policy_payload, dict)
                else None
            )
            checks[semantic_check] = (
                isinstance(policy_payload, dict)
                and policy_payload.get("schema_version")
                == "program-generated-module-policy-v1"
                and policy_payload.get("status") == "passed"
                and policy_payload.get("checked_surface") == "module.py"
                and policy_payload.get("violations") == []
                and isinstance(policy_payload.get("denied_dspy_calls"), list)
                and "dspy.Tool" in policy_payload.get("denied_dspy_calls", [])
                and isinstance(policy_effects, Mapping)
                and policy_effects.get("tool_called") is False
                and policy_effects.get("custom_import_loaded") is False
                and policy_effects.get("network") is False
                and policy_effects.get("filesystem_write") is False
                and policy_effects.get("subprocess") is False
                and policy_effects.get("external_authority") is False
            )
            if not checks[semantic_check]:
                _add_error(
                    report,
                    code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                    message=f"program generated module policy semantic check failed: {artifact_path}",
                    check=semantic_check,
                )

    trace_contract_check = "program_runtime_trace_tool_intents_match_contracts"
    traces_payload = payloads_by_kind.get("runtime_traces")
    tool_payload = payloads_by_kind.get("tool_contracts")
    surfaces_payload = payloads_by_kind.get("module_surfaces")
    if traces_payload is not None or tool_payload is not None:
        checks[trace_contract_check] = (
            traces_payload is not None
            and tool_payload is not None
            and _runtime_trace_tool_intents_match_contracts(
                traces_payload,
                tool_payload,
                module_surfaces_payload=surfaces_payload,
            )
        )
        if not checks[trace_contract_check]:
            _add_error(
                report,
                code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                message="program runtime trace tool intents do not match tool contracts",
                check=trace_contract_check,
            )

    readiness_surface_check = "program_react_v2_tool_readiness_matches_surfaces"
    if tool_payload is not None or surfaces_payload is not None:
        checks[readiness_surface_check] = (
            tool_payload is not None
            and surfaces_payload is not None
            and _react_v2_readiness_matches_surfaces_and_contracts(
                tool_payload, surfaces_payload
            )
        )
        if not checks[readiness_surface_check]:
            _add_error(
                report,
                code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                message="program ReActV2 tool readiness does not match module surfaces/contracts",
                check=readiness_surface_check,
            )


def _expected_cache_payload(receipt: Mapping[str, Any]) -> dict[str, Any] | None:
    run_kind = str(receipt.get("run_kind") or "")
    replay_inputs = _as_dict(receipt.get("replay_inputs"))

    if run_kind == "signature-gen":
        class_name = replay_inputs.get("class_name")
        options = replay_inputs.get("options")
        opts = _as_dict(options)
        cls = str(class_name or "GeneratedSignature")
        return {
            "kind": "signature",
            "prompt": replay_inputs.get("prompt"),
            "template_version": replay_inputs.get("template_version"),
            "class_name": cls,
            "options": opts,
        }

    if run_kind == "signature-refine":
        return {
            "kind": "signature",
            "prompt": replay_inputs.get("prompt"),
            "template_version": replay_inputs.get("template_version"),
            "class_name": str(receipt.get("class_name") or ""),
            "mode": str(receipt.get("mode") or "refine"),
            "backend": str(receipt.get("backend") or "native"),
            "attempts": int(replay_inputs.get("attempts") or 1),
            "non_interactive": bool(replay_inputs.get("non_interactive")),
            "wrap_script": bool(replay_inputs.get("wrap_script")),
            "feedback": _as_list(replay_inputs.get("feedback")),
            "constraints": _as_list(replay_inputs.get("constraints")),
        }

    if run_kind == "module-gen":
        return {
            "kind": "module",
            "name": replay_inputs.get("name"),
            "description": replay_inputs.get("description"),
            "inputs": _as_list(replay_inputs.get("inputs")),
            "outputs": _as_list(replay_inputs.get("outputs")),
            "use_signature": bool(replay_inputs.get("use_signature")),
            "template_version": replay_inputs.get("template_version"),
        }

    if run_kind == "program-gen":
        return {
            "kind": "program",
            "intent": _as_dict(replay_inputs.get("intent")),
        }

    if run_kind == "program-runtime":
        return {
            "kind": "program-runtime",
            "replay_inputs": replay_inputs,
        }

    if run_kind == "codegen":
        return {
            "kind": "codegen",
            "spec": replay_inputs.get("spec"),
            "language": replay_inputs.get("language"),
            "template_version": replay_inputs.get("template_version"),
            "options": _as_dict(replay_inputs.get("options")),
        }

    return None


def check_run_receipt(meta_path: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "ok",
        "receipt_path": str(meta_path),
        "checks": {},
        "errors": [],
        "warnings": [],
        "error_codes": [],
        "error_details": [],
    }

    if not meta_path.exists() or not meta_path.is_file():
        report["status"] = "invalid"
        _add_error(
            report,
            code=_ISSUE_RECEIPT_NOT_FOUND,
            message=f"receipt not found: {meta_path}",
        )
        return report

    receipt = load_run_receipt(meta_path)
    if receipt is None:
        report["status"] = "invalid"
        _add_error(
            report,
            code=_ISSUE_RECEIPT_INVALID_JSON_OBJECT,
            message="receipt is not valid JSON object",
        )
        return report

    report["receipt_version"] = receipt.get("receipt_version")
    report["run_kind"] = receipt.get("run_kind")

    validation_errors = _validate_receipt(receipt)
    if validation_errors:
        report["status"] = "invalid"
        for code, message in validation_errors:
            _add_error(report, code=code, message=message)
        return report

    receipt_hash = str(receipt.get("hash") or "")
    try:
        output_path = _resolve_path(
            str(receipt.get("output_path") or ""),
            meta_path=meta_path,
            output_hint=True,
        )
    except ValueError as exc:
        report["status"] = "invalid"
        _add_error(
            report,
            code=_ISSUE_RECEIPT_INVALID_OUTPUT_PATH,
            message=str(exc),
        )
        return report
    report["output_path"] = str(output_path)
    report["receipt_hash"] = receipt_hash

    checks: dict[str, bool] = report["checks"]

    output_exists = output_path.exists() and output_path.is_file()
    checks["output_exists"] = bool(output_exists)
    if not output_exists:
        _add_error(
            report,
            code=_ISSUE_OUTPUT_MISSING,
            message=f"output artifact missing: {output_path}",
            check="output_exists",
        )
    else:
        actual_hash = _sha256_file(output_path)
        report["actual_output_hash"] = actual_hash
        checks["output_hash_match"] = actual_hash == receipt_hash
        if actual_hash != receipt_hash:
            _add_error(
                report,
                code=_ISSUE_OUTPUT_HASH_MISMATCH,
                message=f"output hash mismatch: expected={receipt_hash} actual={actual_hash}",
                check="output_hash_match",
            )
        _check_program_evidence_artifacts(
            report=report,
            meta_path=meta_path,
            output_path=output_path,
            receipt=receipt,
        )

    cache_key = str(receipt.get("cache_key") or "")
    try:
        cache_file = _resolve_path(
            str(receipt.get("cache_file") or ""),
            meta_path=meta_path,
            allow_external_absolute=True,
        )
    except ValueError as exc:
        report["status"] = "invalid"
        _add_error(
            report,
            code=_ISSUE_RECEIPT_INVALID_CACHE_FILE,
            message=str(exc),
        )
        return report
    cache_enabled = bool(receipt.get("cache_enabled"))
    run_kind = str(receipt.get("run_kind") or "")
    cache_kind = _RUN_KIND_TO_CACHE_KIND.get(run_kind) or ""

    report["cache_key"] = cache_key
    report["cache_file"] = str(cache_file)
    report["cache_enabled"] = cache_enabled

    checks["cache_file_matches_key"] = cache_file.name == f"{cache_key}.json"
    if not checks["cache_file_matches_key"]:
        _add_error(
            report,
            code=_ISSUE_CACHE_LINKAGE_BASENAME_MISMATCH,
            message="cache linkage mismatch: cache_file basename does not match cache_key",
            check="cache_file_matches_key",
        )

    checks["cache_kind_matches_run_kind"] = cache_file.parent.name == cache_kind
    if not checks["cache_kind_matches_run_kind"]:
        _add_error(
            report,
            code=_ISSUE_CACHE_LINKAGE_KIND_MISMATCH,
            message="cache linkage mismatch: cache_file parent kind does not match run_kind",
            check="cache_kind_matches_run_kind",
        )

    expected_payload = _expected_cache_payload(receipt)
    if expected_payload is None:
        checks["cache_key_recomputes"] = False
        _add_error(
            report,
            code=_ISSUE_CACHE_KEY_RECOMPUTE_UNSUPPORTED,
            message=f"cannot recompute cache key for run_kind={run_kind!r}; unsupported",
            check="cache_key_recomputes",
        )
    else:
        expected_key = make_key(expected_payload)
        report["expected_cache_key"] = expected_key
        checks["cache_key_recomputes"] = expected_key == cache_key
        if expected_key != cache_key:
            _add_error(
                report,
                code=_ISSUE_CACHE_KEY_MISMATCH,
                message=f"cache key mismatch: expected={expected_key} receipt={cache_key}",
                check="cache_key_recomputes",
            )

    if cache_enabled:
        cache_exists = cache_file.exists() and cache_file.is_file()
        checks["cache_file_exists"] = bool(cache_exists)
        if not cache_exists:
            _add_error(
                report,
                code=_ISSUE_CACHE_FILE_MISSING,
                message=f"cache file missing: {cache_file}",
                check="cache_file_exists",
            )
        else:
            try:
                cache_payload = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                cache_payload = None
            checks["cache_file_json_object"] = isinstance(cache_payload, dict)
            if not isinstance(cache_payload, dict):
                _add_error(
                    report,
                    code=_ISSUE_CACHE_FILE_INVALID_JSON_OBJECT,
                    message=f"cache file is not valid JSON object: {cache_file}",
                    check="cache_file_json_object",
                )
            else:
                code = cache_payload.get("code")
                checks["cache_has_code"] = isinstance(code, str)
                if not isinstance(code, str):
                    _add_error(
                        report,
                        code=_ISSUE_CACHE_CODE_MISSING,
                        message="cache provenance missing: cache payload has no string 'code'",
                        check="cache_has_code",
                    )
                else:
                    cache_code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
                    report["cache_code_hash"] = cache_code_hash
                    checks["cache_code_hash_matches_receipt"] = (
                        cache_code_hash == receipt_hash
                    )
                    if cache_code_hash != receipt_hash:
                        _add_error(
                            report,
                            code=_ISSUE_CACHE_CODE_HASH_MISMATCH,
                            message="cache provenance mismatch: cache code hash does not match receipt hash",
                            check="cache_code_hash_matches_receipt",
                        )
    else:
        checks["cache_file_exists"] = cache_file.exists() and cache_file.is_file()
        report["warnings"].append(
            "cache disabled in receipt; cache existence/provenance checks are informational"
        )

    if report["errors"]:
        report["status"] = "failed"
    return report


def _signature_execution_replay_argv(
    receipt: Mapping[str, Any], replayed_output: Path
) -> list[str] | None:
    replay_inputs = receipt.get("replay_inputs")
    if not isinstance(replay_inputs, Mapping):
        return None
    prompt = replay_inputs.get("prompt")
    template_version = replay_inputs.get("template_version")
    options = replay_inputs.get("options")
    if (
        not isinstance(prompt, str)
        or not prompt.strip()
        or not isinstance(template_version, str)
        or not template_version.startswith("simple-")
        or not isinstance(options, Mapping)
        or set(options) - _EXECUTION_REPLAY_SIGNATURE_OPTION_KEYS
    ):
        return None

    def string_list(name: str) -> list[str] | None:
        value = options.get(name, [])
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            return None
        return [str(item) for item in value]

    inputs = string_list("inputs")
    outputs = string_list("outputs")
    constraints = string_list("constraints")
    feedback = string_list("feedback")
    if None in (inputs, outputs, constraints, feedback):
        return None

    class_name = replay_inputs.get("class_name")
    option_class_name = options.get("class_name")
    if class_name is not None and (
        not isinstance(class_name, str) or not class_name.strip()
    ):
        return None
    if option_class_name is not None and option_class_name != class_name:
        return None
    max_attempts = options.get("max_attempts")
    if max_attempts is not None and (
        isinstance(max_attempts, bool)
        or not isinstance(max_attempts, int)
        or max_attempts < 1
    ):
        return None

    argv = [
        sys.executable,
        "-I",
        "-m",
        "dspx.cli.dspx",
        "signature",
        "gen",
        prompt,
        "--provider",
        _EXECUTION_REPLAY_PROVIDER,
        "--template-version",
        template_version,
        "--no-cache",
        "--outfile",
        str(replayed_output),
    ]
    if class_name:
        argv.extend(["--class-name", class_name])
    for cli_name, values in (
        ("--input", inputs),
        ("--output", outputs),
        ("--constraint", constraints),
        ("--feedback", feedback),
    ):
        for value in values or []:
            argv.extend([cli_name, value])
    if max_attempts is not None:
        argv.extend(["--max-attempts", str(max_attempts)])
    return argv


def execute_run_receipt(meta_path: Path, replay_output: Path) -> dict[str, Any]:
    """Re-run a deterministic receipt in a scrubbed, receipt-local sandbox.

    Check-only remains the compatibility path. Execution additionally requires an
    exact receipt policy and identity bindings, invokes the real ``signature gen``
    command with the stub provider and cache disabled, compares the fresh output,
    and only then exclusively publishes it to ``replay_output``.
    """
    report = check_run_receipt(meta_path)
    initial_receipt = load_run_receipt(meta_path)
    if (
        isinstance(initial_receipt, Mapping)
        and initial_receipt.get("run_kind") == "program-runtime"
    ):
        from dspx.services.program_execution_replay import (
            execute_program_runtime_receipt,
        )

        return execute_program_runtime_receipt(meta_path, replay_output, report)
    report["replay_mode"] = "execute"
    report["execution"] = {
        "attempted": False,
        "strategy": _EXECUTION_REPLAY_STRATEGY,
        "effects": dict(_EXECUTION_REPLAY_EFFECTS),
    }
    execution: dict[str, Any] = report["execution"]
    if report["status"] != "ok":
        execution["blocked_reason"] = "receipt_or_artifact_drift"
        return report

    receipt = load_run_receipt(meta_path)
    assert receipt is not None
    run_kind = str(receipt.get("run_kind") or "")
    provider = str(receipt.get("provider") or "")
    if run_kind != _EXECUTION_REPLAY_KIND:
        report["status"] = "invalid"
        execution["blocked_reason"] = "unsupported_run_kind"
        _add_error(
            report,
            code=_ISSUE_EXECUTION_REPLAY_UNSUPPORTED_KIND,
            message=f"execution replay does not support run_kind={run_kind!r}",
        )
        return report
    if provider != _EXECUTION_REPLAY_PROVIDER:
        report["status"] = "invalid"
        execution["blocked_reason"] = "unsupported_provider"
        _add_error(
            report,
            code=_ISSUE_EXECUTION_REPLAY_UNSUPPORTED_PROVIDER,
            message=f"execution replay does not support provider={provider!r}",
        )
        return report

    policy = receipt.get("execution_replay")
    if not isinstance(policy, Mapping):
        report["status"] = "invalid"
        execution["blocked_reason"] = "missing_receipt_policy"
        _add_error(
            report,
            code=_ISSUE_EXECUTION_REPLAY_POLICY_MISSING,
            message="receipt has no execution_replay policy; refusing to infer effects",
        )
        return report
    if policy.get("supported") is not True or policy.get("strategy") != (
        _EXECUTION_REPLAY_STRATEGY
    ):
        report["status"] = "invalid"
        execution["blocked_reason"] = "unsupported_receipt_inputs"
        _add_error(
            report,
            code=_ISSUE_EXECUTION_REPLAY_UNSUPPORTED_INPUTS,
            message="receipt inputs/template have no supported deterministic executor",
        )
        return report

    effects = policy.get("effects")
    if (
        policy.get("schema_version") != EXECUTION_REPLAY_POLICY_VERSION
        or policy.get("local_only") is not True
        or not isinstance(effects, Mapping)
        or dict(effects) != _EXECUTION_REPLAY_EFFECTS
    ):
        report["status"] = "invalid"
        execution["blocked_reason"] = "unsupported_effects_or_policy"
        _add_error(
            report,
            code=_ISSUE_EXECUTION_REPLAY_UNSUPPORTED_EFFECTS,
            message="receipt execution replay policy/effects are not exactly supported",
        )
        return report

    provider_details = receipt.get("provider_details")
    provider_identity = policy.get("provider_identity")
    runtime_identity = policy.get("runtime_identity")
    output_identity = policy.get("output_identity")
    expected_provider_identity = {
        "provider": provider,
        "provider_details": dict(provider_details)
        if isinstance(provider_details, Mapping)
        else None,
    }
    current_runtime_identity = current_execution_replay_runtime_identity()
    identity_checks = {
        "execution_replay_input_identity_match": policy.get("input_hash")
        == canonical_replay_identity_hash(receipt.get("replay_inputs")),
        "execution_replay_provider_identity_match": (
            isinstance(provider_details, Mapping)
            and isinstance(provider_identity, Mapping)
            and provider_identity.get("provider") == provider
            and provider_identity.get("provider_details") == dict(provider_details)
            and provider_identity.get("hash")
            == canonical_replay_identity_hash(expected_provider_identity)
        ),
        "execution_replay_runtime_identity_match": (
            isinstance(runtime_identity, Mapping)
            and {key: value for key, value in runtime_identity.items() if key != "hash"}
            == current_runtime_identity
            and runtime_identity.get("hash")
            == canonical_replay_identity_hash(current_runtime_identity)
        ),
        "execution_replay_output_identity_match": (
            isinstance(output_identity, Mapping)
            and output_identity.get("algorithm") == "sha256"
            and output_identity.get("hash") == receipt.get("hash")
        ),
    }
    report["checks"].update(identity_checks)
    failed_identity_checks = [
        name for name, passed in identity_checks.items() if not passed
    ]
    if failed_identity_checks:
        report["status"] = "failed"
        execution["blocked_reason"] = "receipt_identity_drift"
        _add_error(
            report,
            code=_ISSUE_EXECUTION_REPLAY_IDENTITY_DRIFT,
            message="execution replay identity drift: "
            + ", ".join(sorted(failed_identity_checks)),
        )
        return report

    try:
        target = _resolve_path(str(replay_output), meta_path=meta_path)
        source = _resolve_path(
            str(receipt["output_path"]), meta_path=meta_path, output_hint=True
        )
        cache_file = _resolve_path(
            str(receipt["cache_file"]),
            meta_path=meta_path,
            allow_external_absolute=True,
        )
    except (KeyError, ValueError) as exc:
        report["status"] = "invalid"
        execution["blocked_reason"] = "invalid_output_path"
        _add_error(
            report,
            code=_ISSUE_EXECUTION_REPLAY_OUTPUT_INVALID,
            message=str(exc),
        )
        return report

    forbidden_targets = {meta_path.resolve(), source.resolve(), cache_file.resolve()}
    if target.resolve() in forbidden_targets or target.name.endswith(".meta.json"):
        report["status"] = "invalid"
        execution["blocked_reason"] = "protected_output_path"
        _add_error(
            report,
            code=_ISSUE_EXECUTION_REPLAY_OUTPUT_INVALID,
            message="replay output must be a new non-receipt file distinct from source/cache",
        )
        return report
    if target.exists() or target.is_symlink():
        report["status"] = "failed"
        execution["blocked_reason"] = "output_exists"
        _add_error(
            report,
            code=_ISSUE_EXECUTION_REPLAY_OUTPUT_EXISTS,
            message=f"replay output already exists; refusing overwrite: {target}",
        )
        return report
    if not target.parent.exists() or not target.parent.is_dir():
        report["status"] = "invalid"
        execution["blocked_reason"] = "output_parent_missing"
        _add_error(
            report,
            code=_ISSUE_EXECUTION_REPLAY_OUTPUT_INVALID,
            message=f"replay output parent must already exist: {target.parent}",
        )
        return report

    source_hash_before = _sha256_file(source)
    expected_hash = str(receipt["hash"])
    with tempfile.TemporaryDirectory(
        prefix=".dspx-execution-replay-", dir=str(meta_path.parent.resolve())
    ) as temporary_dir:
        sandbox = Path(temporary_dir)
        replayed_output = sandbox / "replayed.py"
        argv = _signature_execution_replay_argv(receipt, replayed_output)
        if argv is None:
            report["status"] = "invalid"
            execution["blocked_reason"] = "unsupported_receipt_inputs"
            _add_error(
                report,
                code=_ISSUE_EXECUTION_REPLAY_UNSUPPORTED_INPUTS,
                message="receipt signature inputs are not safely replayable",
            )
            return report

        allowed_environment_keys = {
            "LANG",
            "LC_ALL",
            "PATH",
            "SYSTEMROOT",
            "TMPDIR",
            "VIRTUAL_ENV",
            "WINDIR",
        }
        scrubbed_env = {
            key: value
            for key, value in os.environ.items()
            if key in allowed_environment_keys
        }
        scrubbed_env.update(
            {
                "HOME": str(sandbox),
                "DSPX_PROVIDER": _EXECUTION_REPLAY_PROVIDER,
                "DSPX_CACHE_ENABLE": "0",
                "DSPX_CACHE_DIR": str(sandbox / "cache"),
                "DSPX_RECEIPT_BRANCH": "local-execution-replay",
                "MLFLOW_ENABLE": "0",
            }
        )
        execution["attempted"] = True
        try:
            completed = subprocess.run(
                argv,
                cwd=sandbox,
                env=scrubbed_env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            report["status"] = "failed"
            execution["blocked_reason"] = "reexecution_process_failed"
            _add_error(
                report,
                code=_ISSUE_EXECUTION_REPLAY_PROCESS_FAILED,
                message=f"local reexecution process failed: {type(exc).__name__}",
            )
            return report
        if completed.returncode != 0:
            report["status"] = "failed"
            execution["blocked_reason"] = "reexecution_process_nonzero"
            execution["returncode"] = completed.returncode
            _add_error(
                report,
                code=_ISSUE_EXECUTION_REPLAY_PROCESS_FAILED,
                message=f"local reexecution exited nonzero: {completed.returncode}",
            )
            return report

        child_meta = replayed_output.parent / f"{replayed_output.name}.meta.json"
        child_receipt = load_run_receipt(child_meta)
        observed_files = sorted(
            str(path.relative_to(sandbox))
            for path in sandbox.rglob("*")
            if path.is_file()
        )
        required_files = {"replayed.py", "replayed.py.meta.json"}
        observed_file_set = set(observed_files)
        unexpected_files = sorted(
            path
            for path in observed_file_set - required_files
            if not (path.startswith(".dspy_cache/") and path.endswith("/cache.db"))
        )
        effects_bounded = required_files <= observed_file_set and not unexpected_files
        report["checks"]["execution_replay_temporary_files_as_declared"] = (
            effects_bounded
        )
        if not effects_bounded:
            report["status"] = "failed"
            execution["blocked_reason"] = "unexpected_local_effect"
            execution["observed_files"] = observed_files
            _add_error(
                report,
                code=_ISSUE_EXECUTION_REPLAY_UNEXPECTED_EFFECT,
                message="local reexecution produced undeclared filesystem artifacts",
                check="execution_replay_temporary_files_as_declared",
            )
            return report
        if child_receipt is None or not replayed_output.is_file():
            report["status"] = "failed"
            execution["blocked_reason"] = "reexecution_evidence_missing"
            _add_error(
                report,
                code=_ISSUE_EXECUTION_REPLAY_PROCESS_FAILED,
                message="local reexecution did not emit output and receipt evidence",
            )
            return report

        replayed_hash = _sha256_file(replayed_output)
        child_provider_identity = {
            "provider": child_receipt.get("provider"),
            "provider_details": child_receipt.get("provider_details"),
        }
        child_policy = child_receipt.get("execution_replay")
        child_runtime = (
            child_policy.get("runtime_identity")
            if isinstance(child_policy, Mapping)
            else None
        )
        child_checks = {
            "execution_replay_child_input_identity_match": (
                canonical_replay_identity_hash(child_receipt.get("replay_inputs"))
                == policy.get("input_hash")
            ),
            "execution_replay_child_provider_identity_match": (
                child_provider_identity == expected_provider_identity
                and canonical_replay_identity_hash(child_provider_identity)
                == provider_identity.get("hash")
            ),
            "execution_replay_child_runtime_identity_match": (
                isinstance(child_runtime, Mapping)
                and child_runtime.get("hash") == runtime_identity.get("hash")
            ),
            "execution_replay_reexecuted_output_hash_match": replayed_hash
            == expected_hash,
        }
        report["checks"].update(child_checks)
        failed_child_checks = [
            name for name, passed in child_checks.items() if not passed
        ]
        if failed_child_checks:
            report["status"] = "failed"
            execution["blocked_reason"] = "reexecution_identity_or_output_drift"
            execution["reexecuted_hash"] = replayed_hash
            code = (
                _ISSUE_EXECUTION_REPLAY_OUTPUT_HASH_MISMATCH
                if not child_checks["execution_replay_reexecuted_output_hash_match"]
                else _ISSUE_EXECUTION_REPLAY_IDENTITY_DRIFT
            )
            _add_error(
                report,
                code=code,
                message="local reexecution drift: "
                + ", ".join(sorted(failed_child_checks)),
            )
            return report

        payload = replayed_output.read_bytes()
        try:
            bytes_written = _exclusive_write_confined(
                meta_path.parent.resolve(), target, payload
            )
        except (FileExistsError, OSError) as exc:
            report["status"] = "failed"
            execution["blocked_reason"] = "exclusive_write_failed"
            code = (
                _ISSUE_EXECUTION_REPLAY_OUTPUT_EXISTS
                if isinstance(exc, FileExistsError)
                else _ISSUE_EXECUTION_REPLAY_WRITE_FAILED
            )
            _add_error(
                report,
                code=code,
                message=f"execution replay output write failed: {type(exc).__name__}",
            )
            return report

        source_hash_after = _sha256_file(source)
        report["checks"]["execution_replay_source_output_preserved"] = (
            source_hash_after == source_hash_before
        )
        if source_hash_after != source_hash_before:
            report["status"] = "failed"
            execution["blocked_reason"] = "source_artifact_drift"
            _add_error(
                report,
                code=_ISSUE_EXECUTION_REPLAY_WRITE_FAILED,
                message="source artifact changed during replay",
            )
            return report

        stdout_hash = hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest()
        stderr_hash = hashlib.sha256(completed.stderr.encode("utf-8")).hexdigest()

    report["status"] = "executed"
    report["execution"] = {
        "attempted": True,
        "strategy": _EXECUTION_REPLAY_STRATEGY,
        "run_kind": run_kind,
        "provider": provider,
        "source_receipt": str(meta_path),
        "source_output": str(source),
        "replay_output": str(target),
        "expected_hash": expected_hash,
        "reexecuted_hash": expected_hash,
        "actual_hash": expected_hash,
        "bytes_written": bytes_written,
        "effects": dict(_EXECUTION_REPLAY_EFFECTS),
        "evidence": {
            "schema_version": "execution-replay-evidence-v1",
            "input_identity_hash": policy.get("input_hash"),
            "provider_identity_hash": provider_identity.get("hash"),
            "runtime_identity_hash": runtime_identity.get("hash"),
            "output_identity_hash": expected_hash,
            "subprocess_returncode": 0,
            "subprocess_stdout_hash": stdout_hash,
            "subprocess_stderr_hash": stderr_hash,
            "temporary_artifacts_cleaned": True,
            "shared_oracle_mutation_requested": False,
            "external_authority_mutation_requested": False,
        },
    }
    return report
