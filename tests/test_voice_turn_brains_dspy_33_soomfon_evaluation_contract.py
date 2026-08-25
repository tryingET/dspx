from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from dspx.services import soomfon_evaluation_contract as contract_service


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    REPO_ROOT
    / "examples/voice_turn_brains/canaries/dspy-3.3.0/soomfon-evaluation-contract.json"
)
IMMEDIATE_PREDECESSOR = (
    REPO_ROOT
    / "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/9034944d7bfcb48624b83fb650cd02c6a43ba401d75a614beb7bd7906be9a837.json"
)
PREDECESSOR = (
    REPO_ROOT
    / "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/44a28a7fa3b0e9ebe600109f8ac36acecc1afad0335c9f186b575ad14965cb97.json"
)
EARLIER = (
    REPO_ROOT
    / "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/6c3f913c2fe05eb5edfc39ee0cbea1a4ca43036bdd0e77c9ad3f37d35c0eadae.json"
)
INTERMEDIATE = (
    REPO_ROOT
    / "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/56b2f269bd6b494a2d4d08c716787449cde5dd5a63bbbfc5d4666feb32306e3a.json"
)
EARLIEST = (
    REPO_ROOT
    / "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/cea459c1926e7cd765372e926a23fbcefab1cfa061024f720de76ba35d002e0d.json"
)
UNATTEMPTED = (
    REPO_ROOT
    / "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/0f602482f29037d1a8f0c71731872390614198998d1fda94079172052cc29207.json"
)
OLDER = (
    REPO_ROOT
    / "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/9d9d1b6ea87d3fd16e3db3e1fc97c5bbc68cc241bf67d52cf6c8b2593a1bf24b.json"
)
ANCIENT = (
    REPO_ROOT
    / "examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/a8afebcd131d59f1bf6794d7a4748906af3fc2a99c7230f7a1256d78bafe2b18.json"
)
ORIGINAL = (
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
CURRENT_SHA256 = "8bc157034ade33e34df33bd059910b24ae7debb06e9d4fb6aadf348ca3760555"
IMMEDIATE_PREDECESSOR_SHA256 = (
    "9034944d7bfcb48624b83fb650cd02c6a43ba401d75a614beb7bd7906be9a837"
)
PREDECESSOR_SHA256 = "44a28a7fa3b0e9ebe600109f8ac36acecc1afad0335c9f186b575ad14965cb97"
EARLIER_SHA256 = "6c3f913c2fe05eb5edfc39ee0cbea1a4ca43036bdd0e77c9ad3f37d35c0eadae"
INTERMEDIATE_SHA256 = "56b2f269bd6b494a2d4d08c716787449cde5dd5a63bbbfc5d4666feb32306e3a"
EARLIEST_SHA256 = "cea459c1926e7cd765372e926a23fbcefab1cfa061024f720de76ba35d002e0d"
UNATTEMPTED_SHA256 = "0f602482f29037d1a8f0c71731872390614198998d1fda94079172052cc29207"
OLDER_SHA256 = "9d9d1b6ea87d3fd16e3db3e1fc97c5bbc68cc241bf67d52cf6c8b2593a1bf24b"
ANCIENT_SHA256 = "a8afebcd131d59f1bf6794d7a4748906af3fc2a99c7230f7a1256d78bafe2b18"
ORIGINAL_SHA256 = "07ba8c3559d1e527bd9fe5376a7accac2f48f617e5ba1288329a9cf4362e69eb"
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


def _copy_contract_chain(root: Path) -> None:
    for source in (
        CONTRACT_PATH,
        IMMEDIATE_PREDECESSOR,
        PREDECESSOR,
        EARLIER,
        INTERMEDIATE,
        EARLIEST,
        OLDER,
        ANCIENT,
        ORIGINAL,
    ):
        target = root / source.relative_to(REPO_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def _write_chain_archive(root: Path, relative: str, payload: object) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_production_loader_reaches_complete_predecessor_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: set[Path] = set()
    read_stable = contract_service._read_stable_regular_file

    def track(path: Path, *, max_bytes: int) -> bytes:
        observed.add(path.resolve())
        return read_stable(path, max_bytes=max_bytes)

    monkeypatch.setattr(contract_service, "_read_stable_regular_file", track)
    contract_service.load_hash_bound_soomfon_contract(
        repo_root=REPO_ROOT, expected_sha256=CURRENT_SHA256
    )

    assert {
        IMMEDIATE_PREDECESSOR.resolve(),
        PREDECESSOR.resolve(),
        EARLIER.resolve(),
        INTERMEDIATE.resolve(),
        EARLIEST.resolve(),
        OLDER.resolve(),
        ANCIENT.resolve(),
        ORIGINAL.resolve(),
    } <= observed


@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_loader_rejects_missing_or_tampered_earliest_archive(
    tmp_path: Path, mutation: str
) -> None:
    _copy_contract_chain(tmp_path)
    original = tmp_path / ORIGINAL.relative_to(REPO_ROOT)
    if mutation == "missing":
        original.unlink()
    else:
        original.write_bytes(original.read_bytes() + b" ")

    with pytest.raises(contract_service.SoomfonEvaluationContractError):
        contract_service.load_hash_bound_soomfon_contract(
            repo_root=tmp_path, expected_sha256=CURRENT_SHA256
        )


def test_loader_rejects_nested_predecessor_summary_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_json = contract_service._load_json_bytes

    def drift_nested_summary(raw: bytes, *, label: str) -> dict[str, Any]:
        value = load_json(raw, label=label)
        if label == "predecessor contract archive" and value.get("task_id") == 4987:
            value = copy.deepcopy(value)
            value["predecessor_contract"]["earlier_predecessor"]["raw_sha256"] = (
                "f" * 64
            )
        return value

    canonical_sha256 = contract_service._canonical_json_sha256

    def preserve_bound_canonical(value: dict[str, Any]) -> str:
        if value.get("task_id") == 4987:
            return "f9924fcf0bd7a402d91c0dca55bced09a827aad08b8f49a21408ae1175fa0c64"
        return canonical_sha256(value)

    monkeypatch.setattr(contract_service, "_load_json_bytes", drift_nested_summary)
    monkeypatch.setattr(
        contract_service, "_canonical_json_sha256", preserve_bound_canonical
    )
    with pytest.raises(
        contract_service.SoomfonEvaluationContractError, match="summary"
    ):
        contract_service.load_hash_bound_soomfon_contract(
            repo_root=REPO_ROOT, expected_sha256=CURRENT_SHA256
        )


def test_recursive_predecessor_verifier_rejects_cycle(tmp_path: Path) -> None:
    relative = "archives/cycle.json"
    payload = {
        "predecessor_contract": {
            "archive_path": relative,
            "raw_sha256": "0" * 64,
        }
    }
    digest = _write_chain_archive(tmp_path, relative, payload)
    contract = {
        "predecessor_contract": {
            "archive_path": relative,
            "raw_sha256": digest,
        }
    }

    with pytest.raises(
        contract_service.SoomfonEvaluationContractError, match="cycle|duplicate"
    ):
        contract_service.validate_predecessor_contract_bindings(
            repo_root=tmp_path, contract=contract
        )


def test_recursive_predecessor_verifier_rejects_depth_overflow(
    tmp_path: Path,
) -> None:
    binding: dict[str, Any] | None = None
    for depth in range(10):
        relative = f"archives/{depth}.json"
        payload = {} if binding is None else {"predecessor_contract": binding}
        digest = _write_chain_archive(tmp_path, relative, payload)
        binding = {"archive_path": relative, "raw_sha256": digest}
    assert binding is not None

    with pytest.raises(contract_service.SoomfonEvaluationContractError, match="depth"):
        contract_service.validate_predecessor_contract_bindings(
            repo_root=tmp_path, contract={"predecessor_contract": binding}
        )


@pytest.mark.parametrize("canonical_sha256", [None, "0" * 64])
def test_recursive_predecessor_verifier_rejects_invalid_present_canonical_hash(
    tmp_path: Path, canonical_sha256: object
) -> None:
    relative = "archives/canonical.json"
    digest = _write_chain_archive(tmp_path, relative, {})
    binding = {
        "archive_path": relative,
        "raw_sha256": digest,
        "canonical_sha256": canonical_sha256,
    }

    with pytest.raises(
        contract_service.SoomfonEvaluationContractError, match="canonical"
    ):
        contract_service.validate_predecessor_contract_bindings(
            repo_root=tmp_path, contract={"predecessor_contract": binding}
        )


def test_recursive_predecessor_verifier_rejects_symlink_and_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    (root / "linked.json").symlink_to(outside)
    for archive_path in ("linked.json", "../outside.json"):
        with pytest.raises(contract_service.SoomfonEvaluationContractError):
            contract_service.validate_predecessor_contract_bindings(
                repo_root=root,
                contract={
                    "predecessor_contract": {
                        "archive_path": archive_path,
                        "raw_sha256": digest,
                    }
                },
            )


def test_recursive_predecessor_verifier_rejects_malformed_archive(
    tmp_path: Path,
) -> None:
    relative = "archives/malformed.json"
    archive = tmp_path / relative
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"not-json")
    binding = {
        "archive_path": relative,
        "raw_sha256": hashlib.sha256(b"not-json").hexdigest(),
    }

    with pytest.raises(contract_service.SoomfonEvaluationContractError, match="JSON"):
        contract_service.validate_predecessor_contract_bindings(
            repo_root=tmp_path, contract={"predecessor_contract": binding}
        )


def test_contract_is_execution_blocked_and_preserves_live_binding() -> None:
    contract = _load(CONTRACT_PATH)
    assert _sha256(CONTRACT_PATH) == CURRENT_SHA256
    assert (
        contract["schema_version"]
        == "soomfon-dspy-3.3-originals-evaluation-contract-v4"
    )
    assert contract["task_id"] == 5071
    assert (
        contract["status"]
        == "luna_xhigh_remote_error_truth_repaired_execution_unauthorized_pending_review"
    )
    assert contract["executor_contract"]["execution_authorized"] is False
    assert contract["executor_contract"]["task_5071_can_authorize_execution"] is False
    assert (
        contract["executor_contract"]["implementation_requires_later_exact_ak_task"]
        is True
    )
    assert contract["source_state"]["installed_binding_config_sha256"] == _sha256(
        ACTIVE_BINDING_PATH
    )
    assert contract["source_state"]["shadow_binding_only"] is True
    assert contract["nonclaims"]["routing"] is False
    assert contract["diagnostic_canary"]["one_provider_transport_claim"] is False
    assert contract["diagnostic_canary"]["execution_authorized"] is False


def test_predecessors_are_byte_exact_and_namespaces_are_immutable() -> None:
    contract = _load(CONTRACT_PATH)
    immediate = contract["predecessor_contract"]
    assert _sha256(IMMEDIATE_PREDECESSOR) == IMMEDIATE_PREDECESSOR_SHA256
    assert immediate["raw_sha256"] == IMMEDIATE_PREDECESSOR_SHA256
    assert immediate["execution_task_id"] == 5065
    assert immediate["execution_disposition"] == "effect_indeterminate"
    assert immediate["terminal_reason"] == "attributable_completion_required"
    assert immediate["attempted_modes"] == ["simple"]
    assert immediate["provider_transports"] == "at_most_one"
    assert immediate["retry_allowed"] is False
    assert immediate["ledger_namespace_reuse_allowed"] is False

    predecessor_binding = _load(IMMEDIATE_PREDECESSOR)["predecessor_contract"]
    assert (
        _sha256(PREDECESSOR) == predecessor_binding["raw_sha256"] == PREDECESSOR_SHA256
    )
    assert predecessor_binding["execution_task_id"] == 5060
    assert predecessor_binding["execution_disposition"] == "pre_effect_review_rejected"
    assert predecessor_binding["provider_transports"] == 0
    assert predecessor_binding["state_created"] is False

    earlier_binding = _load(PREDECESSOR)["predecessor_contract"]
    assert _sha256(EARLIER) == earlier_binding["raw_sha256"] == EARLIER_SHA256
    assert _sha256(INTERMEDIATE) == INTERMEDIATE_SHA256
    assert _sha256(EARLIEST) == EARLIEST_SHA256
    assert _sha256(UNATTEMPTED) == UNATTEMPTED_SHA256
    assert _sha256(OLDER) == OLDER_SHA256
    assert _sha256(ANCIENT) == ANCIENT_SHA256
    assert _sha256(ORIGINAL) == ORIGINAL_SHA256

    archived = _load(EARLIER)
    assert archived["task_id"] == 5042
    assert (
        archived["status"]
        == "luna_xhigh_fd_journal_repair_execution_unauthorized_pending_review"
    )
    assert earlier_binding["task_id"] == 5042
    assert earlier_binding["execution_task_id"] == 5045
    assert earlier_binding["attempted_modes"] == ["simple"]
    assert earlier_binding["unattempted_modes"] == list(EXPECTED_MODES[1:])
    assert earlier_binding["terminal_disposition"] == "effect_indeterminate"
    assert earlier_binding["terminal_reason"] == "provider_receipt_journal_invalid"
    assert earlier_binding["response_sha256"] == (
        "749af25da49ba89dda58ee9bf2b02114282241def1f5d7c2b4430e43be22edbb"
    )
    assert earlier_binding["response_length"] == 304
    assert len(earlier_binding["completed_receipt_chains"]) == 2
    assert earlier_binding["retry_allowed"] is False
    assert earlier_binding["empirical_relabel_allowed"] is False
    assert earlier_binding["ledger_namespace_reuse_allowed"] is False
    assert earlier_binding["unattempted_modes_execution_authority_transferred"] is False


def test_contract_binds_all_six_fresh_originals_exactly() -> None:
    contract = _load(CONTRACT_PATH)
    predecessor = _load(IMMEDIATE_PREDECESSOR)
    assert contract["cases"] == predecessor["cases"]
    assert contract["rubric"] == predecessor["rubric"]
    assert (
        contract["provider_owner_candidate"] != predecessor["provider_owner_candidate"]
    )
    assert contract["runtime_target"] == predecessor["runtime_target"]
    assert contract["effect_budget"] == {
        **predecessor["effect_budget"],
        "failed_provider_error_is_terminal": True,
    }
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
    assert owner["owner_task_id"] == 5070
    assert owner["commit"] == "4bdc3bb2e341b8ebff088828c8604ff8051b5d49"
    assert owner["tree"] == "816c77372e5e9becd5ecc5b95d336625ceb56815"
    assert owner["version"] == "0.1.6.dev0"
    assert owner["wheel_sha256"] is None
    assert owner["installed_payload_sha256"] is None
    assert owner["module_sha256"]["outcome_receipt"] == (
        "dd8b2ff9279d0098e40d04d486a9aa550328650a57d5205971df240bcd4b4d0d"
    )
    assert owner["module_sha256"]["outcome_receipt_state"] == (
        "0f6686b3204df451044f391c66e48ab78a867d997f48fba958d0a1068b9a6f26"
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
        "1830d79944869e8916526cf9fbe9adbc429dfaefbb1bf189d26caebbfed84ac6"
    )
    assert owner["dependency_identity"]["httpx"]["record_sha256"] == (
        "36876854dd991fdbea093ead83f852baf1d9e777126dac8e5d6b722ce0753e92"
    )
    runtime = contract["runtime_target"]
    assert runtime["requested_route"] == "dspy-lm-auth:codex:gpt-5.6-luna:xhigh"
    assert runtime["resolved_route"] == "openai:gpt-5.6-luna:responses"
    assert runtime["requested_model"] == "codex/gpt-5.6-luna"
    assert runtime["auth_provider"] == "codex"
    assert runtime["credential_mode"] == "no-refresh"
    assert runtime["reasoning_effort"] == "xhigh"
    assert runtime["num_retries"] == 0
    assert runtime["cache"] is False
    assert runtime["litellm_local_model_cost_map"] is True
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
    assert (
        executor["canonical_authorization_evidence_schema"]
        == "soomfon-ak5071-authorization-evidence-v4"
    )
    assert executor["live_completion_kind"] == (
        "soomfon_ak5071_ak5070_one_suite_execution_authorization"
    )
    assert {
        "exact_repo_and_done_task_5071_dependency",
        "exact_done_ak_5070_owner_task_and_artifact_identity",
        "exact_live_completion_kind_and_guardrails_binding_ak_5070",
        "exact_ak_5070_owner_source_commit_tree_lock_modules_and_dependencies",
    } <= set(executor["authorization_required_fields"])
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
    assert contract["runtime_target"]["litellm_local_model_cost_map"] is True
    assert (
        "force_litellm_bundled_local_model_cost_map_before_owner_import"
        in executor["required_executor_properties"]
    )
    assert (
        "protect_and_hash_bind_all_soomfon_v2_receipt_modules"
        in executor["required_executor_properties"]
    )
    budget = contract["effect_budget"]
    assert budget["ordered_logical_lm_calls_per_successful_case"] == 2
    assert budget["maximum_suite_logical_lm_calls"] == 12
    assert budget["maximum_suite_provider_transports"] == 12
    assert budget["dspx_managed_retries"] == budget["provider_configured_retries"] == 0
    assert budget["health_probes"] == budget["selective_reruns"] == 0
    assert budget["resume_allowed"] is budget["fallback_allowed"] is False
    assert budget["failed_provider_error_is_terminal"] is True
    receipt = contract["provider_receipt_custody"]
    assert receipt["module_stack"] == {
        "contract": "dspx.services.soomfon_provider_outcome_receipt_contract",
        "identity": "dspx.services.soomfon_provider_outcome_receipt_identity",
        "journal": "dspx.services.soomfon_provider_outcome_receipt_journal",
        "journal_fd": "dspx.services.soomfon_provider_outcome_receipt_journal_fd",
        "reducer": "dspx.services.soomfon_provider_outcome_receipt_reducer",
    }
    assert receipt["event_schema"] == "AK-5070_eight_field_exact_status_v2"
    assert receipt["frozen_v11_parser_or_identity_used"] is False
    assert receipt["accepted_owner_identity"] == "AK-5070_exact_source_candidate"
    assert receipt["accepted_evidence_terminals"] == [
        "provider_response_completed",
        "remote_http_error_final",
    ]
    assert receipt["progression_authorized_terminal"] == "provider_response_completed"
    assert receipt["provider_error_terminal_state"] == "failed_provider_error"
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
        "pending independent review, execution unauthorized",
        "failed_provider_error",
        "receipt integrity",
        "one-provider-transport diagnostic",
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
