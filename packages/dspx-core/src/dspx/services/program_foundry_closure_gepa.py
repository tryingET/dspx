"""Pure GEPA payload inventory, candidate and comparison closure joins."""

from __future__ import annotations

from pathlib import PurePosixPath

from program_foundry_closure_core import NONAUTH, candidate, origin, reference, runtime  # ty: ignore[unresolved-import]
from program_foundry_closure_io import (  # ty: ignore[unresolved-import]
    Snapshot,
    canonical,
    closed,
    digest,
    equal,
    require,
    sibling,
)


def optimizer(s: Snapshot, root: str) -> tuple[dict, str]:
    path = root + "/manifest.json"
    manifest = s.json(path)
    payload = manifest["output_payload"]
    closed(payload, {"hash_algorithm", "tree_hash", "files", "excludes"})
    equal(payload["hash_algorithm"], "sha256")
    equal(payload["excludes"], ["manifest.json"])
    rows = payload["files"]
    require(isinstance(rows, list) and 0 < len(rows) <= 64, "optimizer_payload")
    seen = set()
    for row in rows:
        closed(row, {"path", "sha256", "size_bytes"})
        local = row["path"]
        require(local not in seen and local != "manifest.json", "optimizer_duplicate")
        seen.add(local)
        raw = s.read(root + "/" + local, row["sha256"])
        equal(len(raw), row["size_bytes"])
    equal(rows, sorted(rows, key=lambda item: item["path"]), "optimizer_order")
    equal(payload["tree_hash"], digest(canonical(rows)), "optimizer_payload_hash")
    tree = [{"path": row["path"], "sha256": row["sha256"]} for row in rows]
    tree.append({"path": "manifest.json", "sha256": s.hash(path)})
    tree.sort(key=lambda item: item["path"])
    require({"program.pkl", "metadata.json"} <= seen, "optimizer_missing_payload")
    # No extra declared optimizer aliases may disappear from the committed inventory.
    declared = {
        x.removeprefix(root + "/") for x in s.aliases if x.startswith(root + "/")
    }
    equal(declared, seen | {"manifest.json"}, "optimizer_inventory_incomplete")
    return manifest, digest(canonical(tree))


