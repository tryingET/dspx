"""Captured-v1 runtime and materialization contracts, independent of orchestration."""

import json
from pathlib import PurePosixPath
from types import SimpleNamespace

from program_quality_evaluation import (  # ty: ignore[unresolved-import]
    normalize_quality_criteria,
    evaluate_declared_quality,
    runtime_status_with_declared_quality,
)
from program_runtime_traces import (  # ty: ignore[unresolved-import]
    build_program_runtime_traces,
    validate_program_runtime_traces,
)
from program_foundry_closure_runtime import _oracle_evidence, provider  # ty: ignore[unresolved-import]

from program_foundry_closure_io import digest, equal, require, sibling  # ty: ignore[unresolved-import]


def identity(manifest: dict) -> dict:
    blocks = [
        manifest.get(k, {})
        for k in (
            "request",
            "candidate_assembly",
            "execution_episode",
            "receipt_bundle",
        )
    ]
    require(
        all(isinstance(block, dict) for block in blocks), "candidate_identity_shape"
    )
    orders = {
        "request_id": (0, 1, 2, 3),
        "candidate_id": (1, 2, 3),
        "assembly_id": (1, 2, 3),
        "episode_id": (2, 3),
        "receipt_bundle_id": (3,),
    }
    result = {}
    for key, order in orders.items():
        values = [str(blocks[i].get(key) or "").strip() for i in order]
        result[key] = next((x for x in values if x), None)
        require(result[key] is not None, "missing_candidate_identity")
    return result


def candidate_declarations(s, path: str, manifest: dict) -> None:
    equal(
        manifest["candidate_assembly"]["root_path"],
        str(PurePosixPath(path).parent),
        "candidate_root",
    )
    for role, schema, section, path_key, hash_key in (
        (
            "behavior_results",
            "program-behavior-results-v1",
            "behavior_results",
            "path",
            "content_hash",
        ),
        (
            "behavior_episode",
            "program-behavior-episode-v1",
            "behavior_orchestration",
            "result_artifact",
            "result_hash",
        ),
    ):
        local = role + ".json"
        full = sibling(path, local)
        equal(s.json(full)["schema_version"], schema, "candidate_" + role + "_schema")
        blocks = [
            (manifest["request"], role + "_hash"),
            (manifest["receipt_bundle"]["evidence"], role + "_hash"),
        ]
        embedded = manifest["execution_episode"].get(section, {})
        if embedded.get(path_key):
            equal(embedded[path_key], local, "candidate_" + role + "_path")
        blocks.append((embedded, hash_key))
        artifact = manifest.get(role + "_artifact", {})
        if artifact:
            equal(artifact["path"], local, "candidate_" + role + "_path")
            blocks.append((artifact, "content_hash"))
        for block, key in blocks:
            if block.get(key):
                equal(block[key], s.hash(full), "candidate_" + role + "_declaration")


def gepa_result(result: dict, expected_identity: dict) -> None:
    equal(result["source_identity"], expected_identity, "gepa_result_identity")
    equal(result["candidate"], None, "gepa_result_candidate")
    require(result["status"] != "gepa_output_unverified", "gepa_result_status")
    for key in (
        "source_program_files_mutated",
        "source_dataset_artifacts_mutated",
        "local_gepa_candidate_generated",
        "external_authority_mutated",
        "governance_mutated",
    ):
        equal(result["effect"].get(key), False, "gepa_result_effect")
    equal(
        result["non_authority"].get("local_refinement_only"),
        True,
        "gepa_result_non_authority",
    )
    for key in (
        "automatic_promotion",
        "oracle_ranking",
        "oracle_pruning",
        "oracle_promotion",
        "winner_selection",
        "external_authority_export",
        "governance_authority",
        "external_mutation",
    ):
        equal(result["non_authority"].get(key), False, "gepa_result_non_authority")
    readiness = result["gepa_output"]["readiness"]
    equal(
        readiness.get("ready_for_future_candidate_materializer"),
        True,
        "gepa_result_readiness",
    )
    equal(
        readiness.get("status"),
        "optimizer_output_hash_bound_not_candidate",
        "gepa_result_readiness",
    )


