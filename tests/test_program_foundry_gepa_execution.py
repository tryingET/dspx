# summary: "Tests reviewed foundry GEPA execution, durable no-replay, receipts, drift rejection, and CLI behavior."

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
import dspx.services.program_foundry as foundry
import dspx.services.program_foundry_gepa_execution as execution
from test_program_foundry import (
    _env,
    _inputs,
    _quality_artifacts,
    _successful_semantic_stub,
)


def _proposal(tmp_path: Path, monkeypatch, *, name: str = "foundry") -> Path:
    _env(tmp_path, monkeypatch)
    intent = tmp_path / f"{name}-intent.json"
    quality = tmp_path / f"{name}-quality.json"
    inputs = tmp_path / f"{name}-inputs.json"
    root = tmp_path / name
    _quality_artifacts(intent, quality)
    _inputs(inputs)
    monkeypatch.setattr(
        foundry,
        "run_program_runtime_oracle_semantics",
        _successful_semantic_stub,
    )
    foundry.run_program_foundry(
        intent_path=intent,
        quality_proposal_path=quality,
        inputs_path=inputs,
        outdir=root,
        skip_oracle_index=True,
        gepa_recommendation_index=0,
        gepa_max_metric_calls=3,
        gepa_metric="concept_coverage",
    )
    return root / "gepa_experiment_proposal.json"


