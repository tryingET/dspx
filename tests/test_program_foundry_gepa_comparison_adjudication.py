# summary: "Tests deterministic receipt-bound local adjudication of foundry GEPA comparison juries."

from __future__ import annotations

from contextlib import contextmanager

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
import dspx.services.program_foundry_gepa_comparison_adjudication as adjudication


def _validated_jury(
    tmp_path: Path,
    *,
    recommendation: str,
    counts: dict[str, int],
    jury_status: str = "executed",
) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "foundry"
    experiment = root / "gepa-experiment"
    source = root / "candidate" / "manifest.json"
    candidate = experiment / "materialized-candidate" / "manifest.json"
    experiment.mkdir(parents=True)
    source.parent.mkdir()
    candidate.parent.mkdir()
    receipt = experiment / "comparison-jury-receipt.json"
    jury_result = experiment / "comparison-jury-results.json"
    consumption = experiment / "consumption-receipt.json"
    comparison = experiment / "candidate-comparison.json"
    for path in (source, candidate, receipt, jury_result, consumption, comparison):
        path.write_text("{}", encoding="utf-8")
    aggregate = {
        "judgment_counts": counts,
        "blocking_concerns_present": bool(
            counts["reject"] or counts["request_more_evidence"] or counts["failed"]
        ),
        "recommendation": recommendation,
        "unique_improvement_requests": [],
    }
    validated = {
        "root": root,
        "experiment_root": experiment,
        "proposal_id": "a" * 64,
        "jury_receipt_path": receipt,
        "jury_receipt_sha256": "jury-receipt-hash",
        "jury_result_path": jury_result,
        "jury_result_sha256": "jury-result-hash",
        "receipt_path": consumption,
        "receipt_sha256": "consumption-receipt-hash",
        "source_manifest_path": source,
        "source_manifest_sha256": "source-hash",
        "candidate_manifest_path": candidate,
        "candidate_manifest_sha256": "candidate-hash",
        "comparison_path": comparison,
        "comparison_sha256": "comparison-hash",
        "jury_status": jury_status,
        "aggregate": aggregate,
    }
    return receipt, validated


def _counts(**overrides: int) -> dict[str, int]:
    counts = {
        "supports_review_evidence": 0,
        "withhold": 0,
        "reject": 0,
        "request_more_evidence": 0,
        "failed": 0,
    }
    counts.update(overrides)
    return counts


@pytest.mark.parametrize(
    ("recommendation", "counts", "jury_status", "disposition", "local_state"),
    [
        (
            "supports_review_evidence_only",
            _counts(supports_review_evidence=3),
            "executed",
            "promote_locally",
            "eligible_local_candidate",
        ),
        (
            "reject_or_redesign",
            _counts(reject=2),
            "executed",
            "reject_locally",
            "rejected_local_candidate",
        ),
        (
            "reject_or_redesign",
            _counts(supports_review_evidence=1, reject=1),
            "executed",
            "require_review",
            "held_for_local_review",
        ),
        (
            "request_more_evidence",
            _counts(request_more_evidence=1),
            "executed",
            "require_review",
            "held_for_local_review",
        ),
        (
            "withhold_until_failed_jurors_rerun",
            _counts(failed=1),
            "executed_with_failures",
            "require_review",
            "held_for_local_review",
        ),
    ],
)
def test_adjudication_policy_records_bounded_local_dispositions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    recommendation: str,
    counts: dict[str, int],
    jury_status: str,
    disposition: str,
    local_state: str,
) -> None:
    receipt, validated = _validated_jury(
        tmp_path,
        recommendation=recommendation,
        counts=counts,
        jury_status=jury_status,
    )
    monkeypatch.setattr(
        adjudication,
        "validate_successful_program_foundry_gepa_comparison_jury_receipt",
        lambda path, **kwargs: dict(validated),
    )

    first = adjudication.adjudicate_program_foundry_gepa_comparison(
        comparison_jury_receipt_path=receipt
    )
    second = adjudication.adjudicate_program_foundry_gepa_comparison(
        comparison_jury_receipt_path=receipt
    )

    assert first["status"] == "recorded"
    assert first["disposition"] == disposition
    assert first["local_candidate_state"] == local_state
    assert first["reused"] is False
    assert second["reused"] is True
    assert first["policy"]["models_rerun"] is False
    assert first["effect"]["bounded_local_disposition_recorded"] is True
    assert first["effect"]["candidate_files_mutated"] is False
    assert first["effect"]["production_activation_applied"] is False
    assert first["non_authority"]["production_promotion_authority"] is False
    assert (receipt.parent / "comparison-adjudication.json").exists()