def runtime_manifest(
    s, path: str, source_path: str, episode: dict, manifest: dict, behavior: dict
) -> None:
    equal(
        episode["manifest_path"],
        sibling(path, "manifest.json"),
        "runtime_manifest_path",
    )
    equal(
        manifest.get("schema_version"),
        "program-candidate-assembly-v1",
        "runtime_manifest_schema",
    )
    equal(
        identity(manifest), identity(s.json(source_path)), "runtime_candidate_identity"
    )
    equal(
        manifest.get("source_candidate_manifest"),
        {"path": source_path, "sha256": s.hash(source_path)},
    )
    embedded = manifest.get("runtime_episode", {})
    require(isinstance(embedded, dict), "runtime_manifest_episode_shape")
    expected = {
        "schema_version": "program-runtime-episode-v1",
        "runtime_episode_id": episode["runtime_episode_id"],
        "contract_mode": episode["contract_mode"],
        "inputs_path": "runtime_inputs.json",
        "behavior_results_path": "behavior_results.json",
        "inputs_sha256": episode["artifact_hashes"]["runtime_inputs_sha256"],
        "behavior_results_sha256": episode["artifact_hashes"][
            "behavior_results_sha256"
        ],
    }
    for key, value in expected.items():
        equal(embedded.get(key), value, "runtime_manifest_" + key)
    equal(behavior.get("schema_version"), "program-behavior-results-v1")
    equal(behavior.get("runtime_episode_id"), episode["runtime_episode_id"])
    equal(behavior.get("authority"), "behavior_evidence_only_non_authoritative")


