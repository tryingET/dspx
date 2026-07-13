# summary: "Tests receipt-bound program-specific comparison jury execution, reuse, drift checks, and no replay."

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
import dspx.services.program_foundry_gepa_comparison_jury as comparison_jury


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "foundry"
    experiment = root / "gepa-experiment"
    source_root = root / "candidate"
    candidate_root = experiment / "materialized-candidate"
    experiment.mkdir(parents=True)
    source_root.mkdir()
    candidate_root.mkdir()
    receipt = experiment / "consumption-receipt.json"
    receipt.write_text('{"status":"ok"}', encoding="utf-8")
    execution_receipt = experiment / "execution-receipt.json"
    execution_receipt.write_text('{"status":"ok"}', encoding="utf-8")
    source_manifest = source_root / "manifest.json"
    source_manifest.write_text('{"source":true}', encoding="utf-8")
    candidate_manifest = candidate_root / "manifest.json"
    candidate_manifest.write_text(
        json.dumps(
            {
                "schema_version": "program-candidate-assembly-v1",
                "candidate_assembly": {
                    "candidate_id": "gepa-candidate",
                    "root_path": str(candidate_root),
                },
            }
        ),
        encoding="utf-8",
    )
    for name, schema in (
        ("jury.json", "program-jury-v1"),
        ("jury_selection.json", "program-jury-selection-v1"),
        ("jury_rubric.json", "program-jury-rubric-v1"),
    ):
        (candidate_root / name).write_text(
            json.dumps({"schema_version": schema}), encoding="utf-8"
        )
    comparison = experiment / "candidate-comparison.json"
    comparison.write_text(
        '{"schema_version":"program-refinement-candidate-comparison-v1","status":"compared"}',
        encoding="utf-8",
    )
    validated = {
        "root": root,
        "experiment_root": experiment,
        "receipt": {"status": "ok"},
        "receipt_path": receipt,
        "receipt_sha256": _sha256(receipt),
        "proposal_id": "a" * 64,
        "source_manifest_path": source_manifest,
        "source_manifest_sha256": _sha256(source_manifest),
        "candidate_manifest_path": candidate_manifest,
        "candidate_manifest_sha256": _sha256(candidate_manifest),
        "comparison_path": comparison,
        "comparison_sha256": _sha256(comparison),
        "execution_receipt_path": execution_receipt,
        "execution_receipt_sha256": _sha256(execution_receipt),
    }
    return receipt, validated


def _model_result(validated: dict[str, Any]) -> dict[str, Any]:
    manifest = Path(validated["candidate_manifest_path"])
    root = manifest.parent
    comparison = Path(validated["comparison_path"])
    counts = {
        "supports_review_evidence": 1,
        "withhold": 0,
        "reject": 0,
        "request_more_evidence": 0,
        "failed": 0,
    }
    return {
        "schema_version": "program-model-jury-results-v1",
        "status": "executed",
        "identity": {"candidate_id": "gepa-candidate"},
        "created_from": {
            "manifest_path": str(manifest),
            "manifest_sha256": _sha256(manifest),
            "jury_path": str(root / "jury.json"),
            "jury_sha256": _sha256(root / "jury.json"),
            "jury_selection_path": str(root / "jury_selection.json"),
            "jury_selection_sha256": _sha256(root / "jury_selection.json"),
            "jury_rubric_path": str(root / "jury_rubric.json"),
            "jury_rubric_sha256": _sha256(root / "jury_rubric.json"),
            "evidence_paths": [str(comparison)],
        },
        "jury": {
            "selected_juror_count": 1,
            "provider_backed_model_calls": True,
        },
        "adjudicator": {"promotion_authority": False},
        "evidence": {
            "entry_count": 1,
            "entries": [
                {
                    "kind": "explicit_evidence",
                    "path": str(comparison),
                    "sha256": _sha256(comparison),
                }
            ],
        },
        "juror_results": [
            {
                "juror_id": "quality",
                "status": "judged",
                "judgment": {
                    "outcome": "supports_review_evidence",
                    "improvement_requests": [],
                },
            }
        ],
        "aggregate": {
            "judgment_counts": counts,
            "recommendation": "supports_review_evidence_only",
        },
        "interpretation": {"ready_for_promotion_decision": False},
        "effect": {
            "model_jury_evidence_only": True,
            "program_files_mutated": False,
            "promotion_review_mutated": False,
            "new_candidate_generated": False,
            "oracle_index_mutated": False,
            "external_authority_mutated": False,
            "ak_mutated": False,
            "governance_mutated": False,
        },
        "non_authority": {
            "promotion_approval": False,
            "ranking_or_winner_selection": False,
            "domain_acceptance": False,
            "external_authority_apply": False,
            "canonical_mutation": False,
        },
    }


