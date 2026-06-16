from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services import program_refinement_gepa_candidate_contracts as gepa_contracts
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_refinement_workflow import (
    write_program_refinement_workflow_result,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")


def _hash_tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _identity(manifest: dict[str, Any]) -> dict[str, str | None]:
    request = manifest.get("request") or {}
    assembly = manifest.get("candidate_assembly") or {}
    episode = manifest.get("execution_episode") or {}
    receipt = manifest.get("receipt_bundle") or {}
    return {
        "request_id": request.get("request_id") or assembly.get("request_id"),
        "candidate_id": assembly.get("candidate_id") or episode.get("candidate_id"),
        "assembly_id": assembly.get("assembly_id") or episode.get("assembly_id"),
        "episode_id": episode.get("episode_id") or receipt.get("episode_id"),
        "receipt_bundle_id": receipt.get("receipt_bundle_id"),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _materialize_source(tmp_path: Path) -> Path:
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="TicketProgram",
            objective="Classify support ticket urgency.",
            inputs=["ticket_text"],
            outputs=["urgency"],
            metric="exact_match",
            examples=[
                {
                    "inputs": {"ticket_text": "Server is down for all users"},
                    "outputs": {"urgency": "high"},
                }
            ],
        ),
        outdir=tmp_path / "program",
    )
    return Path(artifact.root_path)