def verify_gepa(s: Snapshot, state: dict, report: dict) -> dict:
    root, execution, proposal = state["root"], state["execution"], state["proposal"]
    eroot = root + "/gepa-experiment"
    result_path = eroot + "/gepa-result.json"
    result = s.json(result_path, execution["result_sha256"])
    equal(result["schema_version"], "program-refinement-gepa-result-v1")
    equal(result["gepa"]["status"], "completed")
    require(result["gepa"]["attempted"] is True, "gepa_not_attempted")
    manifest, tree_hash = optimizer(s, eroot + "/optimizer-output")
    equal(
        execution["optimizer_manifest_sha256"],
        s.hash(eroot + "/optimizer-output/manifest.json"),
    )
    equal(execution["optimizer_tree_sha256"], tree_hash)
    out = result["gepa_output"]
    equal(out["root_path"], eroot + "/optimizer-output")
    equal(out["manifest_sha256"], execution["optimizer_manifest_sha256"])
    equal(out["manifest_path"], eroot + "/optimizer-output/manifest.json")
    require(
        out["manifest_valid"] is True and out["manifest_present"] is True,
        "optimizer_invalid",
    )
    metric = proposal["gepa_plan"]["metric"]["optimizer_metric"]
    mh = execution.get("metric_honesty")
    if metric == "concept_coverage":
        closed(
            mh,
            {
                "metric",
                "criteria_sha256",
                "source_program_sha256",
                "wrapper_program_sha256",
            },
        )
        equal(mh["metric"], metric)
        equal(
            mh["source_program_sha256"],
            s.hash(sibling(state["source_path"], "program.py")),
        )
        equal(
            mh["criteria_sha256"],
            digest(canonical(state["imported"]["quality_criteria"])),
        )
        equal(manifest["metric_honesty"], mh)
        equal(result["gepa"]["concept_coverage_binding"]["metric_honesty"], mh)
        equal(manifest["program"]["sha256"], mh["wrapper_program_sha256"])
    else:
        require(mh is None, "unexpected_metric_honesty")
    # Manifest points to its source wrapper and dataset files; read only their mapped bytes.
    for ref in [manifest["program"], *manifest["dataset"].values()]:
        if isinstance(ref, dict) and "path" in ref and "sha256" in ref:
            s.read(ref["path"], ref["sha256"])
    attempt = s.json(eroot + "/attempt.json", execution["attempt_sha256"])
    equal(
        attempt["attempt_id"],
        digest(canonical({k: v for k, v in attempt.items() if k != "attempt_id"})),
    )
    equal(attempt["proposal_id"], proposal["proposal_id"])
    equal(attempt["proposal_sha256"], execution["proposal_sha256"])
    equal(attempt["schema_version"], "dspx-program-foundry-gepa-attempt-v1")
    require(
        attempt["no_replay_after_marker"] is True
        and attempt["gepa_invocation_possible"] is True,
        "gepa_attempt_boundary",
    )
    equal(attempt["non_authority"], NONAUTH)
    declaration = attempt["review_declaration"]
    equal(declaration["proposal_id"], proposal["proposal_id"])
    require(
        declaration["authenticated"] is False
        and declaration["identity_verified"] is False
        and declaration["approval_authority_asserted"] is False
        and declaration["execution_intent_only"] is True,
        "review_declaration_authority",
    )
    expected_execution = {
        "schema_version": "dspx-program-foundry-gepa-execution-v1",
        "status": "ok",
        "proposal_id": proposal["proposal_id"],
        "proposal_sha256": execution["proposal_sha256"],
        "attempt_sha256": s.hash(eroot + "/attempt.json"),
        "result_path": result_path,
        "result_sha256": s.hash(result_path),
        "gepa_status": "completed",
        "optimizer_output_readiness": out["readiness"],
        "optimizer_manifest_sha256": s.hash(eroot + "/optimizer-output/manifest.json"),
        "optimizer_tree_sha256": tree_hash,
        "effect": {
            "gepa_invoked": True,
            "terminal_result_recorded": True,
            "candidate_materialized": False,
            "winner_selected": False,
            "promotion_applied": False,
            "external_authority_mutated": False,
            "ak_called": False,
        },
        "non_authority": {"local_optimizer_evidence_only": True, **NONAUTH},
    }
    # Historic optional label is preserved as an assertion, never used to establish live.
    if "provider_evidence_kind" in execution:
        require(
            execution["provider_evidence_kind"]
            in {None, "live", "stub_echo", "authored_fixture_replay"},
            "invalid_evidence_label",
        )
        expected_execution["provider_evidence_kind"] = execution[
            "provider_evidence_kind"
        ]
    if mh is not None:
        expected_execution["metric_honesty"] = mh
    equal(execution, expected_execution, "execution_receipt_reconstruction")
    consumption = state["consumption"]
    cb = consumption["bindings"]
    names = {
        "source_manifest",
        "candidate_manifest",
        "candidate_result",
        "comparison",
        "workflow",
        "execution_receipt",
        "gepa_result",
    }
    closed(
        cb,
        {name + ending for name in names for ending in ("_path", "_sha256")}
        | {"consumption_attempt_sha256"},
    )
    for name in names:
        reference(s, cb, name)
    equal(cb["source_manifest_path"], state["source_path"])
    equal(cb["execution_receipt_path"], state["execution_path"])
    equal(cb["gepa_result_path"], result_path)
    s.json(eroot + "/consumption-attempt.json", cb["consumption_attempt_sha256"])
    cp = eroot + "/materialized-candidate/manifest.json"
    equal(cb["candidate_manifest_path"], cp)
    cm, _ = candidate(s, cp)
    candidate_result_path = eroot + "/candidate-result.json"
    cr = s.json(candidate_result_path, cb["candidate_result_sha256"])
    equal(cr["candidate"]["manifest_path"], cp)
    equal(cr["created_from"]["manifest_path"], state["source_path"])
    equal(cr["created_from"]["gepa_refinement_result_path"], result_path)
    copied_root = str(PurePosixPath(cp).parent) + "/gepa_optimizer_output"
    copied, _ = optimizer(s, copied_root)
    equal(copied, manifest, "optimizer_copy_mismatch")
    from program_foundry_closure_contracts import materialization  # ty: ignore[unresolved-import]

    materialization(
        s,
        cm,
        cp,
        state["source_path"],
        result_path,
        cr,
        copied,
        copied["output_payload"]["tree_hash"],
    )
    if mh is not None:
        equal(cr["gepa_output"]["metric_honesty"], mh)
    comparison_path = eroot + "/candidate-comparison.json"
    comparison = s.json(comparison_path, cb["comparison_sha256"])
    equal(comparison["schema_version"], "program-refinement-candidate-comparison-v1")
    equal(comparison["status"], "compared")
    created = comparison["created_from"]
    for label, mp in (("source", state["source_path"]), ("candidate", cp)):
        equal(created[label + "_manifest_path"], mp)
        equal(created[label + "_manifest_hash"], s.hash(mp))
        for role in ("behavior_episode", "behavior_results"):
            p = sibling(mp, role + ".json")
            equal(created[label + "_" + role + "_path"], p)
            equal(created[label + "_" + role + "_hash"], s.hash(p))
    equal(
        created["source_runtime_episode_path"], root + "/runtime/runtime_episode.json"
    )
    runtime_path = eroot + "/candidate-runtime/runtime_episode.json"
    equal(created["candidate_runtime_episode_path"], runtime_path)
    episode, _ = runtime(s, runtime_path, cp, state["inputs"])
    equal(
        created["source_runtime_episode_hash"],
        s.hash(created["source_runtime_episode_path"]),
    )
    equal(created["candidate_runtime_episode_hash"], s.hash(runtime_path))
    for label, mp in (("source", state["source_path"]), ("candidate", cp)):
        mb = s.json(mp)["receipt_bundle"]
        equal(
            comparison[label + "_identity"],
            {
                k: mb[k]
                for k in (
                    "candidate_id",
                    "assembly_id",
                    "receipt_bundle_id",
                    "episode_id",
                    "request_id",
                )
            },
        )
    workflow = s.json(
        eroot + "/materialize-and-compare-result.json", cb["workflow_sha256"]
    )
    from program_foundry_closure_comparison import verify_comparison  # ty: ignore[unresolved-import]

    jury_result = s.json(state["jury"]["bindings"]["jury_results_path"])
    verify_comparison(
        s,
        comparison,
        state["source_path"],
        cp,
        jury_result["jury"]["provider_config"]["owner_commit"],
    )
    equal(workflow["generation"], cr)
    equal(workflow["comparison_sidecar"]["path"], comparison_path)
    equal(workflow["comparison_sidecar"]["status"], comparison["status"])
    equal(
        consumption,
        {
            "schema_version": "dspx-program-foundry-gepa-consumption-v1",
            "status": "ok",
            "proposal_id": proposal["proposal_id"],
            "comparison_status": "compared",
            "bindings": cb,
            "effect": {
                "one_local_candidate_materialized": True,
                "local_comparison_recorded": True,
                "gepa_reexecuted": False,
                "winner_selected": False,
                "promotion_applied": False,
                "external_authority_mutated": False,
                "ak_called": False,
            },
            "non_authority": {
                "local_candidate_and_comparison_evidence_only": True,
                **NONAUTH,
            },
        },
        "consumption_reconstruction",
    )
    report["identities"].update(
        candidate_manifest_sha256=s.hash(cp), comparison_sha256=s.hash(comparison_path)
    )
    report["origins"]["candidate_runtime"] = origin(episode)
    report["origins"]["candidate_generated"] = origin(
        s.json(sibling(cp, "behavior_results.json"))
    )
    return {
        **state,
        "candidate_path": cp,
        "comparison_path": comparison_path,
        "comparison": comparison,
        "candidate": cm,
    }
