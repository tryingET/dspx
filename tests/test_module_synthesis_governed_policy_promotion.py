from __future__ import annotations


from dspx.services.module_synthesis_evidence import (
    build_module_synthesis_governed_policy_evaluations,
    build_module_synthesis_promotion_eligibility_nominations,
)


def test_build_module_synthesis_governed_policy_evaluations_statuses() -> None:
    synthesis = {
        "request": {
            "spec": {
                "name": "Summarizer",
                "description": "Summarizes text",
                "inputs": ["text"],
                "outputs": ["summary"],
                "use_signature": False,
                "template_version": "simple-v1",
            }
        },
        "selection_policy": {
            "policy_id": "module.v7.multi-candidate-ranked",
            "policy_version": "v0",
        },
        "promotion_shell": {
            "metadata": {
                "promotion_policy_id": "module.v7.selected-candidate-promotion",
                "promotion_policy_version": "v0",
            }
        },
    }
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
        "candidate_prior_audit_version": "v1",
        "status": "positive_prior_candidates_present_but_not_selected",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
        },
        "notes": [],
    }
    divergence = {
        "candidate_prior_divergence_explanation_version": "v1",
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
        "candidate_prior_readiness_advisory_version": "v1",
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
        "candidate_prior_counterfactual_advisory_version": "v1",
        "status": "counterfactual_positive_prior_alternatives_present",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "ranking_score": 103.0,
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
            }
        ],
        "notes": [],
    }
    shadow = {
        "shadow_predictive_ranking_advisory_version": "v1",
        "status": "shadow_predictive_ranking_prefers_positive_prior_alternative",
        "shadow_policy_id": "module.sg2.shadow-predictive-ranking.v1",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "ranking_score": 103.0,
        },
        "shadow_preferred_candidate": {
            "candidate_id": "cand-b",
            "variant_id": "variant-b",
            "variant_origin": "deterministic_template_variant",
            "rank": 2,
            "ranking_score": 102.0,
        },
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
    )

    receipts = build_module_synthesis_governed_policy_evaluations(
        synthesis=synthesis,
        candidate_winner_priors=candidate_winner_priors,
        candidate_prior_audit=audit,
        candidate_prior_divergence_explanation=divergence,
        candidate_prior_readiness_advisory=readiness,
        candidate_prior_counterfactual_advisory=counterfactual,
        shadow_predictive_ranking_advisory=shadow,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )

    assert len(receipts) == 2
    ranking = next(
        item for item in receipts if item["variant_class"] == "ranking_evaluation"
    )
    promotion = next(
        item for item in receipts if item["variant_class"] == "promotion_evaluation"
    )
    assert ranking["outcome"] == "policy_evaluation_surfaces_governance_candidate"
    assert ranking["comparison_scope"] == ["cand-a", "cand-b"]
    assert ranking["evaluation_result"]["governance_candidate_id"] == "cand-b"
    assert ranking["decision_rule_summary"].startswith("Compare the live selected")
    assert "shadow_predictive_ranking_advisory:v1" in ranking["input_contracts"]
    assert (
        ranking["bounded_inputs"]["surface_versions"][
            "shadow_predictive_ranking_advisory"
        ]
        == "v1"
    )
    assert ranking["promotion_authority"]["can_change_live_ranking"] is False
    assert ranking["request_context"]["selected_candidate_id"] == "cand-a"
    assert promotion["outcome"] == "policy_evaluation_surfaces_governance_candidate"
    assert promotion["comparison_scope"] == "selected_candidate_only"
    assert (
        promotion["evaluation_result"]["promotion_posture"]
        == "promotion_posture_requires_human_review"
    )
    assert promotion["promotion_authority"]["can_change_live_promotion"] is False


def test_build_module_synthesis_governed_policy_evaluations_fail_closed_without_shadow() -> (
    None
):
    receipts = build_module_synthesis_governed_policy_evaluations(
        synthesis={
            "request": {
                "spec": {
                    "name": "Summarizer",
                    "description": "Summarizes text",
                    "inputs": ["text"],
                    "outputs": ["summary"],
                }
            }
        },
        candidate_winner_priors={"candidate_prior_version": "v1"},
        candidate_prior_audit={"candidate_prior_audit_version": "v1"},
        candidate_prior_divergence_explanation={
            "candidate_prior_divergence_explanation_version": "v1"
        },
        candidate_prior_readiness_advisory={
            "candidate_prior_readiness_advisory_version": "v1"
        },
        candidate_prior_counterfactual_advisory={
            "candidate_prior_counterfactual_advisory_version": "v1",
            "counterfactual_positive_prior_candidates": [],
        },
        shadow_predictive_ranking_advisory=None,
        ranked_candidate_comparison_inputs=(),
    )

    assert len(receipts) == 2
    assert {item["outcome"] for item in receipts} == {"policy_evaluation_unavailable"}
    ranking = next(
        item for item in receipts if item["variant_class"] == "ranking_evaluation"
    )
    promotion = next(
        item for item in receipts if item["variant_class"] == "promotion_evaluation"
    )
    assert ranking["comparison_scope"] == []
    assert promotion["comparison_scope"] == "selected_candidate_only"


