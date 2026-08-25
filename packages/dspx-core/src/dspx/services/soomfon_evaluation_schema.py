"""Closed exact schema for the AK-5056 verification repair contract."""

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
    "956d3ecaba0a3bb43425ecad7cb1297d6b01b70d08bef2ffe9a4173c6ba45915"
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
        or payload.get("status")
        != "luna_xhigh_closed_diagnostics_fd_cursor_repair_execution_unauthorized_pending_review"
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
            "execution_task_id",
            "attempted_modes",
            "unattempted_modes",
            "terminal_disposition",
            "terminal_reason",
            "response_sha256",
            "response_length",
            "runtime_evidence",
            "authorization_evidence",
            "owner_source_identity_sha256",
            "runtime_identity",
            "completed_receipt_chains",
            "retry_allowed",
            "empirical_relabel_allowed",
            "ledger_namespace_reuse_allowed",
            "unattempted_modes_execution_authority_transferred",
            "earlier_predecessor",
        },
        label="contract predecessor",
    )
    earlier = _require_exact_keys(
        predecessor.get("earlier_predecessor"),
        {"archive_path", "raw_sha256", "terminal_disposition", "retry_allowed"},
        label="earlier predecessor",
    )
    runtime_evidence = _require_exact_keys(
        predecessor.get("runtime_evidence"),
        {
            "latency_ms",
            "runtime_episode_sha256",
            "runtime_tree_sha256",
            "runtime_receipt_sha256",
            "behavior_results_sha256",
        },
        label="predecessor runtime evidence",
    )
    authorization_evidence = _require_exact_keys(
        predecessor.get("authorization_evidence"),
        {"authorization_sha256", "ak_reconciliation_sha256"},
        label="predecessor authorization evidence",
    )
    completed_chains = predecessor.get("completed_receipt_chains")
    if (
        predecessor.get("archive_path")
        != "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/6c3f913c2fe05eb5edfc39ee0cbea1a4ca43036bdd0e77c9ad3f37d35c0eadae.json"
        or predecessor.get("raw_sha256")
        != "6c3f913c2fe05eb5edfc39ee0cbea1a4ca43036bdd0e77c9ad3f37d35c0eadae"
        or predecessor.get("canonical_sha256")
        != "b416b542bdbc62dc949773ecb2ff10f71769205ebf78f75e63466a70b7363dc4"
        or predecessor.get("task_id") != 5042
        or predecessor.get("status")
        != "luna_xhigh_fd_journal_repair_execution_unauthorized_pending_review"
        or predecessor.get("execution_task_id") != 5045
        or predecessor.get("attempted_modes") != ["simple"]
        or predecessor.get("unattempted_modes") != list(EXPECTED_MODES[1:])
        or predecessor.get("terminal_disposition") != "effect_indeterminate"
        or predecessor.get("terminal_reason") != "provider_receipt_journal_invalid"
        or predecessor.get("response_sha256")
        != "749af25da49ba89dda58ee9bf2b02114282241def1f5d7c2b4430e43be22edbb"
        or predecessor.get("response_length") != 304
        or predecessor.get("retry_allowed") is not False
        or predecessor.get("empirical_relabel_allowed") is not False
        or predecessor.get("ledger_namespace_reuse_allowed") is not False
        or predecessor.get("unattempted_modes_execution_authority_transferred")
        is not False
        or earlier.get("archive_path")
        != "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/56b2f269bd6b494a2d4d08c716787449cde5dd5a63bbbfc5d4666feb32306e3a.json"
        or earlier.get("raw_sha256")
        != "56b2f269bd6b494a2d4d08c716787449cde5dd5a63bbbfc5d4666feb32306e3a"
        or earlier.get("terminal_disposition") != "effect_indeterminate"
        or earlier.get("retry_allowed") is not False
        or predecessor.get("runtime_identity")
        != {
            "python": "3.13.12",
            "dspx-core": "0.2.1",
            "dspy": "3.3.1",
            "dspy-ai": "3.3.1",
            "gepa": "0.1.4",
            "litellm": "1.82.1",
            "httpx": "0.28.1",
            "httpcore": "1.0.9",
        }
        or not isinstance(completed_chains, list)
        or len(completed_chains) != 2
    ):
        raise SoomfonEvaluationContractError("contract predecessor is invalid")
    evidence_hashes = (
        predecessor.get("raw_sha256"),
        predecessor.get("canonical_sha256"),
        predecessor.get("response_sha256"),
        predecessor.get("owner_source_identity_sha256"),
        earlier.get("raw_sha256"),
        runtime_evidence.get("runtime_episode_sha256"),
        runtime_evidence.get("runtime_tree_sha256"),
        runtime_evidence.get("runtime_receipt_sha256"),
        runtime_evidence.get("behavior_results_sha256"),
        authorization_evidence.get("authorization_sha256"),
        authorization_evidence.get("ak_reconciliation_sha256"),
    )
    for value in evidence_hashes:
        _require_hash(value, "predecessor evidence hash is invalid")
    if (
        runtime_evidence.get("latency_ms") != 43992
        or runtime_evidence.get("runtime_episode_sha256")
        != "af5cf2e553b382f1a2f6ee5dc171a034680781603c2ee3c0338dc33bb8fc42fa"
        or runtime_evidence.get("runtime_tree_sha256")
        != "c231960ab57d7248e2438b12b8f1de453e57b20b1d82628e669065de10792983"
        or runtime_evidence.get("runtime_receipt_sha256")
        != "12c6e1af5349bd70c50f13d5d05b73bfbb4cf49f6aab7f843b89924ac37e0cf2"
        or runtime_evidence.get("behavior_results_sha256")
        != "8275e28fda59b9b80207350d3d000577d240385a9192f62703608f9c8589d7e0"
        or authorization_evidence.get("authorization_sha256")
        != "94cca8f14fc17660de94ad4f09214395f01b1fa049c329c029a9d15a40435a58"
        or authorization_evidence.get("ak_reconciliation_sha256")
        != "97a271cc914e9d4f9e26f5c367c790aa231ad4ab08bc5f0fbbbab91c4f97b097"
    ):
        raise SoomfonEvaluationContractError("predecessor retained evidence is invalid")
    chain_keys = {
        "call_ordinal",
        "signature_name",
        "reservation_id",
        "journal_sha256",
        "provider_outcome_receipt",
        "request_acknowledged",
        "external_effect_possible",
        "producer_terminal",
        "empirical_disposition",
        "reason",
    }
    for ordinal, (chain, signature) in enumerate(
        zip(completed_chains, ("DefinePersona", "AnswerSimple"), strict=True), start=1
    ):
        row = _require_exact_keys(chain, chain_keys, label="completed receipt chain")
        if (
            row.get("call_ordinal") != ordinal
            or row.get("signature_name") != signature
            or row.get("provider_outcome_receipt") != "accepted"
            or row.get("request_acknowledged") is not True
            or row.get("external_effect_possible") is not True
            or row.get("producer_terminal") != "provider_response_completed"
            or row.get("empirical_disposition") != "not_evaluated"
            or row.get("reason") != "attributable_completion_not_evaluated"
        ):
            raise SoomfonEvaluationContractError("completed receipt chain is invalid")
        for key in ("reservation_id", "journal_sha256"):
            _require_hash(row.get(key), "completed receipt chain hash is invalid")

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
        or executor.get("task_5056_can_authorize_execution") is not False
        or executor.get("implementation_requires_later_exact_ak_task") is not True
        or executor.get("execution_authorization_artifact_required") is not True
        or executor.get("execution_authorization_sha256_argument_required") is not True
        or executor.get("child_runtime_queries_ak") is not True
        or not {
            "open_independently_positioned_verification_fd_from_authoritative_parent_fd_and_rebind_parent_inode",
            "retain_only_closed_allowlisted_post_provider_verification_phase_and_reason_without_exception_text",
            "provider_free_parent_child_parent_eof_cursor_dogfood_required",
        }.issubset(set(executor.get("required_executor_properties", [])))
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
    diagnostics = (
        receipt.get("closed_verification_diagnostics")
        if isinstance(receipt, Mapping)
        else None
    )
    if not isinstance(receipt, Mapping) or (
        receipt.get("existing_accepted_v11_owner_identity_unchanged") is not True
        or receipt.get("verify_owner_source_before_marker") is not True
        or receipt.get("verify_loaded_receipt_types_before_call") is not True
        or receipt.get("revalidate_before_each_call_and_progression") is not True
        or receipt.get("canonical_authority_revalidation")
        != "immediately_before_each_logical_call_before_receipt_credential_or_transport_with_90_second_minimum_lease"
        or receipt.get("logical_request_mode") != "sync"
        or receipt.get("missing_open_poisoned_indeterminate_chain_terminal") is not True
        or receipt.get("retained_verification_directory_cursor_policy")
        != "independent_open_file_description_from_authoritative_parent_fd"
        or receipt.get("retained_verification_identity_policy")
        != "original_parent_and_verification_parent_and_members_revalidated_before_close"
        or diagnostics
        != {
            "phases": [
                "owner_source",
                "provider_envelope",
                "marker_hash",
                "retained_journal",
            ],
            "exception_text_allowed": False,
            "traceback_allowed": False,
            "paths_allowed": False,
            "raw_diagnostic_allowed": False,
        }
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
