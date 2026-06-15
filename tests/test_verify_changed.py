from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "verify_changed.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_changed", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _plan(*paths: str) -> dict[str, Any]:
    module = _load_module()
    impact_map = module.load_impact_map()
    return module.build_plan(
        list(paths),
        impact_map,
        base_mode="explicit_files",
        base_ref=None,
    )


def _command_ids(plan: dict[str, Any]) -> list[str]:
    return [str(command["id"]) for command in plan["commands"]]


def test_docs_only_change_selects_docs_strict_without_full_verification() -> None:
    plan = _plan("docs/project/developer_workflow.md")

    assert plan["schema_version"] == "dspx-verification-impact-plan-v1"
    assert plan["risk"] == "docs_only"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == ["docs_strict"]


def test_segment_glob_double_star_matches_zero_or_more_segments() -> None:
    loaded = _load_module()

    assert loaded._matches("docs/**/*.md", "docs/foo.md") is True
    assert loaded._matches("docs/**/*.md", "docs/project/foo.md") is True
    assert loaded._matches("docs/**/*.md", "docs/project/nested/foo.md") is True
    assert loaded._matches("packages/**/*.py", "packages/foo.py") is True
    assert loaded._matches("packages/**/*.py", "packages/dspx/foo.py") is True
    assert loaded._matches("packages/*.py", "packages/dspx/foo.py") is False


def test_docs_globs_match_direct_and_deep_markdown() -> None:
    plan = _plan("docs/ARCHITECTURE.md", "docs/project/nested/deep.md")

    assert plan["risk"] == "docs_only"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == ["docs_strict"]
    reasons = [classification["reasons"] for classification in plan["classifications"]]
    assert reasons == [
        ["matched docs/*.md", "matched docs/**/*.md"],
        ["matched docs/**/*.md"],
    ]


def test_redaction_boundary_selects_provider_runtime_checks() -> None:
    plan = _plan("packages/dspx-core/src/dspx/redaction.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_provider_runtime",
    ]
    classification = plan["classifications"][0]
    assert classification["category"] == "provider_boundary"
    assert classification["reasons"] == [
        "matched packages/dspx-core/src/dspx/redaction.py"
    ]


def test_program_generation_spine_selects_expanded_adjacent_checks() -> None:
    plan = _plan("packages/dspx-core/src/dspx/services/program_service.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_program_generation_spine",
        "boundary_contract_check",
        "docs_strict",
    ]


def test_program_intent_selects_program_generation_spine_checks() -> None:
    plan = _plan("packages/dspx-core/src/dspx/services/program_intent.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_program_generation_spine",
        "boundary_contract_check",
    ]


@pytest.mark.parametrize(
    "path",
    [
        "packages/dspx-core/src/dspx/services/program_capabilities.py",
        "packages/dspx-core/src/dspx/services/program_retrievers.py",
        "packages/dspx-core/src/dspx/services/program_runtime_outcomes.py",
        "packages/dspx-core/src/dspx/services/program_tool_contracts.py",
        "packages/dspx-core/src/dspx/services/program_topology.py",
    ],
)
def test_program_generation_support_modules_select_spine_checks(path: str) -> None:
    plan = _plan(path)

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_program_generation_spine",
        "boundary_contract_check",
    ]


def test_program_runtime_traces_selects_spine_and_direct_trace_checks() -> None:
    plan = _plan("packages/dspx-core/src/dspx/services/program_runtime_traces.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_program_generation_spine",
        "pytest_program_runtime_traces",
        "boundary_contract_check",
    ]


def test_program_runtime_trace_coverage_selects_trace_checks() -> None:
    plan = _plan(
        "packages/dspx-core/src/dspx/services/program_runtime_trace_coverage.py"
    )

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_program_generation_spine",
        "pytest_program_runtime_traces",
        "boundary_contract_check",
    ]


def test_program_generated_policy_selects_targeted_policy_checks() -> None:
    plan = _plan("packages/dspx-core/src/dspx/services/program_generated_policy.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_program_generated_policy",
        "boundary_contract_check",
    ]


