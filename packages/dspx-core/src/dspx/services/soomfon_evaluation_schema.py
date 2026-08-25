"""Closed exact schema for the AK-5033 Luna xhigh Soomfon evaluation contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from dspx.services.soomfon_evaluation_contract import (
    CONTRACT_PREPARATION_TASK_ID,
    CONTRACT_SCHEMA,
    EXPECTED_MODES,
    SoomfonEvaluationContractError,
    _require_exact_keys,
    _SHA256_RE,
    _TOP_LEVEL_KEYS,
)

PROTECTED_DENIED_ATTRIBUTES = set(
    "LM __builtins__ __call__ __class__ __code__ __delattr__ __dict__ "
    "__getattribute__ __getstate__ __globals__ __reduce__ __reduce_ex__ __setattr__ "
    "__setstate__ __subclasses__ __traceback__ ag_frame call configure context "
    "cr_frame dump_state environ f_builtins f_globals f_locals from_file from_url "
    "getoutput getstatusoutput gi_frame glob iterdir load load_state modules parse_file "
    "parse_raw read_bytes read_text rglob save setpriority settings setxattr sys tb_frame".split()
)
_EXPECTED_CANONICAL_SHA256 = (
    "241e47972c1b8ddc8b499c7fa1320a698ee0fe504eb40537cf91bcb90b53dedc"
)


def _require_hash(value: object, reason: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise SoomfonEvaluationContractError(reason)


def validate_soomfon_contract(contract: Mapping[str, Any]) -> None:
    payload = _require_exact_keys(dict(contract), _TOP_LEVEL_KEYS, label="contract")
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    if hashlib.sha256(canonical).hexdigest() != _EXPECTED_CANONICAL_SHA256:
        raise SoomfonEvaluationContractError("contract exact content is invalid")
    if (
        payload.get("schema_version") != CONTRACT_SCHEMA
        or payload.get("task_id") != CONTRACT_PREPARATION_TASK_ID
        or payload.get("status") != "luna_xhigh_execution_unauthorized_pending_review"
    ):
        raise SoomfonEvaluationContractError("contract identity is invalid")

    predecessor = _require_exact_keys(
        payload.get("predecessor_contract"),
        {
            "archive_path",
            "raw_sha256",
            "canonical_sha256",
            "task_id",
            "status",
            "superseded_execution_task_id",
            "superseded_execution_task_claimed",
            "attempted_modes",
            "unattempted_modes",
            "terminal_disposition",
            "terminal_reason",
            "execution_authorized",
            "retry_allowed",
            "earlier_predecessor",
        },
        label="contract predecessor",
    )
    earlier = _require_exact_keys(
        predecessor.get("earlier_predecessor"),
        {"archive_path", "raw_sha256", "terminal_disposition", "retry_allowed"},
        label="earlier predecessor",
    )
    if (
        predecessor.get("archive_path")
        != "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/0f602482f29037d1a8f0c71731872390614198998d1fda94079172052cc29207.json"
        or predecessor.get("raw_sha256")
        != "0f602482f29037d1a8f0c71731872390614198998d1fda94079172052cc29207"
        or predecessor.get("canonical_sha256")
        != "d139b5e2f250113bc3f7c95ec5740499090019dcc88140d3037023d1e7ca46fd"
        or predecessor.get("task_id") != 5028
        or predecessor.get("status")
        != "forward_repair_execution_unauthorized_pending_review"
        or predecessor.get("superseded_execution_task_id") != 5032
        or predecessor.get("superseded_execution_task_claimed") is not False
        or predecessor.get("attempted_modes") != []
        or predecessor.get("unattempted_modes") != list(EXPECTED_MODES)
        or predecessor.get("terminal_disposition") != "execution_unattempted"
        or predecessor.get("terminal_reason")
        != "operator_selected_luna_xhigh_before_claim_or_effect"
        or predecessor.get("execution_authorized") is not False
        or predecessor.get("retry_allowed") is not False
        or earlier.get("archive_path")
        != "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/9d9d1b6ea87d3fd16e3db3e1fc97c5bbc68cc241bf67d52cf6c8b2593a1bf24b.json"
        or earlier.get("raw_sha256")
        != "9d9d1b6ea87d3fd16e3db3e1fc97c5bbc68cc241bf67d52cf6c8b2593a1bf24b"
        or earlier.get("terminal_disposition") != "effect_indeterminate"
        or earlier.get("retry_allowed") is not False
    ):
        raise SoomfonEvaluationContractError("contract predecessor is invalid")
    for value in (
        predecessor.get("raw_sha256"),
        predecessor.get("canonical_sha256"),
        earlier.get("raw_sha256"),
    ):
        _require_hash(value, "predecessor hash is invalid")

    owner = _require_exact_keys(
        payload.get("provider_owner_candidate"),
        {
            "owner_task_id",
            "owner",
            "status",
            "branch",
            "commit",
            "tree",
            "version",
            "wheel_sha256",
            "installed_payload_sha256",
            "lock_sha256",
            "module_sha256",
            "dependency_identity",
            "independent_review_dispatch_id",
            "independent_test_dispatch_id",
            "published",
            "released",
            "generic_dspx_provider_ready",
        },
        label="provider owner candidate",
    )
    if (
        owner.get("owner_task_id") != 4991
        or owner.get("owner") != "tryinget-dspy-lm-auth"
        or owner.get("commit") != "7c51dda703f6a5d0a95aba13734294a82ea4314f"
        or owner.get("tree") != "c303dd657146da90404618adead417e82e2dc2c0"
        or owner.get("version") != "0.1.6.dev0"
        or owner.get("wheel_sha256")
        != "e1b8acaa354df4640422512a779b9486d5c4caceeb9c9ab05c4a07f1b1eb3512"
        or owner.get("installed_payload_sha256")
        != "8c8a2aa569df171fab35e25b02cb313ee20725901c7bec7ede0edc2364dccaf2"
        or owner.get("lock_sha256")
        != "0b18a1759b2507967ed8f2f4918c436e2679e406aafb061620a11954b1550c7c"
        or owner.get("published") is not False
        or owner.get("released") is not False
        or owner.get("generic_dspx_provider_ready") is not False
    ):
        raise SoomfonEvaluationContractError("provider owner identity is invalid")
    modules = owner.get("module_sha256")
    dependencies = owner.get("dependency_identity")
    if not isinstance(modules, Mapping) or set(modules) != {
        "package_init",
        "auth",
        "lm",
        "codex_stream",
        "codex_stream_support",
        "outcome_receipt",
        "outcome_receipt_runtime",
        "outcome_receipt_state",
        "outcome_receipt_transport",
    }:
        raise SoomfonEvaluationContractError("provider module identity is invalid")
    for value in modules.values():
        _require_hash(value, "provider module hash is invalid")
    if not isinstance(dependencies, Mapping) or set(dependencies) != {
        "dspy",
        "litellm",
        "httpx",
        "httpcore",
    }:
        raise SoomfonEvaluationContractError("provider dependency identity is invalid")
    dependency_keys = {
        "version",
        "locked_wheel_sha256",
        "payload_count",
        "payload_sha256",
        "record_sha256",
    }
    for dependency in dependencies.values():
        item = _require_exact_keys(
            dependency, dependency_keys, label="provider dependency"
        )
        for key in ("locked_wheel_sha256", "payload_sha256", "record_sha256"):
            _require_hash(item.get(key), "provider dependency hash is invalid")
        if (
            isinstance(item.get("payload_count"), bool)
            or not isinstance(item.get("payload_count"), int)
            or item["payload_count"] < 1
        ):
            raise SoomfonEvaluationContractError("provider payload count is invalid")

    runtime = payload.get("runtime_target")
    if not isinstance(runtime, Mapping):
        raise SoomfonEvaluationContractError("runtime target is invalid")
    required_runtime = {
        "python": "3.13.12",
        "dspx_core": "0.2.1",
        "dspy": "3.3.1",
        "dspy_ai": "3.3.1",
        "gepa": "0.1.4",
        "provider_scope": "validated_soomfon_runtime_custody_only",
        "provider": "dspy-lm-auth",
        "provider_version": "0.1.6.dev0",
        "dspy_lm_type": "external_owner_LM",
        "dspx_lm_subclass_added": False,
        "adapter": "soomfon_specific_json_adapter_no_chat_fallback",
        "requested_route": "dspy-lm-auth:codex:gpt-5.6-luna:xhigh",
        "resolved_route": "openai:gpt-5.6-luna:responses",
        "requested_model": "codex/gpt-5.6-luna",
        "resolved_model": "openai/gpt-5.6-luna",
        "auth_provider": "codex",
        "credential_mode": "no-refresh",
        "reasoning_effort": "xhigh",
        "num_retries": 0,
        "cache": False,
        "timeout_seconds": 60,
        "sync_only": True,
        "fallback_allowed": False,
        "health_probe_allowed": False,
        "dont_write_bytecode_required": True,
        "child_python_flag_B_required": True,
        "bytecode_cache_allowed": False,
    }
    if any(runtime.get(key) != value for key, value in required_runtime.items()):
        raise SoomfonEvaluationContractError("runtime target is invalid")

    executor = payload.get("executor_contract")
    if not isinstance(executor, Mapping) or (
        executor.get("implementation_ready") is not True
        or executor.get("execution_authorized") is not False
        or executor.get("task_5033_can_authorize_execution") is not False
        or executor.get("implementation_requires_later_exact_ak_task") is not True
        or executor.get("execution_authorization_artifact_required") is not True
        or executor.get("execution_authorization_sha256_argument_required") is not True
        or executor.get("child_runtime_queries_ak") is not True
        or executor.get("execution_authorization_schema")
        != "soomfon-execution-authorization-v3"
        or executor.get("canonical_ak_runtime")
        != {
            "path": "/home/tryinget/.local/libexec/agent-kernel/c6297eccf67a3762ef01269f67e87eaa8828f127/ak-bin",
            "sha256": "61f6290115262e0319c3b178f053d74a486a3eba881aaa13739c1db45f0f6b91",
            "mode": "0555",
            "open_policy": "exact_path_O_NOFOLLOW_hash_fd_execute_proc_fd_pass_fds_refstat",
        }
        or executor.get("lease_requirements")
        != {
            "suite_preflight_minimum_seconds": 1800,
            "before_each_case_marker_minimum_seconds": 1800,
            "before_each_logical_call_minimum_seconds": 90,
            "call_minimum_basis": "provider_timeout_60_plus_30_seconds",
        }
    ):
        raise SoomfonEvaluationContractError("executor authorization is invalid")

    budget = payload.get("effect_budget")
    expected_budget = {
        "fixed_case_order": list(EXPECTED_MODES),
        "candidate_invocations_per_case": 1,
        "ordered_logical_lm_calls_per_successful_case": 2,
        "maximum_suite_logical_lm_calls": 12,
        "maximum_suite_provider_transports": 12,
        "dspx_managed_retries": 0,
        "provider_configured_retries": 0,
        "health_probes": 0,
        "selective_reruns": 0,
        "stop_on_first_non_success": True,
        "effect_indeterminate_is_terminal": True,
        "resume_allowed": False,
        "fallback_allowed": False,
    }
    if budget != expected_budget:
        raise SoomfonEvaluationContractError("effect budget is invalid")

    receipt = payload.get("provider_receipt_custody")
    if not isinstance(receipt, Mapping) or (
        receipt.get("existing_accepted_v11_owner_identity_unchanged") is not True
        or receipt.get("verify_owner_source_before_marker") is not True
        or receipt.get("verify_loaded_receipt_types_before_call") is not True
        or receipt.get("revalidate_before_each_call_and_progression") is not True
        or receipt.get("canonical_authority_revalidation")
        != "immediately_before_each_logical_call_before_receipt_credential_or_transport_with_90_second_minimum_lease"
        or receipt.get("logical_request_mode") != "sync"
        or receipt.get("missing_open_poisoned_indeterminate_chain_terminal") is not True
    ):
        raise SoomfonEvaluationContractError("provider receipt custody is invalid")

    cases = payload.get("cases")
    if not isinstance(cases, list) or [
        item.get("mode") for item in cases if isinstance(item, Mapping)
    ] != list(EXPECTED_MODES):
        raise SoomfonEvaluationContractError("contract cases are invalid")
    for item in cases:
        if not isinstance(item, Mapping):
            raise SoomfonEvaluationContractError("contract case is invalid")
        for key in ("manifest_sha256", "canary_index_sha256"):
            _require_hash(item.get(key), "contract case hash is invalid")

    nonclaims = payload.get("nonclaims")
    if not isinstance(nonclaims, Mapping) or any(
        nonclaims.get(key) is not False
        for key in ("routing", "promotion", "activation", "release", "publication")
    ):
        raise SoomfonEvaluationContractError("authority nonclaims are invalid")


__all__ = ["PROTECTED_DENIED_ATTRIBUTES", "validate_soomfon_contract"]
