from __future__ import annotations

from dspx.services.module_synthesis_quality import (
    ModuleSynthesisQualityGate,
    evaluate_module_quality_gates,
    format_module_quality_summary,
    summarize_module_quality_events,
)


def test_module_synthesis_quality_summary_and_gates() -> None:
    events = [
        {
            "run_kind": "module-gen",
            "candidate_count": 3,
            "selected_candidate_rank": 1,
            "use_signature": False,
            "validation_pass_count": 3,
            "validation_total": 3,
            "smoke_pass_count": 3,
            "smoke_total": 3,
            "selection_integrity": True,
            "receipt_coverage": True,
            "promotion_requested": False,
            "promotion_receipt_coverage": True,
        },
        {
            "run_kind": "module-gen",
            "candidate_count": 3,
            "selected_candidate_rank": 1,
            "use_signature": True,
            "validation_pass_count": 3,
            "validation_total": 3,
            "smoke_pass_count": 3,
            "smoke_total": 3,
            "selection_integrity": True,
            "receipt_coverage": False,
            "promotion_requested": True,
            "promotion_receipt_coverage": False,
        },
    ]

    summary = summarize_module_quality_events(events, run_kind="module-gen")
    assert summary["runs_total"] == 2
    assert summary["signature_runs"] == 1
    assert summary["candidate_count_avg"] == 3.0
    assert summary["selected_rank_distribution"] == {"1": 2}
    assert summary["validation_pass_rate"] == 1.0
    assert summary["smoke_pass_rate"] == 1.0
    assert summary["selection_integrity_rate"] == 1.0
    assert summary["receipt_coverage_rate"] == 0.5
    assert summary["promotion_receipt_coverage_rate"] == 0.0

    gates = evaluate_module_quality_gates(
        summary,
        gate=ModuleSynthesisQualityGate(
            min_validation_pass_rate=1.0,
            min_smoke_pass_rate=1.0,
            min_selection_integrity_rate=1.0,
            min_receipt_coverage_rate=0.5,
            min_promotion_receipt_coverage_rate=0.0,
        ),
    )
    assert gates["overall_pass"] is True

    strict = evaluate_module_quality_gates(
        summary,
        gate=ModuleSynthesisQualityGate(
            min_validation_pass_rate=1.0,
            min_smoke_pass_rate=1.0,
            min_selection_integrity_rate=1.0,
            min_receipt_coverage_rate=1.0,
            min_promotion_receipt_coverage_rate=1.0,
        ),
    )
    assert strict["overall_pass"] is False

    text = format_module_quality_summary(summary, strict)
    assert "module synthesis quality summary" in text
    assert "gates=FAIL" in text