def test_wide_threshold_forces_full_verification_for_mapped_program_slice() -> None:
    plan = _plan(
        "README.md",
        "docs/project/program-synthesis-boundary.md",
        "governance/task-scopes/AK-3415.snapshot.json",
        "packages/dspx-core/src/dspx/services/program_capabilities.py",
        "packages/dspx-core/src/dspx/services/program_generated_policy.py",
        "packages/dspx-core/src/dspx/services/program_intent.py",
        "packages/dspx-core/src/dspx/services/program_retrievers.py",
        "packages/dspx-core/src/dspx/services/program_service.py",
        "tests/test_program_capabilities.py",
        "tests/test_program_topology_intent_validation.py",
    )

    assert plan["risk"] == "wide"
    assert plan["full_verification_required"] is True
    assert "impact group count" in str(plan.get("wide_reason"))
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert "verify_full" in _command_ids(plan)


def test_openapi_tooling_command_includes_enum_array_regressions() -> None:
    loaded = _load_module()
    command = loaded.COMMAND_REGISTRY["pytest_openapi_tooling"].command

    assert "tests/test_openapi_validation_enums_arrays.py" in command


def test_openapi_tooling_uses_targeted_boundary_contracts() -> None:
    plan = _plan("packages/dspx-core/src/dspx/tools/openapi/caller.py")

    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_openapi_tooling",
        "pytest_openapi_boundary_contracts",
    ]
    assert "boundary_contract_check" not in _command_ids(plan)


def test_generated_code_guard_change_uses_adversarial_boundary_matrix() -> None:
    plan = _plan("packages/dspx-core/src/dspx/generated_code_guard.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_boundary_adversarial",
        "pytest_generated_code_guard_adversarial",
        "boundary_contract_check",
    ]


def test_mermaid_workflow_service_uses_targeted_boundary_contracts() -> None:
    plan = _plan("packages/dspx-core/src/dspx/services/mermaid_workflow_service.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_mermaid_workflow",
        "boundary_contract_check",
    ]


def test_generated_direct_runner_change_avoids_program_generation_spine() -> None:
    plan = _plan("packages/dspx-core/src/dspx/services/program_surfaces.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_generated_direct_runner",
        "pytest_program_direct_runner_generation",
    ]
    assert "pytest_program_generation_spine" not in _command_ids(plan)


def test_program_generation_spine_uses_split_program_service_tests() -> None:
    loaded = _load_module()

    direct_runner_command = loaded.COMMAND_REGISTRY[
        "pytest_program_direct_runner_generation"
    ].command
    spine_command = loaded.COMMAND_REGISTRY["pytest_program_generation_spine"].command

    assert (
        "tests/test_program_service_cli_examples.py::test_program_gen_cli_materializes_from_yaml"
        in direct_runner_command
    )
    assert "tests/test_program_service.py" not in direct_runner_command
    assert "tests/test_program_service_core.py" in spine_command
    assert "tests/test_program_service_cli_examples.py" in spine_command
    assert "tests/test_program_service_replay_integrity.py" in spine_command
    assert "tests/test_program_service_jury_authority.py" in spine_command
    assert "tests/test_program_service.py" not in spine_command
    assert "tests/test_program_topology_intent_validation.py" in spine_command
    assert "tests/test_program_topology_intent_pipeline.py" in spine_command
    assert "tests/test_program_topology_intent_react_v2.py" in spine_command
    assert "tests/test_program_topology_intent_prompt_inference.py" in spine_command
    assert "tests/test_program_topology_intent.py" not in spine_command


def test_cli_boundary_change_selects_split_boundary_hardening_tests() -> None:
    plan = _plan("packages/dspx-core/src/dspx/cli/dspx.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_all",
        "pytest_boundary_adversarial",
        "pytest_cli_dspx",
        "pytest_forge_cli_policy",
        "pytest_program_runtime_episode",
        "boundary_contract_check",
    ]
    classification = plan["classifications"][0]
    assert classification["reasons"] == [
        "matched packages/dspx-core/src/dspx/cli/*.py",
        "matched packages/dspx-core/src/dspx/cli/**/*.py",
    ]


