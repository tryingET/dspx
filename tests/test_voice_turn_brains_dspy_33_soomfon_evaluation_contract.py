from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    REPO_ROOT
    / "examples/voice_turn_brains/canaries/dspy-3.3.0/soomfon-evaluation-contract.json"
)
PREDECESSOR = (
    REPO_ROOT
    / "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/a8afebcd131d59f1bf6794d7a4748906af3fc2a99c7230f7a1256d78bafe2b18.json"
)
EARLIER = (
    REPO_ROOT
    / "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/07ba8c3559d1e527bd9fe5376a7accac2f48f617e5ba1288329a9cf4362e69eb.json"
)
DOC_PATH = REPO_ROOT / "docs/project/dspy-3-3-soomfon-originals-evaluation-contract.md"
ACTIVE_BINDING_PATH = REPO_ROOT / "examples/voice_turn_brains/ai-control-brains.json"
EXPECTED_MODES = (
    "simple",
    "elaborate",
    "researched",
    "deep-research",
    "socratic",
    "bloom",
)
RESEARCH_MODES = {"researched", "deep-research"}
CURRENT_SHA256 = "9d9d1b6ea87d3fd16e3db3e1fc97c5bbc68cc241bf67d52cf6c8b2593a1bf24b"
PREDECESSOR_SHA256 = "a8afebcd131d59f1bf6794d7a4748906af3fc2a99c7230f7a1256d78bafe2b18"
EARLIER_SHA256 = "07ba8c3559d1e527bd9fe5376a7accac2f48f617e5ba1288329a9cf4362e69eb"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def test_contract_is_execution_blocked_and_preserves_live_binding() -> None:
    contract = _load(CONTRACT_PATH)
    assert _sha256(CONTRACT_PATH) == CURRENT_SHA256
    assert (
        contract["schema_version"]
        == "soomfon-dspy-3.3-originals-evaluation-contract-v3"
    )
    assert contract["task_id"] == 4987
    assert (
        contract["status"]
        == "implementation_final_hardened_execution_unauthorized_pending_rereview"
    )
    assert contract["executor_contract"]["execution_authorized"] is False
    assert contract["executor_contract"]["task_4987_can_authorize_execution"] is False
    assert (
        contract["executor_contract"]["implementation_requires_later_exact_ak_task"]
        is True
    )
    assert contract["source_state"]["installed_binding_config_sha256"] == _sha256(
        ACTIVE_BINDING_PATH
    )
    assert contract["source_state"]["shadow_binding_only"] is True
    assert contract["nonclaims"]["routing"] is False


def test_predecessors_are_byte_exact_and_namespaces_are_immutable() -> None:
    contract = _load(CONTRACT_PATH)
    predecessor = contract["predecessor_contract"]
    assert _sha256(PREDECESSOR) == predecessor["raw_sha256"] == PREDECESSOR_SHA256
    assert (
        _sha256(EARLIER)
        == predecessor["earlier_predecessor"]["raw_sha256"]
        == EARLIER_SHA256
    )
    archived = _load(PREDECESSOR)
    assert (
        archived["schema_version"]
        == "soomfon-dspy-3.3-originals-evaluation-contract-v2"
    )
    assert archived["task_id"] == 4971
    assert predecessor["attempted_modes"] == []
    assert predecessor["unattempted_modes"] == list(EXPECTED_MODES)
    assert predecessor["retry_allowed"] is False
    assert predecessor["ledger_namespace_reuse_allowed"] is False
    assert (
        predecessor["earlier_predecessor"]["terminal_disposition"]
        == "effect_indeterminate"
    )


def test_contract_binds_all_six_fresh_originals_exactly() -> None:
    contract = _load(CONTRACT_PATH)
    predecessor = _load(PREDECESSOR)
    assert contract["cases"] == predecessor["cases"]
    assert contract["effect_budget"]["fixed_case_order"] == list(EXPECTED_MODES)
    active = _load(ACTIVE_BINDING_PATH)
    for case in contract["cases"]:
        mode = case["mode"]
        manifest_path = REPO_ROOT / case["manifest"]
        canary_path = REPO_ROOT / case["canary_index"]
        assert SHA256_PATTERN.fullmatch(case["manifest_sha256"])
        assert SHA256_PATTERN.fullmatch(case["canary_index_sha256"])
        assert _sha256(manifest_path) == case["manifest_sha256"]
        assert _sha256(canary_path) == case["canary_index_sha256"]
        manifest = _load(manifest_path)
        canary = _load(canary_path)
        assert manifest["candidate_assembly"]["candidate_id"] == case["candidate_id"]
        assert (
            canary["fresh_candidate"]["identity"]["candidate_id"]
            == case["candidate_id"]
        )
        assert canary["fresh_candidate"]["generation_dspy"]["version"] == "3.3.1"
        assert (
            canary["safety"]["policy"] == "unchanged_soomfon_protected_snapshot_policy"
        )
        assert (
            canary["fresh_candidate"]["generated_behavior"]["quality_approved"] is False
        )
        assert active["programs"][mode]["program_id"] != case["candidate_id"]


