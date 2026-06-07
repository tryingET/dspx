from __future__ import annotations


from dspx.services.module_synthesis_evidence import (
    build_module_synthesis_shadow_predictive_ranking_advisory,
)


def test_build_module_synthesis_shadow_predictive_ranking_advisory_statuses() -> None:
    candidate_winner_priors = {
        "candidate_prior_version": "v1",
        "mode": "winner_history_only",
        "history_summary": {
            "exact_match_receipt_count": 4,
            "positive_evidence_count": 4,
            "oracle_neighbor_count": 0,
            "candidate_count": 3,
        },
        "candidate_priors": [
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "status": "no_positive_winner_history",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "status": "matches_positive_winner_history",
            },
            {
                "candidate_id": "cand-c",
                "variant_id": "variant-c",
                "variant_origin": "deterministic_template_variant",
                "status": "matches_positive_winner_history",
            },
        ],
        "notes": [],
    }
    audit = {
        "status": "positive_prior_candidates_present_but_not_selected",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
        },
        "history_summary": {
            "exact_match_receipt_count": 4,
            "positive_evidence_count": 4,
            "candidate_count": 3,
            "positive_prior_candidate_count": 2,
        },
        "positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 2,
            },
            {
                "candidate_id": "cand-c",
                "variant_id": "variant-c",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 3,
            },
        ],
        "non_selected_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 2,
            },
            {
                "candidate_id": "cand-c",
                "variant_id": "variant-c",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 3,
            },
        ],
        "notes": [],
    }
    divergence = {
        "status": "divergence_explained_by_runtime_scoring",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
            "ranking_score": 103.0,
        },
        "compared_positive_prior_candidates": [
            {"candidate_id": "cand-b", "comparison_status": "lower_ranked_pass"},
            {"candidate_id": "cand-c", "comparison_status": "lower_ranked_pass"},
        ],
        "notes": [],
    }
    readiness = {
        "status": "priors_mostly_outscored_under_v7",
        "history_summary": {
            "exact_match_receipt_count": 4,
            "replay_healthy_receipt_count": 4,
            "usable_receipt_count": 4,
            "convergent_receipt_count": 1,
            "runtime_failure_divergence_count": 0,
            "runtime_scoring_divergence_count": 3,
            "mixed_divergence_count": 0,
            "unresolved_receipt_count": 0,
        },
        "notes": [],
    }
    counterfactual = {
        "status": "counterfactual_positive_prior_alternatives_present",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "ranking_score": 103.0,
        },
        "history_summary": {
            "exact_match_receipt_count": 4,
            "replay_healthy_receipt_count": 4,
            "positive_prior_signal_receipt_count": 4,
            "passing_positive_prior_candidate_count": 2,
        },
        "counterfactual_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "rank": 2,
                "ranking_score": 102.0,
                "evaluation_status": "passed",
                "notes": [],
            },
            {
                "candidate_id": "cand-c",
                "variant_id": "variant-c",
                "variant_origin": "deterministic_template_variant",
                "rank": 3,
                "ranking_score": 101.0,
                "evaluation_status": "passed",
                "notes": [],
            },
        ],
        "notes": [],
    }
    comparison_inputs = (
        {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 103.0,
            "evaluation_summary": "selected passed",
        },
        {
            "candidate_id": "cand-b",
            "variant_id": "variant-b",
            "variant_origin": "deterministic_template_variant",
            "rank": 2,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 102.0,
            "evaluation_summary": "cand-b passed",
        },
        {
            "candidate_id": "cand-c",
            "variant_id": "variant-c",
            "variant_origin": "deterministic_template_variant",
            "rank": 3,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 101.0,
            "evaluation_summary": "cand-c passed",
        },
    )

    prefers_alternative = build_module_synthesis_shadow_predictive_ranking_advisory(
        candidate_winner_priors,
        audit,
        divergence,
        readiness,
        counterfactual,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    assert (
        prefers_alternative["status"]
        == "shadow_predictive_ranking_prefers_positive_prior_alternative"
    )
    assert prefers_alternative["shadow_policy_id"]
    assert prefers_alternative["shadow_preferred_candidate"]["candidate_id"] == "cand-b"
    assert (
        prefers_alternative["history_summary"]["passing_positive_prior_candidate_count"]
        == 2
    )

    no_signal = build_module_synthesis_shadow_predictive_ranking_advisory(
        {
            **candidate_winner_priors,
            "candidate_priors": [
                {
                    **candidate_winner_priors["candidate_priors"][0],
                    "status": "no_positive_winner_history",
                },
                {
                    **candidate_winner_priors["candidate_priors"][1],
                    "status": "no_positive_winner_history",
                },
            ],
        },
        {
            "status": "no_positive_prior_candidates",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "positive_evidence_count": 0,
                "candidate_count": 2,
                "positive_prior_candidate_count": 0,
            },
            "positive_prior_candidates": [],
            "non_selected_positive_prior_candidates": [],
            "notes": [],
        },
        {
            "status": "no_divergence_to_explain",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [],
            "notes": [],
        },
        {
            "status": "insufficient_prior_history",
            "history_summary": {
                "exact_match_receipt_count": 1,
                "replay_healthy_receipt_count": 0,
                "usable_receipt_count": 0,
                "convergent_receipt_count": 0,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 0,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "counterfactual_signal_sparse",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "replay_healthy_receipt_count": 0,
                "positive_prior_signal_receipt_count": 0,
                "passing_positive_prior_candidate_count": 0,
            },
            "counterfactual_positive_prior_candidates": [],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "rank": 2,
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 1.0,
                "evaluation_summary": "cand-b failed",
            },
        ),
    )
    assert no_signal["status"] == "no_shadow_predictive_signal"
    assert no_signal["shadow_preferred_candidate"]["candidate_id"] is None

    matches_v7 = build_module_synthesis_shadow_predictive_ranking_advisory(
        {
            **candidate_winner_priors,
            "candidate_priors": [
                {
                    **candidate_winner_priors["candidate_priors"][0],
                    "status": "matches_positive_winner_history",
                },
                {
                    **candidate_winner_priors["candidate_priors"][1],
                    "status": "no_positive_winner_history",
                },
            ],
        },
        {
            "status": "selected_matches_positive_winner_history",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "positive_evidence_count": 1,
                "candidate_count": 2,
                "positive_prior_candidate_count": 1,
            },
            "positive_prior_candidates": [
                {
                    "candidate_id": "cand-a",
                    "variant_id": "variant-a",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 1,
                }
            ],
            "non_selected_positive_prior_candidates": [],
            "notes": [],
        },
        {
            "status": "no_divergence_to_explain",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [],
            "notes": [],
        },
        {
            "status": "insufficient_prior_history",
            "history_summary": {
                "exact_match_receipt_count": 1,
                "replay_healthy_receipt_count": 1,
                "usable_receipt_count": 1,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 0,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "counterfactual_signal_sparse",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "replay_healthy_receipt_count": 1,
                "positive_prior_signal_receipt_count": 1,
                "passing_positive_prior_candidate_count": 0,
            },
            "counterfactual_positive_prior_candidates": [],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )
    assert matches_v7["status"] == "shadow_predictive_ranking_matches_v7"
    assert matches_v7["shadow_preferred_candidate"]["candidate_id"] == "cand-a"

    mixed = build_module_synthesis_shadow_predictive_ranking_advisory(
        {
            **candidate_winner_priors,
            "candidate_priors": [
                {
                    **candidate_winner_priors["candidate_priors"][0],
                    "status": "degraded_history_only",
                },
                {
                    **candidate_winner_priors["candidate_priors"][1],
                    "status": "matches_positive_winner_history",
                },
            ],
        },
        {
            "status": "selected_candidate_prior_degraded",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "degraded_history_only",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 3,
                "positive_evidence_count": 1,
                "candidate_count": 2,
                "positive_prior_candidate_count": 1,
            },
            "positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "notes": [],
        },
        {
            "status": "selected_candidate_prior_unresolved",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "degraded_history_only",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [
                {"candidate_id": "cand-b", "comparison_status": "lower_ranked_pass"}
            ],
            "notes": [],
        },
        {
            "status": "priors_mixed_or_inconclusive",
            "history_summary": {
                "exact_match_receipt_count": 3,
                "replay_healthy_receipt_count": 1,
                "usable_receipt_count": 3,
                "convergent_receipt_count": 0,
                "runtime_failure_divergence_count": 1,
                "runtime_scoring_divergence_count": 1,
                "mixed_divergence_count": 1,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "counterfactual_signal_mixed_or_inconclusive",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "history_summary": {
                "exact_match_receipt_count": 3,
                "replay_healthy_receipt_count": 1,
                "positive_prior_signal_receipt_count": 3,
                "passing_positive_prior_candidate_count": 1,
            },
            "counterfactual_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "rank": 2,
                    "ranking_score": 9.0,
                    "evaluation_status": "passed",
                    "notes": [],
                }
            ],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )
    assert mixed["status"] == "shadow_predictive_ranking_mixed_or_inconclusive"
    assert mixed["shadow_preferred_candidate"]["candidate_id"] is None


