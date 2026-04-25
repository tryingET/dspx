from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional
import os as _os

from dspx.cache import sha256_text
from dspx.coordinates.storage import get_default_index_path
from dspx.dtos import ModuleSpec
from dspx.services.module_artifacts import module_cache_key
from dspx.services.module_synthesis_evidence import (
    ModuleSynthesisEvidenceRequest,
    build_module_synthesis_candidate_prior_audit,
    build_module_synthesis_candidate_prior_counterfactual_advisory,
    build_module_synthesis_candidate_prior_divergence_explanation,
    build_module_synthesis_candidate_prior_readiness_advisory,
    build_module_synthesis_candidate_winner_priors,
    build_module_synthesis_governed_policy_evaluations,
    build_module_synthesis_history_advisory,
    build_module_synthesis_promotion_eligibility_nominations,
    build_module_synthesis_shadow_predictive_ranking_advisory,
    build_unavailable_module_synthesis_candidate_prior_audit,
    build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory,
    build_unavailable_module_synthesis_candidate_prior_divergence_explanation,
    build_unavailable_module_synthesis_candidate_prior_readiness_advisory,
    build_unavailable_module_synthesis_candidate_winner_priors,
    build_unavailable_module_synthesis_shadow_predictive_ranking_advisory,
    extract_module_synthesis_candidate_prior_inputs,
    extract_module_synthesis_ranked_candidate_comparison_inputs,
    extract_module_synthesis_ranked_candidate_inputs,
    retrieve_module_synthesis_evidence,
)

EvidenceRetriever = Callable[..., Any]


def module_synthesis_evidence_receipts_path(
    promotion_target: Optional[Path],
) -> Optional[Path]:
    configured = _os.getenv("DSPX_MODULE_SYNTHESIS_EVIDENCE_RECEIPTS_PATH")
    if configured:
        return Path(configured)
    if promotion_target is not None:
        return promotion_target.parent
    return None


def module_synthesis_evidence_oracle_index_path(
    promotion_target: Optional[Path],
) -> Optional[Path]:
    configured = _os.getenv("DSPX_MODULE_SYNTHESIS_EVIDENCE_ORACLE_INDEX_PATH")
    if configured:
        return Path(configured)
    if promotion_target is not None:
        parent = promotion_target.parent
        oracle_root = parent if parent.name == "generated" else (parent / "generated")
        return oracle_root / "oracle" / "coordinates.db"
    return get_default_index_path()


def module_synthesis_evidence_oracle_top_k() -> int:
    raw = (_os.getenv("DSPX_MODULE_SYNTHESIS_EVIDENCE_ORACLE_TOP_K") or "").strip()
    if not raw:
        return 5
    try:
        return max(1, int(raw))
    except ValueError:
        return 5