def test_provider_owner_and_runtime_identity_are_exact() -> None:
    contract = _load(CONTRACT_PATH)
    owner = contract["provider_owner_candidate"]
    assert owner["owner_task_id"] == 4991
    assert owner["commit"] == "7c51dda703f6a5d0a95aba13734294a82ea4314f"
    assert owner["tree"] == "c303dd657146da90404618adead417e82e2dc2c0"
    assert owner["version"] == "0.1.6.dev0"
    assert (
        owner["wheel_sha256"]
        == "e1b8acaa354df4640422512a779b9486d5c4caceeb9c9ab05c4a07f1b1eb3512"
    )
    assert (
        owner["installed_payload_sha256"]
        == "8c8a2aa569df171fab35e25b02cb313ee20725901c7bec7ede0edc2364dccaf2"
    )
    assert set(owner["module_sha256"]) == {
        "package_init",
        "auth",
        "lm",
        "codex_stream",
        "codex_stream_support",
        "outcome_receipt",
        "outcome_receipt_runtime",
        "outcome_receipt_state",
        "outcome_receipt_transport",
    }
    assert set(owner["dependency_identity"]) == {"dspy", "litellm", "httpx", "httpcore"}
    assert owner["dependency_identity"]["dspy"]["version"] == "3.3.1"
    assert owner["dependency_identity"]["litellm"]["version"] == "1.82.1"
    assert owner["dependency_identity"]["litellm"]["record_sha256"] == (
        "ecd60ab285a5c0afe8353e1e2838f7560aa525715fb6747a5e0f485f9d56c71d"
    )
    assert owner["dependency_identity"]["httpx"]["record_sha256"] == (
        "ad5388cd6ffec977fd4a0c61f550a6a3cbf3ef22cd4098fe01be6101b19194f0"
    )
    runtime = contract["runtime_target"]
    assert runtime["requested_route"] == "dspy-lm-auth:codex:gpt-5.6-sol:max"
    assert runtime["resolved_route"] == "openai:gpt-5.6-sol:responses"
    assert runtime["requested_model"] == "codex/gpt-5.6-sol"
    assert runtime["auth_provider"] == "codex"
    assert runtime["credential_mode"] == "no-refresh"
    assert runtime["reasoning_effort"] == "max"
    assert runtime["num_retries"] == 0
    assert runtime["cache"] is False
    assert runtime["timeout_seconds"] == 60
    assert runtime["fallback_allowed"] is False
    assert runtime["dspx_lm_subclass_added"] is False


