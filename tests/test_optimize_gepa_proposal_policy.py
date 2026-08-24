# summary: "Tests bounded GEPA 0.1.4 proposal policy and receipt summaries."
# read_when:
#   - "Changing proposal strategies, GEPA budget validation, or bounded run statistics."

from __future__ import annotations

import hashlib
import json

from types import SimpleNamespace
from typing import cast

import pytest
from dspy import LMTransportError

from dspx.services.gepa_proposal_policy import (
    GEPAProposalConfig,
    TerminalGEPAReflectionLM,
    compile_with_terminal_reflection_effects,
    detach_gepa_run_stats,
    validate_gepa_budget,
    validate_num_threads,
)


@pytest.mark.parametrize(
    ("config", "sampling_type", "selection_type", "task_count"),
    [
        (
            GEPAProposalConfig(),
            "SingleMutationSampling",
            "AllImprovements",
            1,
        ),
        (
            GEPAProposalConfig(
                sampling="same-parent",
                proposal_n=3,
                selection="best-improvement",
            ),
            "SameParentSampling",
            "BestImprovement",
            3,
        ),
        (
            GEPAProposalConfig(
                sampling="independent",
                proposal_n=2,
                selection="top-k-improvements",
                top_k=2,
                acceptance="improvement-or-equal",
            ),
            "IndependentSampling",
            "TopKImprovements",
            2,
        ),
        (
            GEPAProposalConfig(
                sampling="pxn",
                proposal_p=2,
                proposal_n=4,
                selection="top-k-improvements",
                top_k=4,
            ),
            "PxNSampling",
            "TopKImprovements",
            8,
        ),
    ],
)
def test_proposal_config_builds_exact_upstream_strategies(
    config: GEPAProposalConfig,
    sampling_type: str,
    selection_type: str,
    task_count: int,
) -> None:
    kwargs = config.to_gepa_kwargs()
    manifest = config.to_manifest()

    assert type(kwargs["sampling_strategy"]).__name__ == sampling_type
    assert type(kwargs["selection_strategy"]).__name__ == selection_type
    assert kwargs["acceptance_criterion"] == config.acceptance.replace("-", "_")
    assert manifest["proposal_task_count"] == task_count
    assert manifest["upstream_sampling_type"] == sampling_type
    assert manifest["upstream_selection_type"] == selection_type


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sampling": "single", "proposal_n": 2},
        {"proposal_n": 2.5},
        {"proposal_p": True},
        {"top_k": 1.5},
        {"sampling": "same-parent", "proposal_n": 1},
        {"sampling": "independent", "proposal_n": 2, "proposal_p": 2},
        {"sampling": "pxn", "proposal_p": 3, "proposal_n": 3},
        {"sampling": "pxn", "proposal_p": 1, "proposal_n": 1},
        {"selection": "best-improvement", "top_k": 2},
        {
            "sampling": "same-parent",
            "proposal_n": 2,
            "selection": "top-k-improvements",
            "top_k": 3,
        },
    ],
)
def test_proposal_config_rejects_ambiguous_or_unbounded_combinations(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        GEPAProposalConfig(**kwargs)  # type: ignore[arg-type]


def test_multi_proposal_requires_positive_explicit_metric_threshold() -> None:
    multi = GEPAProposalConfig(sampling="same-parent", proposal_n=2)

    with pytest.raises(ValueError, match="requires explicit max_metric_calls"):
        validate_gepa_budget(
            multi, auto="light", max_metric_calls=None, max_full_evals=None
        )
    with pytest.raises(ValueError, match="max_metric_calls must be >= 1"):
        validate_gepa_budget(multi, auto=None, max_metric_calls=0, max_full_evals=None)

    validate_gepa_budget(multi, auto=None, max_metric_calls=8, max_full_evals=None)
    validate_gepa_budget(
        GEPAProposalConfig(),
        auto="light",
        max_metric_calls=None,
        max_full_evals=None,
    )

    with pytest.raises(ValueError, match="must be an integer"):
        validate_gepa_budget(
            multi,
            auto=None,
            max_metric_calls=8.5,  # type: ignore[arg-type]
            max_full_evals=None,
        )


def test_num_threads_requires_exact_bounded_integer() -> None:
    for invalid in (True, 1.5, 0, 33):
        with pytest.raises(ValueError):
            validate_num_threads(invalid)  # type: ignore[arg-type]
    validate_num_threads(1)
    validate_num_threads(32)


def test_terminal_reflection_guard_escapes_upstream_exception_fallback() -> None:
    continued_after_provider_failure = False

    class FailingLM:
        def __call__(self, prompt: str) -> list[str]:
            del prompt
            raise LMTransportError(
                "indeterminate",
                code="effect_indeterminate",
                model="stub/echo",
                provider="StubProvider",
            )

    guarded = TerminalGEPAReflectionLM(FailingLM())

    class SwallowingCompiler:
        def compile(self, **kwargs: object) -> object:
            nonlocal continued_after_provider_failure
            del kwargs
            try:
                guarded("reflection")
            except Exception:
                continued_after_provider_failure = True
                return object()
            raise AssertionError("provider failure did not terminate compilation")

    with pytest.raises(LMTransportError) as captured:
        compile_with_terminal_reflection_effects(
            SwallowingCompiler(), student=object(), trainset=[]
        )
    assert captured.value.code == "effect_indeterminate"
    assert continued_after_provider_failure is False


def test_detach_run_stats_hashes_lineage_without_retaining_outputs() -> None:
    details = SimpleNamespace(
        candidates=[{"instruction": "a"}, {"instruction": "b"}],
        parents=[[None], [0]],
        discovery_eval_counts=[2, 8],
        val_aggregate_scores=[0.25, 0.75],
        best_idx=1,
        total_metric_calls=9,
        num_full_val_evals=2,
        _candidate_components=lambda candidate: candidate,
    )
    compiled = SimpleNamespace(detailed_results=details)

    stats = detach_gepa_run_stats(
        compiled,
        event_counts={"schema_version": "events-v1", "proposal_starts": 2},
    )

    assert not hasattr(compiled, "detailed_results")
    assert stats["candidate_count"] == 2
    assert stats["best_candidate_index"] == 1
    assert stats["best_validation_score"] == 0.75
    assert stats["total_metric_calls"] == 9
    assert stats["num_full_val_evals"] == 2
    candidate_hashes = cast(list[str], stats["candidate_component_sha256"])
    assert candidate_hashes and len(candidate_hashes) == 2
    assert stats["parents"] == [[None], [0]]
    assert stats["discovery_eval_counts"] == [2, 8]
    assert stats["validation_scores"] == [0.25, 0.75]
    assert stats["candidate_summary_truncated"] is False
    event_counts = cast(dict[str, object], stats["event_counts"])
    assert event_counts["proposal_starts"] == 2
    assert stats["raw_detailed_result_candidates_or_outputs_retained"] is False
    for key in (
        "parents_sha256",
        "discovery_eval_counts_sha256",
        "validation_scores_sha256",
    ):
        assert len(str(stats[key])) == 64


def test_detach_run_stats_bounds_large_candidate_receipt() -> None:
    count = 257
    parents = [[index - 1] if index else [None] for index in range(count)]
    details = SimpleNamespace(
        candidates=[{"instruction": f"candidate-{index}"} for index in range(count)],
        parents=parents,
        discovery_eval_counts=list(range(count)),
        val_aggregate_scores=[float(index) for index in range(count)],
        best_idx=count - 1,
        total_metric_calls=999,
        num_full_val_evals=10,
        _candidate_components=lambda candidate: candidate,
    )
    compiled = SimpleNamespace(detailed_results=details)

    stats = detach_gepa_run_stats(compiled, event_counts={})

    assert stats["candidate_count"] == count
    assert stats["retained_candidate_count"] == 256
    assert stats["candidate_summary_truncated"] is True
    assert len(cast(list[object], stats["candidate_component_sha256"])) == 256
    assert len(cast(list[object], stats["parents"])) == 256
    payload = json.dumps(
        parents, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert (
        stats["parents_sha256"] == hashlib.sha256(payload.encode("utf-8")).hexdigest()
    )