def _install_success(
    monkeypatch: pytest.MonkeyPatch,
    validated: dict[str, Any],
    calls: list[dict[str, Any]],
) -> None:
    monkeypatch.setattr(
        comparison_jury,
        "validate_successful_program_foundry_gepa_consumption_receipt",
        lambda path, **kwargs: dict(validated),
    )

    def build(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return _model_result(validated)

    monkeypatch.setattr(
        comparison_jury,
        "build_program_model_jury_execution_result",
        build,
    )


def test_executes_program_specific_comparison_jury_once_and_reuses_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    _install_success(monkeypatch, validated, calls)

    first = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider="fixture-provider",
        max_jurors=1,
    )
    second = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider="fixture-provider",
        max_jurors=1,
    )

    assert first["status"] == "ok"
    assert first["reused"] is False
    assert second["reused"] is True
    assert len(calls) == 1
    assert calls[0]["manifest_path"] == validated["candidate_manifest_path"]
    assert calls[0]["evidence_paths"] == [validated["comparison_path"]]
    assert first["effect"]["program_specific_jury_executed"] is True
    assert first["effect"]["winner_selected"] is False
    assert first["non_authority"]["promotion_authority"] is False
    experiment = receipt.parent
    assert (experiment / "comparison-jury-attempt.json").exists()
    assert (experiment / "comparison-jury-results.json").exists()
    assert (experiment / "comparison-jury-receipt.json").exists()


def test_comparison_jury_attempt_blocks_replay_after_possible_provider_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    monkeypatch.setattr(
        comparison_jury,
        "validate_successful_program_foundry_gepa_consumption_receipt",
        lambda path, **kwargs: dict(validated),
    )
    calls = 0

    def crash(**kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise RuntimeError("provider call may have occurred")

    monkeypatch.setattr(
        comparison_jury,
        "build_program_model_jury_execution_result",
        crash,
    )
    with pytest.raises(RuntimeError, match="may have occurred"):
        comparison_jury.execute_program_foundry_gepa_comparison_jury(
            consumption_receipt_path=receipt,
            provider="fixture-provider",
        )
    blocked = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider="fixture-provider",
    )
    assert calls == 1
    assert blocked["status"] == "blocked_indeterminate"
    assert blocked["effect_disposition"] == (
        "one_or_more_provider_juror_calls_may_have_occurred"
    )


def test_comparison_jury_rejects_drift_and_changed_replay_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    _install_success(monkeypatch, validated, calls)
    comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider="fixture-provider",
    )

    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="execution request drifted",
    ):
        comparison_jury.execute_program_foundry_gepa_comparison_jury(
            consumption_receipt_path=receipt,
            provider="different-provider",
        )

    Path(validated["comparison_path"]).write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="comparison changed before",
    ):
        comparison_jury.execute_program_foundry_gepa_comparison_jury(
            consumption_receipt_path=receipt,
            provider="fixture-provider",
        )
    assert len(calls) == 1


def test_comparison_jury_cli_forwards_only_consumption_receipt_and_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = tmp_path / "consumption-receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("dspx.cli.utils.ensure_env", lambda provider: None)

    def execute(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"status": "ok", "reused": False}

    monkeypatch.setattr(
        comparison_jury,
        "execute_program_foundry_gepa_comparison_jury",
        execute,
    )
    result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "jury-foundry-gepa-comparison",
            "--receipt",
            str(receipt),
            "--provider",
            "fixture-provider",
            "--max-jurors",
            "2",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "consumption_receipt_path": receipt,
            "provider": "fixture-provider",
            "adjudicator_id": "local_foundry_adjudicator",
            "adjudicator_kind": "local_foundry_adjudicator",
            "adjudicator_repo": None,
            "max_jurors": 2,
        }
    ]