def runtime_graph(
    s, path: str, source_path: str, episode: dict, behavior: dict, receipt: dict
) -> None:
    """Complete current readback joins over captured bytes, with finite runtime support."""
    source = s.json(source_path)
    hashes = episode["artifact_hashes"]
    expected_id = (
        "prog-run-"
        + digest(
            json.dumps(
                {
                    "manifest_hash": s.hash(source_path),
                    "inputs_hash": hashes["runtime_inputs_sha256"],
                    "contract_mode": episode["contract_mode"],
                },
                sort_keys=True,
            ).encode()
        )[:16]
    )
    equal(episode["runtime_episode_id"], expected_id, "runtime_identity")
    intent = source["intent"]
    criteria = normalize_quality_criteria(
        intent.get("quality_criteria", []), outputs=intent["outputs"]
    )
    equal(
        behavior["intent"].get("quality_criteria", []),
        criteria,
        "runtime_quality_criteria",
    )
    records = behavior["examples"]
    require(
        isinstance(records, list)
        and len(records) == 1
        and isinstance(records[0], dict),
        "runtime_behavior_record_count",
    )
    record = records[0]
    equal(
        record["inputs"],
        s.json(sibling(path, "runtime_inputs.json"))["inputs"],
        "runtime_behavior_inputs",
    )
    equal(behavior["input_fields"], intent["inputs"], "runtime_behavior_input_fields")
    equal(
        behavior["output_fields"], intent["outputs"], "runtime_behavior_output_fields"
    )
    quality = evaluate_declared_quality(criteria, record["observed_outputs"])
    equal(behavior["quality_evaluation"], quality, "runtime_quality_evaluation")
    equal(record["quality_evaluation"], quality, "runtime_record_quality_evaluation")
    status = runtime_status_with_declared_quality(
        episode["execution_status"], quality["status"]
    )
    equal(episode["status"], status, "runtime_quality_status")
    equal(record["status"], status, "runtime_record_status")
    for block in (behavior, record):
        equal(
            block["execution_status"],
            episode["execution_status"],
            "runtime_behavior_execution_status",
        )
    summary = {
        "total": 1,
        "passed": int(status == "executed_quality_passed"),
        "failed": int(status.startswith("failed") or status == "error"),
        "error": int(status == "error"),
        "degraded": int(status.startswith("degraded")),
        "executed": int(
            status
            in {"executed", "executed_quality_passed", "executed_valid_review_only"}
        ),
        "status_counts": {status: 1},
        "status": status,
    }
    equal(behavior["summary"], summary, "runtime_behavior_summary")
    for key in (
        "optimization_authority",
        "promotion_authority",
        "oracle_ranking",
        "oracle_pruning",
        "oracle_promotion",
        "governance_authority",
        "external_mutation",
        "external_authority_mutated",
        "winner_selection",
    ):
        equal(
            behavior["non_authority"].get(key), False, "runtime_behavior_non_authority"
        )
    traces = s.json(sibling(path, "program_runtime_traces.json"))
    equal(
        traces["sources"],
        [
            {
                "path": "behavior_results.json",
                "content_hash": hashes["behavior_results_sha256"],
                "kind": "examples",
                "split": None,
                "record_count": 1,
                "summary": summary,
            }
        ],
        "runtime_trace_source",
    )
    # Cap producer coverage loops before validating attacker-controlled counts.
    require(
        isinstance(traces["module_calls"], list)
        and len(traces["module_calls"]) <= 64
        and isinstance(traces["final_outputs"], list)
        and len(traces["final_outputs"]) <= 32,
        "runtime_trace_count",
    )
    require(validate_program_runtime_traces(traces), "runtime_trace_contract")
    trace_intent = SimpleNamespace(
        name=intent["name"], objective=intent["objective"], outputs=intent["outputs"]
    )
    surfaces = s.json(sibling(source_path, "module_surfaces.json"))
    calls = record.get("runtime_trace", {}).get("module_calls", [])
    require(
        isinstance(calls, list) and len(calls) <= 64, "runtime_behavior_trace_bound"
    )
    require(
        isinstance(surfaces["module_surfaces"], list)
        and len(surfaces["module_surfaces"]) <= 64,
        "runtime_module_bound",
    )
    rebuilt_traces = build_program_runtime_traces(
        trace_intent,
        module_surfaces=surfaces,
        behavior_results=behavior,
        behavior_results_hash=hashes["behavior_results_sha256"],
    )
    equal(traces, rebuilt_traces, "runtime_trace_reconstruction")
    oracle = s.json(sibling(path, "oracle_evidence.json"))
    expected_oracle = _oracle_evidence(
        manifest_identity=identity(source),
        runtime_episode_id=expected_id,
        behavior_results=behavior,
        behavior_results_hash=hashes["behavior_results_sha256"],
        runtime_traces=traces,
        runtime_traces_hash=hashes["program_runtime_traces_sha256"],
        inputs_hash=hashes["runtime_inputs_sha256"],
        contract_mode=episode["contract_mode"],
        manifest=source,
    )
    for key, value in expected_oracle.items():
        equal(oracle.get(key), value, "runtime_oracle_" + key)
    replay = receipt["replay_inputs"]
    equal(replay["contract_mode"], episode["contract_mode"], "runtime_replay_mode")
    for key, value in {
        "runtime_episode_id": expected_id,
        "contract_mode": episode["contract_mode"],
        "execution_status": episode["execution_status"],
        "status": status,
        "quality_status": quality["status"],
    }.items():
        equal(replay["expected_episode"][key], value, "runtime_replay_" + key)
    run_summary = receipt["run_summary"]
    for key, value in {
        "runtime_episode_id": expected_id,
        "runtime_status": status,
        "evidence_only": True,
        **{
            k: hashes[k]
            for k in (
                "behavior_results_sha256",
                "program_runtime_traces_sha256",
                "oracle_evidence_sha256",
            )
        },
    }.items():
        equal(run_summary[key], value, "runtime_receipt_summary_" + key)
    raw_provider = episode.get("provider")
    if raw_provider is None:
        legacy = behavior.get("provider", {})
        unavailable = (
            legacy.get("status") == "unavailable"
            and set(legacy) == {"status", "error"}
            and set(legacy["error"]) == {"type", "message"}
            and all(isinstance(x, str) for x in legacy["error"].values())
        )
        require(
            legacy == {"status": "configured", "provider": "stub/echo"} or unavailable,
            "runtime_legacy_provider",
        )
        details = {
            "provider": "stub",
            "provider_family": "stub",
            "model": "stub/echo",
            "effect_contract": "dspx-provider-effect-v1",
        }
    else:
        details = provider(raw_provider)
        equal(behavior["provider"], raw_provider, "runtime_behavior_provider")
        equal(run_summary["provider"], raw_provider, "runtime_receipt_provider")
    equal(receipt["provider_details"], details, "runtime_provider_details")
    equal(receipt["provider"], details["provider"], "runtime_provider_identity")


