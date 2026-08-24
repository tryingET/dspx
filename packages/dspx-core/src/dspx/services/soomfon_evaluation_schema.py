"""Closed recursive schema for the frozen Soomfon evaluation contract."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from dspx.services.soomfon_evaluation_contract import (
    CONTRACT_SCHEMA,
    EXPECTED_MODES,
    REQUIRED_ENVIRONMENT,
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
    "a8ec67b7ddf711142312ffd6caf0a7d57eeb48617e92025a0d45ae48dedd26c0"
)


def validate_soomfon_contract(contract: Mapping[str, Any]) -> None:
    payload = _require_exact_keys(dict(contract), _TOP_LEVEL_KEYS, label="contract")
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    if hashlib.sha256(canonical).hexdigest() != _EXPECTED_CANONICAL_SHA256:
        raise SoomfonEvaluationContractError("contract exact content is invalid")
    if (
        payload.get("schema_version") != CONTRACT_SCHEMA
        or payload.get("task_id") != 4808
        or payload.get("status") != "implementation_reviewed_execution_unauthorized"
    ):
        raise SoomfonEvaluationContractError("contract identity is invalid")
    source = _require_exact_keys(
        payload.get("source_state"),
        {
            "dspx_base_commit",
            "workstation_reconciliation_commit",
            "local_ai_control_plane_commit",
            "installed_binding_config",
            "installed_binding_config_sha256",
            "installed_binding_disposition",
            "shadow_binding_only",
        },
        label="contract source state",
    )
    if source.get("shadow_binding_only") is not True:
        raise SoomfonEvaluationContractError("contract source posture is invalid")
    runtime = _require_exact_keys(
        payload.get("runtime_target"),
        {
            "python",
            "dspx_core",
            "dspy",
            "dspy_ai",
            "gepa",
            "provider",
            "typed_contract",
            "model",
            "base_url",
            "timeout_seconds",
            "network_scope",
            "backend_locality",
            "credentials_allowed",
            "microphone_allowed",
            "tts_allowed",
            "physical_key_allowed",
        },
        label="contract runtime target",
    )
    if runtime != {
        "python": "3.13.12",
        "dspx_core": "0.2.1",
        "dspy": "3.3.1",
        "dspy_ai": "3.3.1",
        "gepa": "0.1.4",
        "provider": "openai-compatible",
        "typed_contract": "typed_lm",
        "model": "baseline-text",
        "base_url": "http://127.0.0.1:1234/v1",
        "timeout_seconds": "30",
        "network_scope": "exact_ip_literal_loopback_client_hop_only",
        "backend_locality": "unverified_not_established_by_loopback_client_hop",
        "credentials_allowed": False,
        "microphone_allowed": False,
        "tts_allowed": False,
        "physical_key_allowed": False,
    }:
        raise SoomfonEvaluationContractError("contract runtime target is invalid")
    executor = _require_exact_keys(
        payload.get("executor_contract"),
        {
            "implementation_ready",
            "execution_authorized",
            "implementation_requires_separate_exact_ak_task",
            "expected_contract_sha256_source",
            "expected_contract_sha256_argument_required",
            "derive_expected_contract_sha256_from_contract_forbidden",
            "required_executor_properties",
            "required_environment",
            "forbidden_environment",
            "required_negative_tests",
            "known_blockers",
        },
        label="contract executor",
    )
    _require_exact_keys(
        executor.get("required_environment"),
        set(REQUIRED_ENVIRONMENT),
        label="contract executor environment",
    )
    if (
        executor.get("required_environment") != REQUIRED_ENVIRONMENT
        or executor.get("forbidden_environment") != ["DSPX_OPENAI_COMPAT_API_KEY"]
        or executor.get("implementation_ready") is not True
        or executor.get("execution_authorized") is not False
        or executor.get("implementation_requires_separate_exact_ak_task") is not True
        or executor.get("expected_contract_sha256_argument_required") is not True
        or executor.get("derive_expected_contract_sha256_from_contract_forbidden")
        is not True
    ):
        raise SoomfonEvaluationContractError("contract executor semantics are invalid")
    ledger = _require_exact_keys(
        payload.get("attempt_ledger"),
        {
            "implementation_required",
            "storage",
            "directory_mode",
            "file_mode",
            "directory_owner",
            "symlink_policy",
            "concurrency",
            "marker_create_flags",
            "key_fields",
            "pre_effect_state",
            "terminal_states",
            "pre_effect_persistence",
            "terminal_transition",
            "fsync_file_before_effect",
            "fsync_containing_directory_before_effect",
            "terminal_transition_fsync_required",
            "existing_key_refuses_execution",
            "crash_or_timeout_refuses_rerun",
            "new_attempt_requires_new_contract_and_exact_ak_task",
        },
        label="contract attempt ledger",
    )
    if (
        ledger.get("implementation_required") is not True
        or ledger.get("directory_mode") != "0700"
        or ledger.get("file_mode") != "0600"
        or ledger.get("existing_key_refuses_execution") is not True
        or ledger.get("crash_or_timeout_refuses_rerun") is not True
    ):
        raise SoomfonEvaluationContractError("contract attempt ledger is invalid")
    for key in (
        "fsync_file_before_effect",
        "fsync_containing_directory_before_effect",
        "terminal_transition_fsync_required",
        "new_attempt_requires_new_contract_and_exact_ak_task",
    ):
        if ledger.get(key) is not True:
            raise SoomfonEvaluationContractError(
                "contract ledger durability is invalid"
            )
    if (
        ledger.get("pre_effect_state") != "attempted_outcome_unknown"
        or ledger.get("terminal_states")
        != ["succeeded", "failed_no_effect_proved", "effect_indeterminate"]
        or ledger.get("key_fields") != ["contract_sha256", "mode"]
    ):
        raise SoomfonEvaluationContractError("contract ledger state model is invalid")
    retention = _require_exact_keys(
        payload.get("retention"),
        {
            "predeclared_text_input_committed",
            "captured_microphone_transcript_committed",
            "predeclared_persona_intent_committed",
            "observed_response_committed",
            "response_sha256_required",
            "manifest_sha256_required",
            "runtime_episode_required",
            "receipt_integrity_required",
            "provider_effect_disposition_required",
            "latency_ms_required",
            "raw_response_handling",
        },
        label="contract retention",
    )
    raw_handling = _require_exact_keys(
        retention.get("raw_response_handling"),
        {
            "storage",
            "directory_mode",
            "file_mode",
            "stdout_allowed",
            "general_logging_allowed",
            "access",
            "digest_before_deletion",
            "delete_after_scoring_and_independent_review",
            "crash_handling",
            "post_deletion_score_reproduction",
        },
        label="contract raw response handling",
    )
    for key, expected in {
        "predeclared_text_input_committed": True,
        "captured_microphone_transcript_committed": False,
        "predeclared_persona_intent_committed": True,
        "observed_response_committed": False,
        "response_sha256_required": True,
        "manifest_sha256_required": True,
        "runtime_episode_required": True,
        "receipt_integrity_required": True,
        "provider_effect_disposition_required": True,
        "latency_ms_required": True,
    }.items():
        if retention.get(key) != expected:
            raise SoomfonEvaluationContractError(
                "contract retention semantics are invalid"
            )
    if (
        raw_handling.get("directory_mode") != "0700"
        or raw_handling.get("file_mode") != "0600"
        or raw_handling.get("stdout_allowed") is not False
        or raw_handling.get("general_logging_allowed") is not False
        or raw_handling.get("digest_before_deletion") is not True
    ):
        raise SoomfonEvaluationContractError("contract raw retention is invalid")
    rubric = _require_exact_keys(
        payload.get("rubric"),
        {
            "classification",
            "scorer_count",
            "independent_review_required",
            "rationale_required_per_dimension",
            "missing_or_unknown_score_fails",
            "scored_dimensions",
            "dimensions",
            "mandatory_failure",
            "bounded_observation_threshold",
            "threshold_authorizes_routing",
            "threshold_establishes_general_quality",
            "threshold_selects_winner",
        },
        label="contract rubric",
    )
    _require_exact_keys(
        rubric.get("scored_dimensions"),
        {"non_research_modes", "research_modes"},
        label="contract scored dimensions",
    )
    dimensions = _require_exact_keys(
        rubric.get("dimensions"),
        {
            "relevance",
            "mode_adherence",
            "clarity",
            "capability_truthfulness",
            "evidence_grounding",
        },
        label="contract rubric dimensions",
    )
    for anchors in dimensions.values():
        _require_exact_keys(anchors, {"0", "1", "2"}, label="contract rubric anchors")
    _require_exact_keys(
        rubric.get("bounded_observation_threshold"),
        {
            "non_research_total_min",
            "non_research_total_max",
            "research_total_min",
            "research_total_max",
            "every_scored_dimension_min",
        },
        label="contract rubric threshold",
    )
    if (
        rubric.get("independent_review_required") is not True
        or rubric.get("rationale_required_per_dimension") is not True
        or rubric.get("missing_or_unknown_score_fails") is not True
        or rubric.get("threshold_authorizes_routing") is not False
        or rubric.get("threshold_establishes_general_quality") is not False
        or rubric.get("threshold_selects_winner") is not False
    ):
        raise SoomfonEvaluationContractError("contract rubric semantics are invalid")
    deep = _require_exact_keys(
        payload.get("deep_research_disposition"),
        {
            "iterative_reactv2_retrieval",
            "external_retrieval",
            "bounded_inline_corpus",
            "decision_115_required_for_fixed_reactv2_tool",
            "button_label_is_not_capability_proof",
        },
        label="contract deep research disposition",
    )
    if (
        deep.get("iterative_reactv2_retrieval") is not False
        or deep.get("external_retrieval") is not False
        or deep.get("bounded_inline_corpus") is not True
        or deep.get("decision_115_required_for_fixed_reactv2_tool") is not True
        or deep.get("button_label_is_not_capability_proof") is not True
    ):
        raise SoomfonEvaluationContractError(
            "contract deep research posture is invalid"
        )
    nonclaims = _require_exact_keys(
        payload.get("nonclaims"),
        {
            "soomfon_physical_execution",
            "live_model_compatibility",
            "semantic_equivalence",
            "general_answer_quality",
            "gepa_improvement",
            "routing",
            "promotion",
            "activation",
            "release",
            "publication",
            "backend_locality",
        },
        label="contract nonclaims",
    )
    if any(
        nonclaims.get(key) is not False
        for key in ("routing", "promotion", "activation", "release", "publication")
    ):
        raise SoomfonEvaluationContractError("contract authority nonclaims are invalid")
    if (
        nonclaims.get("semantic_equivalence") != "not_evaluated"
        or nonclaims.get("general_answer_quality") != "not_evaluated"
        or nonclaims.get("gepa_improvement") != "not_evaluated"
        or nonclaims.get("backend_locality") != "not_verified"
        or nonclaims.get("soomfon_physical_execution") is not False
        or nonclaims.get("live_model_compatibility") is not False
    ):
        raise SoomfonEvaluationContractError("contract evidence nonclaims are invalid")
    if (
        executor.get("implementation_ready") is not True
        or executor.get("execution_authorized") is not False
    ):
        raise SoomfonEvaluationContractError("contract executor posture is invalid")
    if executor.get("expected_contract_sha256_argument_required") is not True:
        raise SoomfonEvaluationContractError("contract trust anchor is invalid")
    if (
        executor.get("derive_expected_contract_sha256_from_contract_forbidden")
        is not True
    ):
        raise SoomfonEvaluationContractError("contract self-hash posture is invalid")
    budget = _require_exact_keys(
        payload.get("effect_budget"),
        {
            "fixed_case_order",
            "candidate_invocations_per_case",
            "dspx_managed_retries",
            "health_probes",
            "selective_reruns",
            "provider_transport_call_cardinality",
            "stop_on_first_non_success",
            "effect_indeterminate_is_terminal",
            "resume_allowed",
            "fallback_allowed",
        },
        label="contract effect budget",
    )
    if budget.get("fixed_case_order") != list(EXPECTED_MODES):
        raise SoomfonEvaluationContractError("contract case order is invalid")
    for key, expected in {
        "candidate_invocations_per_case": 1,
        "dspx_managed_retries": 0,
        "health_probes": 0,
        "selective_reruns": 0,
        "effect_indeterminate_is_terminal": True,
        "resume_allowed": False,
        "fallback_allowed": False,
        "stop_on_first_non_success": True,
        "provider_transport_call_cardinality": (
            "unproved_not_bounded_by_candidate_invocation_count"
        ),
    }.items():
        if budget.get(key) != expected:
            raise SoomfonEvaluationContractError("contract effect budget is invalid")
    cases = payload.get("cases")
    if not isinstance(cases, list) or [
        row.get("mode") for row in cases if isinstance(row, dict)
    ] != list(EXPECTED_MODES):
        raise SoomfonEvaluationContractError("contract cases are invalid")
    for row in cases:
        if not isinstance(row, dict):
            raise SoomfonEvaluationContractError("contract case is invalid")
        required = {
            "mode",
            "candidate_id",
            "manifest",
            "manifest_sha256",
            "canary_index",
            "canary_index_sha256",
            "transcription",
            "persona_intent",
            "expected_posture",
        }
        if row.get("mode") in {"researched", "deep-research"}:
            required.add("corpus_sha256")
        if set(row) != required:
            raise SoomfonEvaluationContractError("contract case schema is not exact")
        for key in ("manifest_sha256", "canary_index_sha256"):
            if _SHA256_RE.fullmatch(str(row.get(key, ""))) is None:
                raise SoomfonEvaluationContractError("contract case hash is invalid")
        for key in (
            "candidate_id",
            "manifest",
            "canary_index",
            "transcription",
            "persona_intent",
            "expected_posture",
        ):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise SoomfonEvaluationContractError("contract case value is invalid")


__all__ = ["validate_soomfon_contract"]