def test_nested_cli_boundary_change_uses_nested_rule_only() -> None:
    plan = _plan("packages/dspx-core/src/dspx/cli/commands/openapi.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_all",
        "pytest_boundary_adversarial",
        "pytest_cli_dspx",
        "pytest_forge_cli_policy",
        "pytest_program_runtime_episode",
        "boundary_contract_check",
    ]
    classification = plan["classifications"][0]
    assert classification["reasons"] == [
        "matched packages/dspx-core/src/dspx/cli/**/*.py"
    ]


def test_program_promote_cli_change_uses_activation_packet_override() -> None:
    plan = _plan("packages/dspx-core/src/dspx/cli/commands/program_promote.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_program_activation_packet",
    ]
    classification = plan["classifications"][0]
    assert classification["category"] == "activation_packet_cli"
    assert classification["reasons"] == [
        "matched packages/dspx-core/src/dspx/cli/commands/program_promote.py"
    ]


def test_activation_packet_service_change_is_mapped_without_full_verification() -> None:
    plan = _plan("packages/dspx-core/src/dspx/services/program_activation_packet.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert "verify_full" not in _command_ids(plan)
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_program_activation_packet",
    ]


def test_program_refine_cli_change_routes_to_refinement_candidates() -> None:
    plan = _plan("packages/dspx-core/src/dspx/cli/commands/program_refine.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert "verify_full" not in _command_ids(plan)
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_program_oracle_refinement",
        "pytest_refinement_candidate_comparison",
        "pytest_program_sidecar_boundaries",
    ]
    classification = plan["classifications"][0]
    assert classification["category"] == "program_refinement_cli"


def test_refinement_comparison_and_test_change_deduplicate_commands() -> None:
    plan = _plan(
        "packages/dspx-core/src/dspx/services/program_refinement_comparison.py",
        "tests/test_program_refinement_comparison.py",
    )

    assert plan["risk"] == "bounded"
    command_ids = _command_ids(plan)
    assert command_ids.count("ruff_touched") == 1
    assert command_ids.count("pytest_refinement_candidate_comparison") == 1
    assert "pytest_touched" in command_ids


def test_scripts_ci_recursive_rule_matches_nested_paths() -> None:
    plan = _plan("scripts/ci/nested/helper.py")

    assert plan["risk"] == "bounded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    classification = plan["classifications"][0]
    assert classification["category"] == "ci"
    assert classification["reasons"] == ["matched scripts/ci/**"]


def test_ci_planner_change_runs_planner_checks_without_full_verification() -> None:
    plan = _plan("scripts/ci/verify_changed.py")

    assert plan["risk"] == "bounded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == [
        "workflow_contract_check",
        "ruff_touched",
        "impact_plan_smoke",
        "pytest_verify_changed",
    ]


def test_dynamic_touched_commands_skip_deleted_paths() -> None:
    loaded = _load_module()
    deleted_path = "tests/test_verify_changed_missing_deleted_path.py"
    assert not (ROOT / deleted_path).exists()

    assert loaded._command_from_id("ruff_touched", [deleted_path], "") is None
    assert loaded._command_from_id("pytest_touched", [deleted_path], "") is None


def test_pytest_touched_uses_xdist_loadfile_for_existing_test_paths() -> None:
    loaded = _load_module()

    command = loaded._command_from_id(
        "pytest_touched", ["tests/test_verify_changed.py"], ""
    )

    assert command is not None
    assert command["command"] == [
        "uv",
        "run",
        "--no-sync",
        "-m",
        "pytest",
        "-q",
        "tests/test_verify_changed.py",
        "-n",
        "auto",
        "--dist=loadfile",
    ]