def test_build_module_synthesis_promotion_eligibility_nominations_statuses() -> None:
    synthesis = {
        "request": {
            "spec": {
                "name": "Summarizer",
                "description": "Summarizes text",
                "inputs": ["text"],
                "outputs": ["summary"],
                "use_signature": False,
                "template_version": "simple-v1",
            }
        },
        "selection_policy": {
            "policy_id": "module.v7.multi-candidate-ranked",
            "policy_version": "v0",
        },
        "promotion_shell": {
            "metadata": {
                "promotion_policy_id": "module.v7.selected-candidate-promotion",
                "promotion_policy_version": "v0",
            }
        },
        "candidates": [
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
            },
        ],
        "candidate_assemblies": [
            {
                "candidate_id": "cand-a",
                "assembly_id": "assembly-a",
                "artifact_path": "/tmp/cand-a.py",
                "content_hash": "hash-a",
            },
            {
                "candidate_id": "cand-b",
                "assembly_id": "assembly-b",
                "artifact_path": "/tmp/cand-b.py",
                "content_hash": "hash-b",
            },
        ],
        "execution_episodes": [
            {
                "candidate_id": "cand-a",
                "episode_id": "episode-a",
                "status": "passed",
                "score": 103.0,
                "summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "episode_id": "episode-b",
                "status": "passed",
                "score": 102.0,
                "summary": "governance candidate passed",
            },
        ],
        "receipt_bundles": [
            {
                "candidate_id": "cand-a",
                "receipt_bundle_id": "receipt-a",
            },
            {
                "candidate_id": "cand-b",
                "receipt_bundle_id": "receipt-b",
            },
        ],
    }
    candidate_winner_priors = {
        "candidate_prior_version": "v1",
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
    }
    audit = {
        "candidate_prior_audit_version": "v1",
        "status": "positive_prior_candidates_present_but_not_selected",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
        },
    }
    divergence = {
        "candidate_prior_divergence_explanation_version": "v1",
        "status": "divergence_explained_by_runtime_scoring",
    }
    readiness = {
        "candidate_prior_readiness_advisory_version": "v1",
        "status": "priors_mostly_outscored_under_v7",
    }
    counterfactual = {
        "candidate_prior_counterfactual_advisory_version": "v1",
        "status": "counterfactual_positive_prior_alternatives_present",
        "counterfactual_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "rank": 2,
                "ranking_score": 102.0,
                "evaluation_status": "passed",
            }
        ],
    }
    shadow = {
        "shadow_predictive_ranking_advisory_version": "v1",
        "status": "shadow_predictive_ranking_prefers_positive_prior_alternative",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "ranking_score": 103.0,
        },
        "shadow_preferred_candidate": {
            "candidate_id": "cand-b",
            "variant_id": "variant-b",
            "variant_origin": "deterministic_template_variant",
            "rank": 2,
            "ranking_score": 102.0,
        },
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
    )

    governed = build_module_synthesis_governed_policy_evaluations(
        synthesis=synthesis,
        candidate_winner_priors=candidate_winner_priors,
        candidate_prior_audit=audit,
        candidate_prior_divergence_explanation=divergence,
        candidate_prior_readiness_advisory=readiness,
        candidate_prior_counterfactual_advisory=counterfactual,
        shadow_predictive_ranking_advisory=shadow,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    nominations = build_module_synthesis_promotion_eligibility_nominations(
        synthesis=synthesis,
        governed_policy_evaluations=governed,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )

    assert len(nominations) == 2
    ranking = next(
        item for item in nominations if item["variant_class"] == "ranking_evaluation"
    )
    promotion = next(
        item for item in nominations if item["variant_class"] == "promotion_evaluation"
    )
    assert (
        ranking["eligibility_outcome"]
        == "promotion_eligibility_nominated_for_human_review"
    )
    assert ranking["review_scope"] == "bounded_current_run_comparison"
    assert (
        ranking["runtime_spine_refs"]["selected_candidate"]["assembly_id"]
        == "assembly-a"
    )
    assert (
        ranking["runtime_spine_refs"]["governance_candidate"]["receipt_bundle_id"]
        == "receipt-b"
    )
    assert ranking["review_artifacts"]["required_artifacts_present"] is True
    assert ranking["human_governance"]["can_change_live_policy_in_run"] is False
    assert (
        promotion["eligibility_outcome"]
        == "promotion_eligibility_nominated_for_human_review"
    )
    assert promotion["review_scope"] == "selected_candidate_only"
    assert (
        promotion["review_artifacts"]["selected_candidate_passed_current_boundary"]
        is True
    )


def test_build_module_synthesis_promotion_eligibility_nominations_fail_closed_without_governed_receipts() -> (
    None
):
    nominations = build_module_synthesis_promotion_eligibility_nominations(
        synthesis={
            "candidates": [
                {
                    "candidate_id": "cand-a",
                    "variant_id": "variant-a",
                    "variant_origin": "deterministic_template_variant",
                }
            ]
        },
        governed_policy_evaluations=None,
        ranked_candidate_comparison_inputs=(),
    )

    assert len(nominations) == 2
    assert {item["eligibility_outcome"] for item in nominations} == {
        "promotion_eligibility_unavailable"
    }
    assert {item["variant_class"] for item in nominations} == {
        "ranking_evaluation",
        "promotion_evaluation",
    }