def test_build_module_synthesis_shadow_predictive_ranking_advisory_fails_closed_on_counterfactual_comparison_set_drift() -> (
    None
):
    advisory = build_module_synthesis_shadow_predictive_ranking_advisory(
        {
            "candidate_prior_version": "v1",
            "mode": "winner_history_only",
            "history_summary": {
                "exact_match_receipt_count": 2,
                "positive_evidence_count": 2,
                "oracle_neighbor_count": 0,
                "candidate_count": 2,
            },
            "candidate_priors": [
                {
                    "candidate_id": "cand-a",
                    "variant_id": "variant-a",
                    "variant_origin": "deterministic_template_variant",
                    "status": "no_positive_winner_history",
                },
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "status": "matches_positive_winner_history",
                },
            ],
            "notes": [],
        },
        {
            "status": "positive_prior_candidates_present_but_not_selected",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {},
            "positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "notes": [],
        },
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [
                {"candidate_id": "cand-b", "comparison_status": "lower_ranked_pass"}
            ],
            "notes": [],
        },
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {
                "exact_match_receipt_count": 2,
                "replay_healthy_receipt_count": 2,
                "usable_receipt_count": 2,
                "convergent_receipt_count": 0,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 2,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "counterfactual_positive_prior_alternatives_present",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "history_summary": {
                "exact_match_receipt_count": 2,
                "replay_healthy_receipt_count": 2,
                "positive_prior_signal_receipt_count": 2,
                "passing_positive_prior_candidate_count": 0,
            },
            "counterfactual_positive_prior_candidates": [],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert advisory["status"] == "shadow_predictive_ranking_unavailable"