def build_unavailable_synthesis_diagnostics(
    spec: ModuleSpec,
    *,
    use_signature: bool,
    promotion_target: Optional[Path],
    synthesis_payload: dict[str, Any] | None,
    selected_candidate_id: str | None,
    output_hash: str | None,
    cache_key: str | None,
    retrieval_error: dict[str, Any],
) -> dict[str, Any]:
    request = ModuleSynthesisEvidenceRequest.from_spec(
        spec,
        use_signature=use_signature,
    )
    receipts_path = (
        module_synthesis_evidence_receipts_path(promotion_target)
        or (Path.cwd() / "generated")
    ).resolve()
    oracle_index_path = (
        module_synthesis_evidence_oracle_index_path(promotion_target)
        or get_default_index_path()
    ).resolve()
    evidence_bundle = {
        "request": request.to_dict(),
        "retrieval_order": [
            "exact_match_receipts",
            "replay_verification",
            "oracle_neighbors",
        ],
        "exact_match_receipts": [],
        "oracle_neighbors": [],
        "receipts_path": str(receipts_path),
        "oracle_index_path": str(oracle_index_path),
        "receipts_scanned": 0,
        "oracle_query_text": request.oracle_query_text(),
        "receipt_scan_errors": [],
        "receipt_scan_error_count": 0,
        "exact_match_receipt_scan_errors": [],
        "exact_match_receipt_scan_error_count": 0,
        "oracle_lookup_status": "unavailable",
        "oracle_lookup_error": dict(retrieval_error),
        "oracle_index_available": False,
        "positive_evidence_count": 0,
    }
    current_candidates = extract_module_synthesis_candidate_prior_inputs(
        synthesis_payload
    )
    candidate_prior_audit = build_unavailable_module_synthesis_candidate_prior_audit(
        selected_candidate_id=selected_candidate_id,
        current_candidates=current_candidates,
        notes=["candidate-prior audit unavailable because evidence retrieval failed"],
    )
    candidate_prior_divergence_explanation = build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
        candidate_prior_audit=candidate_prior_audit,
        notes=[
            "candidate-prior divergence explanation unavailable because evidence retrieval failed"
        ],
    )
    candidate_prior_readiness_advisory = build_unavailable_module_synthesis_candidate_prior_readiness_advisory(
        notes=[
            "candidate-prior readiness advisory unavailable because evidence retrieval failed"
        ],
    )
    candidate_prior_counterfactual_advisory = build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
        candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
        candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
        candidate_prior_audit=candidate_prior_audit,
        notes=[
            "candidate-prior counterfactual advisory unavailable because evidence retrieval failed"
        ],
    )
    shadow_predictive_ranking_advisory = build_unavailable_module_synthesis_shadow_predictive_ranking_advisory(
        candidate_prior_audit=candidate_prior_audit,
        candidate_prior_divergence_explanation=(candidate_prior_divergence_explanation),
        candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
        candidate_prior_counterfactual_advisory=(
            candidate_prior_counterfactual_advisory
        ),
        notes=[
            "shadow predictive-ranking advisory unavailable because evidence retrieval failed"
        ],
    )
    governed_policy_evaluations = build_module_synthesis_governed_policy_evaluations(
        synthesis=synthesis_payload,
        candidate_winner_priors=build_unavailable_module_synthesis_candidate_winner_priors(
            current_candidates=current_candidates,
            notes=[
                "candidate winner-prior payload unavailable because evidence retrieval failed"
            ],
        ),
        candidate_prior_audit=candidate_prior_audit,
        candidate_prior_divergence_explanation=(candidate_prior_divergence_explanation),
        candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
        candidate_prior_counterfactual_advisory=(
            candidate_prior_counterfactual_advisory
        ),
        shadow_predictive_ranking_advisory=shadow_predictive_ranking_advisory,
        ranked_candidate_comparison_inputs=(),
    )
    promotion_eligibility_nominations = (
        build_module_synthesis_promotion_eligibility_nominations(
            synthesis=synthesis_payload,
            governed_policy_evaluations=governed_policy_evaluations,
            ranked_candidate_comparison_inputs=(),
        )
    )
    return {
        "evidence_bundle_version": "v1",
        "retrieval_status": "unavailable",
        "retrieval_error": dict(retrieval_error),
        "evidence_summary": {
            "exact_match_receipt_count": 0,
            "positive_evidence_count": 0,
            "oracle_neighbor_count": 0,
            "oracle_index_available": False,
            "oracle_lookup_status": "unavailable",
            "receipt_scan_error_count": 0,
        },
        "evidence_bundle": evidence_bundle,
        "historical_convergence_advisory": {
            "advisory_version": "v1",
            "status": "unavailable",
            "selected_artifact": {
                "selected_candidate_id": selected_candidate_id,
                "output_hash": output_hash,
                "cache_key": cache_key,
            },
            "history_summary": {
                "exact_match_receipt_count": 0,
                "positive_evidence_count": 0,
                "oracle_neighbor_count": 0,
            },
            "matching_positive_receipts": [],
            "divergent_positive_receipts": [],
            "notes": ["evidence retrieval unavailable"],
        },
        "candidate_winner_priors": build_unavailable_module_synthesis_candidate_winner_priors(
            current_candidates=current_candidates,
            notes=[
                "candidate winner-prior payload unavailable because evidence retrieval failed"
            ],
        ),
        "candidate_prior_audit": candidate_prior_audit,
        "candidate_prior_divergence_explanation": (
            candidate_prior_divergence_explanation
        ),
        "candidate_prior_readiness_advisory": candidate_prior_readiness_advisory,
        "candidate_prior_counterfactual_advisory": (
            candidate_prior_counterfactual_advisory
        ),
        "shadow_predictive_ranking_advisory": shadow_predictive_ranking_advisory,
        "governed_policy_evaluations": governed_policy_evaluations,
        "promotion_eligibility_nominations": promotion_eligibility_nominations,
    }


