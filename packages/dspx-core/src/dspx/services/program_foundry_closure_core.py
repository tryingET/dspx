"""Pure captured-v1 source/runtime and accepted-intent joins."""

from __future__ import annotations

from pathlib import PurePosixPath
import json

from program_foundry_closure_io import (  # ty: ignore[unresolved-import]
    Snapshot,
    canonical,
    closed,
    digest,
    decode,
    equal,
    require,
    sha,
    sibling,
)
from program_foundry_closure_import import (  # ty: ignore[unresolved-import]
    intent,
    intent_hash,
    package_import,
    pretty,
    quality_binding,
    runtime_inputs,
)


NONAUTH = {
    "winner_selection": False,
    "promotion_authority": False,
    "activation_authority": False,
    "governance_authority": False,
}


def reference(s: Snapshot, block: dict, name: str) -> tuple[str, dict]:
    path = block[name + "_path"]
    return path, s.json(path, block[name + "_sha256"])


def meta(s: Snapshot, path: str, output: dict) -> dict:
    receipt = s.json(path + ".meta.json")
    require(
        {
            "receipt_version",
            "created_at",
            "run_kind",
            "provider",
            "output_path",
            "hash",
            "template_version",
            "cache_key",
            "cache_file",
            "cache_enabled",
            "replay_inputs",
        }
        <= set(receipt),
        "meta_required_fields",
    )
    require(type(receipt["cache_enabled"]) is bool, "meta_cache_enabled")
    equal(receipt["receipt_version"], "v2")
    equal(receipt["output_path"], path)
    equal(receipt["hash"], s.hash(path), "meta_output_hash")
    require(receipt["outcome"] == "success", "meta_outcome")
    replay = receipt["replay_inputs"]
    if receipt["run_kind"] == "program-gen":
        equal(intent(receipt["program_intent"]), intent(output["intent"]))
        equal(intent(replay["intent"]), intent(output["intent"]))
        equal(receipt["program_receipt_bundle"], output["receipt_bundle"])
        equal(receipt["program_candidate_assembly"], output["candidate_assembly"])
        payload = {"kind": "program", "intent": replay["intent"]}
    else:
        equal(receipt["run_kind"], "program-runtime")
        require(
            {
                "candidate_manifest_path",
                "candidate_manifest_sha256",
                "candidate_receipt_path",
                "candidate_receipt_sha256",
                "runtime_inputs_sha256",
                "replay_fixture_path",
                "replay_fixture_sha256",
                "contract_mode",
                "skip_oracle_index",
                "publication_preflight_requested",
                "expected_episode",
            }
            <= set(replay),
            "runtime_replay_required_fields",
        )
        require(receipt["cache_enabled"] is False, "runtime_cache_not_captured")
        payload = {"kind": "program-runtime", "replay_inputs": replay}
    cache_key = digest(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )
    equal(receipt["cache_key"], cache_key, "meta_cache_key")
    require(
        PurePosixPath(receipt["cache_file"]).name == cache_key + ".json",
        "meta_cache_path",
    )
    equal(
        PurePosixPath(receipt["cache_file"]).parent.name,
        payload["kind"],
        "meta_cache_kind",
    )
    policy = receipt["execution_replay"]
    equal(policy["schema_version"], "local-execution-replay-v2")
    equal(policy["input_hash"], digest(canonical(replay)), "replay_input_hash")
    equal(policy["output_identity"], {"algorithm": "sha256", "hash": s.hash(path)})
    provider = {
        "provider": receipt["provider"],
        "provider_details": receipt["provider_details"],
    }
    equal(
        policy["provider_identity"], {**provider, "hash": digest(canonical(provider))}
    )
    runtime_identity = policy["runtime_identity"]
    equal(
        runtime_identity["hash"],
        digest(canonical({k: v for k, v in runtime_identity.items() if k != "hash"})),
    )
    # Historical identity equality, never comparison with this interpreter or a cache read.
    return receipt


