from __future__ import annotations

from pathlib import Path

from dspx.services.signature_quality import (
    SignatureQualityGate,
    append_quality_event,
    evaluate_quality_gates,
    format_quality_summary,
    read_quality_events,
    summarize_quality_events,
)


def test_signature_quality_append_and_read(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path / "quality.jsonl"
    monkeypatch.setenv("DSPX_SIGNATURE_QUALITY_LOG", str(log))
    monkeypatch.setenv("DSPX_SIGNATURE_QUALITY_ENABLE", "1")

    append_quality_event(
        {
            "run_kind": "signature-gen",
            "provider": "stub",
            "attempts_used": 1,
            "fallback_used": False,
            "validation_pass_count": 1,
            "validation_total": 1,
            "smoke_pass_count": 1,
            "smoke_total": 1,
        }
    )

    events = read_quality_events(log)
    assert len(events) == 1
    assert events[0]["provider"] == "stub"
    assert "timestamp" in events[0]


def test_signature_quality_summary_and_gates() -> None:
    events = [
        {
            "run_kind": "signature-gen",
            "provider": "pi-rpc",
            "attempts_used": 1,
            "fallback_used": False,
            "validation_pass_count": 1,
            "validation_total": 1,
            "smoke_pass_count": 1,
            "smoke_total": 1,
        },
        {
            "run_kind": "signature-gen",
            "provider": "pi-rpc",
            "attempts_used": 2,
            "fallback_used": True,
            "validation_pass_count": 1,
            "validation_total": 2,
            "smoke_pass_count": 1,
            "smoke_total": 2,
        },
        {
            "run_kind": "signature-gen",
            "provider": "openrouter",
            "attempts_used": 3,
            "fallback_used": False,
            "validation_pass_count": 3,
            "validation_total": 3,
            "smoke_pass_count": 3,
            "smoke_total": 3,
        },
    ]

    summary = summarize_quality_events(events, run_kind="signature-gen")
    assert summary["runs_total"] == 3
    assert abs(float(summary["fallback_rate"]) - (1.0 / 3.0)) < 1e-9
    assert summary["attempts_used_distribution"] == {"1": 1, "2": 1, "3": 1}
    assert summary["by_provider"]["pi-rpc"]["runs_total"] == 2

    gates = evaluate_quality_gates(
        summary,
        gate=SignatureQualityGate(
            max_fallback_rate=0.5,
            max_attempts_p95=3.0,
            min_validation_pass_rate=0.7,
            min_smoke_pass_rate=0.7,
        ),
    )
    assert gates["overall_pass"] is True

    strict = evaluate_quality_gates(
        summary,
        gate=SignatureQualityGate(
            max_fallback_rate=0.0,
            max_attempts_p95=1.0,
            min_validation_pass_rate=0.99,
            min_smoke_pass_rate=0.99,
        ),
    )
    assert strict["overall_pass"] is False

    txt = format_quality_summary(summary, strict)
    assert "signature quality summary" in txt
    assert "gates=FAIL" in txt
