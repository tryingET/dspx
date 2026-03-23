from __future__ import annotations

from pathlib import Path

from dspx.dtos import ModuleSpec
from dspx.services.module_service import run_generate
from dspx.services.module_synthesis_quality import (
    build_module_quality_event_from_metadata,
    read_module_quality_events,
)


def test_run_generate_appends_module_quality_event(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_SYNTHESIS_DIR", str(tmp_path / "synthesis"))
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_QUALITY_LOG",
        str(tmp_path / "quality" / "module_quality.jsonl"),
    )
    monkeypatch.setenv("DSPX_MODULE_SYNTHESIS_QUALITY_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "0")

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    art = run_generate(spec, use_signature=False)

    quality_event = art.metadata["quality_event"]
    assert quality_event["run_kind"] == "module-gen"
    assert quality_event["selection_integrity"] is True
    assert quality_event["receipt_coverage"] is True
    assert quality_event["promotion_receipt_coverage"] is True
    assert quality_event["selected_candidate_rank"] == 1

    loaded = read_module_quality_events(
        Path(tmp_path / "quality" / "module_quality.jsonl")
    )
    assert len(loaded) == 1
    assert loaded[0]["selected_candidate_id"] == art.metadata["selected_candidate_id"]
    assert loaded[0]["receipt_invariant_issues"] == []


def test_module_quality_event_detects_receipt_drift() -> None:
    metadata = {
        "run_summary": {"backend": "synthesis_runtime"},
        "selected_candidate_id": "cand-a",
        "selected_candidate_rank": 1,
        "ranking_policy_id": "module.v7.multi-candidate-ranked",
        "ranked_candidate_ids": ["cand-a"],
        "validation_pass_count": 1,
        "validation_total": 1,
        "smoke_pass_count": 1,
        "smoke_total": 1,
        "candidate_count": 1,
        "synthesis": {
            "request": {},
            "strategy": {},
            "selection_policy": {"policy_id": "module.v7.multi-candidate-ranked"},
            "promotion_shell": {"selected_candidate_id": "cand-b", "status": "ready"},
            "promotion_decision": {
                "candidate_id": "cand-a",
                "metadata": {
                    "ranked_candidates": [
                        {"candidate_id": "cand-a", "rank": 1},
                    ]
                },
            },
            "candidates": [{"candidate_id": "cand-a"}],
            "candidate_workspaces": [{"candidate_id": "cand-a"}],
            "evaluations": [{"candidate_id": "cand-a"}],
        },
    }

    event = build_module_quality_event_from_metadata(
        metadata,
        use_signature=False,
        promotion_requested=False,
        output_hash="deadbeef",
    )

    assert event.receipt_invariants.ok is False
    assert (
        "promotion_shell selected_candidate_id drift" in event.receipt_invariants.issues
    )
    assert "selected candidate content hash missing" in event.receipt_invariants.issues
    assert event.payload["receipt_coverage"] is False
    assert event.payload["selection_integrity"] is False


def test_module_quality_event_detects_output_hash_drift() -> None:
    metadata = {
        "run_summary": {"backend": "synthesis_runtime"},
        "selected_candidate_id": "cand-a",
        "selected_candidate_rank": 1,
        "ranking_policy_id": "module.v7.multi-candidate-ranked",
        "ranked_candidate_ids": ["cand-a"],
        "validation_pass_count": 1,
        "validation_total": 1,
        "smoke_pass_count": 1,
        "smoke_total": 1,
        "candidate_count": 1,
        "synthesis": {
            "request": {},
            "strategy": {},
            "selection_policy": {"policy_id": "module.v7.multi-candidate-ranked"},
            "promotion_shell": {"selected_candidate_id": "cand-a", "status": "ready"},
            "promotion_decision": {
                "candidate_id": "cand-a",
                "metadata": {
                    "ranked_candidates": [{"candidate_id": "cand-a", "rank": 1}]
                },
            },
            "candidates": [
                {"candidate_id": "cand-a", "artifact": {"content_hash": "abc123"}}
            ],
            "candidate_workspaces": [{"candidate_id": "cand-a"}],
            "evaluations": [{"candidate_id": "cand-a"}],
        },
    }

    event = build_module_quality_event_from_metadata(
        metadata,
        use_signature=False,
        promotion_requested=False,
        output_hash="deadbeef",
    )

    assert event.receipt_invariants.ok is False
    assert (
        "output hash drift from selected candidate artifact"
        in event.receipt_invariants.issues
    )
    assert event.payload["receipt_coverage"] is False
