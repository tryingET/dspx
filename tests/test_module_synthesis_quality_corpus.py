from __future__ import annotations

from pathlib import Path

from dspx.services.module_synthesis_corpus import (
    MODULE_SYNTHESIS_CORPUS_GATE,
    build_module_synthesis_quality_events,
    load_module_synthesis_cases,
    write_module_quality_events_jsonl,
)
from dspx.services.module_synthesis_quality import (
    evaluate_module_quality_gates,
    read_module_quality_events,
    summarize_module_quality_events,
)


_CORPUS = Path(__file__).parent / "golden" / "module_synthesis_cases.json"


def test_module_synthesis_quality_gate_profile_passes(tmp_path: Path) -> None:
    cases = load_module_synthesis_cases(_CORPUS)
    events = build_module_synthesis_quality_events(
        cases,
        workspace_root=tmp_path / "module-synthesis-corpus",
    )

    summary = summarize_module_quality_events(events, run_kind="module-gen")
    gates = evaluate_module_quality_gates(
        summary,
        gate=MODULE_SYNTHESIS_CORPUS_GATE,
    )

    assert summary["runs_total"] == 3
    assert summary["signature_runs"] == 1
    assert summary["candidate_count_avg"] == 3.0
    assert summary["validation_pass_rate"] == 1.0
    assert summary["smoke_pass_rate"] == 1.0
    assert summary["selection_integrity_rate"] == 1.0
    assert summary["receipt_coverage_rate"] == 1.0
    assert summary["promotion_receipt_coverage_rate"] == 1.0
    assert gates["overall_pass"] is True


def test_module_synthesis_quality_log_roundtrip(tmp_path: Path) -> None:
    cases = load_module_synthesis_cases(_CORPUS)
    events = build_module_synthesis_quality_events(
        cases,
        workspace_root=tmp_path / "module-synthesis-corpus-roundtrip",
    )

    log_path = tmp_path / "module_synthesis_quality.jsonl"
    write_module_quality_events_jsonl(events, log_path)
    loaded = read_module_quality_events(log_path)

    assert len(loaded) == len(events)
    assert {str(row.get("case_name") or "") for row in loaded} == {
        "summarizer_simple",
        "intent_signature",
        "router_multi_io_promoted",
    }