def candidate(s: Snapshot, path: str) -> tuple[dict, str]:
    manifest = s.json(path)
    equal(manifest["schema_version"], "program-candidate-assembly-v1")
    from program_foundry_closure_contracts import candidate_declarations  # ty: ignore[unresolved-import]

    candidate_declarations(s, path, manifest)
    declarations = manifest["candidate_assembly"]["surfaces"]
    require(
        isinstance(declarations, list) and 0 < len(declarations) <= 64,
        "candidate_surfaces",
    )
    seen_kinds, seen_paths, rows = set(), set(), []
    for row in declarations:
        kind, local, hashed = row["kind"], row.get("path"), row.get("content_hash")
        if local in (None, "") and hashed in (None, ""):
            continue
        require(kind not in seen_kinds and local not in seen_paths, "duplicate_surface")
        seen_kinds.add(kind)
        seen_paths.add(local)
        full = str(PurePosixPath(path).parent / local)
        require(
            PurePosixPath(full).is_relative_to(PurePosixPath(path).parent),
            "surface_escape",
        )
        s.read(full, sha(hashed))
        rows.append({"kind": kind, "path": full, "sha256": hashed})
    require(
        {"program.py", "behavior_results.json", "behavior_episode.json"} <= seen_paths,
        "missing_core_surfaces",
    )
    equal(
        intent(s.json(sibling(path, "intent.json"))),
        intent(manifest["intent"]),
        "source_intent_file",
    )
    equal(
        manifest["receipt_bundle"]["evidence"]["intent_hash"],
        intent_hash(manifest["intent"]),
        "source_intent_hash",
    )
    receipt = meta(s, path, manifest)
    evidence = manifest["receipt_bundle"]["evidence"]
    equal(
        evidence["surface_hashes"],
        {
            str(
                PurePosixPath(row["path"]).relative_to(PurePosixPath(path).parent)
            ): row["sha256"]
            for row in rows
        },
    )
    examples_path = sibling(path, "examples.json")
    examples = decode(s.read(examples_path, evidence["examples_hash"]))
    equal(examples, intent(manifest["intent"])["examples"])
    for role, local in {
        "plan": "plan",
        "jury_selection": "jury_selection",
        "jury_rubric": "jury_rubric",
        "behavior_results": "behavior_results",
        "behavior_episode": "behavior_episode",
        "execution_episode": "execution_episode",
        "module_surfaces": "module_surfaces",
        "runtime_outcomes": "program_runtime_outcomes",
        "runtime_traces": "program_runtime_traces",
        "tool_contracts": "program_tool_contracts",
        "capability_registry": "program_capability_registry",
        "generated_module_policy": "generated_module_policy",
        "intent_normalization": "intent_normalization",
        "oracle_evidence": "oracle_evidence",
        "promotion_review": "promotion_review",
        "promotion_adjudication_request": "promotion_adjudication_request",
        "promotion_decision_template": "promotion_decision_template",
    }.items():
        if role == "oracle_evidence" and evidence[role + "_hash"] is None:
            equal(manifest["oracle_evidence_artifact"], None)
            equal(receipt["program_oracle_evidence"], None)
            continue
        retained = s.json(sibling(path, local + ".json"), evidence[role + "_hash"])
        # Materialization refreshes the embedded execution episode, not the generated
        # episode file. Both are separately retained and hash-bound in existing v1.
        projected = (
            manifest["execution_episode"] if role == "execution_episode" else retained
        )
        equal(receipt["program_" + role], projected, "meta_embedded_surface_" + role)
    return manifest, digest(canonical(rows))


def origin(value: dict) -> str:
    provider = value.get("provider", {})
    if not isinstance(provider, dict):
        return "unknown"
    effect = provider.get("effect_evidence", {})
    if (
        isinstance(effect, dict)
        and effect.get("schema_version") == "dspx-provider-effect-evidence-v1"
    ):
        return "local_effect_record"
    fixture = value.get("replay_fixture_sha256")
    return "fixture_record" if isinstance(fixture, str) else "unknown"


