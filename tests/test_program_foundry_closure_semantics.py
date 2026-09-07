"""HOLD regressions: semantic contradictions, immutable roots, and shared reducers."""

import copy
import importlib
import json
from pathlib import Path

import pytest
import test_program_foundry_closure_check as shared

pure = shared.pure
saved = shared.saved


def change(root, request, relative, mutate):
    row = next(x for x in request["locators"] if x["path"] == relative)
    old = row["sha256"]
    path = root / relative
    payload = json.loads(path.read_bytes())
    mutate(payload)
    raw = (
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2).encode()
        + b"\n"
    )
    path.write_bytes(raw)
    row.update(bytes=len(raw), sha256=shared.hashlib.sha256(raw).hexdigest())
    return old, row["sha256"]


def copied(saved, tmp_path):
    import shutil

    source, request = saved
    root = tmp_path / "mutant"
    request = copy.deepcopy(request)
    for row in request["locators"]:
        target = root / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / row["path"], target)
    request["roots"] = [str(root)]
    return root, request


def rejected(request):
    result = shared.invoke(json.dumps(request).encode())
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "invalid", report
    assert report["review_eligible"] is False
    return report


@pytest.mark.parametrize("runtime", ["runtime", "gepa-experiment/candidate-runtime"])
@pytest.mark.parametrize(
    "field",
    [
        "strip",
        "schema_version",
        "candidate_identity",
        "runtime_episode_id",
        "contract_mode",
        "inputs_path",
        "behavior_results_path",
        "inputs_sha256",
        "behavior_results_sha256",
    ],
)
def test_capsule_runtime_manifest_rehashed_contradictions(
    saved, tmp_path, runtime, field
):
    root, request = copied(saved, tmp_path)
    expected = copy.deepcopy(request["expected"])
    subject = copy.deepcopy(request["subject"])

    def mutate(payload):
        if field == "strip":
            keep = {
                key: payload[key] for key in ("intent", "source_candidate_manifest")
            }
            payload.clear()
            payload.update(keep)
        elif field == "schema_version":
            payload[field] = "wrong"
        elif field == "candidate_identity":
            payload["candidate_assembly"]["candidate_id"] = "wrong"
        else:
            payload["runtime_episode"][field] = "wrong"

    change(root, request, "foundry/" + runtime + "/manifest.json", mutate)
    report = rejected(request)
    assert report["reason_codes"][0].startswith("runtime_"), report
    assert request["expected"] == expected and request["subject"] == subject


@pytest.mark.parametrize(
    "field",
    [
        "strip",
        "status",
        "source_identity",
        "source_manifest_sha256",
        "gepa_refinement_result_sha256",
        "gepa_optimizer_manifest_sha256",
        "gepa_optimizer_payload_tree_sha256",
        "gepa_optimizer_payload_file_count",
        "metric_honesty",
        "non_authority",
    ],
)
def test_materialization_inner_contract_and_transitive_capsule_mutant(
    saved, pure, tmp_path, field
):
    root, request = copied(saved, tmp_path)
    prefix = "foundry/gepa-experiment/"
    cp = prefix + "materialized-candidate/manifest.json"
    anchors = copy.deepcopy(request["expected"])
    source_path = next(
        x["aliases"][0]
        for x in request["locators"]
        if x["path"] == "foundry/candidate/manifest.json"
    )
    candidate_path = next(
        x["aliases"][0] for x in request["locators"] if x["path"] == cp
    )
    result_path = next(
        x["aliases"][0]
        for x in request["locators"]
        if x["path"] == prefix + "gepa-result.json"
    )

    def mutate(payload):
        lineage = payload["gepa_refinement"]
        if field == "strip":
            payload.pop("gepa_refinement")
        elif field == "non_authority":
            lineage[field]["winner_selection"] = True
        elif field == "source_identity":
            lineage[field]["candidate_id"] = "other"
        elif field == "metric_honesty":
            lineage[field]["source_program_sha256"] = "0" * 64
        else:
            lineage[field] = 99 if field.endswith("count") else "wrong"

    old, new = change(root, request, cp, mutate)
    contracts = importlib.import_module("program_foundry_closure_contracts")
    s = pure.Snapshot(request)
    try:
        candidate = s.json(candidate_path)
        generation = s.json(str(Path(result_path).parent / "candidate-result.json"))
        optimizer = s.json(
            str(Path(candidate_path).parent / "gepa_optimizer_output/manifest.json")
        )
        with pytest.raises(pure.Rejected, match="materialization_"):
            contracts.materialization(
                s,
                candidate,
                candidate_path,
                source_path,
                result_path,
                generation,
                optimizer,
                optimizer["output_payload"]["tree_hash"],
            )
    finally:
        s.close()
    # Update a real two-hop reference chain, NOT unknown keys. Terminal expected
    # roots remain immutable: the capsule must reject, not accept a repaired hash leaf.
    replacements = {old: new}
    for relative in (
        prefix + "candidate-comparison.json",
        prefix + "materialize-and-compare-result.json",
        prefix + "consumption-receipt.json",
    ):

        def rehash(payload):
            raw = json.dumps(payload)
            for before, after in replacements.items():
                raw = raw.replace(before, after)
            payload.clear()
            payload.update(json.loads(raw))

        before, after = change(root, request, relative, rehash)
        replacements[before] = after
    rejected(request)
    assert request["expected"] == anchors