def _optimizer_payload_inventory(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == "manifest.json":
            continue
        files.append(
            {
                "path": rel,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size_bytes": path.stat().st_size,
            }
        )
    tree_text = json.dumps(
        files, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        "hash_algorithm": "sha256",
        "tree_hash": hashlib.sha256(tree_text.encode("utf-8")).hexdigest(),
        "files": files,
        "excludes": ["manifest.json"],
    }


def _write_ready_gepa_result(
    tmp_path: Path,
    program_root: Path,
    *,
    identity_drift: bool = False,
    unready: bool = False,
    effect_spoof: bool = False,
    authority_spoof: bool = False,
    source_program_hash: str | None = None,
) -> Path:
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    identity = _identity(manifest)
    if identity_drift:
        identity = {**identity, "candidate_id": "wrong-candidate"}
    optimizer_root = tmp_path / "program-gepa"
    optimizer_root.mkdir(parents=True, exist_ok=True)
    (optimizer_root / "compiled.bin").write_text(
        "fake optimizer payload", encoding="utf-8"
    )
    program_hash = (
        source_program_hash
        or hashlib.sha256((program_root / "program.py").read_bytes()).hexdigest()
    )
    optimizer_manifest = {
        "created_by": "fake_gepa_for_candidate_materializer_test",
        "program": {
            "path": str(program_root / "program.py"),
            "sha256": program_hash,
        },
        "dataset": {"train": "train.csv", "val": "validation.csv"},
        "io": {"inputs": ["ticket_text"], "outputs": ["urgency"]},
        "gepa": {"metric": "exact", "max_metric_calls": 2},
        "output_payload": _optimizer_payload_inventory(optimizer_root),
    }
    _write_json(optimizer_root / "manifest.json", optimizer_manifest)
    optimizer_hash = hashlib.sha256(
        (optimizer_root / "manifest.json").read_bytes()
    ).hexdigest()
    payload: dict[str, Any] = {
        "schema_version": "program-refinement-gepa-result-v1",
        "status": "degraded",
        "source_identity": identity,
        "created_from": {"manifest_path": str(program_root / "manifest.json")},
        "evidence_inputs": {"source": "inline_examples", "train_examples_count": 1},
        "gepa": {
            "attempted": True,
            "status": "completed",
            "metric": "exact_match",
            "optimizer_metric": "exact",
            "max_metric_calls": 2,
        },
        "gepa_output": {
            "root_path": str(optimizer_root),
            "manifest_path": str(optimizer_root / "manifest.json"),
            "manifest_present": True,
            "manifest_valid": not unready,
            "manifest_sha256": optimizer_hash,
            "manifest_schema_version": None,
            "manifest_kind": "dspy_gepa_optimizer_output_manifest",
            "candidate_assembly_manifest": False,
            "readiness": {
                "status": "optimizer_output_hash_bound_not_candidate",
                "ready_for_future_candidate_materializer": not unready,
                "blockers": [
                    "no_program_candidate_assembly_materializer_in_this_command"
                ],
            },
        },
        "candidate": None,
        "effect": {
            "local_gepa_candidate_generated": effect_spoof,
            "source_program_files_mutated": False,
            "source_dataset_artifacts_mutated": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
        },
        "non_authority": {
            "local_refinement_only": True,
            "automatic_promotion": False,
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "winner_selection": authority_spoof,
            "external_authority_export": False,
            "governance_authority": False,
            "external_mutation": False,
        },
    }
    result_path = tmp_path / "refinement" / "gepa_refinement_result.json"
    _write_json(result_path, payload)
    return result_path


def test_program_refine_materialize_gepa_candidate_creates_local_non_authoritative_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    before = _hash_tree(program_root)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    optimizer_before = _hash_tree(tmp_path / "program-gepa")
    result_out = tmp_path / "refinement" / "gepa_candidate_result.json"
    outdir = tmp_path / "program-gepa-candidate"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-gepa-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(outdir),
            "--result-out",
            str(result_out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == json.loads(result_out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "program-refinement-gepa-candidate-result-v1"
    assert payload["status"] == "materialized"
    assert payload["candidate"]["promotion_state"] == "not_promoted"
    assert payload["effect"] == {
        "local_gepa_candidate_generated": True,
        "source_program_files_mutated": False,
        "source_dataset_artifacts_mutated": False,
        "gepa_optimizer_output_mutated": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
    }
    assert payload["non_authority"]["winner_selection"] is False
    assert payload["non_authority"]["external_authority_export"] is False
    assert payload["gepa_output"]["payload_tree_sha256"]
    assert payload["gepa_output"]["payload_file_count"] == 1
    assert payload["behavior_refresh"]["status"] == "refreshed"
    assert payload["behavior_refresh"]["behavior_results_sha256"] is None
    assert payload["behavior_refresh"]["oracle_evidence_removed"] is True
    assert (outdir / "manifest.json").exists()
    assert (outdir / "gepa_optimizer_output" / "manifest.json").exists()
    assert (outdir / "gepa_candidate_lineage.json").exists()
    assert not (outdir / "behavior_results.json").exists()
    assert not (outdir / "oracle_evidence.json").exists()
    behavior_episode = json.loads(
        (outdir / "behavior_episode.json").read_text(encoding="utf-8")
    )
    assert behavior_episode["schema_version"] == "program-behavior-episode-v1"
    assert behavior_episode["sources"][0]["status"] == "failed"
    assert "behavior_results_hash" not in behavior_episode["sources"][0]
    program_code = (outdir / "program.py").read_text(encoding="utf-8")
    assert "dspy.load" in program_code
    assert "GEPA_OPTIMIZER_OUTPUT_DIR" in program_code
    assert "def configure_observability" in program_code
    assert "def end_observability_run" in program_code
    candidate_manifest = json.loads(
        (outdir / "manifest.json").read_text(encoding="utf-8")
    )
    assert candidate_manifest["request"]["behavior_results_hash"] is None
    assert candidate_manifest["request"]["oracle_evidence_hash"] is None
    assert (
        candidate_manifest["behavior_episode_artifact"]["content_hash"]
        == payload["behavior_refresh"]["behavior_episode_sha256"]
    )
    assert candidate_manifest["oracle_evidence_artifact"] is None
    assert candidate_manifest["oracle_readability"]["status"] == (
        "not_applicable_after_gepa_program_rewrite"
    )
    surface_paths = {
        surface["path"]
        for surface in candidate_manifest["candidate_assembly"]["surfaces"]
    }
    assert "behavior_results.json" not in surface_paths
    assert "oracle_evidence.json" not in surface_paths
    assert (
        candidate_manifest["gepa_refinement"]["behavior_refresh"]["status"]
        == "refreshed"
    )
    assert (
        candidate_manifest["candidate_assembly"]["materialized_from"]
        == "gepa_optimizer_output"
    )
    assert candidate_manifest["gepa_refinement"]["gepa_optimizer_payload_tree_sha256"]
    assert (
        candidate_manifest["gepa_refinement"]["non_authority"]["winner_selection"]
        is False
    )
    assert _hash_tree(program_root) == before
    assert _hash_tree(tmp_path / "program-gepa") == optimizer_before


def test_program_refine_materialize_and_compare_gepa_candidate_writes_local_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    source_before = _hash_tree(program_root)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    optimizer_before = _hash_tree(tmp_path / "program-gepa")
    outdir = tmp_path / "program-gepa-candidate"
    comparison_out = tmp_path / "refinement" / "gepa_candidate_comparison.json"
    gepa_candidate_result_out = tmp_path / "refinement" / "gepa_candidate_result.json"
    workflow_out = tmp_path / "refinement" / "gepa_generate_compare_result.json"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-and-compare-gepa-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(outdir),
            "--comparison-out",
            str(comparison_out),
            "--gepa-candidate-result-out",
            str(gepa_candidate_result_out),
            "--workflow-out",
            str(workflow_out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == json.loads(workflow_out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == (
        "program-refinement-gepa-generate-and-compare-result-v1"
    )
    assert payload["status"] == "materialized_and_compared_gepa_candidate"
    assert payload["created_from"] == {
        "manifest_path": str((program_root / "manifest.json").resolve()),
        "gepa_refinement_result_path": str(gepa_result.resolve()),
    }
    assert payload["generation"]["schema_version"] == (
        "program-refinement-gepa-candidate-result-v1"
    )
    assert payload["generation"]["behavior_refresh"]["status"] == "refreshed"
    assert payload["comparison_sidecar"]["path"] == str(comparison_out.resolve())
    assert payload["comparison_sidecar"]["status"] == "compared"
    assert payload["effect"] == {
        "local_gepa_candidate_generated": True,
        "local_comparison_written": True,
        "source_program_files_mutated": False,
        "gepa_optimizer_output_mutated": False,
        "comparison_mutated_source_candidate": False,
        "comparison_mutated_gepa_candidate": False,
        "third_candidate_generated": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
    }
    assert payload["non_authority"]["local_gepa_generation_and_comparison_only"] is True
    assert payload["non_authority"]["winner_selection"] is False
    assert payload["non_authority"]["external_authority_export"] is False
    comparison = json.loads(comparison_out.read_text(encoding="utf-8"))
    candidate_manifest = json.loads(
        (outdir / "manifest.json").read_text(encoding="utf-8")
    )
    assert (
        comparison["candidate_identity"]["candidate_id"]
        == candidate_manifest["candidate_assembly"]["candidate_id"]
    )
    assert comparison["non_authority"]["winner_selection"] is False
    assert gepa_candidate_result_out.exists()
    assert _hash_tree(program_root) == source_before
    assert _hash_tree(tmp_path / "program-gepa") == optimizer_before


def test_program_refinement_workflow_result_rejects_overwriting_nested_sidecar_path(
    tmp_path: Path,
) -> None:
    comparison_out = tmp_path / "refinement" / "gepa_candidate_comparison.json"
    _write_json(
        comparison_out,
        {"schema_version": "program-refinement-candidate-comparison-v1"},
    )
    payload = {
        "schema_version": "program-refinement-gepa-generate-and-compare-result-v1",
        "created_from": {"manifest_path": str(tmp_path / "program" / "manifest.json")},
        "comparison_sidecar": {
            "path": str(comparison_out),
            "schema_version": "program-refinement-candidate-comparison-v1",
        },
    }

    with pytest.raises(
        ValueError,
        match="must not overwrite an input artifact",
    ):
        write_program_refinement_workflow_result(payload, comparison_out)

    assert json.loads(comparison_out.read_text(encoding="utf-8")) == {
        "schema_version": "program-refinement-candidate-comparison-v1"
    }


@pytest.mark.parametrize(
    ("overlap_args", "expected"),
    [
        (
            lambda path: ["--workflow-out", str(path), "--comparison-out", str(path)],
            "comparison_out and workflow_out both resolve",
        ),
        (
            lambda path: [
                "--gepa-candidate-result-out",
                str(path),
                "--comparison-out",
                str(path),
            ],
            "comparison_out and gepa_candidate_result_out both resolve",
        ),
    ],
)
def test_program_refine_materialize_and_compare_gepa_candidate_rejects_overlapping_outputs_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overlap_args: Any,
    expected: str,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    output = tmp_path / "refinement" / "overlap.json"
    outdir = tmp_path / "program-gepa-candidate"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-and-compare-gepa-candidate",
            "--manifest",
            str(tmp_path / "missing" / "manifest.json"),
            "--gepa-result",
            str(tmp_path / "missing" / "gepa_result.json"),
            "--outdir",
            str(outdir),
            *overlap_args(output),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert expected in (result.stdout + result.stderr)
    assert not output.exists()
    assert not outdir.exists()


@pytest.mark.parametrize(
    ("sidecar_label", "expected"),
    [
        ("comparison_out", "comparison_out output path must not be inside outdir"),
        (
            "gepa_candidate_result_out",
            "gepa_candidate_result_out output path must not be inside outdir",
        ),
        ("workflow_out", "workflow_out output path must not be inside outdir"),
    ],
)
def test_program_refine_materialize_and_compare_gepa_candidate_rejects_sidecars_inside_output_root_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sidecar_label: str,
    expected: str,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    outdir = tmp_path / "program-gepa-candidate"
    nested_sidecar = outdir / "local_sidecar.json"
    args = [
        "program-refine",
        "materialize-and-compare-gepa-candidate",
        "--manifest",
        str(tmp_path / "missing" / "manifest.json"),
        "--gepa-result",
        str(tmp_path / "missing" / "gepa_result.json"),
        "--outdir",
        str(outdir),
    ]
    if sidecar_label == "comparison_out":
        args.extend(["--comparison-out", str(nested_sidecar)])
    else:
        args.extend(
            ["--comparison-out", str(tmp_path / "refinement" / "comparison.json")]
        )
        if sidecar_label == "gepa_candidate_result_out":
            args.extend(["--gepa-candidate-result-out", str(nested_sidecar)])
        else:
            args.extend(["--workflow-out", str(nested_sidecar)])
    args.append("--json")

    result = runner.invoke(app, args)

    assert result.exit_code == 2
    assert expected in (result.stdout + result.stderr)
    assert not nested_sidecar.exists()
    assert not outdir.exists()


@pytest.mark.parametrize(
    ("sidecar_label", "expected"),
    [
        ("comparison_out", "comparison_out output path must not be inside source_root"),
        (
            "gepa_candidate_result_out",
            "gepa_candidate_result_out output path must not be inside source_root",
        ),
        ("workflow_out", "workflow_out output path must not be inside source_root"),
    ],
)
def test_program_refine_materialize_and_compare_gepa_candidate_rejects_sidecars_inside_source_root_before_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sidecar_label: str,
    expected: str,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    before = _hash_tree(program_root)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    outdir = tmp_path / "program-gepa-candidate"
    source_sidecar = program_root / "local_sidecar.json"
    args = [
        "program-refine",
        "materialize-and-compare-gepa-candidate",
        "--manifest",
        str(program_root / "manifest.json"),
        "--gepa-result",
        str(gepa_result),
        "--outdir",
        str(outdir),
    ]
    if sidecar_label == "comparison_out":
        args.extend(["--comparison-out", str(source_sidecar)])
    else:
        args.extend(
            ["--comparison-out", str(tmp_path / "refinement" / "comparison.json")]
        )
        if sidecar_label == "gepa_candidate_result_out":
            args.extend(["--gepa-candidate-result-out", str(source_sidecar)])
        else:
            args.extend(["--workflow-out", str(source_sidecar)])
    args.append("--json")

    result = runner.invoke(app, args)

    assert result.exit_code == 2
    assert expected in (result.stdout + result.stderr)
    assert not source_sidecar.exists()
    assert not outdir.exists()
    assert _hash_tree(program_root) == before


def test_program_promote_decide_comparison_feeds_local_plan_for_gepa_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    outdir = tmp_path / "program-gepa-candidate"
    comparison_out = tmp_path / "refinement" / "gepa_candidate_comparison.json"
    workflow = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-and-compare-gepa-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(outdir),
            "--comparison-out",
            str(comparison_out),
            "--json",
        ],
    )
    assert workflow.exit_code == 0, workflow.output
    decision_out = tmp_path / "refinement" / "gepa_comparison_decision.json"

    decision = runner.invoke(
        app,
        [
            "program-promote",
            "decide-comparison",
            "--comparison",
            str(comparison_out),
            "--outcome",
            "withhold",
            "--decided-by",
            "local-operator",
            "--rationale",
            "GEPA comparison is local evidence only; keep candidate withheld pending external authority.",
            "--out",
            str(decision_out),
            "--json",
        ],
    )

    assert decision.exit_code == 0, decision.output
    decision_payload = json.loads(decision.stdout)
    comparison_payload = json.loads(comparison_out.read_text(encoding="utf-8"))
    assert decision_payload == json.loads(decision_out.read_text(encoding="utf-8"))
    assert decision_payload["schema_version"] == "program-promotion-decision-record-v1"
    assert decision_payload["outcome"] == "withhold"
    assert decision_payload["identity"] == comparison_payload["source_identity"]
    assert decision_payload["created_from"]["comparison_path"] == str(
        comparison_out.resolve()
    )
    assert (
        decision_payload["comparison_snapshot"]["candidate_identity"]
        == comparison_payload["candidate_identity"]
    )
    assert (
        decision_payload["decision_constraints"]["promote_allowed_by_review"] is False
    )
    assert decision_payload["non_authority"]["comparison_decision_only"] is True
    assert decision_payload["non_authority"]["winner_selection"] is False
    plan_out = tmp_path / "refinement" / "gepa_promotion_plan.json"

    plan = runner.invoke(
        app,
        [
            "program-promote",
            "plan",
            "--manifest",
            str(outdir / "manifest.json"),
            "--decision-record",
            str(decision_out),
            "--comparison",
            str(comparison_out),
            "--source-manifest",
            str(program_root / "manifest.json"),
            "--target",
            "local_preferred_candidate",
            "--authority-owner",
            "local-operator",
            "--out",
            str(plan_out),
            "--json",
        ],
    )

    assert plan.exit_code == 0, plan.output
    plan_payload = json.loads(plan.stdout)
    assert plan_payload["schema_version"] == "program-promotion-plan-v1"
    assert plan_payload["status"] == "planned_not_applied"
    assert plan_payload["promotion_state"] == "not_promoted"
    assert plan_payload["eligibility"]["allowed_for_apply"] is False
    assert plan_payload["non_authority"]["winner_selection"] is False


def test_program_promote_decide_comparison_rejects_promote_and_spoofed_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    comparison_out = tmp_path / "refinement" / "gepa_candidate_comparison.json"
    workflow = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-and-compare-gepa-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(tmp_path / "program-gepa-candidate"),
            "--comparison-out",
            str(comparison_out),
            "--json",
        ],
    )
    assert workflow.exit_code == 0, workflow.output

    promote = runner.invoke(
        app,
        [
            "program-promote",
            "decide-comparison",
            "--comparison",
            str(comparison_out),
            "--outcome",
            "promote",
            "--decided-by",
            "local-operator",
            "--rationale",
            "try to promote from comparison only",
            "--out",
            str(tmp_path / "refinement" / "bad_decision.json"),
            "--json",
        ],
    )
    assert promote.exit_code == 2
    assert "must be one of" in (promote.stdout + promote.stderr)
    assert not (tmp_path / "refinement" / "bad_decision.json").exists()

    spoofed = json.loads(comparison_out.read_text(encoding="utf-8"))
    spoofed["non_authority"]["winner_selection"] = True
    spoofed_path = tmp_path / "refinement" / "spoofed_comparison.json"
    _write_json(spoofed_path, spoofed)
    spoof = runner.invoke(
        app,
        [
            "program-promote",
            "decide-comparison",
            "--comparison",
            str(spoofed_path),
            "--outcome",
            "withhold",
            "--decided-by",
            "local-operator",
            "--rationale",
            "reject spoofed authority",
            "--out",
            str(tmp_path / "refinement" / "spoof_decision.json"),
            "--json",
        ],
    )
    assert spoof.exit_code == 2
    assert "widens non-authority flags" in (spoof.stdout + spoof.stderr)
    assert not (tmp_path / "refinement" / "spoof_decision.json").exists()


def test_program_refine_materialize_and_compare_gepa_candidate_fails_closed_before_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    before = _hash_tree(program_root)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root, identity_drift=True)
    comparison_out = tmp_path / "refinement" / "gepa_candidate_comparison.json"
    workflow_out = tmp_path / "refinement" / "gepa_generate_compare_result.json"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-and-compare-gepa-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(tmp_path / "program-gepa-candidate"),
            "--comparison-out",
            str(comparison_out),
            "--workflow-out",
            str(workflow_out),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "identity does not match" in (result.stdout + result.stderr)
    assert not (tmp_path / "program-gepa-candidate").exists()
    assert not comparison_out.exists()
    assert not workflow_out.exists()
    assert _hash_tree(program_root) == before


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        ({"identity_drift": True}, "identity does not match"),
        ({"unready": True}, "manifest must be valid"),
        ({"effect_spoof": True}, "widens effect flags"),
        ({"authority_spoof": True}, "widens non-authority flags"),
        ({"source_program_hash": "0" * 64}, "source program hash does not match"),
    ],
)
def test_program_refine_materialize_gepa_candidate_rejects_spoofed_or_stale_sidecars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutator: dict[str, Any],
    expected: str,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    before = _hash_tree(program_root)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root, **mutator)

    result = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-gepa-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(tmp_path / "program-gepa-candidate"),
            "--result-out",
            str(tmp_path / "refinement" / "bad-candidate-result.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert expected in (result.stdout + result.stderr)
    assert not (tmp_path / "program-gepa-candidate").exists()
    assert not (tmp_path / "refinement" / "bad-candidate-result.json").exists()
    assert _hash_tree(program_root) == before


def test_program_refine_materialize_gepa_candidate_rejects_drifted_source_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    manifest_path = program_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["candidate_assembly"]["root_path"] = str(tmp_path / "wrong-root")
    _write_json(manifest_path, manifest)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)

    result = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-gepa-candidate",
            "--manifest",
            str(manifest_path),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(program_root / "gepa-candidate"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "root_path must match manifest parent" in (result.stdout + result.stderr)
    assert not (program_root / "gepa-candidate").exists()


def test_program_refine_materialize_gepa_candidate_rejects_external_program_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    external_program = tmp_path / "external.py"
    external_program.write_text("# external program\n", encoding="utf-8")
    manifest_path = program_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for surface in manifest["candidate_assembly"]["surfaces"]:
        if surface.get("kind") == "program":
            surface["path"] = str(external_program)
            break
    _write_json(manifest_path, manifest)
    gepa_result = _write_ready_gepa_result(
        tmp_path,
        program_root,
        source_program_hash=hashlib.sha256(external_program.read_bytes()).hexdigest(),
    )

    result = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-gepa-candidate",
            "--manifest",
            str(manifest_path),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(tmp_path / "program-gepa-candidate"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "program surface path must stay under source candidate root" in (
        result.stdout + result.stderr
    )
    assert not (tmp_path / "program-gepa-candidate").exists()


def test_copy_optimizer_output_rechecks_copied_manifest_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    expected_hash = json.loads(gepa_result.read_text(encoding="utf-8"))["gepa_output"][
        "manifest_sha256"
    ]
    original_copytree = gepa_contracts.shutil.copytree

    def copytree_and_tamper(src: Path, dst: Path, *, symlinks: bool) -> Path:
        copied = original_copytree(src, dst, symlinks=symlinks)
        manifest_path = Path(dst) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["tampered_after_copy"] = True
        _write_json(manifest_path, manifest)
        return Path(copied)

    monkeypatch.setattr(gepa_contracts.shutil, "copytree", copytree_and_tamper)

    copied_dir = tmp_path / "copied-gepa"
    with pytest.raises(
        gepa_contracts.ProgramRefinementGepaCandidateError,
        match="copied GEPA optimizer manifest hash changed",
    ):
        gepa_contracts._copy_optimizer_output(
            tmp_path / "program-gepa",
            copied_dir,
            expected_manifest_hash=expected_hash,
        )
    assert not copied_dir.exists()


def test_materialized_gepa_candidate_rejects_payload_tampering_before_pickle_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    outdir = tmp_path / "program-gepa-candidate"
    result = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-gepa-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(outdir),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    (outdir / "gepa_optimizer_output" / "compiled.bin").write_text(
        "post materialization tamper", encoding="utf-8"
    )

    spec = importlib.util.spec_from_file_location(
        "gepa_candidate_program", outdir / "program.py"
    )
    assert spec is not None and spec.loader is not None
    sys.path.insert(0, str(outdir))
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with pytest.raises(RuntimeError, match="payload hash changed before load"):
            module.build_program()
    finally:
        sys.path.remove(str(outdir))


def test_materialized_gepa_candidate_rejects_manifest_and_payload_rewrite_before_pickle_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    outdir = tmp_path / "program-gepa-candidate"
    result = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-gepa-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(outdir),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    copied_root = outdir / "gepa_optimizer_output"
    (copied_root / "compiled.bin").write_text(
        "tamper plus refreshed manifest", encoding="utf-8"
    )
    manifest_path = copied_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["output_payload"] = _optimizer_payload_inventory(copied_root)
    _write_json(manifest_path, manifest)

    spec = importlib.util.spec_from_file_location(
        "gepa_candidate_program_rewrite", outdir / "program.py"
    )
    assert spec is not None and spec.loader is not None
    sys.path.insert(0, str(outdir))
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with pytest.raises(RuntimeError, match="optimizer manifest hash changed"):
            module.build_program()
    finally:
        sys.path.remove(str(outdir))


def test_program_refine_materialize_gepa_candidate_rejects_tampered_optimizer_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    (tmp_path / "program-gepa" / "compiled.bin").write_text(
        "tampered optimizer payload", encoding="utf-8"
    )

    result = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-gepa-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(tmp_path / "program-gepa-candidate"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "payload hash does not match" in (result.stdout + result.stderr)
    assert not (tmp_path / "program-gepa-candidate").exists()


def test_program_refine_materialize_gepa_candidate_rejects_path_overlap_and_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    program_root = _materialize_source(tmp_path)
    before = _hash_tree(program_root)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)

    overlap = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-gepa-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(program_root / "gepa-candidate"),
            "--json",
        ],
    )
    assert overlap.exit_code == 2
    assert "must be outside source candidate root" in (overlap.stdout + overlap.stderr)

    optimizer_root = tmp_path / "program-gepa"
    try:
        (optimizer_root / "evil-link").symlink_to(
            program_root, target_is_directory=True
        )
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    symlink = runner.invoke(
        app,
        [
            "program-refine",
            "materialize-gepa-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--gepa-result",
            str(gepa_result),
            "--outdir",
            str(tmp_path / "program-gepa-candidate"),
            "--json",
        ],
    )
    assert symlink.exit_code == 2
    assert "contains a symlink" in (symlink.stdout + symlink.stderr)
    assert not (tmp_path / "program-gepa-candidate").exists()
    assert _hash_tree(program_root) == before