def runtime(
    s: Snapshot, path: str, manifest_path: str, inputs: dict
) -> tuple[dict, dict]:
    episode = s.json(path)
    equal(episode["schema_version"], "program-runtime-episode-v1")
    equal(episode["candidate_manifest_path"], manifest_path, "runtime_manifest_path")
    equal(
        episode["artifact_hashes"]["source_manifest_sha256"],
        s.hash(manifest_path),
        "runtime_manifest_hash",
    )
    require(episode["execution_status"] == "executed", "runtime_not_executed")
    require(
        episode["status"]
        in {
            "executed_quality_passed",
            "failed_quality",
            "executed",
        },
        "runtime_status",
    )
    hashes = closed(
        episode["artifact_hashes"],
        {
            "source_manifest_sha256",
            "runtime_inputs_sha256",
            "behavior_results_sha256",
            "program_runtime_traces_sha256",
            "oracle_evidence_sha256",
        },
    )
    expected_inputs = pretty(runtime_inputs(inputs))
    equal(
        digest(expected_inputs), hashes["runtime_inputs_sha256"], "runtime_input_splice"
    )
    equal(
        s.read(sibling(path, "runtime_inputs.json"), hashes["runtime_inputs_sha256"]),
        expected_inputs,
    )
    for key in ("behavior_results", "program_runtime_traces", "oracle_evidence"):
        s.json(sibling(path, key + ".json"), hashes[key + "_sha256"])
    behavior = s.json(sibling(path, "behavior_results.json"))
    rmanifest = s.json(episode["manifest_path"])
    from program_foundry_closure_contracts import runtime_manifest  # ty: ignore[unresolved-import]

    runtime_manifest(s, path, manifest_path, episode, rmanifest, behavior)
    equal(
        rmanifest["source_candidate_manifest"],
        {"path": manifest_path, "sha256": s.hash(manifest_path)},
    )
    equal(intent(rmanifest["intent"]), intent(s.json(manifest_path)["intent"]))
    receipt = meta(s, path, episode)
    from program_foundry_closure_contracts import runtime_graph  # ty: ignore[unresolved-import]

    runtime_graph(s, path, manifest_path, episode, behavior, receipt)
    replay = receipt["replay_inputs"]
    equal(replay["candidate_manifest_path"], manifest_path)
    equal(replay["candidate_manifest_sha256"], s.hash(manifest_path))
    equal(replay["runtime_inputs_sha256"], hashes["runtime_inputs_sha256"])
    equal(replay["candidate_receipt_path"], manifest_path + ".meta.json")
    equal(replay["candidate_receipt_sha256"], s.hash(manifest_path + ".meta.json"))
    for name in ("behavior_results", "program_runtime_traces", "oracle_evidence"):
        equal(replay["expected_episode"][name + "_sha256"], hashes[name + "_sha256"])
    equal(replay["expected_episode"]["runtime_episode_sha256"], s.hash(path))
    outputs = behavior["examples"][0]["observed_outputs"]
    equal(
        replay["expected_episode"]["observed_outputs_sha256"],
        digest(canonical(outputs)),
    )
    equal(
        replay["expected_episode"]["quality_evaluation_sha256"],
        digest(canonical(behavior["quality_evaluation"])),
    )
    require(
        isinstance(episode["output_files"], list)
        and len(episode["output_files"]) <= 32,
        "runtime_outputs",
    )
    for name in episode["output_files"]:
        raw = s.read(sibling(path, name))
        require(name in outputs, "runtime_output_field")
        expected = (
            outputs[name]
            if isinstance(outputs[name], str)
            else json.dumps(outputs[name], ensure_ascii=False, indent=2, sort_keys=True)
        )
        equal(raw.decode("utf-8"), expected.rstrip() + "\n", "runtime_output_content")
    equal(
        episode["non_authority"],
        {
            "activation_authority": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "promotion_authority": False,
            "shared_oracle_mutated": False,
        },
    )
    return episode, behavior