@pytest.mark.parametrize(
    "field", ["behavior_comparison", "runtime_evidence_comparison", "interpretation"]
)
def test_comparison_reconstruction_not_just_leaf_hashes(saved, pure, tmp_path, field):
    root, request = copied(saved, tmp_path)
    prefix = "foundry/gepa-experiment/"
    anchors = copy.deepcopy(request["expected"])
    module = importlib.import_module("program_foundry_closure_comparison")
    path = prefix + "candidate-comparison.json"

    def mutate(payload):
        if field == "interpretation":
            payload[field]["improvement_observed"] = True
        else:
            payload[field]["delta"]["failed_count_delta"] = -42

    old, new = change(root, request, path, mutate)
    s = pure.Snapshot(request)
    try:
        alias = next(x["aliases"][0] for x in request["locators"] if x["path"] == path)
        comparison = s.json(alias)
        with pytest.raises(pure.Rejected, match="comparison_semantics_mismatch"):
            module.verify_comparison(
                s,
                comparison,
                comparison["created_from"]["source_manifest_path"],
                comparison["created_from"]["candidate_manifest_path"],
                "80cc409da976028263da884ed633bef0806cd986",
            )
    finally:
        s.close()
    for relative in (
        prefix + "materialize-and-compare-result.json",
        prefix + "consumption-receipt.json",
    ):

        def rehash(payload):
            changed = json.loads(json.dumps(payload).replace(old, new))
            payload.clear()
            payload.update(changed)

        change(root, request, relative, rehash)
    rejected(request)
    assert request["expected"] == anchors


def test_legacy777_deterministic_projection_golden(saved, pure):
    module = importlib.import_module("program_foundry_closure_comparison")
    root, _ = saved
    paths = [
        root / "foundry/candidate",
        root / "foundry/gepa-experiment/materialized-candidate",
    ]
    runtimes = [
        root / "foundry/runtime",
        root / "foundry/gepa-experiment/candidate-runtime",
    ]

    def load(path):
        return json.loads(path.read_bytes())

    result = module.view(
        [load(p / "manifest.json") for p in paths],
        [load(p / "behavior_results.json") for p in paths],
        [load(p / "behavior_episode.json") for p in paths],
        [load(p / "runtime_episode.json") for p in runtimes],
        [load(p / "behavior_results.json") for p in runtimes],
        "unlabelled_exact",
    )
    # Frozen from the retained 777388a imported-vLLM comparison, not this reducer.
    assert (
        pure.digest(pure.canonical(result["interpretation"]))
        == "b9c2c1d6837274543c4f6d1888ce2e67f5bddf436087eafea9d93177847ee7c7"
    )
    assert result["behavior_comparison"]["source"]["failure_signals"] == [
        "mismatch:answer"
    ]


def test_producer_uses_shared_reducers_and_frozen_outputs(saved, pure):
    from dspx.services import program_refinement_comparison as producer
    from dspx.services import program_foundry_closure_reducers as reducers

    assert producer._behavior_summary is reducers._behavior_summary
    assert producer._behavior_delta is reducers._behavior_delta
    assert producer._interpretation is reducers._interpretation
    root, _ = saved
    manifest = json.loads((root / "foundry/candidate/manifest.json").read_bytes())
    behavior = json.loads(
        (root / "foundry/candidate/behavior_results.json").read_bytes()
    )
    episode = json.loads(
        (root / "foundry/candidate/behavior_episode.json").read_bytes()
    )
    comparison = json.loads(
        (root / "foundry/gepa-experiment/candidate-comparison.json").read_bytes()
    )
    summary = producer._behavior_summary(
        manifest=manifest, behavior=behavior, behavior_episode=episode
    )
    assert summary == comparison["behavior_comparison"]["source"]
    for status in ("passed", "failed", "error", "degraded_mock"):
        altered = copy.deepcopy(summary)
        altered["status_counts"] = {status: 4}
        expected = reducers._behavior_delta(summary, altered)
        assert expected["failed_count_delta"] == (4 if status == "failed" else 0)
        assert expected["error_count_delta"] == (4 if status == "error" else 0)
        assert expected["degraded_count_delta"] == (
            4 if status == "degraded_mock" else 0
        )
