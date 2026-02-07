from __future__ import annotations

from pathlib import Path

from dspx.services.signature_quality import (
    evaluate_quality_gates,
    read_quality_events,
    summarize_quality_events,
)
from dspx.services.signature_quality_corpus import (
    PROVIDER_CORPUS_GATE,
    build_provider_corpus_quality_events,
    load_provider_corpus_cases,
    write_quality_events_jsonl,
)


_PROVIDER_CASES = Path(__file__).parent / "golden" / "signature_provider_cases.json"


def test_provider_corpus_quality_gate_profile_passes() -> None:
    cases = load_provider_corpus_cases(_PROVIDER_CASES)
    events = build_provider_corpus_quality_events(cases)

    providers = {str(event.get("provider") or "") for event in events}
    assert providers == {
        "pi-rpc",
        "openrouter",
        "codex-exec",
        "claude-cli",
        "gemini-cli",
    }

    summary = summarize_quality_events(events, run_kind="signature-gen")
    gates = evaluate_quality_gates(summary, gate=PROVIDER_CORPUS_GATE)

    assert summary["runs_total"] == 5
    assert gates["overall_pass"] is True
    assert summary["attempts_p95"] == 1.0

    by_provider = summary["by_provider"]
    for provider in providers:
        assert by_provider[provider]["runs_total"] == 1


def test_provider_corpus_quality_log_roundtrip(tmp_path: Path) -> None:
    cases = load_provider_corpus_cases(_PROVIDER_CASES)
    events = build_provider_corpus_quality_events(cases)

    log_path = tmp_path / "provider_quality.jsonl"
    write_quality_events_jsonl(events, log_path)
    loaded = read_quality_events(log_path)

    assert len(loaded) == len(events)
    assert {str(row.get("provider") or "") for row in loaded} == {
        "pi-rpc",
        "openrouter",
        "codex-exec",
        "claude-cli",
        "gemini-cli",
    }
