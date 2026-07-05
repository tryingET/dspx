#!/usr/bin/env python3
"""Deterministic impact-aware verification planner for DSPx.

This script is intentionally table-driven. It selects existing verification
commands from changed paths; it does not infer semantic coverage or replace the
full verification gate.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP = ROOT / "scripts" / "ci" / "verification-impact.yml"

RISK_ORDER = {"docs_only": 0, "bounded": 1, "expanded": 2, "wide": 3}
LINTABLE_SUFFIXES = {".py", ".md"}


@dataclass(frozen=True)
class CommandSpec:
    command: list[str]
    reason: str


COMMAND_REGISTRY: dict[str, CommandSpec] = {
    "docs_strict": CommandSpec(
        [
            "node",
            str(Path.home() / "ai-society/core/agent-scripts/scripts/docs-list.mjs"),
            "--docs",
            ".",
            "--strict",
        ],
        "documentation contract changed",
    ),
    "governance_check": CommandSpec(
        ["just", "governance-check"],
        "governance projection changed",
    ),
    "task_scope_check": CommandSpec(
        ["just", "task-scope-check"],
        "task-scope projection or scoped work changed",
    ),
    "pytest_task_scope": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_task_scope_manifest_and_binding.py",
            "tests/test_task_scope_head_mode.py",
            "tests/test_task_scope_working_tree.py",
            "tests/test_task_scope_cli_contract.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "task-scope checker test harness changed",
    ),
    "workflow_contract_check": CommandSpec(
        ["just", "workflow-contract-check"],
        "workflow command contract changed",
    ),
    "direction_contract_check": CommandSpec(
        ["just", "direction-contract-check"],
        "direction-to-execution contract changed",
    ),
    "verify_fast": CommandSpec(
        ["just", "verify-fast"],
        "workflow, governance, or CI contract changed",
    ),
    "verify_runtime_replay": CommandSpec(
        ["just", "verify-runtime-replay"],
        "replay-sensitive runtime surface changed",
    ),
    "verify_runtime_monorepo": CommandSpec(
        ["just", "verify-runtime-monorepo"],
        "monorepo boundary surface changed",
    ),
    "verify_runtime_module_synthesis": CommandSpec(
        ["just", "verify-runtime-module-synthesis"],
        "module-synthesis quality surface changed",
    ),
    "verify_runtime_boundary": CommandSpec(
        ["just", "verify-runtime-boundary"],
        "runtime boundary contract surface changed",
    ),
    "verify_runtime": CommandSpec(
        ["just", "verify-runtime"],
        "aggregate runtime bundle changed or explicitly required",
    ),
    "verify_full": CommandSpec(
        ["just", "verify-full"],
        "wide-risk change requires full verification",
    ),
    "impact_plan_smoke": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "python",
            "scripts/ci/verify_changed.py",
            "--files",
            "scripts/ci/verify_changed.py",
            "tests/test_verify_changed.py",
            "--plan-only",
            "--json",
        ],
        "verification impact planner changed",
    ),
    "typecheck_core": CommandSpec(
        ["uvx", "ty", "check", "packages/dspx-core/src"],
        "core Python service changed",
    ),
    "typecheck_all": CommandSpec(
        ["uvx", "ty", "check", "packages/dspx-core/src", "apps/forge/src"],
        "Python package code changed",
    ),
    "boundary_contract_check": CommandSpec(
        ["just", "boundary-contract-check"],
        "boundary-sensitive surface changed",
    ),
    "pytest_boundary_hardening": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_adversarial_boundary_contracts.py",
            "tests/test_cli_dspx.py",
            "tests/test_forge_cli_policy.py",
            "tests/test_program_runtime_episode.py",
        ],
        "CLI/provider/runtime boundary hardening changed",
    ),
    "pytest_boundary_adversarial": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_adversarial_boundary_contracts.py",
        ],
        "adversarial boundary contract changed",
    ),
    "pytest_generated_code_guard_adversarial": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_generated_code_guard_adversarial.py",
        ],
        "generated-code guard boundary changed",
    ),
    "pytest_cli_dspx": CommandSpec(
        ["uv", "run", "--no-sync", "-m", "pytest", "-q", "tests/test_cli_dspx.py"],
        "DSPx CLI boundary changed",
    ),
    "pytest_forge_cli_policy": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_forge_cli_policy.py",
        ],
        "Forge CLI policy boundary changed",
    ),
    "pytest_program_runtime_episode": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_runtime_episode.py",
        ],
        "program runtime episode boundary changed",
    ),
    "pytest_program_activation_packet": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_activation_packet_core_review.py",
            "tests/test_program_activation_packet_publication_preflight.py",
            "tests/test_program_activation_packet_publication_receipt.py",
            "tests/test_program_activation_packet_rollout_binding.py",
            "tests/test_program_activation_packet_authority_integrity.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "generated-program activation packet boundary changed",
    ),
    "pytest_program_adjudication_publication": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_adjudication_publication.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "program adjudication publication boundary changed",
    ),
    "pytest_program_oracle_publication": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_oracle_publication.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "program Oracle publication boundary changed",
    ),
    "pytest_program_architecture": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_architecture_planner.py",
            "tests/test_program_architecture_contracts.py",
            "tests/test_program_architecture_cli.py",
            "tests/test_program_architecture_program_gen_integration.py",
            "tests/test_program_architect_loop.py",
            "tests/test_program_architect_tournament.py",
            "tests/test_program_architect_recommend.py",
            "tests/test_program_architect_tournament_validation.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "program architecture test harness changed",
    ),
    "pytest_module_synthesis_evidence": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_module_synthesis_evidence_retrieval.py",
            "tests/test_module_synthesis_history_priors.py",
            "tests/test_module_synthesis_ranked_candidate_inputs.py",
            "tests/test_module_synthesis_prior_divergence.py",
            "tests/test_module_synthesis_prior_readiness_counterfactual.py",
            "tests/test_module_synthesis_governed_policy_promotion.py",
            "tests/test_module_synthesis_shadow_predictive_ranking.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "module synthesis evidence test harness changed",
    ),
    "pytest_run_receipts": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_run_receipts_replay.py",
            "tests/test_run_receipts_explain.py",
            "tests/test_run_receipts_identity_lineage.py",
            "tests/test_run_receipts_module_oracle.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "run receipt test harness changed",
    ),
    "pytest_program_meta_adjudication": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_meta_adjudication_target_jury.py",
            "tests/test_program_meta_adjudication_adjudicator.py",
            "tests/test_program_meta_adjudication_evidence.py",
            "tests/test_program_meta_adjudication_gepa_plan.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "program meta-adjudication test harness changed",
    ),
    "pytest_program_model_jury": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_model_jury_execution.py",
            "tests/test_program_promotion_refinement.py",
            "tests/test_program_candidate_state.py",
            "tests/test_program_activation_packet_core_review.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "program model-jury evidence seam changed",
    ),
    "pytest_verify_changed": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_verify_changed.py",
        ],
        "verification impact planner changed",
    ),
    "pytest_test_defaults": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_test_defaults.py",
            "-n",
            "2",
            "--dist=loadfile",
        ],
        "test harness defaults changed",
    ),
    "pytest_generated_direct_runner": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_adversarial_boundary_contracts.py",
            "-k",
            "generated_direct",
        ],
        "generated direct-runner surface changed",
    ),
    "pytest_program_direct_runner_generation": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_service_cli_examples.py::test_program_gen_cli_materializes_from_yaml",
        ],
        "generated direct-runner rendering changed",
    ),
    "pytest_program_generation_spine": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_service_core.py",
            "tests/test_program_service_cli_examples.py",
            "tests/test_program_service_replay_integrity.py",
            "tests/test_program_service_jury_authority.py",
            "tests/test_program_dataset_splits.py",
            "tests/test_program_topology_intent_validation.py",
            "tests/test_program_topology_intent_pipeline.py",
            "tests/test_program_topology_intent_react_v2.py",
            "tests/test_program_topology_intent_prompt_inference.py",
        ],
        "program generation spine changed",
    ),
    "pytest_mermaid_workflow": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_mermaid_clis.py",
            "tests/test_server_api.py",
        ],
        "Mermaid workflow generation or server boundary changed",
    ),
    "pytest_program_generated_policy": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_generated_policy.py",
        ],
        "generated module policy changed",
    ),
    "pytest_program_runtime_traces": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_runtime_traces.py",
        ],
        "program runtime trace evidence changed",
    ),
    "pytest_program_oracle_refinement": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_oracle_index.py",
            "tests/test_program_oracle_report.py",
            "tests/test_program_refinement.py",
        ],
        "Oracle/refinement evidence seam changed",
    ),
    "pytest_program_refinement_candidate": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_refinement_candidate.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "refinement second-candidate seam changed",
    ),
    "pytest_program_refinement_comparison": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_refinement_comparison.py",
            "tests/test_program_promotion_plan.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "refinement comparison/planning seam changed",
    ),
    "pytest_program_refinement_episode": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_refinement_episode.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "guided refinement episode seam changed",
    ),
    "pytest_program_refinement_gepa_candidate": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_refinement_gepa_candidate.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "GEPA candidate materialization/workflow seam changed",
    ),
    "pytest_program_promotion_review": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_promotion_refinement.py",
            "tests/test_program_promotion_decision.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "promotion review/refined-decision seam changed",
    ),
    "pytest_program_promotion_decision": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_promotion_decision.py",
            "tests/test_program_promotion_plan.py",
            "tests/test_authority_adapter_export_preflight.py",
            "tests/test_program_refinement_candidate.py",
            "-k",
            "program_promotion_decision or decision_effect_authority_drift or agent_kernel_export_preflight",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "promotion decision-record producer/consumer seam changed",
    ),
    "pytest_refinement_candidate_comparison": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_refinement_candidate.py",
            "tests/test_program_refinement_comparison.py",
            "tests/test_program_refinement_episode.py",
            "tests/test_program_refinement_gepa_candidate.py",
            "tests/test_program_promotion_plan.py",
        ],
        "aggregate refinement candidate/comparison seam changed",
    ),
    "pytest_optimize_gepa": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_optimize_gepa_metric_hooks.py",
            "tests/test_optimize_gepa_stub.py",
            "tests/test_program_refinement_gepa.py",
            "tests/test_program_refinement_gepa_candidate.py",
        ],
        "GEPA optimizer/refinement seam changed",
    ),
    "pytest_program_sidecar_boundaries": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_refinement.py",
            "tests/test_program_refinement_comparison.py",
            "tests/test_program_promotion_decision.py",
            "tests/test_program_oracle_publication_preflight.py",
            "tests/test_program_runtime_episode.py",
        ],
        "program sidecar/output boundary guard changed",
    ),
    "pytest_promotion_plan_adjacent": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_program_promotion_plan.py",
            "tests/test_program_promotion_decision.py",
            "tests/test_authority_adapter_export_preflight.py",
        ],
        "promotion planning or authority-adjacent surface changed",
    ),
    "pytest_coordinates": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_coordinates.py",
            "tests/test_coordinates_phase_b_territory_contracts.py",
            "tests/test_coordinates_phase_b_frontiers_attractors.py",
            "tests/test_coordinates_phase_b_regressions.py",
            "tests/test_coordinates_phase_b_real_embeddings.py",
            "-n",
            "auto",
            "--dist=loadfile",
        ],
        "Oracle coordinate storage or behavioral topology changed",
    ),
    "pytest_provider_runtime": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_multi_provider_parallel_semantics.py",
            "tests/test_openrouter_provider_unit.py",
            "tests/test_provider_runtime.py",
            "tests/test_provider_registry.py",
        ],
        "provider runtime boundary changed",
    ),
    "pytest_provider_v4": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_provider_v4.py",
        ],
        "provider v4 auth adapter boundary changed",
    ),
    "pytest_cache_boundary": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_cache.py",
            "tests/test_cache_cli.py",
            "tests/test_cache_controls_cli.py",
            "tests/test_boundary_contracts.py",
        ],
        "cache boundary changed",
    ),
    "pytest_server_security": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_server_auth.py",
            "tests/test_server_body_size.py",
            "tests/test_server_confirm_mutations.py",
            "tests/test_server_rate_limit.py",
            "tests/test_web_tools_allowlist.py",
            "tests/test_boundary_contracts.py",
        ],
        "server security boundary changed",
    ),
    "pytest_adapters_eval": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_adapters_eval.py",
            "tests/test_adapters_eval_cli.py",
            "tests/test_eval_exporters_cli.py",
        ],
        "adapter evaluation metrics changed",
    ),
    "pytest_tools_registry": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_tools_registry.py",
            "tests/test_tool_capability_wrapper.py",
            "tests/test_web_tools_allowlist.py",
        ],
        "tool registry boundary changed",
    ),
    "pytest_openapi_tooling": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_openapi_yaml_and_validation.py",
            "tests/test_openapi_toolpack.py",
            "tests/test_openapi_deep_schema.py",
            "tests/test_openapi_schema_refs_allof.py",
            "tests/test_openapi_validation_enums_arrays.py",
        ],
        "OpenAPI tooling changed",
    ),
    "pytest_openapi_boundary_contracts": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_boundary_contracts.py",
        ],
        "OpenAPI boundary contract changed",
    ),
    "pytest_authority_boundary_contracts": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_authority_adapter_export_preflight.py",
            "tests/test_program_candidate_state.py",
        ],
        "authority-adjacent boundary contract changed",
    ),
    "pytest_oracle_time_travel": CommandSpec(
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_oracle_time_travel_cli.py",
        ],
        "Oracle time-travel surface changed",
    ),
}


def _repo_rel(path: str | Path) -> str:
    text = str(path).strip()
    if not text:
        return text
    candidate = Path(text)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


def _run_git(args: list[str]) -> list[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.rstrip() for line in proc.stdout.splitlines() if line.strip()]


def _working_tree_paths() -> list[str]:
    paths: list[str] = []
    for line in _run_git(["status", "--porcelain"]):
        # Porcelain v1: XY PATH or XY OLD -> NEW. Keep the new path for renames.
        payload = line[3:] if len(line) > 3 else ""
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1]
        if payload:
            paths.append(_repo_rel(payload))
    return sorted(dict.fromkeys(paths))


def changed_files(
    *, base: str, staged: bool, explicit_files: list[str]
) -> tuple[str, str | None, list[str]]:
    if base.startswith("base="):
        base = base.split("=", 1)[1]
    if explicit_files:
        return (
            "explicit_files",
            None,
            sorted(dict.fromkeys(_repo_rel(item) for item in explicit_files)),
        )
    if staged:
        return (
            "staged",
            "--cached",
            sorted(dict.fromkeys(_run_git(["diff", "--name-only", "--cached"]))),
        )
    if base != "auto":
        return (
            "diff",
            base,
            sorted(dict.fromkeys(_run_git(["diff", "--name-only", base]))),
        )
    working = _working_tree_paths()
    if working:
        return "working_tree", "HEAD", working
    try:
        _run_git(["rev-parse", "--verify", "HEAD~1"])
    except subprocess.CalledProcessError:
        return "initial_commit", None, sorted(dict.fromkeys(_run_git(["ls-files"])))
    return (
        "head_commit",
        "HEAD~1..HEAD",
        sorted(dict.fromkeys(_run_git(["diff", "--name-only", "HEAD~1", "HEAD"]))),
    )


def load_impact_map(path: Path = DEFAULT_MAP) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("verification impact map must be a YAML object")
    if payload.get("schema_version") != "dspx-verification-impact-map-v1":
        raise ValueError("unsupported verification impact map schema_version")
    rules = payload.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("verification impact map must define non-empty rules")
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"rule {index} must be an object")
        if not rule.get("match") or not rule.get("category") or not rule.get("risk"):
            raise ValueError(f"rule {index} must include match, category, and risk")
        if rule["risk"] not in RISK_ORDER:
            raise ValueError(f"rule {index} has unsupported risk: {rule['risk']}")
        for command_id in rule.get("commands") or []:
            if command_id not in COMMAND_REGISTRY and command_id not in {
                "ruff_touched",
                "pytest_touched",
            }:
                raise ValueError(
                    f"rule {index} references unknown command id: {command_id}"
                )
    return payload


def _matches(pattern: str, path: str) -> bool:
    """Slash-aware glob matcher for impact-map paths.

    ``pathlib.PurePath.match`` and ``fnmatch`` each disagree with one part of the
    impact-map contract: ``PurePath.match('docs/**/*.md')`` misses direct docs
    files, while ``fnmatch`` lets ``*`` cross ``/``. Match segment-by-segment so
    ``*`` stays within one path segment and ``**`` means zero or more segments.
    """

    pattern_parts = [part for part in pattern.replace("\\", "/").split("/") if part]
    path_parts = [part for part in path.replace("\\", "/").split("/") if part]

    def match_from(pattern_index: int, path_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        part = pattern_parts[pattern_index]
        if part == "**":
            if pattern_index == len(pattern_parts) - 1:
                return True
            return any(
                match_from(pattern_index + 1, next_path_index)
                for next_path_index in range(path_index, len(path_parts) + 1)
            )
        if path_index >= len(path_parts):
            return False
        return fnmatch.fnmatchcase(path_parts[path_index], part) and match_from(
            pattern_index + 1,
            path_index + 1,
        )

    return match_from(0, 0)


def _risk_max(risks: list[str]) -> str:
    if not risks:
        return "docs_only"
    return max(risks, key=lambda item: RISK_ORDER[item])


def _existing_repo_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if (ROOT / path).exists()]


def _lintable(paths: list[str]) -> list[str]:
    return [
        path
        for path in _existing_repo_paths(paths)
        if Path(path).suffix in LINTABLE_SUFFIXES
    ]


def _touched_tests(paths: list[str]) -> list[str]:
    return [
        path
        for path in _existing_repo_paths(paths)
        if path.startswith("tests/test_") and path.endswith(".py")
    ]


def _command_from_id(
    command_id: str, paths: list[str], reason: str
) -> dict[str, Any] | None:
    if command_id == "ruff_touched":
        lintable = _lintable(paths)
        if not lintable:
            return None
        return {
            "id": command_id,
            "command": ["uv", "run", "--no-sync", "ruff", "check", *lintable],
            "reason": reason or "lintable file changed",
        }
    if command_id == "pytest_touched":
        tests = _touched_tests(paths)
        if not tests:
            return None
        return {
            "id": command_id,
            "command": [
                "uv",
                "run",
                "--no-sync",
                "-m",
                "pytest",
                "-q",
                *tests,
                "-n",
                "auto",
                "--dist=loadfile",
            ],
            "reason": reason or "test file changed",
        }
    spec = COMMAND_REGISTRY[command_id]
    return {
        "id": command_id,
        "command": list(spec.command),
        "reason": reason or spec.reason,
    }


def build_plan(
    paths: list[str],
    impact_map: dict[str, Any],
    *,
    base_mode: str,
    base_ref: str | None,
) -> dict[str, Any]:
    rel_paths = sorted(
        dict.fromkeys(_repo_rel(path) for path in paths if str(path).strip())
    )
    rules = impact_map["rules"]
    classifications: list[dict[str, Any]] = []
    risks: list[str] = []
    command_reasons: dict[str, list[str]] = {}
    impact_groups: set[str] = set()
    full_required = False
    wide_reasons: list[str] = []

    for path in rel_paths:
        matched = [rule for rule in rules if _matches(str(rule["match"]), path)]
        exclusive_matches = [rule for rule in matched if rule.get("exclusive") is True]
        if exclusive_matches:
            matched = exclusive_matches
        if not matched:
            classifications.append(
                {
                    "path": path,
                    "category": "unknown",
                    "impact_group": "unknown",
                    "risk": "wide",
                    "reasons": ["no impact-map rule matched"],
                }
            )
            risks.append("wide")
            impact_groups.add("unknown")
            full_required = True
            wide_reasons.append(f"unmapped path: {path}")
            command_reasons.setdefault("verify_full", []).append(
                f"{path}: no impact-map rule matched"
            )
            continue
        # Deterministic merge policy: strongest risk wins; commands are unioned.
        risk = _risk_max([str(rule["risk"]) for rule in matched])
        categories = sorted({str(rule["category"]) for rule in matched})
        groups = sorted(
            {str(rule.get("impact_group") or rule["category"]) for rule in matched}
        )
        reasons = [f"matched {rule['match']}" for rule in matched]
        classifications.append(
            {
                "path": path,
                "category": "+".join(categories),
                "impact_group": "+".join(groups),
                "risk": risk,
                "reasons": reasons,
            }
        )
        risks.append(risk)
        impact_groups.update(groups)
        if any(bool(rule.get("requires_full_verification")) for rule in matched):
            full_required = True
            wide_reasons.append(f"{path} requires full verification")
        for rule in matched:
            for command_id in rule.get("commands") or []:
                command_reasons.setdefault(str(command_id), []).append(
                    f"{path}: matched {rule['match']}"
                )

    raw_thresholds = impact_map.get("thresholds")
    thresholds: dict[str, Any] = (
        raw_thresholds if isinstance(raw_thresholds, dict) else {}
    )
    max_files = int(thresholds.get("max_changed_files_before_wide", 20))
    max_groups = int(thresholds.get("max_impact_groups_before_wide", 3))
    docs_only_paths = (
        all(item.get("risk") == "docs_only" for item in classifications)
        if classifications
        else True
    )
    if len(rel_paths) > max_files and not docs_only_paths:
        risks.append("wide")
        wide_reasons.append(
            f"changed file count {len(rel_paths)} exceeds threshold {max_files}"
        )
    if len(impact_groups) > max_groups:
        risks.append("wide")
        wide_reasons.append(
            f"impact group count {len(impact_groups)} exceeds threshold {max_groups}"
        )

    risk = _risk_max(risks)
    wide_reason = "; ".join(dict.fromkeys(wide_reasons)) or None
    full_verification_required = full_required or risk == "wide"
    if full_verification_required:
        command_reasons.setdefault("verify_full", []).append(
            wide_reason or "wide/full verification required"
        )

    commands: list[dict[str, Any]] = []
    seen_commands: set[tuple[str, ...]] = set()
    command_order = [
        "workflow_contract_check",
        "direction_contract_check",
        "governance_check",
        "task_scope_check",
        "ruff_touched",
        "typecheck_core",
        "typecheck_all",
        "impact_plan_smoke",
        "pytest_touched",
        "pytest_verify_changed",
        "pytest_test_defaults",
        "pytest_task_scope",
        "pytest_boundary_hardening",
        "pytest_boundary_adversarial",
        "pytest_generated_code_guard_adversarial",
        "pytest_cli_dspx",
        "pytest_forge_cli_policy",
        "pytest_program_runtime_episode",
        "pytest_program_activation_packet",
        "pytest_program_adjudication_publication",
        "pytest_program_oracle_publication",
        "pytest_program_architecture",
        "pytest_module_synthesis_evidence",
        "pytest_run_receipts",
        "pytest_program_meta_adjudication",
        "pytest_program_model_jury",
        "pytest_generated_direct_runner",
        "pytest_program_direct_runner_generation",
        "pytest_program_generation_spine",
        "pytest_mermaid_workflow",
        "pytest_program_generated_policy",
        "pytest_program_runtime_traces",
        "pytest_program_oracle_refinement",
        "pytest_program_refinement_candidate",
        "pytest_program_refinement_comparison",
        "pytest_program_refinement_episode",
        "pytest_program_refinement_gepa_candidate",
        "pytest_program_promotion_review",
        "pytest_program_promotion_decision",
        "pytest_refinement_candidate_comparison",
        "pytest_optimize_gepa",
        "pytest_program_sidecar_boundaries",
        "pytest_promotion_plan_adjacent",
        "pytest_coordinates",
        "pytest_provider_runtime",
        "pytest_provider_v4",
        "pytest_cache_boundary",
        "pytest_server_security",
        "pytest_adapters_eval",
        "pytest_tools_registry",
        "pytest_openapi_tooling",
        "pytest_openapi_boundary_contracts",
        "pytest_authority_boundary_contracts",
        "pytest_oracle_time_travel",
        "boundary_contract_check",
        "verify_runtime_replay",
        "verify_runtime_monorepo",
        "verify_runtime_module_synthesis",
        "verify_runtime_boundary",
        "docs_strict",
        "verify_runtime",
        "verify_fast",
        "verify_full",
    ]
    for command_id in command_order:
        if command_id not in command_reasons:
            continue
        command = _command_from_id(
            command_id, rel_paths, "; ".join(command_reasons[command_id])
        )
        if command is None:
            continue
        key = tuple(command["command"])
        if key not in seen_commands:
            seen_commands.add(key)
            commands.append(command)

    return {
        "schema_version": "dspx-verification-impact-plan-v1",
        "base_mode": base_mode,
        "base_ref": base_ref,
        "changed_files": rel_paths,
        "classifications": classifications,
        "commands": commands,
        "risk": risk,
        "full_verification_required": full_verification_required,
        "wide_reason": wide_reason,
    }


def _print_text_summary(plan: dict[str, Any]) -> None:
    print(f"Plan risk: {plan['risk']}")
    print(f"Base: {plan['base_mode']} {plan.get('base_ref') or ''}".rstrip())
    print(
        f"Full verification required: {str(plan['full_verification_required']).lower()}"
    )
    if plan.get("wide_reason"):
        print(f"Wide reason: {plan['wide_reason']}")
    print("Changed files:")
    for path in plan["changed_files"]:
        print(f"- {path}")
    print("Commands:")
    for command in plan["commands"]:
        print(f"- {command['id']}: {' '.join(command['command'])}")


def _now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _result_payload(
    *,
    plan: dict[str, Any],
    status: str,
    started_at: str,
    ended_at: str,
    command_results: list[dict[str, Any]],
    exit_code: int,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "dspx-verification-impact-result-v1",
        "status": status,
        "started_at": started_at,
        "ended_at": ended_at,
        "exit_code": exit_code,
        "plan": plan,
        "commands": command_results,
        "summary": {
            "command_count": len(command_results),
            "passed_count": sum(
                1 for item in command_results if item["status"] == "passed"
            ),
            "failed_count": sum(
                1 for item in command_results if item["status"] == "failed"
            ),
            "blocked_wide": status == "blocked_wide",
            "full_verification_required": bool(plan.get("full_verification_required")),
            "risk": plan.get("risk"),
        },
        "non_authority": {
            "local_verification_receipt_only": True,
            "full_verification_replacement": False,
            "ak_mutation": False,
            "governance_mutation": False,
            "oracle_mutation": False,
            "external_authority_mutation": False,
        },
        **({"note": note} if note else {}),
    }


def execute_plan(
    plan: dict[str, Any], *, allow_wide: bool
) -> tuple[int, dict[str, Any]]:
    started_at = _now_utc()
    command_results: list[dict[str, Any]] = []
    requires_wide_allowance = plan["risk"] == "wide" or bool(
        plan["full_verification_required"]
    )
    if requires_wide_allowance and not allow_wide:
        ended_at = _now_utc()
        return (
            2,
            _result_payload(
                plan=plan,
                status="blocked_wide",
                started_at=started_at,
                ended_at=ended_at,
                command_results=command_results,
                exit_code=2,
                note="impact plan is wide or full-required; rerun with --allow-wide to execute selected commands",
            ),
        )

    if plan["full_verification_required"] and not plan["commands"]:
        ended_at = _now_utc()
        return (
            2,
            _result_payload(
                plan=plan,
                status="failed",
                started_at=started_at,
                ended_at=ended_at,
                command_results=command_results,
                exit_code=2,
                note="full-required impact plan selected no commands",
            ),
        )

    exit_code = 0
    for command in plan["commands"]:
        print(f"==> {command['id']}: {' '.join(command['command'])}", flush=True)
        command_started_at = _now_utc()
        command_start = time.monotonic()
        proc = subprocess.run(command["command"], cwd=ROOT, check=False)
        command_ended_at = _now_utc()
        command_result = {
            "id": command["id"],
            "command": list(command["command"]),
            "reason": command.get("reason"),
            "started_at": command_started_at,
            "ended_at": command_ended_at,
            "duration_seconds": round(time.monotonic() - command_start, 6),
            "returncode": proc.returncode,
            "status": "passed" if proc.returncode == 0 else "failed",
        }
        command_results.append(command_result)
        if proc.returncode != 0:
            exit_code = int(proc.returncode)
            break
    ended_at = _now_utc()
    status = "passed" if exit_code == 0 else "failed"
    return (
        exit_code,
        _result_payload(
            plan=plan,
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            command_results=command_results,
            exit_code=exit_code,
        ),
    )


def run_plan(
    plan: dict[str, Any], *, allow_wide: bool, result_out: Path | None = None
) -> int:
    exit_code, result = execute_plan(plan, allow_wide=allow_wide)
    if result_out is not None:
        _write_json(result_out.expanduser().resolve(), result)
    if result["status"] == "blocked_wide":
        print(str(result["note"]), file=sys.stderr)
    return exit_code


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="auto", help="Git base ref, or auto")
    parser.add_argument("--staged", action="store_true", help="Use staged changes")
    parser.add_argument(
        "--files", nargs="*", default=[], help="Explicit repo-relative files"
    )
    parser.add_argument("--map", default=str(DEFAULT_MAP), help="Impact map path")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--plan-only",
        action="store_true",
        help="Print the plan without running commands",
    )
    mode.add_argument("--run", action="store_true", help="Run selected commands")
    parser.add_argument(
        "--allow-wide", action="store_true", help="Allow execution of wide-risk plans"
    )
    parser.add_argument(
        "--result-out",
        help="Optional path for a local JSON verification result receipt when --run is used",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    impact_map = load_impact_map(Path(args.map))
    base_mode, base_ref, paths = changed_files(
        base=args.base,
        staged=args.staged,
        explicit_files=list(args.files),
    )
    plan = build_plan(paths, impact_map, base_mode=base_mode, base_ref=base_ref)
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        _print_text_summary(plan)
        print("\nJSON plan:")
        print(json.dumps(plan, indent=2, sort_keys=True))
    if args.run:
        sys.stdout.flush()
        result_out = Path(args.result_out) if args.result_out else None
        return run_plan(plan, allow_wide=args.allow_wide, result_out=result_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
