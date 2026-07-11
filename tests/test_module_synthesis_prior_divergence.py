# summary: "Tests explanations for module-synthesis candidate-prior divergence and their fail-closed comparison validation."
# read_when:
#   - "Changing prior-divergence statuses, ranked comparison metadata, identity checks, or incomplete-input handling."

from __future__ import annotations


from dspx.services.module_synthesis_evidence import (
    build_module_synthesis_candidate_prior_divergence_explanation,
)


def test_build_module_synthesis_candidate_prior_divergence_explanation_fails_closed_on_malformed_or_duplicate_current_comparison_metadata() -> (
    None
):
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
            "exact_match_receipt_count": 3,
            "positive_evidence_count": 3,
            "positive_prior_candidate_count": 1,
        },
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
    }

    malformed = build_module_synthesis_candidate_prior_divergence_explanation(
        audit,
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": True,
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": False,
                "evaluation_summary": "cand-b malformed",
            },
        ),
    )
    assert malformed["status"] == "candidate_prior_divergence_unavailable"

    duplicated = build_module_synthesis_candidate_prior_divergence_explanation(
        audit,
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 1.0,
                "evaluation_summary": "cand-b duplicate",
            },
        ),
    )
    assert duplicated["status"] == "candidate_prior_divergence_unavailable"


def test_build_module_synthesis_candidate_prior_divergence_explanation_statuses() -> (
    None
):
    no_divergence = build_module_synthesis_candidate_prior_divergence_explanation(
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
                "positive_prior_candidate_count": 1,
            },
            "non_selected_positive_prior_candidates": [],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(),
    )
    assert no_divergence["status"] == "no_divergence_to_explain"
    assert no_divergence["selected_candidate"]["candidate_id"] == "cand-a"

    unresolved = build_module_synthesis_candidate_prior_divergence_explanation(
        {
            "status": "selected_candidate_prior_degraded",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "degraded_history_only",
                "rank": None,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "positive_evidence_count": 0,
                "positive_prior_candidate_count": 0,
            },
            "non_selected_positive_prior_candidates": [],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(),
    )
    assert unresolved["status"] == "selected_candidate_prior_unresolved"

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
            "exact_match_receipt_count": 2,
            "positive_evidence_count": 2,
            "positive_prior_candidate_count": 2,
        },
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

    failures = build_module_synthesis_candidate_prior_divergence_explanation(
        audit,
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 103.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 2.0,
                "evaluation_summary": "cand-b failed",
            },
            {
                "candidate_id": "cand-c",
                "rank": 3,
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 1.0,
                "evaluation_summary": "cand-c failed",
            },
        ),
    )
    assert failures["status"] == "divergence_explained_by_runtime_failures"
    assert {
        item["comparison_status"]
        for item in failures["compared_positive_prior_candidates"]
    } == {"failed_runtime_validation"}
    assert failures["history_summary"]["compared_candidate_count"] == 2

    scoring = build_module_synthesis_candidate_prior_divergence_explanation(
        audit,
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 103.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 102.0,
                "evaluation_summary": "cand-b passed",
            },
            {
                "candidate_id": "cand-c",
                "rank": 3,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 101.0,
                "evaluation_summary": "cand-c passed",
            },
        ),
    )
    assert scoring["status"] == "divergence_explained_by_runtime_scoring"
    assert {
        item["comparison_status"]
        for item in scoring["compared_positive_prior_candidates"]
    } == {"lower_ranked_pass"}
    assert scoring["selected_candidate"]["ranking_score"] == 103.0

    mixed = build_module_synthesis_candidate_prior_divergence_explanation(
        audit,
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 103.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 2.0,
                "evaluation_summary": "cand-b failed",
            },
            {
                "candidate_id": "cand-c",
                "rank": 3,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 101.0,
                "evaluation_summary": "cand-c passed",
            },
        ),
    )
    assert mixed["status"] == "divergence_explained_by_mixed_runtime_outcomes"


def test_build_module_synthesis_candidate_prior_divergence_explanation_fails_closed_on_incomplete_comparison_truth() -> (
    None
):
    explanation = build_module_synthesis_candidate_prior_divergence_explanation(
        {
            "status": "positive_prior_candidates_present_but_not_selected",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "positive_evidence_count": 1,
                "positive_prior_candidate_count": 1,
            },
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
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 103.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": None,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert explanation["status"] == "candidate_prior_divergence_unavailable"
    assert explanation["history_summary"]["compared_candidate_count"] == 1
    assert explanation["compared_positive_prior_candidates"] == []


def test_build_module_synthesis_candidate_prior_divergence_explanation_fails_closed_on_malformed_compared_candidates() -> (
    None
):
    explanation = build_module_synthesis_candidate_prior_divergence_explanation(
        {
            "status": "positive_prior_candidates_present_but_not_selected",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "positive_evidence_count": 1,
                "positive_prior_candidate_count": 2,
            },
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                },
                "MALFORMED",
            ],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 103.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 102.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert explanation["status"] == "candidate_prior_divergence_unavailable"
    assert explanation["compared_positive_prior_candidates"] == []