def source_closure(s: Snapshot, report: dict) -> dict:
    imported, inputs = package_import(s)
    jpath, jury = s.expected("jury_receipt")
    jb = jury["bindings"]
    consumption_path, consumption = reference(s, jb, "consumption_receipt")
    execution_path, execution = reference(s, jb, "execution_receipt")
    root = str(PurePosixPath(execution_path).parent.parent)
    proposal_path = root + "/gepa_experiment_proposal.json"
    proposal = s.json(proposal_path, execution["proposal_sha256"])
    equal(proposal["schema_version"], "dspx-program-foundry-gepa-proposal-v1")
    equal(proposal["status"], "proposal_ready_for_review")
    equal(proposal["authority"], "local_advisory_experiment_proposal_only")
    equal(
        proposal["proposal_id"],
        digest(canonical({k: v for k, v in proposal.items() if k != "proposal_id"})),
    )
    for record in (jury, consumption, execution):
        equal(record["proposal_id"], proposal["proposal_id"], "proposal_id_mismatch")
    source_path = root + "/candidate/manifest.json"
    equal(jb["source_manifest_path"], source_path)
    source, closure_hash = candidate(s, source_path)
    equal(intent(source["intent"]), imported, "source_import_splice")
    cb = proposal["candidate_binding"]
    equal(cb["manifest_sha256"], s.hash(source_path))
    equal(cb["receipt_sha256"], s.hash(source_path + ".meta.json"))
    equal(cb["closure_sha256"], closure_hash, "candidate_closure_hash")
    accepted, quality_origin = quality_binding(
        s, cb["accepted_binding"]["quality_proposal_path"], imported
    )
    equal(cb["accepted_binding"], accepted, "accepted_binding_mismatch")
    report["quality"]["origin"] = quality_origin
    normalized = s.json(sibling(source_path, "intent_normalization.json"))
    equal(intent(normalized["normalized_intent"]), imported)
    equal(
        normalized["source"],
        {
            "path": s.request["expected"]["imported_intent"]["original_path"],
            "kind": "intent_file",
            "content_hash": s.request["expected"]["imported_intent"]["sha256"],
        },
        "normalization_import_splice",
    )
    runtime_path = root + "/runtime/runtime_episode.json"
    episode, behavior = runtime(s, runtime_path, source_path, inputs)
    rb = proposal["runtime_binding"]
    equal(rb["runtime_episode_sha256"], s.hash(runtime_path))
    equal(rb["runtime_receipt_sha256"], s.hash(runtime_path + ".meta.json"))
    equal(rb["artifact_hashes"], episode["artifact_hashes"])
    report["origins"]["source_runtime"] = origin(episode)
    report["origins"]["source_generated"] = origin(
        s.json(sibling(source_path, "behavior_results.json"))
    )
    semantic_path = root + "/runtime/program_oracle_semantic.json"
    semantic = s.json(semantic_path, proposal["semantic_binding"]["sha256"])
    equal(semantic["schema_version"], "program-runtime-oracle-semantic-v1")
    equal(semantic["source_binding"], proposal["semantic_binding"]["source_binding"])
    expected_bindings = {}
    for role, name in {
        "runtime_episode": "runtime_episode.json",
        "runtime_receipt": "runtime_episode.json.meta.json",
        "behavior_results": "behavior_results.json",
        "oracle_evidence": "oracle_evidence.json",
    }.items():
        path = sibling(runtime_path, name)
        expected_bindings[role] = {"path": path, "sha256": s.hash(path)}
    equal(semantic["source_binding"], expected_bindings, "oracle_source_splice")
    sr = semantic["semantic_result"]
    equal(sr["request_sha256"], semantic["request_sha256"])
    equal(sr["request_sha256"], proposal["semantic_binding"]["request_sha256"])
    equal(
        digest(canonical(sr["analysis"])),
        proposal["semantic_binding"]["analysis_sha256"],
    )
    selection = proposal["selection"]
    index = selection["recommended_experiment_index"]
    require(
        type(index) is int
        and 0 <= index < len(sr["analysis"]["recommended_experiments"]),
        "oracle_selection",
    )
    text = sr["analysis"]["recommended_experiments"][index]
    equal(text, selection["recommended_experiment_text"])
    equal(digest(text.encode()), selection["recommended_experiment_sha256"])
    report["origins"]["oracle"] = (
        "fixture_record" if sr["backend_kind"] == "fixture-replay" else "unknown"
    )
    workflow = s.json(root + "/foundry.json")
    equal(workflow["schema_version"], "dspx-program-foundry-workflow-v1")
    equal(workflow["foundry_root"], root)
    equal(workflow["workflow_path"], root + "/foundry.json")
    equal(
        workflow["intent_path"],
        s.request["expected"]["imported_intent"]["original_path"],
    )
    equal(
        workflow["inputs_path"],
        s.request["expected"]["imported_inputs"]["original_path"],
    )
    identity = {
        k: source["receipt_bundle"][k]
        for k in ("candidate_id", "assembly_id", "episode_id", "receipt_bundle_id")
    }
    equal(
        workflow["bindings"],
        {
            "accepted_intent_sha256": accepted["program_intent_sha256"],
            "candidate_identity": identity,
            "candidate_manifest_sha256": s.hash(source_path),
            "runtime_artifact_hashes": episode["artifact_hashes"],
            "runtime_episode_id": episode["runtime_episode_id"],
            "semantic_request_sha256": semantic["request_sha256"],
            "semantic_source_binding": semantic["source_binding"],
        },
    )
    stages = workflow["stages"]
    equal(stages["accepted_intent"], {"status": "accepted", "binding": accepted})
    equal(stages["candidate"]["closure_sha256"], closure_hash)
    for name, stage, path in (
        ("manifest", "candidate", source_path),
        ("receipt", "candidate", source_path + ".meta.json"),
        ("runtime_episode", "runtime", runtime_path),
        ("runtime_receipt", "runtime", runtime_path + ".meta.json"),
    ):
        equal(stages[stage][name + "_path"], path)
        equal(stages[stage][name + "_sha256"], s.hash(path))
    equal(stages["candidate"]["identity"], identity)
    equal(stages["runtime"]["artifact_hashes"], episode["artifact_hashes"])
    equal(stages["oracle_semantic"]["request_sha256"], semantic["request_sha256"])
    equal(stages["oracle_semantic"]["path"], semantic_path)
    equal(stages["gepa_experiment_proposal"]["path"], proposal_path)
    equal(stages["gepa_experiment_proposal"]["proposal_id"], proposal["proposal_id"])
    report["identities"].update(
        {
            "program_intent_sha256": accepted["program_intent_sha256"],
            "normalized_runtime_inputs_sha256": digest(pretty(runtime_inputs(inputs))),
            "source_manifest_sha256": s.hash(source_path),
            "consumption_receipt_sha256": s.hash(consumption_path),
        }
    )
    return dict(
        jpath=jpath,
        jury=jury,
        proposal=proposal,
        root=root,
        inputs=inputs,
        imported=imported,
        source=source,
        source_path=source_path,
        execution=execution,
        execution_path=execution_path,
        consumption=consumption,
        consumption_path=consumption_path,
    )
