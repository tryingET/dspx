from __future__ import annotations


from dspx.services.module_synthesis_evidence import (
    build_module_synthesis_candidate_prior_audit,
    extract_module_synthesis_ranked_candidate_comparison_inputs,
    extract_module_synthesis_ranked_candidate_inputs,
)


def test_extract_module_synthesis_ranked_candidate_comparison_inputs_preserves_explicit_runtime_metadata() -> (
    None
):
    synthesis = {
        "promotion_decision": {
            "metadata": {
                "ranked_candidates": [
                    {
                        "candidate_id": "cand-a",
                        "rank": 1,
                        "variant_id": "variant-a",
                        "variant_origin": "runtime-origin-a",
                        "ordinal": 0,
                        "status": "passed",
                        "passed": True,
                        "score": 103.0,
                    },
                    {
                        "candidate_id": "cand-b",
                        "rank": 2,
                        "variant_id": "variant-b",
                        "variant_origin": "runtime-origin-b",
                        "ordinal": 1,
                        "status": "failed",
                        "passed": False,
                        "score": 2.0,
                    },
                ]
            }
        },
        "evaluations": [
            {"candidate_id": "cand-a", "summary": "selected summary"},
            {"candidate_id": "cand-b", "summary": "failed summary"},
        ],
    }

    comparison_inputs = extract_module_synthesis_ranked_candidate_comparison_inputs(
        synthesis
    )

    assert comparison_inputs == (
        {
            "candidate_id": "cand-a",
            "rank": 1,
            "variant_id": "variant-a",
            "variant_origin": "runtime-origin-a",
            "ordinal": 0,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 103.0,
            "evaluation_summary": "selected summary",
        },
        {
            "candidate_id": "cand-b",
            "rank": 2,
            "variant_id": "variant-b",
            "variant_origin": "runtime-origin-b",
            "ordinal": 1,
            "evaluation_status": "failed",
            "passed": False,
            "ranking_score": 2.0,
            "evaluation_summary": "failed summary",
        },
    )


def test_extract_module_synthesis_ranked_candidate_comparison_inputs_augments_variant_origin_from_candidates() -> (
    None
):
    synthesis = {
        "candidates": [
            {
                "candidate_id": "cand-a",
                "ordinal": 0,
                "metadata": {"variant_id": "variant-a"},
                "lineage": {"variant_origin": "deterministic_template_variant"},
            }
        ],
        "promotion_decision": {
            "metadata": {
                "ranked_candidates": [
                    {
                        "candidate_id": "cand-a",
                        "rank": 1,
                        "variant_id": "variant-a",
                        "ordinal": 0,
                        "status": "passed",
                        "passed": True,
                        "score": 103.0,
                    }
                ]
            }
        },
        "evaluations": [{"candidate_id": "cand-a", "summary": "selected summary"}],
    }

    comparison_inputs = extract_module_synthesis_ranked_candidate_comparison_inputs(
        synthesis
    )

    assert comparison_inputs[0]["variant_origin"] == "deterministic_template_variant"


def test_extract_module_synthesis_ranked_candidate_inputs_fails_closed_without_rank_metadata() -> (
    None
):
    synthesis = {
        "promotion_decision": {
            "metadata": {
                "ranked_candidates": [
                    {"candidate_id": "cand-a", "ordinal": 0},
                    {"candidate_id": "cand-b", "rank": 0, "ordinal": 1},
                ]
            }
        },
        "promotion_shell": {
            "metadata": {
                "ranked_candidates": [
                    {"candidate_id": "cand-a", "rank": 1, "ordinal": 0},
                    {"candidate_id": "cand-b", "rank": 2, "ordinal": 1},
                ]
            }
        },
    }

    ranked_candidates = extract_module_synthesis_ranked_candidate_inputs(synthesis)

    assert ranked_candidates == (
        {"candidate_id": "cand-a", "rank": 1, "variant_id": None, "ordinal": 0},
        {"candidate_id": "cand-b", "rank": 2, "variant_id": None, "ordinal": 1},
    )


def test_build_module_synthesis_candidate_prior_audit_omits_fabricated_rank_context() -> (
    None
):
    current_candidates = (
        {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "ordinal": 0,
        },
        {
            "candidate_id": "cand-b",
            "variant_id": "variant-b",
            "variant_origin": "deterministic_template_variant",
            "ordinal": 1,
        },
    )
    candidate_winner_priors = {
        "candidate_prior_version": "v1",
        "mode": "winner_history_only",
        "history_summary": {
            "exact_match_receipt_count": 1,
            "positive_evidence_count": 1,
            "candidate_count": 2,
        },
        "candidate_priors": [
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "status": "matches_positive_winner_history",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "status": "no_positive_winner_history",
            },
        ],
        "notes": [],
    }

    audit = build_module_synthesis_candidate_prior_audit(
        candidate_winner_priors,
        current_candidates=current_candidates,
        ranked_candidates=(),
        selected_candidate_id="cand-a",
    )

    assert audit["selected_candidate"]["rank"] is None
    assert audit["positive_prior_candidates"][0]["rank"] is None
    assert any("ranked-candidate order unavailable" in note for note in audit["notes"])


def test_build_module_synthesis_candidate_prior_audit_omits_partial_rank_context() -> (
    None
):
    current_candidates = (
        {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "ordinal": 0,
        },
        {
            "candidate_id": "cand-b",
            "variant_id": "variant-b",
            "variant_origin": "deterministic_template_variant",
            "ordinal": 1,
        },
    )
    candidate_winner_priors = {
        "candidate_prior_version": "v1",
        "mode": "winner_history_only",
        "history_summary": {
            "exact_match_receipt_count": 1,
            "positive_evidence_count": 1,
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
    }

    audit = build_module_synthesis_candidate_prior_audit(
        candidate_winner_priors,
        current_candidates=current_candidates,
        ranked_candidates=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "variant_id": "variant-a",
                "ordinal": 0,
            },
        ),
        selected_candidate_id="cand-a",
    )

    assert audit["status"] == "positive_prior_candidates_present_but_not_selected"
    assert audit["selected_candidate"]["rank"] is None
    assert audit["positive_prior_candidates"][0]["rank"] is None
    assert any("ranked-candidate order incomplete" in note for note in audit["notes"])
