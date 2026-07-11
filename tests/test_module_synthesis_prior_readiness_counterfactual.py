# summary: "Tests module-synthesis prior-readiness and counterfactual advisories, including strict evidence and identity validation."
# read_when:
#   - "Changing readiness aggregation, counterfactual signal statuses, comparison truth, or fail-closed advisory inputs."

from __future__ import annotations


from dspx.services.module_synthesis_evidence import (
    ModuleSynthesisEvidenceBundle,
    ModuleSynthesisEvidenceMatch,
    ModuleSynthesisEvidenceRequest,
    build_module_synthesis_candidate_prior_counterfactual_advisory,
    build_module_synthesis_candidate_prior_readiness_advisory,
)
from module_synthesis_evidence_helpers import (
    _synthetic_prior_readiness_match,
)


def test_build_module_synthesis_candidate_prior_readiness_advisory_statuses() -> None:
    request = ModuleSynthesisEvidenceRequest(
        name="Summarizer",
        description="Summarizes text",
        inputs=("text",),
        outputs=("summary",),
        use_signature=False,
        template_version="simple-v1",
    )

    def _bundle(
        *matches: ModuleSynthesisEvidenceMatch,
    ) -> ModuleSynthesisEvidenceBundle:
        return ModuleSynthesisEvidenceBundle(
            request=request,
            retrieval_order=("exact_match_receipts", "replay_verification"),
            exact_match_receipts=matches,
            oracle_neighbors=(),
            receipts_path="/tmp/receipts",
            oracle_index_path="/tmp/oracle.db",
            receipts_scanned=len(matches),
            oracle_query_text=request.oracle_query_text(),
            receipt_scan_errors=(),
            exact_match_receipt_scan_errors=(),
            oracle_lookup_status="missing",
            oracle_lookup_error=None,
        )

    insufficient = build_module_synthesis_candidate_prior_readiness_advisory(
        _bundle(
            _synthetic_prior_readiness_match(
                receipt_path="r1.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            )
        )
    )
    assert insufficient["status"] == "insufficient_prior_history"

    unavailable = build_module_synthesis_candidate_prior_readiness_advisory(
        _bundle(
            _synthetic_prior_readiness_match(
                receipt_path="r1.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r2.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
                include_diagnostics=False,
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r3.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
        )
    )
    assert unavailable["status"] == "candidate_prior_readiness_unavailable"
    assert unavailable["history_summary"]["unusable_receipt_count"] == 1

    convergent = build_module_synthesis_candidate_prior_readiness_advisory(
        _bundle(
            _synthetic_prior_readiness_match(
                receipt_path="r1.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r2.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r3.meta.json",
                audit_status="no_positive_prior_candidates",
                divergence_status="no_divergence_to_explain",
            ),
        )
    )
    assert convergent["status"] == "priors_consistently_convergent"

    runtime_failures = build_module_synthesis_candidate_prior_readiness_advisory(
        _bundle(
            _synthetic_prior_readiness_match(
                receipt_path="r1.meta.json",
                audit_status="positive_prior_candidates_present_but_not_selected",
                divergence_status="divergence_explained_by_runtime_failures",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r2.meta.json",
                audit_status="positive_prior_candidates_present_but_not_selected",
                divergence_status="divergence_explained_by_runtime_failures",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r3.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
        )
    )
    assert runtime_failures["status"] == "priors_mostly_blocked_by_runtime_failures"

    runtime_scoring = build_module_synthesis_candidate_prior_readiness_advisory(
        _bundle(
            _synthetic_prior_readiness_match(
                receipt_path="r1.meta.json",
                audit_status="positive_prior_candidates_present_but_not_selected",
                divergence_status="divergence_explained_by_runtime_scoring",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r2.meta.json",
                audit_status="positive_prior_candidates_present_but_not_selected",
                divergence_status="divergence_explained_by_runtime_scoring",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r3.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
        )
    )
    assert runtime_scoring["status"] == "priors_mostly_outscored_under_v7"

    mixed = build_module_synthesis_candidate_prior_readiness_advisory(
        _bundle(
            _synthetic_prior_readiness_match(
                receipt_path="r1.meta.json",
                audit_status="positive_prior_candidates_present_but_not_selected",
                divergence_status="divergence_explained_by_runtime_failures",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r2.meta.json",
                audit_status="positive_prior_candidates_present_but_not_selected",
                divergence_status="divergence_explained_by_runtime_scoring",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r3.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
        )
    )
    assert mixed["status"] == "priors_mixed_or_inconclusive"


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_statuses() -> (
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
            "exact_match_receipt_count": 4,
            "positive_evidence_count": 4,
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
    comparison_inputs = (
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
    )
    scoring_divergence = {
        "status": "divergence_explained_by_runtime_scoring",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "ranking_score": 103.0,
        },
        "compared_positive_prior_candidates": [
            {"candidate_id": "cand-b", "comparison_status": "lower_ranked_pass"},
            {"candidate_id": "cand-c", "comparison_status": "lower_ranked_pass"},
        ],
        "notes": [],
    }

    positive = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
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
        },
        scoring_divergence,
        audit,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    assert positive["status"] == "counterfactual_positive_prior_alternatives_present"
    assert positive["history_summary"]["passing_positive_prior_candidate_count"] == 2
    assert [
        item["candidate_id"]
        for item in positive["counterfactual_positive_prior_candidates"]
    ] == ["cand-b", "cand-c"]

    sparse = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "insufficient_prior_history",
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
        scoring_divergence,
        audit,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    assert sparse["status"] == "counterfactual_signal_sparse"
    assert sparse["counterfactual_positive_prior_candidates"]

    no_signal = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_blocked_by_runtime_failures",
            "history_summary": {
                "exact_match_receipt_count": 4,
                "replay_healthy_receipt_count": 4,
                "usable_receipt_count": 4,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 3,
                "runtime_scoring_divergence_count": 0,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "divergence_explained_by_runtime_failures",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 103.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "failed_runtime_validation",
                }
            ],
            "notes": [],
        },
        {
            **audit,
            "non_selected_positive_prior_candidates": [
                audit["non_selected_positive_prior_candidates"][0]
            ],
        },
        ranked_candidate_comparison_inputs=(
            comparison_inputs[0],
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 2.0,
                "evaluation_summary": "cand-b failed",
            },
        ),
    )
    assert no_signal["status"] == "no_counterfactual_signal"
    assert no_signal["counterfactual_positive_prior_candidates"] == []

    mixed = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mixed_or_inconclusive",
            "history_summary": {
                "exact_match_receipt_count": 4,
                "replay_healthy_receipt_count": 4,
                "usable_receipt_count": 4,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 1,
                "runtime_scoring_divergence_count": 1,
                "mixed_divergence_count": 1,
                "unresolved_receipt_count": 1,
            },
            "notes": [],
        },
        {
            "status": "divergence_explained_by_mixed_runtime_outcomes",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 103.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "lower_ranked_pass",
                },
                {
                    "candidate_id": "cand-c",
                    "comparison_status": "failed_runtime_validation",
                },
            ],
            "notes": [],
        },
        audit,
        ranked_candidate_comparison_inputs=(
            comparison_inputs[0],
            comparison_inputs[1],
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
    assert mixed["status"] == "counterfactual_signal_mixed_or_inconclusive"
    assert len(mixed["counterfactual_positive_prior_candidates"]) == 1


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_fails_closed_on_incomplete_comparison_truth() -> (
    None
):
    advisory = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {
                "exact_match_receipt_count": 3,
                "replay_healthy_receipt_count": 3,
                "usable_receipt_count": 3,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 2,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 103.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "lower_ranked_pass",
                }
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

    assert advisory["status"] == "candidate_prior_counterfactual_unavailable"
    assert advisory["counterfactual_positive_prior_candidates"] == []


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_preserves_zero_selected_ranking_score() -> (
    None
):
    advisory = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {
                "exact_match_receipt_count": 3,
                "replay_healthy_receipt_count": 3,
                "usable_receipt_count": 3,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 2,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 999.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "lower_ranked_pass",
                }
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
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 0.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": -1.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert advisory["selected_candidate"]["ranking_score"] == 0.0


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_fails_closed_on_unsupported_status_values() -> (
    None
):
    base_readiness = {
        "status": "priors_mostly_outscored_under_v7",
        "history_summary": {},
        "notes": [],
    }
    base_divergence = {
        "status": "divergence_explained_by_runtime_scoring",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "ranking_score": 10.0,
        },
        "compared_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "comparison_status": "lower_ranked_pass",
            }
        ],
        "notes": [],
    }
    base_audit = {
        "status": "positive_prior_candidates_present_but_not_selected",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
        },
        "history_summary": {},
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
    comparison_inputs = (
        {
            "candidate_id": "cand-a",
            "rank": 1,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 10.0,
            "evaluation_summary": "selected passed",
        },
        {
            "candidate_id": "cand-b",
            "rank": 2,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 9.0,
            "evaluation_summary": "cand-b passed",
        },
    )

    unsupported_readiness = (
        build_module_synthesis_candidate_prior_counterfactual_advisory(
            {**base_readiness, "status": "NOT_A_REAL_STATUS"},
            base_divergence,
            base_audit,
            ranked_candidate_comparison_inputs=comparison_inputs,
        )
    )
    assert (
        unsupported_readiness["status"] == "candidate_prior_counterfactual_unavailable"
    )

    unsupported_divergence = (
        build_module_synthesis_candidate_prior_counterfactual_advisory(
            base_readiness,
            {**base_divergence, "status": "NOT_A_REAL_DIVERGENCE_STATUS"},
            base_audit,
            ranked_candidate_comparison_inputs=comparison_inputs,
        )
    )
    assert (
        unsupported_divergence["status"] == "candidate_prior_counterfactual_unavailable"
    )

    unsupported_audit = build_module_synthesis_candidate_prior_counterfactual_advisory(
        base_readiness,
        base_divergence,
        {**base_audit, "status": "NOT_A_REAL_AUDIT_STATUS"},
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    assert unsupported_audit["status"] == "candidate_prior_counterfactual_unavailable"


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_fails_closed_on_selected_candidate_identity_drift() -> (
    None
):
    advisory = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {},
            "notes": [],
        },
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-z",
                "variant_id": "variant-z",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "lower_ranked_pass",
                }
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
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert advisory["status"] == "candidate_prior_counterfactual_unavailable"


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_fails_closed_on_duplicate_compared_candidate_ids() -> (
    None
):
    advisory = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {
                "exact_match_receipt_count": 3,
                "replay_healthy_receipt_count": 3,
                "usable_receipt_count": 3,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 2,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
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
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "lower_ranked_pass",
                }
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
                },
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                },
            ],
            "notes": [],
        },
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
        ),
    )

    assert advisory["status"] == "candidate_prior_counterfactual_unavailable"


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_fails_closed_on_malformed_or_mismatched_divergence_compared_candidates() -> (
    None
):
    base_readiness = {
        "status": "priors_mostly_outscored_under_v7",
        "history_summary": {},
        "notes": [],
    }
    base_audit = {
        "status": "positive_prior_candidates_present_but_not_selected",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
        },
        "history_summary": {},
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
    comparison_inputs = (
        {
            "candidate_id": "cand-a",
            "rank": 1,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 10.0,
            "evaluation_summary": "selected passed",
        },
        {
            "candidate_id": "cand-b",
            "rank": 2,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 9.0,
            "evaluation_summary": "cand-b passed",
        },
    )

    malformed = build_module_synthesis_candidate_prior_counterfactual_advisory(
        base_readiness,
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": ["MALFORMED"],
            "notes": [],
        },
        base_audit,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    assert malformed["status"] == "candidate_prior_counterfactual_unavailable"

    mismatched = build_module_synthesis_candidate_prior_counterfactual_advisory(
        base_readiness,
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
                {
                    "candidate_id": "cand-z",
                    "comparison_status": "lower_ranked_pass",
                }
            ],
            "notes": [],
        },
        base_audit,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    assert mismatched["status"] == "candidate_prior_counterfactual_unavailable"


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_fails_closed_on_current_comparison_variant_identity_drift() -> (
    None
):
    advisory = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {
                "exact_match_receipt_count": 3,
                "replay_healthy_receipt_count": 3,
                "usable_receipt_count": 3,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 2,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
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
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "lower_ranked_pass",
                }
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
            "history_summary": {
                "exact_match_receipt_count": 3,
                "positive_evidence_count": 3,
                "positive_prior_candidate_count": 1,
            },
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b-audit",
                    "variant_origin": "audit-origin",
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
                "variant_id": "variant-b-runtime",
                "variant_origin": "runtime-origin",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert advisory["status"] == "candidate_prior_counterfactual_unavailable"
