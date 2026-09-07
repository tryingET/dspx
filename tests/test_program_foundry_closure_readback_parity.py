"""Readback inventory: provider/receipt contracts and GEPA/comparison base gates."""

import copy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_program_foundry_closure_runtime_graph as graph

pure = graph.pure
saved = graph.saved


@pytest.mark.parametrize("runtime", ["runtime", "gepa-experiment/candidate-runtime"])
@pytest.mark.parametrize(
    "target,field,value,reason",
    [
        ("episode", "runtime_episode_id", "other", "runtime_identity"),
        ("receipt", "replay_inputs.contract_mode", "other", "runtime_replay_mode"),
        (
            "receipt",
            "replay_inputs.expected_episode.runtime_episode_id",
            "other",
            "runtime_replay_runtime_episode_id",
        ),
        (
            "receipt",
            "replay_inputs.expected_episode.status",
            "other",
            "runtime_replay_status",
        ),
        (
            "receipt",
            "replay_inputs.expected_episode.quality_status",
            "other",
            "runtime_replay_quality_status",
        ),
        (
            "receipt",
            "run_summary.runtime_status",
            "other",
            "runtime_receipt_summary_runtime_status",
        ),
        (
            "receipt",
            "run_summary.runtime_episode_id",
            "other",
            "runtime_receipt_summary_runtime_episode_id",
        ),
        (
            "receipt",
            "run_summary.behavior_results_sha256",
            "0" * 64,
            "runtime_receipt_summary_behavior_results_sha256",
        ),
        (
            "receipt",
            "run_summary.evidence_only",
            False,
            "runtime_receipt_summary_evidence_only",
        ),
        (
            "receipt",
            "run_summary.provider.metadata.model",
            "other",
            "runtime_receipt_provider",
        ),
        ("receipt", "provider_details.model", "other", "runtime_provider_details"),
        ("receipt", "provider", "other", "runtime_provider_identity"),
    ],
)
def test_direct_runtime_dependency_contract(
    saved, pure, runtime, target, field, value, reason
):
    _, request = saved
    _, alias = graph.runtime_paths(request, runtime)
    s = pure.Snapshot(request)
    try:
        episode = copy.deepcopy(s.json(alias))
        receipt = copy.deepcopy(s.json(alias + ".meta.json"))
        behavior = s.json(str(Path(alias).parent / "behavior_results.json"))
        source = episode["candidate_manifest_path"]
        graph.set_field(episode if target == "episode" else receipt, field, value)
        with pytest.raises(pure.Rejected, match="^" + reason + "$"):
            importlib.import_module("program_foundry_closure_contracts").runtime_graph(
                s, alias, source, episode, behavior, receipt
            )
    finally:
        s.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "unavailable"),
        ("metadata.provider", "other"),
        ("metadata.model", "with spaces"),
        ("metadata.model", "x" * 257),
        ("metadata.model_type", "chat"),
        ("metadata.typed_contract", "other"),
        ("metadata.capabilities.supports_tools", True),
        ("metadata.runtime.provider_kind", "other"),
        ("metadata.runtime.base_endpoint", "http://localhost/v1"),
        ("metadata.runtime.base_endpoint", "http://127.0.0.1/v1/../other"),
        ("metadata.runtime.base_endpoint", "http://127.0.0.1/v1/chat/completions"),
        ("metadata.runtime.effective_timeout", 0),
        ("effect_evidence.schema_version", "other"),
        ("effect_evidence.attempt_total", True),
        ("effect_evidence.attempt_total", 0),
        ("effect_evidence.attempts_truncated", True),
        ("effect_evidence.terminal_effect", None),
        ("effect_evidence.attempts.0.provider_kind", "other"),
        ("effect_evidence.attempts.0.requested_model", "other"),
        ("effect_evidence.attempts.0.observed_model", None),
        ("effect_evidence.attempts.0.dispatch_count", 0),
        ("effect_evidence.attempts.0.effect_disposition", "other"),
    ],
)
def test_runtime_provider_mutants_differential(saved, pure, field, value):
    from dspx.services.program_runtime_episode import _validate_provider_evidence

    root, _ = saved
    provider = json.loads((root / "foundry/runtime/runtime_episode.json").read_bytes())[
        "provider"
    ]
    graph.set_field(provider, field, value)
    # This is the local-runtime effect contract, NOT the reviewed auth jury's
    # non-strict model projection (tested separately below).
    with pytest.raises((ValueError, TypeError, KeyError)):
        _validate_provider_evidence(provider)
    with pytest.raises((pure.Rejected, ValueError, TypeError, KeyError)):
        importlib.import_module("program_foundry_closure_runtime").provider(provider)