def build_synthesis_diagnostics(
    spec: ModuleSpec,
    *,
    use_signature: bool,
    promotion_target: Optional[Path],
    synthesis_payload: dict[str, Any] | None,
    selected_candidate_id: str | None,
    output_hash: str | None,
    cache_key: str | None,
    evidence_retriever: EvidenceRetriever = retrieve_module_synthesis_evidence,
) -> dict[str, Any]:
    try:
        evidence_bundle = evidence_retriever(
            spec,
            use_signature=use_signature,
            receipts_path=module_synthesis_evidence_receipts_path(promotion_target),
            oracle_index_path=module_synthesis_evidence_oracle_index_path(
                promotion_target
            ),
            oracle_top_k=module_synthesis_evidence_oracle_top_k(),
        )
    except Exception as exc:
        return build_unavailable_synthesis_diagnostics(
            spec,
            use_signature=use_signature,
            promotion_target=promotion_target,
            synthesis_payload=synthesis_payload,
            selected_candidate_id=selected_candidate_id,
            output_hash=output_hash,
            cache_key=cache_key,
            retrieval_error={
                "type": exc.__class__.__name__,
                "message": str(exc),
            },
        )

    payload = evidence_bundle.to_dict()
    current_candidates = extract_module_synthesis_candidate_prior_inputs(
        synthesis_payload
    )
    ranked_candidates = extract_module_synthesis_ranked_candidate_inputs(
        synthesis_payload
    )
    ranked_candidate_comparison_inputs = (
        extract_module_synthesis_ranked_candidate_comparison_inputs(synthesis_payload)
    )
    retrieval_status = (
        "degraded"
        if evidence_bundle.receipt_scan_error_count > 0
        or evidence_bundle.oracle_lookup_status == "unavailable"
        else "ok"
    )
    candidate_winner_priors = build_module_synthesis_candidate_winner_priors(
        evidence_bundle,
        current_candidates=current_candidates,
    )
    candidate_prior_audit = build_module_synthesis_candidate_prior_audit(
        candidate_winner_priors,
        current_candidates=current_candidates,
        ranked_candidates=ranked_candidates,
        selected_candidate_id=selected_candidate_id,
    )
    candidate_prior_divergence_explanation = (
        build_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit,
            ranked_candidate_comparison_inputs=ranked_candidate_comparison_inputs,
        )
    )
    candidate_prior_readiness_advisory = (
        build_module_synthesis_candidate_prior_readiness_advisory(
            evidence_bundle,
        )
    )
    candidate_prior_counterfactual_advisory = (
        build_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation,
            candidate_prior_audit,
            ranked_candidate_comparison_inputs=ranked_candidate_comparison_inputs,
        )
    )
    shadow_predictive_ranking_advisory = (
        build_module_synthesis_shadow_predictive_ranking_advisory(
            candidate_winner_priors,
            candidate_prior_audit,
            candidate_prior_divergence_explanation,
            candidate_prior_readiness_advisory,
            candidate_prior_counterfactual_advisory,
            ranked_candidate_comparison_inputs=ranked_candidate_comparison_inputs,
        )
    )
    governed_policy_evaluations = build_module_synthesis_governed_policy_evaluations(
        synthesis=synthesis_payload,
        candidate_winner_priors=candidate_winner_priors,
        candidate_prior_audit=candidate_prior_audit,
        candidate_prior_divergence_explanation=(candidate_prior_divergence_explanation),
        candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
        candidate_prior_counterfactual_advisory=(
            candidate_prior_counterfactual_advisory
        ),
        shadow_predictive_ranking_advisory=shadow_predictive_ranking_advisory,
        ranked_candidate_comparison_inputs=ranked_candidate_comparison_inputs,
    )
    promotion_eligibility_nominations = (
        build_module_synthesis_promotion_eligibility_nominations(
            synthesis=synthesis_payload,
            governed_policy_evaluations=governed_policy_evaluations,
            ranked_candidate_comparison_inputs=ranked_candidate_comparison_inputs,
        )
    )
    return {
        "evidence_bundle_version": "v1",
        "retrieval_status": retrieval_status,
        "evidence_summary": {
            "exact_match_receipt_count": len(evidence_bundle.exact_match_receipts),
            "positive_evidence_count": evidence_bundle.positive_evidence_count,
            "oracle_neighbor_count": len(evidence_bundle.oracle_neighbors),
            "oracle_index_available": evidence_bundle.oracle_index_available,
            "oracle_lookup_status": evidence_bundle.oracle_lookup_status,
            "receipt_scan_error_count": evidence_bundle.receipt_scan_error_count,
        },
        "evidence_bundle": payload,
        "historical_convergence_advisory": build_module_synthesis_history_advisory(
            evidence_bundle,
            selected_candidate_id=selected_candidate_id,
            output_hash=output_hash,
            cache_key=cache_key,
        ),
        "candidate_winner_priors": candidate_winner_priors,
        "candidate_prior_audit": candidate_prior_audit,
        "candidate_prior_divergence_explanation": (
            candidate_prior_divergence_explanation
        ),
        "candidate_prior_readiness_advisory": candidate_prior_readiness_advisory,
        "candidate_prior_counterfactual_advisory": (
            candidate_prior_counterfactual_advisory
        ),
        "shadow_predictive_ranking_advisory": shadow_predictive_ranking_advisory,
        "governed_policy_evaluations": governed_policy_evaluations,
        "promotion_eligibility_nominations": promotion_eligibility_nominations,
    }


def synthesis_diagnostics_for_artifact(
    spec: ModuleSpec,
    *,
    code: str,
    use_signature: bool,
    template_version: Optional[str],
    promotion_target: Optional[Path],
    synthesis_payload: dict[str, Any] | None,
    selected_candidate_id: str | None,
    evidence_retriever: EvidenceRetriever = retrieve_module_synthesis_evidence,
) -> dict[str, Any]:
    return build_synthesis_diagnostics(
        spec,
        use_signature=use_signature,
        promotion_target=promotion_target,
        synthesis_payload=synthesis_payload,
        selected_candidate_id=selected_candidate_id,
        output_hash=sha256_text(code),
        cache_key=module_cache_key(
            spec,
            use_signature=use_signature,
            template_version=template_version,
        ),
        evidence_retriever=evidence_retriever,
    )