@pytest.mark.parametrize(
    ("path", "category", "expected_command"),
    [
        (
            "packages/dspx-core/src/dspx/coordinates/storage.py",
            "oracle_coordinate_store",
            "pytest_coordinates",
        ),
        (
            "packages/dspx-core/src/dspx/coordinates/postgres_store.py",
            "oracle_coordinate_store",
            "pytest_coordinates",
        ),
        (
            "packages/dspx-core/src/dspx/cache.py",
            "cache_boundary",
            "pytest_cache_boundary",
        ),
        (
            "packages/dspx-core/src/dspx/multi_provider_lm.py",
            "provider_boundary",
            "pytest_provider_runtime",
        ),
        (
            "packages/dspx-core/src/dspx/openrouter_lm.py",
            "provider_boundary",
            "pytest_provider_runtime",
        ),
        (
            "packages/dspx-core/src/dspx/providers_register_openrouter.py",
            "provider_boundary",
            "pytest_provider_runtime",
        ),
        (
            "packages/dspx-core/src/dspx/openai_compatible_lm.py",
            "provider_boundary",
            "pytest_provider_runtime",
        ),
        (
            "packages/dspx-core/src/dspx/dspy_lm_auth_lm.py",
            "provider_boundary",
            "pytest_provider_v4",
        ),
        (
            "packages/dspx-core/src/dspx/oracle_time_travel.py",
            "oracle_time_travel",
            "pytest_oracle_time_travel",
        ),
        (
            "packages/dspx-core/src/dspx/server/security.py",
            "server_security_boundary",
            "pytest_server_security",
        ),
        (
            "packages/dspx-core/src/dspx/adapters/eval.py",
            "adapter_evaluation_boundary",
            "pytest_adapters_eval",
        ),
        (
            "packages/dspx-core/src/dspx/tools/registry.py",
            "tool_registry_boundary",
            "pytest_tools_registry",
        ),
        (
            "packages/dspx-core/src/dspx/services/program_promotion.py",
            "python_service",
            "pytest_promotion_plan_adjacent",
        ),
        (
            "packages/dspx-core/src/dspx/services/program_refinement_episode.py",
            "python_service",
            "pytest_refinement_candidate_comparison",
        ),
        (
            "packages/dspx-core/src/dspx/tools/openapi/loader.py",
            "openapi_tooling",
            "pytest_openapi_tooling",
        ),
    ],
)
def test_boundary_debt_paths_are_mapped(
    path: str, category: str, expected_command: str
) -> None:
    plan = _plan(path)

    assert "unmapped path" not in str(plan.get("wide_reason"))
    classification = plan["classifications"][0]
    assert classification["category"] == category
    assert expected_command in _command_ids(plan)


def test_coordinate_storage_does_not_run_aggregate_runtime_gate() -> None:
    plan = _plan("packages/dspx-core/src/dspx/coordinates/storage.py")

    assert "pytest_coordinates" in _command_ids(plan)
    assert "verify_runtime" not in _command_ids(plan)
    assert "verify_runtime_module_synthesis" not in _command_ids(plan)


def test_coordinates_command_uses_split_phase_b_suite() -> None:
    loaded = _load_module()

    command = loaded.COMMAND_REGISTRY["pytest_coordinates"].command

    assert "tests/test_coordinates.py" in command
    assert "tests/test_coordinates_phase_b_territory_contracts.py" in command
    assert "tests/test_coordinates_phase_b_frontiers_attractors.py" in command
    assert "tests/test_coordinates_phase_b_regressions.py" in command
    assert "tests/test_coordinates_phase_b_real_embeddings.py" in command
    assert "tests/test_coordinates_phase_b.py" not in command
    assert command[-3:] == ["-n", "auto", "--dist=loadfile"]


def test_provider_v4_auth_adapter_change_stays_bounded() -> None:
    plan = _plan("packages/dspx-core/src/dspx/dspy_lm_auth_lm.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_provider_v4",
    ]
    assert "verify_full" not in _command_ids(plan)