def materialization(
    s,
    candidate: dict,
    candidate_path: str,
    source_path: str,
    result_path: str,
    generation: dict,
    optimizer: dict,
    tree_hash: str,
) -> None:
    equal(generation["schema_version"], "program-refinement-gepa-candidate-result-v1")
    equal(generation["status"], "materialized")
    equal(generation["source_identity"], identity(s.json(source_path)))
    equal(
        generation["candidate"],
        {
            **identity(candidate),
            "manifest_path": candidate_path,
            "root_path": str(PurePosixPath(candidate_path).parent),
            "promotion_state": "not_promoted",
        },
    )
    equal(
        generation["effect"],
        {
            "local_gepa_candidate_generated": True,
            **{
                k: False
                for k in (
                    "source_program_files_mutated",
                    "source_dataset_artifacts_mutated",
                    "gepa_optimizer_output_mutated",
                    "external_authority_mutated",
                    "governance_mutated",
                )
            },
        },
    )
    equal(
        generation["non_authority"],
        {
            "local_candidate_generation_only": True,
            **{
                k: False
                for k in (
                    "automatic_promotion",
                    "oracle_ranking",
                    "oracle_pruning",
                    "oracle_promotion",
                    "winner_selection",
                    "external_authority_export",
                    "governance_authority",
                    "external_mutation",
                )
            },
        },
    )
    lineage = candidate.get("gepa_refinement", {})
    require(isinstance(lineage, dict), "materialization_lineage_shape")
    output = generation["gepa_output"]
    equal(output["source_program_sha256"], s.hash(sibling(source_path, "program.py")))
    equal(output["optimizer_manifest_program_sha256"], optimizer["program"]["sha256"])
    copied_root = sibling(candidate_path, "gepa_optimizer_output")
    equal(output["copied_to"], copied_root, "optimizer_copy_root")
    manifest_hash = s.hash(copied_root + "/manifest.json")
    # Payload inventory excludes manifest.json; execution tree hash does not.
    file_count = len(optimizer["output_payload"]["files"])
    expected = {
        "schema_version": "program-gepa-candidate-materialization-v1",
        "status": "materialized_local_candidate",
        "source_identity": identity(s.json(source_path)),
        "source_manifest_path": source_path,
        "source_manifest_sha256": s.hash(source_path),
        "gepa_refinement_result_path": result_path,
        "gepa_refinement_result_sha256": s.hash(result_path),
        "gepa_optimizer_manifest_sha256": manifest_hash,
        "gepa_optimizer_payload_tree_sha256": tree_hash,
        "gepa_optimizer_payload_file_count": file_count,
        "non_authority": {
            key: False
            for key in (
                "automatic_promotion",
                "winner_selection",
                "external_authority_export",
                "governance_authority",
                "external_mutation",
            )
        },
    }
    for key, value in expected.items():
        equal(lineage.get(key), value, "materialization_" + key)
    equal(output["manifest_sha256"], manifest_hash)
    equal(output["payload_tree_sha256"], tree_hash, "optimizer_payload_tree")
    equal(output["payload_file_count"], file_count)
    metric = optimizer.get("metric_honesty")
    equal(lineage.get("metric_honesty"), metric, "materialization_metric_honesty")
    equal(output.get("metric_honesty"), metric)
    if metric is not None:
        equal(output["source_program_sha256"], metric["source_program_sha256"])
        require(
            s.hash(sibling(candidate_path, "program.py"))
            != metric["wrapper_program_sha256"],
            "candidate_is_metric_wrapper",
        )
    refresh = lineage["behavior_refresh"]
    equal(refresh["status"], "refreshed")
    equal(refresh["authority"], "local_behavior_evidence_only_non_authoritative")
    for role in ("behavior_episode", "behavior_results"):
        equal(
            generation["behavior_refresh"][role + "_path"],
            sibling(candidate_path, role + ".json"),
        )
        equal(
            generation["behavior_refresh"][role + "_sha256"],
            s.hash(sibling(candidate_path, role + ".json")),
        )
        equal(
            refresh[role + "_sha256"], s.hash(sibling(candidate_path, role + ".json"))
        )
    require(
        refresh["oracle_evidence_removed_as_stale"] is True, "stale_generated_oracle"
    )
