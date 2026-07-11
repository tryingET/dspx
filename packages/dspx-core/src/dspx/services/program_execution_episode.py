# summary: "Builds the non-authoritative execution episode assembled from program materialization and behavior evidence."
# read_when:
#   - "Changing execution episode checks, topology reporting, or evidence summaries."

from __future__ import annotations

from typing import Any, Mapping

from dspx.services.program_dataset import SPLIT_NAMES
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_topology import (
    MATERIALIZABLE_DECLARED_TOPOLOGY_KINDS,
    PIPELINE_MATERIALIZED_STATUS,
    PROMPT_INFERRED_PIPELINE_RENDERER,
    RETRIEVE_THEN_ANSWER_RENDERER,
    prompt_inferred_pipeline_topology,
)


def _harness_status(result: Mapping[str, Any] | None) -> str:
    if result is None:
        return "not_applicable"
    return "passed" if result.get("returncode") == 0 else "failed"


def _behavior_provider(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    raw_provider = payload.get("provider")
    return dict(raw_provider) if isinstance(raw_provider, Mapping) else {}


def build_program_execution_episode(
    *,
    ids: Mapping[str, str],
    intent: ProgramIntent,
    generated_file_names: list[str],
    smoke_result: Mapping[str, Any],
    jury_result: Mapping[str, Any],
    promotion_result: Mapping[str, Any],
    examples_result: Mapping[str, Any] | None,
    behavior_episode_result: Mapping[str, Any] | None,
    behavior_episode_hash: str | None,
    behavior_episode_payload: Mapping[str, Any] | None,
    dataset_manifest_hash: str | None,
    dataset_manifest_payload: Mapping[str, Any] | None,
    dataset_split_results: Mapping[str, Mapping[str, Any]],
    dataset_split_behavior_payloads: Mapping[str, Mapping[str, Any]],
    dataset_split_behavior_hashes: Mapping[str, str],
    behavior_results_hash: str | None,
    behavior_summary: Mapping[str, Any] | None,
    behavior_results_payload: Mapping[str, Any] | None,
    oracle_evidence_hash: str | None,
    oracle_readability_summary: Mapping[str, Any] | None,
    oracle_readability_facets: Mapping[str, Any] | None,
    evaluation_sources: list[dict[str, Any]],
    behavior_evidence_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the non-authoritative episode contract from observed runtime inputs."""

    examples_count = len(intent.examples or [])
    dataset_artifacts = (
        dict(dataset_manifest_payload.get("artifacts") or {})
        if dataset_manifest_payload is not None
        else {}
    )
    behavior_status = None
    if behavior_summary is not None:
        behavior_status = str(behavior_summary.get("status") or "executed")
    behavioral_evaluation = {
        "status": behavior_status if behavior_status is not None else "not_applicable",
        "examples_count": examples_count,
        "result_artifact": "behavior_results.json"
        if behavior_results_hash is not None
        else None,
        "result_hash": behavior_results_hash,
        "summary": dict(behavior_summary or {}),
    }
    oracle_readability = {
        "status": "captured" if oracle_evidence_hash is not None else "not_applicable",
        "oracle_invoked": False,
        "result_artifact": "oracle_evidence.json"
        if oracle_evidence_hash is not None
        else None,
        "result_hash": oracle_evidence_hash,
        "summary": dict(oracle_readability_summary or {}),
        "facets": dict(oracle_readability_facets or {}),
    }
    provider_conditions: dict[str, Any] = {}
    if behavior_results_payload is not None:
        provider_conditions["examples"] = _behavior_provider(behavior_results_payload)
    if dataset_split_behavior_payloads:
        provider_conditions["dataset_splits"] = {
            split: _behavior_provider(payload)
            for split, payload in dataset_split_behavior_payloads.items()
        }
    declared_topology = dict(intent.topology or {})
    inferred_topology = prompt_inferred_pipeline_topology(intent)
    declared_kind = str(declared_topology.get("kind") or "")
    if declared_kind in MATERIALIZABLE_DECLARED_TOPOLOGY_KINDS:
        status = (
            PIPELINE_MATERIALIZED_STATUS
            if declared_kind == "pipeline"
            else f"{declared_kind}_materialized"
        )
        renderer = (
            "pipeline_topology_renderer"
            if declared_kind == "pipeline"
            else RETRIEVE_THEN_ANSWER_RENDERER
            if declared_kind == "retrieve_then_answer"
            else f"{declared_kind}_topology_renderer"
        )
        notes = [
            f"Explicit {declared_kind} topology was rendered into signature.py, module.py, and program.py.",
            "Routing supports only simple when.field/equals clauses; no executable expressions are evaluated.",
        ]
        if declared_kind == "retrieve_then_answer":
            notes.insert(
                1,
                "Retrieval is limited to generated bounded inline-corpus adapters or materialization-time local_corpus_snapshot adapters; no live external retriever is bound or executed.",
            )
        topology_execution = {
            "declared_topology_present": True,
            "declared_topology_kind": declared_kind,
            "materialized": True,
            "status": status,
            "current_renderer": renderer,
            "materialized_topology_kind": declared_kind,
            "notes": notes,
        }
    elif inferred_topology:
        topology_execution = {
            "declared_topology_present": False,
            "declared_topology_kind": None,
            "inferred_topology_present": True,
            "inferred_topology_kind": "pipeline",
            "materialized": True,
            "status": PIPELINE_MATERIALIZED_STATUS,
            "current_renderer": PROMPT_INFERRED_PIPELINE_RENDERER,
            "materialized_topology_kind": "pipeline",
            "notes": [
                "Prompt-inferred generated module topology was rendered into signature.py, module.py, and program.py.",
                "Inference supports only bounded generated Predict/ChainOfThought modules and simple deterministic routing.",
                "No custom Python imports, external tools/retrievers, ReAct, ranking, promotion, or external authority mutation are performed.",
            ],
        }
    else:
        topology_execution = {
            "declared_topology_present": bool(declared_topology),
            "declared_topology_kind": declared_topology.get("kind"),
            "inferred_topology_present": False,
            "materialized": not bool(declared_topology),
            "status": str(
                declared_topology.get("execution_status")
                or "single_module_scaffold_materialized"
            ),
            "current_renderer": "single_module_scaffold",
            "materialized_topology_kind": "single_module",
            "notes": [
                "Explicit topology is declared-only unless materialized is true.",
                "program.py delegates to the generated single module scaffold for non-pipeline topology kinds.",
            ],
        }
    return {
        "schema_version": "program-execution-episode-v1",
        "episode_id": ids["episode_id"],
        "request_id": ids["request_id"],
        "candidate_id": ids["candidate_id"],
        "assembly_id": ids["assembly_id"],
        "phase": "materialize",
        "evaluator": "deterministic_program_bundle_smoke",
        "status": "passed",
        "status_scope": "materialization_and_binding_checks",
        "authority": "execution_episode_evidence_only_non_authoritative",
        "runtime_conditions": {
            "runtime": dict(intent.runtime),
            "metric": intent.metric or "unspecified",
            "providers": provider_conditions,
        },
        "materialization": {
            "status": "passed",
            "generated_file_count": len(generated_file_names),
            "generated_files": list(generated_file_names),
        },
        "checks": {
            "compile": {
                "status": "passed",
                "files": [
                    name for name in generated_file_names if name.endswith(".py")
                ],
            },
            "smoke": {
                "status": _harness_status(smoke_result),
                "returncode": smoke_result.get("returncode"),
                "command": smoke_result.get("command"),
            },
            "examples_binding": {
                "status": _harness_status(examples_result),
                "examples_count": examples_count,
                "artifact_refs": ["examples.json", "eval_examples.py"]
                if examples_result is not None
                else [],
            },
            "dataset_binding": {
                "status": "passed"
                if dataset_manifest_payload is not None
                else "not_applicable",
                "dataset_manifest": "dataset_manifest.json"
                if dataset_manifest_payload is not None
                else None,
                "split_artifacts": {
                    split: {
                        "split_path": artifact.get("path"),
                        "eval_harness": artifact.get("eval_harness"),
                        "behavior_results": artifact.get("behavior_results"),
                        "record_count": artifact.get("record_count"),
                    }
                    for split, artifact in dataset_artifacts.items()
                    if isinstance(artifact, Mapping)
                },
            },
            "jury_binding": {
                "status": _harness_status(jury_result),
                "returncode": jury_result.get("returncode"),
                "artifact_refs": [
                    "jury.json",
                    "jury_selection.json",
                    "jury_rubric.json",
                    "eval_jury.py",
                ],
            },
            "promotion_binding": {
                "status": _harness_status(promotion_result),
                "returncode": promotion_result.get("returncode"),
                "artifact_refs": [
                    "promotion_review.json",
                    "promotion_adjudication_request.json",
                    "promotion_decision_template.json",
                    "eval_promotion.py",
                ],
            },
        },
        "behavior_status": behavior_status,
        "topology_execution": topology_execution,
        "evaluation_sources": list(evaluation_sources),
        "behavior_evidence_summary": dict(behavior_evidence_summary),
        "behavior_orchestration": {
            "status": _harness_status(behavior_episode_result),
            "harness": "eval_behavior.py"
            if behavior_episode_result is not None
            else None,
            "returncode": behavior_episode_result.get("returncode")
            if behavior_episode_result is not None
            else None,
            "result_artifact": "behavior_episode.json"
            if behavior_episode_hash is not None
            else None,
            "result_hash": behavior_episode_hash,
            "summary": dict(dict(behavior_episode_payload or {}).get("summary") or {}),
        },
        "behavioral_evaluation": behavioral_evaluation,
        "behavior_results": {
            "path": "behavior_results.json",
            "content_hash": behavior_results_hash,
            "summary": dict(behavior_summary or {}),
        }
        if behavior_results_hash is not None
        else None,
        "dataset_evaluation": {
            "status": "captured"
            if dataset_manifest_payload is not None
            else "not_applicable",
            "dataset_manifest": {
                "path": "dataset_manifest.json",
                "content_hash": dataset_manifest_hash,
                "schema_version": dataset_manifest_payload.get("schema_version"),
            }
            if dataset_manifest_payload is not None
            else None,
            "split_results": {
                split: {
                    "harness": dict(dataset_split_results.get(split) or {}),
                    "behavior_results_path": dataset_artifacts.get(split, {}).get(
                        "behavior_results"
                    )
                    if isinstance(dataset_artifacts.get(split), Mapping)
                    else None,
                    "behavior_results_hash": dataset_split_behavior_hashes.get(split),
                    "summary": dict(
                        dataset_split_behavior_payloads.get(split, {}).get("summary")
                        or {}
                    ),
                }
                for split in SPLIT_NAMES
            },
        },
        "oracle_readability": oracle_readability,
        "oracle_evidence": {
            "path": "oracle_evidence.json",
            "content_hash": oracle_evidence_hash,
            "summary": dict(oracle_readability_summary or {}),
            "facets": dict(oracle_readability_facets or {}),
        }
        if oracle_evidence_hash is not None
        else None,
        "non_authority": {
            "evidence_only": True,
            "oracle_role": "not_invoked",
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "ranking_pruning_promotion": False,
            "promotion_authority": False,
            "oracle_authority": False,
            "winner_selection": False,
            "automatic_promotion": False,
            "governance_authority": False,
            "ak_mutation": False,
            "governance_mutation": False,
            "external_mutation": False,
            "external_authority_mutated": False,
        },
        "metadata": {
            "smoke": dict(smoke_result),
            "jury": dict(jury_result),
            "promotion": dict(promotion_result),
            **(
                {"examples": dict(examples_result)}
                if examples_result is not None
                else {}
            ),
            **(
                {"behavior_episode": dict(behavior_episode_payload)}
                if behavior_episode_payload is not None
                else {}
            ),
            **(
                {
                    "dataset": {
                        "manifest": dict(dataset_manifest_payload),
                        "split_harnesses": {
                            split: dict(result)
                            for split, result in dataset_split_results.items()
                        },
                        "split_behavior_results": {
                            split: dict(payload)
                            for split, payload in dataset_split_behavior_payloads.items()
                        },
                    }
                }
                if dataset_manifest_payload is not None
                else {}
            ),
            **(
                {"behavior_results": dict(behavior_results_payload)}
                if behavior_results_payload is not None
                else {}
            ),
        },
        "notes": [
            "Materialization, binding checks, behavioral evaluation, and Oracle readability are separate episode sections.",
            "eval_examples.py is the example-backed behavior harness when examples exist.",
            "Oracle readability is captured without invoking Oracle or mutating an index.",
            "This artifact is evidence only and cannot rank, prune, promote, export, or mutate governance authority.",
        ],
    }