def test_test_harness_change_runs_default_contract_without_full_verification() -> None:
    plan = _plan("tests/conftest.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == ["ruff_touched", "pytest_test_defaults"]
    assert "verify_full" not in _command_ids(plan)


def test_program_architecture_shared_helper_runs_split_architecture_suite() -> None:
    plan = _plan("tests/program_architecture_shared.py")

    assert plan["risk"] == "bounded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == ["ruff_touched", "pytest_program_architecture"]
    assert plan["commands"][1]["command"][-3:] == [
        "-n",
        "auto",
        "--dist=loadfile",
    ]
    assert "verify_full" not in _command_ids(plan)


def test_program_activation_packet_shared_helper_runs_split_packet_suite() -> None:
    plan = _plan("tests/program_activation_packet_shared.py")

    assert plan["risk"] == "bounded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == ["ruff_touched", "pytest_program_activation_packet"]
    command = plan["commands"][1]["command"]
    assert "tests/test_program_activation_packet_core_review.py" in command
    assert command[-3:] == ["-n", "auto", "--dist=loadfile"]
    assert "verify_full" not in _command_ids(plan)


def test_module_synthesis_evidence_helper_runs_split_evidence_suite() -> None:
    plan = _plan("tests/module_synthesis_evidence_helpers.py")

    assert plan["risk"] == "bounded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == ["ruff_touched", "pytest_module_synthesis_evidence"]
    command = plan["commands"][1]["command"]
    assert "tests/test_module_synthesis_evidence_retrieval.py" in command
    assert command[-3:] == ["-n", "auto", "--dist=loadfile"]
    assert "verify_full" not in _command_ids(plan)


def test_run_receipts_helper_runs_split_receipt_suite() -> None:
    plan = _plan("tests/run_receipts_helpers.py")

    assert plan["risk"] == "bounded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == ["ruff_touched", "pytest_run_receipts"]
    command = plan["commands"][1]["command"]
    assert "tests/test_run_receipts_replay.py" in command
    assert command[-3:] == ["-n", "auto", "--dist=loadfile"]
    assert "verify_full" not in _command_ids(plan)


def test_program_topology_helper_runs_program_generation_spine() -> None:
    plan = _plan("tests/program_topology_intent_helpers.py")

    assert plan["risk"] == "bounded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == ["ruff_touched", "pytest_program_generation_spine"]
    command = plan["commands"][1]["command"]
    assert "tests/test_program_topology_intent_validation.py" in command
    assert "tests/test_program_topology_intent.py" not in command
    assert "verify_full" not in _command_ids(plan)


def test_program_meta_adjudication_helper_runs_split_meta_suite() -> None:
    plan = _plan("tests/program_meta_adjudication_helpers.py")

    assert plan["risk"] == "bounded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == ["ruff_touched", "pytest_program_meta_adjudication"]
    command = plan["commands"][1]["command"]
    assert "tests/test_program_meta_adjudication_target_jury.py" in command
    assert "tests/test_program_meta_adjudication.py" not in command
    assert command[-3:] == ["-n", "auto", "--dist=loadfile"]
    assert "verify_full" not in _command_ids(plan)


def test_task_scope_helper_runs_split_task_scope_suite() -> None:
    plan = _plan("tests/task_scope_helpers.py")

    assert plan["risk"] == "bounded"
    assert plan["full_verification_required"] is False
    assert "unmapped path" not in str(plan.get("wide_reason"))
    assert _command_ids(plan) == ["ruff_touched", "pytest_task_scope"]
    command = plan["commands"][1]["command"]
    assert "tests/test_task_scope_manifest_and_binding.py" in command
    assert "tests/test_task_scope_head_mode.py" in command
    assert "tests/test_task_scope_working_tree.py" in command
    assert "tests/test_task_scope_cli_contract.py" in command
    assert "tests/test_task_scope.py" not in command
    assert command[-3:] == ["-n", "auto", "--dist=loadfile"]
    assert "verify_full" not in _command_ids(plan)


def test_task_scope_source_change_runs_split_task_scope_suite() -> None:
    plan = _plan("packages/dspx-core/src/dspx/task_scope.py")

    assert plan["risk"] == "wide"
    assert plan["full_verification_required"] is True
    assert "pytest_task_scope" in _command_ids(plan)
    command = next(
        command["command"]
        for command in plan["commands"]
        if command["id"] == "pytest_task_scope"
    )
    assert "tests/test_task_scope_manifest_and_binding.py" in command
    assert "tests/test_task_scope.py" not in command


def test_task_scope_checker_script_change_runs_split_task_scope_suite() -> None:
    plan = _plan("scripts/check_task_scope.py")

    assert plan["risk"] == "wide"
    assert plan["full_verification_required"] is True
    assert "pytest_task_scope" in _command_ids(plan)
    command = next(
        command["command"]
        for command in plan["commands"]
        if command["id"] == "pytest_task_scope"
    )
    assert "tests/test_task_scope_cli_contract.py" in command
    assert "tests/test_task_scope.py" not in command


@pytest.mark.parametrize("path", ["pyproject.toml", "uv.lock"])
def test_dependency_metadata_change_runs_fast_defaults_and_full_gate(
    path: str,
) -> None:
    plan = _plan(path)

    assert plan["risk"] == "wide"
    assert plan["full_verification_required"] is True
    assert _command_ids(plan) == ["pytest_test_defaults", "verify_fast", "verify_full"]


def test_replay_service_selects_replay_runtime_and_program_trace_checks() -> None:
    plan = _plan("packages/dspx-core/src/dspx/services/run_replay_service.py")

    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_program_runtime_traces",
        "verify_runtime_replay",
    ]
    assert "verify_runtime" not in _command_ids(plan)
    assert "verify_runtime_module_synthesis" not in _command_ids(plan)
    assert "verify_runtime_boundary" not in _command_ids(plan)