def test_adjudication_commit_followed_by_lock_release_failure_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _validated_jury(
        tmp_path,
        recommendation="supports_review_evidence_only",
        counts=_counts(supports_review_evidence=1),
    )
    monkeypatch.setattr(
        adjudication,
        "validate_successful_program_foundry_gepa_comparison_jury_receipt",
        lambda path, **kwargs: dict(validated),
    )
    real_lock = adjudication.foundry_lock

    @contextmanager
    def failing_release(root: Path):
        with real_lock(root) as descriptor:
            yield descriptor
        raise OSError("simulated lock release failure")

    monkeypatch.setattr(adjudication, "foundry_lock", failing_release)
    with pytest.raises(
        adjudication.ProgramFoundryGepaComparisonAdjudicationIndeterminateError,
        match="may have committed before lock release",
    ):
        adjudication.adjudicate_program_foundry_gepa_comparison(
            comparison_jury_receipt_path=receipt
        )
    assert (receipt.parent / "comparison-adjudication.json").exists()


def test_adjudication_rejects_malformed_counts_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _validated_jury(
        tmp_path,
        recommendation="supports_review_evidence_only",
        counts=_counts(supports_review_evidence=1),
    )
    validated["aggregate"]["judgment_counts"]["unexpected"] = 1
    monkeypatch.setattr(
        adjudication,
        "validate_successful_program_foundry_gepa_comparison_jury_receipt",
        lambda path, **kwargs: dict(validated),
    )

    with pytest.raises(
        adjudication.ProgramFoundryGepaComparisonAdjudicationError,
        match="not policy-recognized",
    ):
        adjudication.adjudicate_program_foundry_gepa_comparison(
            comparison_jury_receipt_path=receipt
        )
    assert not (receipt.parent / "comparison-adjudication.json").exists()


def test_adjudication_reuse_rejects_jury_lineage_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _validated_jury(
        tmp_path,
        recommendation="supports_review_evidence_only",
        counts=_counts(supports_review_evidence=2),
    )
    current = dict(validated)
    monkeypatch.setattr(
        adjudication,
        "validate_successful_program_foundry_gepa_comparison_jury_receipt",
        lambda path, **kwargs: dict(current),
    )
    adjudication.adjudicate_program_foundry_gepa_comparison(
        comparison_jury_receipt_path=receipt
    )
    current["jury_receipt_sha256"] = "drifted"

    with pytest.raises(
        adjudication.ProgramFoundryGepaComparisonAdjudicationError,
        match="drifted",
    ):
        adjudication.adjudicate_program_foundry_gepa_comparison(
            comparison_jury_receipt_path=receipt
        )


def test_adjudication_translates_terminal_revalidation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _validated_jury(
        tmp_path,
        recommendation="supports_review_evidence_only",
        counts=_counts(supports_review_evidence=1),
    )
    calls = 0

    def validate(path: Path, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return dict(validated)
        raise adjudication.ProgramFoundryGepaComparisonJuryError("lineage drift")

    monkeypatch.setattr(
        adjudication,
        "validate_successful_program_foundry_gepa_comparison_jury_receipt",
        validate,
    )
    with pytest.raises(
        adjudication.ProgramFoundryGepaComparisonAdjudicationError,
        match="lineage drift",
    ):
        adjudication.adjudicate_program_foundry_gepa_comparison(
            comparison_jury_receipt_path=receipt
        )
    assert not (receipt.parent / "comparison-adjudication.json").exists()


def test_adjudication_rejects_dangling_output_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _validated_jury(
        tmp_path,
        recommendation="withhold_for_owner_review",
        counts=_counts(withhold=1),
    )
    monkeypatch.setattr(
        adjudication,
        "validate_successful_program_foundry_gepa_comparison_jury_receipt",
        lambda path, **kwargs: dict(validated),
    )
    output = receipt.parent / "comparison-adjudication.json"
    output.symlink_to(receipt.parent / "missing.json")

    with pytest.raises(
        adjudication.ProgramFoundryGepaComparisonAdjudicationError,
        match="must not be a symlink",
    ):
        adjudication.adjudicate_program_foundry_gepa_comparison(
            comparison_jury_receipt_path=receipt
        )


def test_adjudication_cli_forwards_only_canonical_jury_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = tmp_path / "comparison-jury-receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    calls: list[Path] = []

    def fake_adjudicate(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["comparison_jury_receipt_path"])
        return {
            "status": "recorded",
            "disposition": "require_review",
            "reused": False,
        }

    monkeypatch.setattr(
        adjudication,
        "adjudicate_program_foundry_gepa_comparison",
        fake_adjudicate,
    )
    result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "adjudicate-foundry-gepa-comparison",
            "--receipt",
            str(receipt),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [receipt]