def test_unknown_observed_jury_model_is_not_requested_model():
    from dspx.services.program_foundry_gepa_comparison_jury_provider_custody import (
        observed_model_of,
    )

    completed = SimpleNamespace(terminal="provider_response_completed")
    for requested in ("alias", "local/prefixed/model"):
        journal = SimpleNamespace(
            events=[
                SimpleNamespace(
                    event=SimpleNamespace(
                        observed_model=None, requested_model=requested
                    )
                )
            ]
        )
        assert observed_model_of(journal, completed) is None


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("source_identity.candidate_id", "other", "gepa_result_identity"),
        ("candidate", {}, "gepa_result_candidate"),
        ("status", "gepa_output_unverified", "gepa_result_status"),
        ("effect.source_program_files_mutated", True, "gepa_result_effect"),
        ("non_authority.local_refinement_only", False, "gepa_result_non_authority"),
        ("non_authority.winner_selection", True, "gepa_result_non_authority"),
        (
            "gepa_output.readiness.ready_for_future_candidate_materializer",
            False,
            "gepa_result_readiness",
        ),
        ("gepa_output.readiness.status", "other", "gepa_result_readiness"),
    ],
)
def test_gepa_base_readback_mutants(saved, pure, field, value, reason):
    from dspx.services.program_refinement_gepa_candidate_contracts import (
        validate_program_refinement_gepa_result_contract,
    )

    root, _ = saved
    result = json.loads(
        (root / "foundry/gepa-experiment/gepa-result.json").read_bytes()
    )
    identity = copy.deepcopy(result["source_identity"])
    graph.set_field(result, field, value)
    if not field.endswith("ready_for_future_candidate_materializer"):
        with pytest.raises(ValueError):
            validate_program_refinement_gepa_result_contract(
                result, expected_identities=[identity]
            )
    # A complete materialized closure additionally requires readiness, unlike an
    # unconsumed non-ready proposal. This is an intentional stricter prerequisite.
    with pytest.raises(pure.Rejected, match="^" + reason + "$"):
        importlib.import_module("program_foundry_closure_contracts").gepa_result(
            result, identity
        )


@pytest.mark.parametrize(
    "section,field",
    [
        ("effect", "local_comparison_only"),
        ("effect", "source_program_files_mutated"),
        ("effect", "new_candidate_generated"),
        ("non_authority", "local_comparison_only"),
        ("non_authority", "oracle_ranking"),
        ("non_authority", "winner_selection"),
    ],
)
def test_comparison_non_authority_before_summaries(saved, pure, section, field):
    root, request = saved
    comparison = json.loads(
        (root / "foundry/gepa-experiment/candidate-comparison.json").read_bytes()
    )
    comparison[section][field] = field != "local_comparison_only"
    s = pure.Snapshot(request)
    try:
        with pytest.raises(pure.Rejected, match="^comparison_" + section + "$"):
            importlib.import_module(
                "program_foundry_closure_comparison"
            ).verify_comparison(
                s,
                comparison,
                comparison["created_from"]["source_manifest_path"],
                comparison["created_from"]["candidate_manifest_path"],
                "80cc409da976028263da884ed633bef0806cd986",
            )
    finally:
        s.close()