def test_module_synthesis_quality_log_selects_module_synthesis_runtime_only() -> None:
    plan = _plan("scripts/build_module_synthesis_quality_log.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == ["ruff_touched", "verify_runtime_module_synthesis"]
    assert "verify_runtime" not in _command_ids(plan)


def test_runtime_aggregate_command_exists_for_explicit_full_confidence_only() -> None:
    loaded = _load_module()

    assert loaded.COMMAND_REGISTRY["verify_runtime"].command == [
        "just",
        "verify-runtime",
    ]


def test_unknown_file_fails_wide() -> None:
    plan = _plan("misc/unmapped.file")

    assert plan["risk"] == "wide"
    assert plan["full_verification_required"] is True
    assert "unmapped path: misc/unmapped.file" in str(plan["wide_reason"])
    classification = plan["classifications"][0]
    assert classification["category"] == "unknown"
    assert _command_ids(plan) == ["verify_full"]


def test_cross_group_threshold_requires_verify_full() -> None:
    module = _load_module()
    plan = _plan(
        "docs/project/developer_workflow.md",
        "policy/engineering-lane.json",
        "packages/dspx-core/src/dspx/services/program_surfaces.py",
        "tests/test_verify_changed.py",
    )

    assert plan["risk"] == "wide"
    assert plan["full_verification_required"] is True
    assert "impact group count 4 exceeds threshold 3" in str(plan["wide_reason"])
    assert "verify_full" in _command_ids(plan)

    exit_code, result = module.execute_plan(plan, allow_wide=False)

    assert exit_code == 2
    assert result["status"] == "blocked_wide"
    assert result["commands"] == []


def test_engineering_policy_change_selects_workflow_contract_check() -> None:
    plan = _plan("policy/engineering-lane.json")

    assert plan["risk"] == "bounded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == ["workflow_contract_check"]


def test_direction_contract_change_selects_direction_and_fast_checks() -> None:
    plan = _plan("scripts/check_direction_to_execution.py")

    assert plan["risk"] == "wide"
    assert plan["full_verification_required"] is True
    assert _command_ids(plan) == [
        "direction_contract_check",
        "ruff_touched",
        "verify_fast",
        "verify_full",
    ]


def test_full_required_plan_without_commands_fails_even_when_wide_allowed() -> None:
    module = _load_module()
    plan = {
        "full_verification_required": True,
        "commands": [],
        "risk": "wide",
    }

    exit_code, result = module.execute_plan(plan, allow_wide=True)

    assert exit_code == 2
    assert result["status"] == "failed"
    assert result["note"] == "full-required impact plan selected no commands"


def test_justfile_change_runs_workflow_gates_and_full_verification() -> None:
    plan = _plan("Justfile")

    assert plan["risk"] == "wide"
    assert plan["full_verification_required"] is True
    assert _command_ids(plan) == [
        "workflow_contract_check",
        "verify_fast",
        "verify_full",
    ]


def test_pre_commit_config_change_runs_workflow_gates_and_full_verification() -> None:
    plan = _plan(".pre-commit-config.yaml")

    assert plan["risk"] == "wide"
    assert plan["full_verification_required"] is True
    assert _command_ids(plan) == [
        "workflow_contract_check",
        "verify_fast",
        "verify_full",
    ]


def test_workflow_contract_checker_change_runs_fast_contract_gates_and_full_verification() -> (
    None
):
    plan = _plan("scripts/check_workflow_contracts.py")

    assert plan["risk"] == "wide"
    assert plan["full_verification_required"] is True
    assert _command_ids(plan) == [
        "workflow_contract_check",
        "ruff_touched",
        "verify_fast",
        "verify_full",
    ]


def test_changed_files_accepts_just_style_base_assignment(monkeypatch) -> None:
    module = _load_module()

    calls: list[list[str]] = []

    def fake_run_git(args: list[str]) -> list[str]:
        calls.append(args)
        return ["docs/project/developer_workflow.md"]

    monkeypatch.setattr(module, "_run_git", fake_run_git)

    mode, base_ref, paths = module.changed_files(
        base="base=HEAD~1",
        staged=False,
        explicit_files=[],
    )

    assert mode == "diff"
    assert base_ref == "HEAD~1"
    assert paths == ["docs/project/developer_workflow.md"]
    assert calls == [["diff", "--name-only", "HEAD~1"]]


def test_working_tree_status_parser_preserves_first_path_character(monkeypatch) -> None:
    module = _load_module()

    monkeypatch.setattr(
        module,
        "_run_git",
        lambda args: [" M Justfile", "?? docs/project/developer_workflow.md"],
    )

    assert module._working_tree_paths() == [
        "Justfile",
        "docs/project/developer_workflow.md",
    ]


def test_run_plan_writes_result_receipt(tmp_path, monkeypatch) -> None:
    module = _load_module()
    plan = _plan("docs/project/developer_workflow.md")
    result_out = tmp_path / "impact-result.json"
    calls: list[list[str]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    exit_code = module.run_plan(plan, allow_wide=False, result_out=result_out)

    assert exit_code == 0
    assert calls == [
        [
            "node",
            str(Path.home() / "ai-society/core/agent-scripts/scripts/docs-list.mjs"),
            "--docs",
            ".",
            "--strict",
        ]
    ]
    payload = json.loads(result_out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "dspx-verification-impact-result-v1"
    assert payload["status"] == "passed"
    assert payload["exit_code"] == 0
    assert payload["summary"] == {
        "blocked_wide": False,
        "command_count": 1,
        "failed_count": 0,
        "full_verification_required": False,
        "passed_count": 1,
        "risk": "docs_only",
    }
    assert payload["commands"][0]["id"] == "docs_strict"
    assert payload["commands"][0]["returncode"] == 0
    assert payload["non_authority"]["full_verification_replacement"] is False


def test_main_run_writes_result_receipt_from_cli_args(tmp_path, monkeypatch) -> None:
    module = _load_module()
    result_out = tmp_path / "cli-impact-result.json"
    calls: list[list[str]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    exit_code = module.main(
        [
            "--files",
            "tests/test_verify_changed.py",
            "--run",
            "--result-out",
            str(result_out),
            "--json",
        ]
    )

    assert exit_code == 0
    assert calls == [
        ["uv", "run", "--no-sync", "ruff", "check", "tests/test_verify_changed.py"],
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_verify_changed.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
    ]
    payload = json.loads(result_out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "dspx-verification-impact-result-v1"
    assert payload["status"] == "passed"
    assert payload["summary"]["command_count"] == 2
    assert payload["plan"]["changed_files"] == ["tests/test_verify_changed.py"]


def test_run_plan_writes_blocked_wide_receipt(tmp_path) -> None:
    module = _load_module()
    plan = _plan("Justfile")
    result_out = tmp_path / "impact-wide-result.json"

    exit_code = module.run_plan(plan, allow_wide=False, result_out=result_out)

    assert exit_code == 2
    payload = json.loads(result_out.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked_wide"
    assert payload["summary"]["blocked_wide"] is True
    assert payload["commands"] == []
    assert payload["plan"]["full_verification_required"] is True


def test_plan_json_is_serializable() -> None:
    plan = _plan("docs/project/developer_workflow.md")

    encoded = json.dumps(plan, sort_keys=True)

    assert "dspx-verification-impact-plan-v1" in encoded