def test_executor_attempt_receipt_and_retention_requirements_are_explicit() -> None:
    contract = _load(CONTRACT_PATH)
    executor = contract["executor_contract"]
    assert (
        executor["authorization_validation_order"]
        == "parent_canonical_ak_reconciliation_before_state_and_every_marker_child_reconciliation_before_provider_import_and_90_second_minimum_reconciliation_before_each_logical_call"
    )
    assert (
        executor["execution_authorization_schema"]
        == "soomfon-execution-authorization-v3"
    )
    assert executor["child_runtime_queries_ak"] is True
    assert executor["canonical_ak_runtime"] == {
        "path": "/home/tryinget/.local/libexec/agent-kernel/c6297eccf67a3762ef01269f67e87eaa8828f127/ak-bin",
        "sha256": "61f6290115262e0319c3b178f053d74a486a3eba881aaa13739c1db45f0f6b91",
        "mode": "0555",
        "open_policy": "exact_path_O_NOFOLLOW_hash_fd_execute_proc_fd_pass_fds_refstat",
    }
    assert executor["lease_requirements"]["suite_preflight_minimum_seconds"] == 1800
    assert (
        executor["lease_requirements"]["before_each_logical_call_minimum_seconds"] == 90
    )
    assert (
        "not_cryptographic_distinct_principal"
        in executor["canonical_evidence_semantics"]
    )
    assert contract["runtime_target"]["dont_write_bytecode_required"] is True
    assert contract["runtime_target"]["child_python_flag_B_required"] is True
    assert contract["runtime_target"]["bytecode_cache_allowed"] is False
    budget = contract["effect_budget"]
    assert budget["ordered_logical_lm_calls_per_successful_case"] == 2
    assert budget["maximum_suite_logical_lm_calls"] == 12
    assert budget["maximum_suite_provider_transports"] == 12
    assert budget["dspx_managed_retries"] == budget["provider_configured_retries"] == 0
    assert budget["health_probes"] == budget["selective_reruns"] == 0
    assert budget["resume_allowed"] is budget["fallback_allowed"] is False
    receipt = contract["provider_receipt_custody"]
    assert receipt["existing_accepted_v11_owner_identity_unchanged"] is True
    assert receipt["verify_owner_source_before_marker"] is True
    assert receipt["verify_loaded_receipt_types_before_call"] is True
    assert receipt["revalidate_before_each_call_and_progression"] is True
    assert receipt["missing_open_poisoned_indeterminate_chain_terminal"] is True
    assert receipt["provider_evidence_retains_only"] == [
        "hashes",
        "identities",
        "closed_receipt_projections",
    ]
    raw = contract["retention"]["raw_response_handling"]
    assert raw["stdout_allowed"] is raw["general_logging_allowed"] is False
    assert raw["directory_mode"] == "0700" and raw["file_mode"] == "0600"


def test_research_and_bloom_cases_match_candidate_capabilities() -> None:
    contract = _load(CONTRACT_PATH)
    for case in contract["cases"]:
        manifest = _load(REPO_ROOT / case["manifest"])
        modules = manifest["program_plan"]["topology"]["modules"]
        retrievers = [item for item in modules if item.get("primitive") == "Retriever"]
        if case["mode"] in RESEARCH_MODES:
            assert case["corpus_sha256"] == _hash_json(
                [item["retriever"]["documents"] for item in retrievers]
            )
        else:
            assert "corpus_sha256" not in case
    assert contract["deep_research_disposition"]["iterative_reactv2_retrieval"] is False
    assert contract["deep_research_disposition"]["external_retrieval"] is False


def test_unknown_missing_or_safety_drift_fails_exact_validator() -> None:
    from dspx.services.soomfon_evaluation_contract import validate_soomfon_contract

    contract = _load(CONTRACT_PATH)
    for mutate in (
        lambda value: value.__setitem__("unexpected", True),
        lambda value: value.pop("attempt_ledger"),
        lambda value: value["effect_budget"].__setitem__(
            "maximum_suite_provider_transports", 13
        ),
        lambda value: value["runtime_target"].__setitem__("cache", True),
        lambda value: value["nonclaims"].__setitem__("routing", True),
    ):
        changed = copy.deepcopy(contract)
        mutate(changed)
        with pytest.raises(Exception):
            validate_soomfon_contract(changed)


def test_documentation_and_nonclaims_match_machine_contract() -> None:
    document = DOC_PATH.read_text(encoding="utf-8")
    for phrase in (
        "pending independent rereview, execution unauthorized",
        "dspy-lm-auth",
        "no-refresh",
        "exactly two",
        "maximum twelve",
        "execution authorization",
        CURRENT_SHA256,
        PREDECESSOR_SHA256,
        "must remain unchanged",
    ):
        assert phrase in document
    nonclaims = _load(CONTRACT_PATH)["nonclaims"]
    assert all(
        nonclaims[key] is False
        for key in ("routing", "promotion", "activation", "release", "publication")
    )


def test_each_fixed_candidate_has_exactly_two_lm_modules() -> None:
    contract = _load(CONTRACT_PATH)
    for case in contract["cases"]:
        module_path = (REPO_ROOT / case["manifest"]).with_name("module.py")
        source = module_path.read_text(encoding="utf-8")
        logical_lm_constructors = source.count("dspy.Predict(") + source.count(
            "dspy.ChainOfThought("
        )
        assert logical_lm_constructors == 2
        if case["mode"] in RESEARCH_MODES:
            assert "dspy.Prediction(passages=" in source
