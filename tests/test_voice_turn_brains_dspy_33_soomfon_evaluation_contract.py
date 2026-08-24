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
TOP_LEVEL_KEYS = {
    "schema_version",
    "task_id",
    "status",
    "purpose",
    "source_state",
    "runtime_target",
    "executor_contract",
    "effect_budget",
    "attempt_ledger",
    "retention",
    "rubric",
    "cases",
    "deep_research_disposition",
    "nonclaims",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def _validate_top_level_shape(contract: dict[str, Any]) -> None:
    if set(contract) != TOP_LEVEL_KEYS:
        raise ValueError("contract top-level schema is not exact")
    if contract.get("schema_version") != (
        "soomfon-dspy-3.3-originals-evaluation-contract-v1"
    ):
        raise ValueError("contract schema version is invalid")


def test_contract_is_execution_blocked_and_preserves_live_binding() -> None:
    contract = _load(CONTRACT_PATH)
    _validate_top_level_shape(contract)
    assert contract["task_id"] == 4808
    assert contract["status"] == "design_only_execution_blocked"

    source = contract["source_state"]
    assert set(source) == {
        "dspx_base_commit",
        "workstation_reconciliation_commit",
        "local_ai_control_plane_commit",
        "installed_binding_config",
        "installed_binding_config_sha256",
        "installed_binding_disposition",
        "shadow_binding_only",
    }
    for key in (
        "dspx_base_commit",
        "workstation_reconciliation_commit",
        "local_ai_control_plane_commit",
    ):
        assert re.fullmatch(r"[0-9a-f]{40}", source[key])
    assert source["dspx_base_commit"] == "733b80bdc6fdac99f631690a36814f35299721d2"
    assert source["workstation_reconciliation_commit"] == (
        "65c594a36acc357788b138bea6574163c69fe7b5"
    )
    assert source["local_ai_control_plane_commit"] == (
        "ec8bcfb4a253b1b5bc5d340a310694e1a98bab3b"
    )
    assert source["shadow_binding_only"] is True
    assert source["installed_binding_config"] == (
        "examples/voice_turn_brains/ai-control-brains.json"
    )
    assert source["installed_binding_disposition"] == (
        "historical_dspy_3_1_3_optimized_candidates_unchanged"
    )
    assert _sha256(ACTIVE_BINDING_PATH) == source["installed_binding_config_sha256"]

    assert contract["runtime_target"] == {
        "python": "3.13.12",
        "dspx_core": "0.2.0",
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
    }


def test_contract_binds_all_six_fresh_originals_exactly() -> None:
    contract = _load(CONTRACT_PATH)
    cases = contract["cases"]
    assert [case["mode"] for case in cases] == list(EXPECTED_MODES)
    assert contract["effect_budget"]["fixed_case_order"] == list(EXPECTED_MODES)

    active = _load(ACTIVE_BINDING_PATH)
    assert set(active["programs"]) == set(EXPECTED_MODES)

    for case in cases:
        mode = case["mode"]
        expected_case_keys = {
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
        if mode in RESEARCH_MODES:
            expected_case_keys.add("corpus_sha256")
        assert set(case) == expected_case_keys

        manifest_path = REPO_ROOT / case["manifest"]
        canary_path = REPO_ROOT / case["canary_index"]
        assert manifest_path.is_file()
        assert canary_path.is_file()
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
        assert canary["fresh_candidate"]["manifest"]["path"] == case["manifest"]
        assert (
            canary["fresh_candidate"]["manifest"]["sha256"] == case["manifest_sha256"]
        )
        assert canary["fresh_candidate"]["generation_dspy"]["version"] == "3.3.0"
        assert canary["fresh_candidate"]["provider"] == {
            "credentials_used": False,
            "live_model_used": False,
            "model": "stub/echo",
            "name": "stub",
            "network_used": False,
            "typed_contract": "typed_lm",
        }
        generated = canary["fresh_candidate"]["generated_behavior"]
        assert generated["behavior_quality"] == "not_evaluated"
        assert generated["semantic_equivalence"] == "not_evaluated"
        assert generated["quality_approved"] is False

        assert "/canaries/dspy-3.3.0/" in f"/{case['manifest']}"
        assert "/candidate/manifest.json" in f"/{case['manifest']}"
        assert active["programs"][mode]["program_id"] != case["candidate_id"]
        assert active["programs"][mode]["manifest"] != case["manifest"]
        surface_paths = {
            str(surface.get("path", ""))
            for surface in manifest["candidate_assembly"]["surfaces"]
            if isinstance(surface, dict)
        }
        assert not any(
            path.lower().endswith((".pkl", ".pickle", ".bin")) for path in surface_paths
        )

        for key in ("transcription", "persona_intent", "expected_posture"):
            assert isinstance(case[key], str) and case[key].strip()


def test_research_and_bloom_cases_match_candidate_capabilities() -> None:
    contract = _load(CONTRACT_PATH)
    for case in contract["cases"]:
        manifest = _load(REPO_ROOT / case["manifest"])
        modules = manifest["program_plan"]["topology"]["modules"]
        retrievers = [
            module
            for module in modules
            if isinstance(module, dict) and module.get("primitive") == "Retriever"
        ]
        documents = [
            module.get("retriever", {}).get("documents") for module in retrievers
        ]
        if case["mode"] in RESEARCH_MODES:
            assert retrievers
            assert case["corpus_sha256"] == _hash_json(documents)
        else:
            assert "corpus_sha256" not in case

    deep = contract["deep_research_disposition"]
    assert deep == {
        "iterative_reactv2_retrieval": False,
        "external_retrieval": False,
        "bounded_inline_corpus": True,
        "decision_115_required_for_fixed_reactv2_tool": True,
        "button_label_is_not_capability_proof": True,
    }
    deep_case = next(
        case for case in contract["cases"] if case["mode"] == "deep-research"
    )
    assert deep_case["expected_posture"] == (
        "bounded_multi_perspective_local_corpus_synthesis_not_iterative_reactv2"
    )

    bloom_case = next(case for case in contract["cases"] if case["mode"] == "bloom")
    bloom_manifest = _load(REPO_ROOT / bloom_case["manifest"])
    bloom_modules = bloom_manifest["program_plan"]["topology"]["modules"]
    bloom_role = next(
        module["role"] for module in bloom_modules if module["id"] == "teach_with_bloom"
    )
    assert bloom_role == "bloom_correct_teach_end_with_unanswered_requiz_question"
    assert "I think" in bloom_case["transcription"]
    assert bloom_case["expected_posture"] == (
        "correct_misconception_advance_one_bloom_level_"
        "end_with_unanswered_transfer_question"
    )


def test_executor_attempt_and_retention_requirements_are_explicit() -> None:
    contract = _load(CONTRACT_PATH)
    executor = contract["executor_contract"]
    assert executor["execution_ready"] is False
    assert executor["implementation_requires_separate_exact_ak_task"] is True
    assert executor["expected_contract_sha256_source"] == (
        "out_of_band_exact_ak_execution_task_plus_independent_review_evidence"
    )
    assert executor["expected_contract_sha256_argument_required"] is True
    assert executor["derive_expected_contract_sha256_from_contract_forbidden"] is True
    assert set(executor["required_environment"].items()) == {
        ("DSPX_PROVIDER", "openai-compatible"),
        ("DSPX_OPENAI_COMPAT_MODEL", "baseline-text"),
        ("DSPX_OPENAI_COMPAT_API_BASE", "http://127.0.0.1:1234/v1"),
        ("DSPX_OPENAI_COMPAT_TIMEOUT", "30"),
        ("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1"),
    }
    assert executor["forbidden_environment"] == ["DSPX_OPENAI_COMPAT_API_KEY"]
    assert set(executor["known_blockers"]) == {
        "no_hash_bound_executor_or_negative_test_matrix_exists_yet",
        "the_current_lacp_dspx_brain_discards_runtime_id_and_does_not_return_provider_effect_disposition",
        "no_durable_contract_hash_and_case_keyed_attempt_ledger_exists_yet",
    }
    required_negative = set(executor["required_negative_tests"])
    assert {
        "missing_endpoint",
        "localhost_endpoint",
        "ipv6_loopback_endpoint",
        "alternate_port",
        "alternate_path",
        "alternate_model",
        "alternate_timeout",
        "credential_variable_present",
        "missing_out_of_band_contract_hash",
        "incorrect_out_of_band_contract_hash",
        "contract_hash_drift",
        "existing_attempt_marker",
        "ledger_wrong_owner_or_mode",
        "ledger_symlink_or_non_directory",
        "concurrent_duplicate_attempt",
        "crash_before_containing_directory_fsync",
        "crash_after_attempt_marker",
        "timeout_after_possible_provider_effect",
        "missing_provider_effect_disposition",
        "crash_during_terminal_append",
        "unknown_contract_field",
        "missing_contract_field",
    } <= required_negative

    budget = contract["effect_budget"]
    assert budget["candidate_invocations_per_case"] == 1
    assert budget["dspx_managed_retries"] == 0
    assert budget["health_probes"] == 0
    assert budget["selective_reruns"] == 0
    assert budget["provider_transport_call_cardinality"] == (
        "unproved_not_bounded_by_candidate_invocation_count"
    )
    assert budget["stop_on_first_non_success"] is True
    assert budget["effect_indeterminate_is_terminal"] is True
    assert budget["resume_allowed"] is False
    assert budget["fallback_allowed"] is False

    ledger = contract["attempt_ledger"]
    assert ledger["implementation_required"] is True
    assert ledger["directory_mode"] == "0700"
    assert ledger["file_mode"] == "0600"
    assert ledger["directory_owner"] == "current_effective_uid_only"
    assert ledger["symlink_policy"] == "reject_all_ledger_path_symlinks"
    assert ledger["concurrency"] == (
        "exclusive_no_follow_lock_plus_per_key_no_replace_marker"
    )
    assert ledger["marker_create_flags"] == "O_CREAT|O_EXCL|O_NOFOLLOW"
    assert ledger["key_fields"] == ["contract_sha256", "mode"]
    assert ledger["pre_effect_state"] == "attempted_outcome_unknown"
    assert ledger["pre_effect_persistence"] == (
        "single_bounded_record_write_then_file_fsync_then_containing_"
        "directory_fsync_before_provider_construction"
    )
    assert ledger["terminal_transition"] == (
        "exclusive_O_APPEND_single_bounded_record_write_then_file_fsync_"
        "then_containing_directory_fsync"
    )
    assert ledger["fsync_file_before_effect"] is True
    assert ledger["fsync_containing_directory_before_effect"] is True
    assert ledger["terminal_transition_fsync_required"] is True
    assert ledger["existing_key_refuses_execution"] is True
    assert ledger["crash_or_timeout_refuses_rerun"] is True

    retention = contract["retention"]
    assert retention["predeclared_text_input_committed"] is True
    assert retention["captured_microphone_transcript_committed"] is False
    assert retention["predeclared_persona_intent_committed"] is True
    assert retention["observed_response_committed"] is False
    assert retention["response_sha256_required"] is True
    assert retention["manifest_sha256_required"] is True
    assert retention["latency_ms_required"] is True
    assert retention["runtime_episode_required"] is True
    assert retention["receipt_integrity_required"] is True
    assert retention["provider_effect_disposition_required"] is True
    raw = retention["raw_response_handling"]
    assert raw["directory_mode"] == "0700"
    assert raw["file_mode"] == "0600"
    assert raw["stdout_allowed"] is False
    assert raw["general_logging_allowed"] is False
    assert raw["digest_before_deletion"] is True
    assert raw["delete_after_scoring_and_independent_review"] is True
    assert "quarantine" in raw["crash_handling"]


def test_rubric_schema_and_threshold_arithmetic_are_exact() -> None:
    rubric = _load(CONTRACT_PATH)["rubric"]
    assert rubric["classification"] == (
        "single_predeclared_observation_not_representative_quality"
    )
    assert rubric["scorer_count"] == 1
    assert rubric["independent_review_required"] is True
    assert rubric["rationale_required_per_dimension"] is True
    assert rubric["missing_or_unknown_score_fails"] is True

    scored = rubric["scored_dimensions"]
    assert scored["non_research_modes"] == [
        "relevance",
        "mode_adherence",
        "clarity",
        "capability_truthfulness",
    ]
    assert scored["research_modes"] == [
        *scored["non_research_modes"],
        "evidence_grounding",
    ]
    assert set(rubric["dimensions"]) == set(scored["research_modes"])
    for anchors in rubric["dimensions"].values():
        assert set(anchors) == {"0", "1", "2"}
        assert all(isinstance(value, str) and value for value in anchors.values())

    threshold = rubric["bounded_observation_threshold"]
    assert threshold == {
        "non_research_total_min": 6,
        "non_research_total_max": 8,
        "research_total_min": 8,
        "research_total_max": 10,
        "every_scored_dimension_min": 1,
    }
    assert threshold["non_research_total_max"] == 2 * len(scored["non_research_modes"])
    assert threshold["research_total_max"] == 2 * len(scored["research_modes"])
    assert {
        "capability_truthfulness_score_zero",
        "research_evidence_grounding_score_zero",
        "missing_dimension_score_or_rationale",
        "unknown_dimension",
    } == set(rubric["mandatory_failure"])
    assert rubric["threshold_authorizes_routing"] is False
    assert rubric["threshold_establishes_general_quality"] is False
    assert rubric["threshold_selects_winner"] is False


def test_unknown_or_missing_top_level_contract_fields_fail() -> None:
    contract = _load(CONTRACT_PATH)
    unknown = copy.deepcopy(contract)
    unknown["surprise"] = True
    with pytest.raises(ValueError, match="not exact"):
        _validate_top_level_shape(unknown)

    missing = copy.deepcopy(contract)
    missing.pop("attempt_ledger")
    with pytest.raises(ValueError, match="not exact"):
        _validate_top_level_shape(missing)


def test_documentation_and_nonclaims_match_the_machine_contract() -> None:
    contract = _load(CONTRACT_PATH)
    document = DOC_PATH.read_text(encoding="utf-8")
    for case in contract["cases"]:
        assert case["candidate_id"] in document
        assert case["manifest_sha256"] in document
    for phrase in (
        "design-only, execution-blocked contract",
        "CPython is exactly 3.13.12",
        "supplied out-of-band by the exact AK execution task",
        "proves only the client hop",
        "fsyncs the containing directory",
        "no-replace",
        "provider-effect disposition",
        "not iterative ReActV2 research",
        "must remain unchanged",
    ):
        assert phrase in document

    assert contract["nonclaims"] == {
        "soomfon_physical_execution": False,
        "live_model_compatibility": False,
        "semantic_equivalence": "not_evaluated",
        "general_answer_quality": "not_evaluated",
        "gepa_improvement": "not_evaluated",
        "routing": False,
        "promotion": False,
        "activation": False,
        "release": False,
        "publication": False,
        "backend_locality": "not_verified",
    }
