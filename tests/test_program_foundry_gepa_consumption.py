# summary: "Tests successful foundry GEPA receipt consumption, terminal reuse, drift detection, and downstream no-replay."

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
import dspx.services.program_foundry_gepa_consumption as consumption


def _execution_fixture(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "foundry"
    experiment = root / "gepa-experiment"
    candidate = root / "candidate"
    experiment.mkdir(parents=True)
    candidate.mkdir()
    source_manifest = candidate / "manifest.json"
    source_manifest.write_text(
        '{"schema_version":"program-candidate-assembly-v1"}', encoding="utf-8"
    )
    gepa_result = experiment / "gepa-result.json"
    gepa_result.write_text(
        '{"schema_version":"program-refinement-gepa-result-v1"}', encoding="utf-8"
    )
    execution_receipt = experiment / "execution-receipt.json"
    execution_receipt.write_text('{"status":"ok"}', encoding="utf-8")
    execution = {
        "proposal_id": "a" * 64,
        "root": root,
        "experiment_root": experiment,
        "execution_receipt": {
            "status": "ok",
            "result_sha256": hashlib.sha256(gepa_result.read_bytes()).hexdigest(),
        },
        "execution_receipt_path": execution_receipt,
        "execution_receipt_sha256": hashlib.sha256(
            execution_receipt.read_bytes()
        ).hexdigest(),
        "manifest_path": source_manifest,
        "source_manifest_sha256": hashlib.sha256(
            source_manifest.read_bytes()
        ).hexdigest(),
        "result_path": gepa_result,
    }
    return execution_receipt, execution


def _install_success_stubs(
    monkeypatch: pytest.MonkeyPatch,
    execution: dict[str, Any],
    calls: list[dict[str, Any]],
) -> None:
    monkeypatch.setattr(
        consumption,
        "validate_successful_program_foundry_gepa_execution_receipt",
        lambda path, **kwargs: execution,
    )

    def workflow(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        candidate_root = Path(kwargs["outdir"])
        candidate_root.mkdir()
        candidate_manifest = candidate_root / "manifest.json"
        candidate_manifest.write_text('{"candidate":"local"}', encoding="utf-8")
        candidate_result = {
            "schema_version": "program-refinement-gepa-candidate-result-v1",
            "status": "materialized",
            "candidate": {
                "manifest_path": str(candidate_manifest),
                "root_path": str(candidate_root),
            },
        }
        Path(kwargs["gepa_candidate_result_out"]).write_text(
            json.dumps(candidate_result), encoding="utf-8"
        )
        comparison = {
            "schema_version": "program-refinement-candidate-comparison-v1",
            "status": "compared",
        }
        Path(kwargs["comparison_out_path"]).write_text(
            json.dumps(comparison), encoding="utf-8"
        )
        return {
            "schema_version": "program-refinement-gepa-generate-and-compare-result-v1",
            "status": "materialized_and_compared_gepa_candidate",
            "generation": candidate_result,
            "comparison_sidecar": {
                "path": str(kwargs["comparison_out_path"]),
                "status": "compared",
            },
            "effect": {
                "local_gepa_candidate_generated": True,
                "local_comparison_written": True,
                "source_program_files_mutated": False,
                "gepa_optimizer_output_mutated": False,
                "comparison_mutated_source_candidate": False,
                "comparison_mutated_gepa_candidate": False,
                "third_candidate_generated": False,
                "external_authority_mutated": False,
                "governance_mutated": False,
            },
            "non_authority": {
                "local_generation_and_comparison_only": False,
                "local_gepa_generation_and_comparison_only": True,
                "program_gen_automation": False,
                "automatic_promotion": False,
                "oracle_ranking": False,
                "oracle_pruning": False,
                "oracle_promotion": False,
                "winner_selection": False,
                "external_authority_export": False,
                "governance_authority": False,
                "external_mutation": False,
            },
        }

    monkeypatch.setattr(
        consumption,
        "materialize_and_compare_gepa_refinement_candidate",
        workflow,
    )

    def write_workflow(payload: dict[str, Any], path: Path) -> dict[str, Any]:
        path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(
        consumption,
        "write_program_refinement_workflow_result",
        write_workflow,
    )
    monkeypatch.setattr(
        consumption,
        "validate_program_refinement_gepa_candidate_result_contract",
        lambda payload, **kwargs: {
            "candidate_manifest_path": Path(payload["candidate"]["manifest_path"]),
            "candidate_root": Path(payload["candidate"]["root_path"]),
        },
    )
    monkeypatch.setattr(
        consumption,
        "validate_program_refinement_candidate_comparison_contract",
        lambda comparison_path, **kwargs: json.loads(
            Path(comparison_path).read_text(encoding="utf-8")
        ),
    )


def test_consumes_successful_execution_once_and_reuses_bound_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution_receipt, execution = _execution_fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    _install_success_stubs(monkeypatch, execution, calls)

    first = consumption.consume_successful_program_foundry_gepa_receipt(
        execution_receipt_path=execution_receipt
    )
    second = consumption.consume_successful_program_foundry_gepa_receipt(
        execution_receipt_path=execution_receipt
    )

    assert first["status"] == "ok"
    assert first["reused"] is False
    assert second["status"] == "ok"
    assert second["reused"] is True
    assert len(calls) == 1
    assert first["effect"]["one_local_candidate_materialized"] is True
    assert first["effect"]["local_comparison_recorded"] is True
    assert first["effect"]["gepa_reexecuted"] is False
    assert first["effect"]["winner_selected"] is False
    assert first["non_authority"]["promotion_authority"] is False
    experiment = execution_receipt.parent
    assert (experiment / "materialized-candidate" / "manifest.json").exists()
    assert (experiment / "candidate-comparison.json").exists()
    assert (experiment / "consumption-receipt.json").exists()

    comparison = experiment / "candidate-comparison.json"
    comparison.write_text('{"status":"tampered"}', encoding="utf-8")
    with pytest.raises(
        consumption.ProgramFoundryGepaConsumptionError,
        match="drifted|workflow binding is invalid",
    ):
        consumption.consume_successful_program_foundry_gepa_receipt(
            execution_receipt_path=execution_receipt
        )
    assert len(calls) == 1


def test_consumption_attempt_blocks_replay_after_possible_candidate_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution_receipt, execution = _execution_fixture(tmp_path)
    monkeypatch.setattr(
        consumption,
        "validate_successful_program_foundry_gepa_execution_receipt",
        lambda path, **kwargs: execution,
    )
    calls = 0

    def crash(**kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise RuntimeError("candidate behavior execution may have occurred")

    monkeypatch.setattr(
        consumption,
        "materialize_and_compare_gepa_refinement_candidate",
        crash,
    )
    with pytest.raises(RuntimeError, match="may have occurred"):
        consumption.consume_successful_program_foundry_gepa_receipt(
            execution_receipt_path=execution_receipt
        )
    blocked = consumption.consume_successful_program_foundry_gepa_receipt(
        execution_receipt_path=execution_receipt
    )
    assert calls == 1
    assert blocked["status"] == "blocked_indeterminate"
    assert blocked["effect_disposition"] == (
        "candidate_materialization_or_comparison_may_have_occurred"
    )
    assert blocked["non_authority"]["winner_selection"] is False


def test_consumption_cli_forwards_only_canonical_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = tmp_path / "execution-receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    calls: list[Path] = []

    def fake_consume(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["execution_receipt_path"])
        return {"status": "ok", "reused": False}

    monkeypatch.setattr(
        consumption,
        "consume_successful_program_foundry_gepa_receipt",
        fake_consume,
    )
    result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "consume-foundry-gepa-receipt",
            "--receipt",
            str(receipt),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [receipt]
