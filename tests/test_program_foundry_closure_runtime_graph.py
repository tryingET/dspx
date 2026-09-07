"""Residual HOLD: direct reanchored runtime capsules versus immutable outer roots."""

import copy
import importlib
import json
from pathlib import Path

import pytest
import test_program_foundry_closure_semantics as shared

pure = shared.pure
saved = shared.saved


def runtime_paths(request, runtime):
    relative = "foundry/" + runtime + "/runtime_episode.json"
    alias = next(x["aliases"][0] for x in request["locators"] if x["path"] == relative)
    return relative, alias


def repair_runtime_capsule(root, request, runtime, pure):
    """Reanchor local hashes only; never claim these are the historical root bytes."""
    relative, alias = runtime_paths(request, runtime)
    prefix = str(Path(relative).parent) + "/"
    episode = json.loads((root / relative).read_bytes())
    hashes = episode["artifact_hashes"]
    for name in (
        "runtime_inputs",
        "behavior_results",
        "program_runtime_traces",
        "oracle_evidence",
    ):
        hashes[name + "_sha256"] = pure.digest(
            (root / (prefix + name + ".json")).read_bytes()
        )
    shared.change(root, request, relative, lambda p: p.update(artifact_hashes=hashes))
    episode_hash = pure.digest((root / relative).read_bytes())
    shared.change(
        root,
        request,
        prefix + "manifest.json",
        lambda p: p["runtime_episode"].update(
            behavior_results_sha256=hashes["behavior_results_sha256"]
        ),
    )
    behavior = json.loads((root / (prefix + "behavior_results.json")).read_bytes())

    def receipt(p):
        p["hash"] = episode_hash
        p["execution_replay"]["output_identity"]["hash"] = episode_hash
        expected = p["replay_inputs"]["expected_episode"]
        for name in ("behavior_results", "program_runtime_traces", "oracle_evidence"):
            expected[name + "_sha256"] = hashes[name + "_sha256"]
            p["run_summary"][name + "_sha256"] = hashes[name + "_sha256"]
        expected["runtime_episode_sha256"] = episode_hash
        expected["quality_evaluation_sha256"] = pure.digest(
            pure.canonical(behavior["quality_evaluation"])
        )
        expected["observed_outputs_sha256"] = pure.digest(
            pure.canonical(behavior["examples"][0]["observed_outputs"])
        )
        replay = p["replay_inputs"]
        p["execution_replay"]["input_hash"] = pure.digest(pure.canonical(replay))
        key = pure.digest(
            json.dumps(
                {"kind": "program-runtime", "replay_inputs": replay},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
        p["cache_key"] = key
        p["cache_file"] = str(Path(p["cache_file"]).parent / (key + ".json"))

    shared.change(root, request, relative + ".meta.json", receipt)
    return alias, episode["candidate_manifest_path"]


@pytest.mark.parametrize("runtime", ["runtime", "gepa-experiment/candidate-runtime"])
def test_rehashed_trace_source_hash_semantic_repro(saved, pure, tmp_path, runtime):
    root, request = shared.copied(saved, tmp_path)
    anchors = copy.deepcopy((request["subject"], request["expected"]))
    shared.change(
        root,
        request,
        "foundry/" + runtime + "/program_runtime_traces.json",
        lambda p: p["sources"][0].update(content_hash="0" * 64),
    )
    alias, manifest = repair_runtime_capsule(root, request, runtime, pure)
    core = importlib.import_module("program_foundry_closure_core")
    s = pure.Snapshot(request)
    try:
        inputs = s.json(str(Path(alias).parent / "runtime_inputs.json"))
        with pytest.raises(pure.Rejected, match="runtime_trace"):
            core.runtime(s, alias, manifest, inputs)
    finally:
        s.close()
    report = shared.rejected(request)
    assert report["reason_codes"][0].startswith("runtime_trace"), report
    assert (request["subject"], request["expected"]) == anchors


# Each row names an independent readback dependency, not an opaque outer hash.
MUTANTS = [
    ("oracle_evidence", key, "wrong", "runtime_oracle_" + key.split(".")[0])
    for key in (
        "schema_version",
        "evidence_kind",
        "authority",
        "identity.candidate_id",
        "identity.runtime_episode_id",
        "source_artifacts.0.content_hash",
        "source_artifacts.1.content_hash",
        "source_artifacts.2.content_hash",
        "source_artifacts.0.path",
        "source_artifacts.1.path",
        "source_artifacts.2.path",
        "behavior.result_path",
        "behavior.result_hash",
        "behavior.summary.status",
        "behavior.statuses",
        "oracle_facets.behavior_status",
        "oracle_facets.status_counts",
        "oracle_facets.runtime_episode_id",
        "oracle_facets.contract_mode",
        "behavior.evaluation_sources.0.input_artifact_hash",
        "behavior.evidence_summary",
        "runtime_traces.content_hash",
        "runtime_traces.coverage.status",
        "oracle_text",
        "intent.objective",
        "io.outputs",
    )
] + [
    (
        "oracle_evidence",
        "non_authority.oracle_ranking",
        True,
        "runtime_oracle_non_authority",
    ),
    ("oracle_evidence", "source_artifacts", [], "runtime_oracle_source_artifacts"),
    ("program_runtime_traces", "schema_version", "wrong", "runtime_trace_contract"),
    ("program_runtime_traces", "sources.0.record_count", 2**50, "runtime_trace_source"),
    (
        "program_runtime_traces",
        "module_calls.0.effects.network",
        True,
        "runtime_trace_contract",
    ),
    (
        "program_runtime_traces",
        "module_calls.0.inputs",
        {},
        "runtime_trace_reconstruction",
    ),
    (
        "program_runtime_traces",
        "module_calls.0.trajectory_slots.tool_calls_executed",
        True,
        "runtime_trace_contract",
    ),
    (
        "program_runtime_traces",
        "module_calls.0.scheduler_events.0.status",
        "wrong",
        "runtime_trace_contract",
    ),
    (
        "program_runtime_traces",
        "module_calls.0.non_authority.winner_selection",
        True,
        "runtime_trace_contract",
    ),
    (
        "program_runtime_traces",
        "final_outputs.0.outputs",
        {"answer": "substituted"},
        "runtime_trace_reconstruction",
    ),
    ("program_runtime_traces", "coverage.status", "partial", "runtime_trace_contract"),
    (
        "program_runtime_traces",
        "source_record_coverage.0.records_with_final_outputs",
        [],
        "runtime_trace_contract",
    ),
    (
        "program_runtime_traces",
        "runtime_policy.tool_execution_allowed",
        True,
        "runtime_trace_contract",
    ),
    ("behavior_results", "examples.0.inputs", {}, "runtime_behavior_inputs"),
    ("behavior_results", "input_fields", [], "runtime_behavior_input_fields"),
    ("behavior_results", "output_fields", [], "runtime_behavior_output_fields"),
    (
        "behavior_results",
        "quality_evaluation.quality_approved",
        True,
        "runtime_quality_evaluation",
    ),
    (
        "behavior_results",
        "examples.0.quality_evaluation.criteria_passed",
        0,
        "runtime_record_quality_evaluation",
    ),
    ("behavior_results", "examples.0.status", "passed", "runtime_record_status"),
    ("behavior_results", "summary.passed", 0, "runtime_behavior_summary"),
    (
        "behavior_results",
        "non_authority.winner_selection",
        True,
        "runtime_behavior_non_authority",
    ),
]


def set_field(payload, field, value):
    keys = [int(k) if k.isdecimal() else k for k in field.split(".")]
    for key in keys[:-1]:
        payload = payload[key]
    payload[keys[-1]] = value


@pytest.mark.parametrize("runtime", ["runtime", "gepa-experiment/candidate-runtime"])
@pytest.mark.parametrize("artifact,field,value,reason", MUTANTS)
def test_runtime_semantic_check_inventory(
    saved, pure, tmp_path, runtime, artifact, field, value, reason
):
    root, request = shared.copied(saved, tmp_path)
    anchors = copy.deepcopy((request["subject"], request["expected"]))

    def mutate(payload):
        set_field(payload, field, value)
        if artifact == "program_runtime_traces":
            for key in ("module_calls", "final_outputs"):
                for record in payload[key]:
                    record["trace_hash"] = pure.digest(
                        pure.canonical(
                            {k: v for k, v in record.items() if k != "trace_hash"}
                        )
                    )
                payload["trace_hashes"][key] = [r["trace_hash"] for r in payload[key]]

    shared.change(
        root, request, "foundry/" + runtime + "/" + artifact + ".json", mutate
    )
    alias, manifest = repair_runtime_capsule(root, request, runtime, pure)
    s = pure.Snapshot(request)
    try:
        inputs = s.json(str(Path(alias).parent / "runtime_inputs.json"))
        with pytest.raises(pure.Rejected, match="^" + reason + "$"):
            importlib.import_module("program_foundry_closure_core").runtime(
                s, alias, manifest, inputs
            )
    finally:
        s.close()
    report = shared.rejected(request)
    assert report["reason_codes"] == [reason], report
    assert (request["subject"], request["expected"]) == anchors


@pytest.mark.parametrize("runtime", ["runtime", "gepa-experiment/candidate-runtime"])
def test_reanchored_local_positive_is_not_original_root_proof(
    saved, pure, tmp_path, runtime
):
    root, request = shared.copied(saved, tmp_path)
    anchors = copy.deepcopy((request["subject"], request["expected"]))
    relative, _ = runtime_paths(request, runtime)
    shared.change(
        root,
        request,
        relative,
        lambda p: p.update(
            fixture_annotation="reanchored local positive, not historical root"
        ),
    )
    alias, manifest = repair_runtime_capsule(root, request, runtime, pure)
    s = pure.Snapshot(request)
    try:
        inputs = s.json(str(Path(alias).parent / "runtime_inputs.json"))
        episode, _ = importlib.import_module("program_foundry_closure_core").runtime(
            s, alias, manifest, inputs
        )
        assert "fixture_annotation" in episode
    finally:
        s.close()
    # This validates ONLY the internally consistent fixture capsule above. It
    # cannot pass the unchanged historical jury/proposal/comparison anchors.
    shared.rejected(request)
    assert (request["subject"], request["expected"]) == anchors


def test_oracle_reducers_match_complete_current_producer_ast(pure):
    import ast
    import inspect
    from dspx.services import program_runtime_episode as producer

    reducers = importlib.import_module("program_foundry_closure_runtime")
    for name in ("_safe_mapping", "_runtime_trace_summary", "_oracle_evidence"):
        assert ast.dump(
            ast.parse(inspect.getsource(getattr(reducers, name)))
        ) == ast.dump(ast.parse(inspect.getsource(getattr(producer, name))))