def _completed_result(**kwargs: Any) -> dict[str, Any]:
    """Fake a completed concept_coverage GEPA run: wrapper program + honesty block."""

    outdir = Path(kwargs["outdir"])
    outdir.mkdir(parents=True)
    source_program = Path(kwargs["manifest_path"]).parent / "program.py"
    source_sha256 = hashlib.sha256(source_program.read_bytes()).hexdigest()
    wrapper = outdir / "source" / "concept_coverage_program.py"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text(
        f"CANDIDATE_PROGRAM_SHA256 = {source_sha256!r}\n", encoding="utf-8"
    )
    wrapper_sha256 = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    criteria_sha256 = hashlib.sha256(b"criteria").hexdigest()
    files = [
        {
            "path": "source/concept_coverage_program.py",
            "sha256": wrapper_sha256,
            "size_bytes": wrapper.stat().st_size,
        }
    ]
    tree_text = json.dumps(
        files, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    metric_honesty = {
        "metric": "concept_coverage",
        "wrapper_program_sha256": wrapper_sha256,
        "source_program_sha256": source_sha256,
        "criteria_sha256": criteria_sha256,
    }
    optimizer_manifest = outdir / "manifest.json"
    optimizer_manifest.write_text(
        json.dumps(
            {
                "created_at": "2026-07-12T00:00:00+00:00",
                "dspy_version": "test",
                "dspx_version": "test",
                "python": {},
                "program": {"path": str(wrapper), "sha256": wrapper_sha256},
                "dataset": {},
                "io": {},
                "gepa": {"metric": "exact"},
                "gepa_version": "0.1.1",
                "providers": {},
                "output_payload": {
                    "hash_algorithm": "sha256",
                    "tree_hash": hashlib.sha256(tree_text.encode("utf-8")).hexdigest(),
                    "files": files,
                    "excludes": ["manifest.json"],
                },
                "metric_honesty": metric_honesty,
            }
        ),
        encoding="utf-8",
    )
    manifest_sha256 = hashlib.sha256(optimizer_manifest.read_bytes()).hexdigest()
    return {
        "schema_version": "program-refinement-gepa-result-v1",
        "status": "degraded",
        "gepa": {
            "attempted": True,
            "status": "completed",
            "metric": "concept_coverage",
            "concept_coverage_binding": {
                "candidate_program_sha256": source_sha256,
                "wrapper_program_sha256": wrapper_sha256,
                "criteria_sha256": criteria_sha256,
                "metric_honesty": metric_honesty,
            },
        },
        "gepa_output": {
            "root_path": str(outdir),
            "manifest_path": str(optimizer_manifest),
            "manifest_present": True,
            "manifest_valid": True,
            "manifest_kind": "dspy_gepa_optimizer_output_manifest",
            "manifest_sha256": manifest_sha256,
            "readiness": {
                "status": "optimizer_output_hash_bound_not_candidate",
                "ready_for_future_candidate_materializer": True,
                "blockers": [],
            },
        },
        "candidate": None,
        "effect": {
            "local_gepa_candidate_generated": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
        },
        "non_authority": {
            "winner_selection": False,
            "automatic_promotion": False,
        },
    }


def test_reviewed_foundry_gepa_executes_once_and_reuses_terminal_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    proposal_path = _proposal(tmp_path, monkeypatch)
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    calls: list[dict[str, Any]] = []

    def fake_build(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return _completed_result(**kwargs)

    monkeypatch.setattr(execution, "build_program_refinement_gepa_result", fake_build)
    first = execution.execute_reviewed_program_foundry_gepa(
        proposal_path=proposal_path,
        declared_reviewed=proposal["proposal_id"],
        operator_label="local-operator",
    )
    root = proposal_path.parent / "gepa-experiment"
    (root / "execution-receipt.json").unlink()
    second = execution.execute_reviewed_program_foundry_gepa(
        proposal_path=proposal_path,
        declared_reviewed=proposal["proposal_id"],
        operator_label="local-operator",
    )
    third = execution.execute_reviewed_program_foundry_gepa(
        proposal_path=proposal_path,
        declared_reviewed=proposal["proposal_id"],
        operator_label="local-operator",
    )

    assert first["status"] == "ok"
    assert first["reused"] is False
    assert second["status"] == "ok"
    assert second["reused"] is True
    assert second["receipt_finalized"] is True
    assert third["status"] == "ok"
    assert third["reused"] is True
    assert len(calls) == 1
    assert calls[0]["metric"] == "concept_coverage"
    assert calls[0]["max_metric_calls"] == 3
    attempt = json.loads((root / "attempt.json").read_text(encoding="utf-8"))
    assert attempt["review_declaration"]["authenticated"] is False
    assert attempt["review_declaration"]["execution_intent_only"] is True
    assert attempt["no_replay_after_marker"] is True
    receipt = json.loads((root / "execution-receipt.json").read_text(encoding="utf-8"))
    assert receipt["effect"]["gepa_invoked"] is True
    assert receipt["effect"]["winner_selected"] is False
    assert receipt["non_authority"]["promotion_authority"] is False
    optimizer_manifest = root / "optimizer-output" / "manifest.json"
    manifest = json.loads(optimizer_manifest.read_text(encoding="utf-8"))
    assert receipt["metric_honesty"] == manifest["metric_honesty"]
    assert set(receipt["metric_honesty"]) == {
        "metric",
        "wrapper_program_sha256",
        "source_program_sha256",
        "criteria_sha256",
    }
    # A receipt whose mirrored block drifts from the manifest is rejected.
    receipt_path = root / "execution-receipt.json"
    tampered = dict(receipt)
    tampered["metric_honesty"] = {
        **receipt["metric_honesty"],
        "source_program_sha256": "0" * 64,
    }
    receipt_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(
        execution.ProgramFoundryGepaExecutionError, match="bound output drifted"
    ):
        execution.execute_reviewed_program_foundry_gepa(
            proposal_path=proposal_path,
            declared_reviewed=proposal["proposal_id"],
            operator_label="local-operator",
        )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    # A manifest block that no longer matches the result binding is rejected,
    # as is a concept_coverage run whose manifest carries no block at all.
    gepa_result = json.loads((root / "gepa-result.json").read_text(encoding="utf-8"))
    validated = {"optimizer_metric": "concept_coverage"}
    assert (
        execution._validate_metric_honesty(
            manifest, gepa=gepa_result["gepa"], validated=validated
        )
        == receipt["metric_honesty"]
    )
    drifted = json.loads(json.dumps(manifest))
    drifted["metric_honesty"]["wrapper_program_sha256"] = "1" * 64
    with pytest.raises(
        execution.ProgramFoundryGepaExecutionError,
        match="metric_honesty does not match the result binding",
    ):
        execution._validate_metric_honesty(
            drifted, gepa=gepa_result["gepa"], validated=validated
        )
    with pytest.raises(
        execution.ProgramFoundryGepaExecutionError,
        match="must carry a metric_honesty block",
    ):
        execution._validate_metric_honesty(
            {k: v for k, v in manifest.items() if k != "metric_honesty"},
            gepa=gepa_result["gepa"],
            validated=validated,
        )
    assert (
        execution._validate_metric_honesty(
            {k: v for k, v in manifest.items() if k != "metric_honesty"},
            gepa={"attempted": True, "status": "completed"},
            validated={"optimizer_metric": "exact"},
        )
        is None
    )
    optimizer_manifest.write_text("{}", encoding="utf-8")
    with pytest.raises(
        execution.ProgramFoundryGepaExecutionError,
        match="optimizer output (binding|manifest contract)|bound output drifted",
    ):
        execution.execute_reviewed_program_foundry_gepa(
            proposal_path=proposal_path,
            declared_reviewed=proposal["proposal_id"],
            operator_label="local-operator",
        )


def test_foundry_gepa_attempt_marker_blocks_replay_after_exception(
    tmp_path: Path, monkeypatch
) -> None:
    proposal_path = _proposal(tmp_path, monkeypatch, name="crash-foundry")
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    calls = 0

    def crash(**kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise RuntimeError("simulated crash after possible model effect")

    monkeypatch.setattr(execution, "build_program_refinement_gepa_result", crash)
    with pytest.raises(RuntimeError, match="possible model effect"):
        execution.execute_reviewed_program_foundry_gepa(
            proposal_path=proposal_path,
            declared_reviewed=proposal["proposal_id"],
            operator_label="local-operator",
        )
    blocked = execution.execute_reviewed_program_foundry_gepa(
        proposal_path=proposal_path,
        declared_reviewed=proposal["proposal_id"],
        operator_label="local-operator",
    )
    assert calls == 1
    assert blocked["status"] == "blocked_indeterminate"
    assert blocked["effect_disposition"] == "indeterminate_no_replay"
    assert not (
        proposal_path.parent / "gepa-experiment" / "execution-receipt.json"
    ).exists()
    attempt_path = proposal_path.parent / "gepa-experiment" / "attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["review_declaration"]["authenticated"] = True
    attempt_path.write_text(json.dumps(attempt), encoding="utf-8")
    with pytest.raises(
        execution.ProgramFoundryGepaExecutionError,
        match="attempt identity drifted",
    ):
        execution.execute_reviewed_program_foundry_gepa(
            proposal_path=proposal_path,
            declared_reviewed=proposal["proposal_id"],
            operator_label="local-operator",
        )
    assert calls == 1


def test_foundry_gepa_execution_rejects_declaration_and_source_drift(
    tmp_path: Path, monkeypatch
) -> None:
    proposal_path = _proposal(tmp_path, monkeypatch, name="drift-foundry")
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    with pytest.raises(
        execution.ProgramFoundryGepaExecutionError, match="exactly equal"
    ):
        execution.execute_reviewed_program_foundry_gepa(
            proposal_path=proposal_path,
            declared_reviewed="0" * 64,
            operator_label="local-operator",
        )
    behavior = proposal_path.parent / "runtime" / "behavior_results.json"
    behavior.write_text("{}", encoding="utf-8")
    with pytest.raises(execution.ProgramFoundryGepaExecutionError, match="drifted"):
        execution.execute_reviewed_program_foundry_gepa(
            proposal_path=proposal_path,
            declared_reviewed=proposal["proposal_id"],
            operator_label="local-operator",
        )
    assert not (proposal_path.parent / "gepa-experiment").exists()


def test_foundry_gepa_execution_cli_forwards_review_declaration(
    tmp_path: Path, monkeypatch
) -> None:
    proposal = tmp_path / "gepa_experiment_proposal.json"
    proposal.write_text("{}", encoding="utf-8")
    calls: list[dict[str, Any]] = []

    def fake_execute(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"status": "ok", "reused": False}

    monkeypatch.setattr(
        execution, "execute_reviewed_program_foundry_gepa", fake_execute
    )
    result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "execute-foundry-gepa",
            "--proposal",
            str(proposal),
            "--declare-reviewed",
            "a" * 64,
            "--operator-label",
            "local-operator",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls[0]["declared_reviewed"] == "a" * 64
    assert calls[0]["operator_label"] == "local-operator"
