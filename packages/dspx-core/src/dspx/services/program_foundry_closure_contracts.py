"""Captured-v1 runtime and materialization contracts, independent of orchestration."""

from pathlib import PurePosixPath

from program_foundry_closure_io import equal, require, sibling  # ty: ignore[unresolved-import]


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
