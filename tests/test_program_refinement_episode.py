from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_refinement_episode import (
    ProgramRefinementEpisodeError,
    run_program_refinement_episode,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _identity(manifest: Mapping[str, Any]) -> dict[str, str | None]:
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


def _optimizer_payload_inventory(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
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
    program_hash = hashlib.sha256(
        (program_root / "program.py").read_bytes()
    ).hexdigest()
    optimizer_manifest = {
        "created_by": "fake_gepa_for_refinement_episode_test",
        "program": {"path": str(program_root / "program.py"), "sha256": program_hash},
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
            "manifest_valid": True,
            "manifest_sha256": optimizer_hash,
            "manifest_schema_version": None,
            "manifest_kind": "dspy_gepa_optimizer_output_manifest",
            "candidate_assembly_manifest": False,
            "readiness": {
                "status": "optimizer_output_hash_bound_not_candidate",
                "ready_for_future_candidate_materializer": True,
                "blockers": [
                    "no_program_candidate_assembly_materializer_in_this_command"
                ],
            },
        },
        "candidate": None,
        "effect": {
            "local_gepa_candidate_generated": False,
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
            "winner_selection": False,
            "external_authority_export": False,
            "governance_authority": False,
            "external_mutation": False,
        },
    }
    result_path = tmp_path / "refinement" / "gepa_refinement_result.json"
    _write_json(result_path, payload)
    return result_path


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_program_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="TicketProgram",
        objective="Classify support ticket urgency.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        metric="exact_match",
        constraints=["use only the supplied ticket text"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    program_root = Path(artifact.root_path)
    assert (program_root / "behavior_results.json").exists()
    assert (program_root / "oracle_evidence.json").exists()

    index_path = tmp_path / "oracle" / "coordinates.db"
    index_result = index_program_oracle_evidence_path(
        program_root,
        index_path=index_path,
    )
    assert index_result["indexed"] == 1
    assert index_result["errors"] == 0

    report = build_program_oracle_evidence_report(index_path=index_path)
    report_path = tmp_path / "oracle" / "program-evidence-report.json"
    _write_json(report_path, report)
    return program_root, report_path


def test_program_refinement_episode_cli_materializes_second_candidate_and_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    before_source_hashes = _file_hashes(program_root)
    outdir = tmp_path / "refinement-episode"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "episode",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--outdir",
            str(outdir),
            "--decision-outcome",
            "request_more_evidence",
            "--decided-by",
            "operator-test",
            "--rationale",
            "collect one bounded second candidate before any promotion review",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["schema_version"] == "program-refinement-episode-v1"
    assert payload["status"] in {
        "second_candidate_compared",
        "second_candidate_materialized_with_insufficient_behavior_evidence",
    }
    assert payload["non_authority"]["promotion_authority"] is False
    assert payload["non_authority"]["winner_selection"] is False
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["external_authority_mutated"] is False
    assert payload["effect"]["governance_mutated"] is False
    assert payload["effect"]["promotion_applied"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["steps"]["decision_record"]["outcome"] == "request_more_evidence"
    assert payload["steps"]["second_candidate"]["manifest_path"]
    workflow_payload = json.loads(
        (outdir / "program_refinement_episode.json").read_text(encoding="utf-8")
    )
    assert workflow_payload == payload
    assert workflow_payload["effect"]["workflow_summary_written"] is True

    for key in (
        "refinement_proposal.json",
        "promotion_review_refined.json",
        "promotion_decision_record.json",
        "program_candidate_comparison.json",
        "program_candidate_state.refinement.json",
        "program_refinement_episode.json",
    ):
        assert (outdir / key).exists(), key
    assert (outdir / "second_candidate" / "manifest.json").exists()

    state = json.loads(
        (outdir / "program_candidate_state.refinement.json").read_text(encoding="utf-8")
    )
    assert state["truth_summary"]["decision_record_present"] is True
    assert state["truth_summary"]["comparison_present"] is True
    assert state["truth_summary"]["ak_called"] is False
    assert state["truth_summary"]["winner_selected"] is False
    assert _file_hashes(program_root) == before_source_hashes


def test_program_refinement_episode_can_write_local_promotion_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    before_source_hashes = _file_hashes(program_root)
    outdir = tmp_path / "refinement-episode"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "episode",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--outdir",
            str(outdir),
            "--decision-outcome",
            "request_more_evidence",
            "--decided-by",
            "operator-test",
            "--rationale",
            "collect one bounded second candidate and local plan only",
            "--promotion-plan",
            "--promotion-plan-target",
            "local_preferred_candidate",
            "--promotion-plan-authority-owner",
            "operator-test",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["status"] == "local_promotion_plan_written"
    assert payload["steps"]["promotion_plan"] == {
        "status": "planned_not_applied",
        "path": str((outdir / "promotion_plan.json").resolve()),
        "target": "local_preferred_candidate",
        "allowed_for_apply": False,
    }
    assert payload["effect"]["local_promotion_plan_written"] is True
    assert payload["effect"]["promotion_applied"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["non_authority"]["local_promotion_plan_only"] is True
    assert payload["non_authority"]["promotion_authority"] is False

    plan = json.loads((outdir / "promotion_plan.json").read_text(encoding="utf-8"))
    assert plan["schema_version"] == "program-promotion-plan-v1"
    assert plan["status"] == "planned_not_applied"
    assert plan["promotion_state"] == "not_promoted"
    assert plan["eligibility"]["allowed_for_apply"] is False
    assert plan["effect"]["external_authority_mutated"] is False
    assert plan["effect"]["governance_mutated"] is False
    assert plan["non_authority"]["winner_selection"] is False

    second_candidate = outdir / "second_candidate"
    assert (second_candidate / "manifest.json").exists()
    candidate_manifest = json.loads(
        (second_candidate / "manifest.json").read_text(encoding="utf-8")
    )
    state = json.loads(
        (outdir / "program_candidate_state.refinement.json").read_text(encoding="utf-8")
    )
    assert (
        state["candidate_identity"]["candidate_id"]
        == candidate_manifest["candidate_assembly"]["candidate_id"]
    )
    assert state["truth_summary"]["promotion_plan_present"] is True
    assert state["truth_summary"]["oracle_report_present"] is False
    assert state["truth_summary"]["winner_selected"] is False
    assert state["evidence_state"]["oracle_report"]["present"] is False
    assert state["promotion_state"]["promotion_plan"]["allowed_for_apply"] is False
    assert state["created_from"]["source_manifest_path"] == str(
        (program_root / "manifest.json").resolve()
    )
    assert not (program_root / "promotion_plan.json").exists()
    assert not (second_candidate / "promotion_plan.json").exists()
    assert _file_hashes(program_root) == before_source_hashes


def test_program_refinement_episode_can_materialize_gepa_candidate_and_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    before_source_hashes = _file_hashes(program_root)
    before_optimizer_hashes = _file_hashes(tmp_path / "program-gepa")
    outdir = tmp_path / "refinement-episode"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "episode",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--outdir",
            str(outdir),
            "--decision-outcome",
            "request_more_evidence",
            "--decided-by",
            "operator-test",
            "--rationale",
            "compare one ready GEPA candidate before any promotion review",
            "--gepa-result",
            str(gepa_result),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["schema_version"] == "program-refinement-episode-v1"
    assert payload["status"] in {
        "gepa_candidate_compared",
        "gepa_candidate_materialized_with_insufficient_behavior_evidence",
    }
    assert payload["steps"]["second_candidate"]["status"] == "skipped"
    assert payload["steps"]["gepa_candidate"]["status"] in {
        "materialized_and_compared_gepa_candidate",
        "materialized_gepa_candidate_with_insufficient_behavior_evidence",
    }
    assert payload["steps"]["gepa_candidate"]["gepa_result_path"] == str(
        gepa_result.resolve()
    )
    assert payload["effect"]["local_second_candidate_generated"] is False
    assert payload["effect"]["local_gepa_candidate_generated"] is True
    assert payload["effect"]["gepa_optimizer_output_mutated"] is False
    assert payload["effect"]["local_comparison_written"] is True
    assert payload["effect"]["winner_selected"] is False
    assert payload["non_authority"]["gepa_candidate_evidence_only"] is True
    assert payload["non_authority"]["gepa_approval"] is False
    assert payload["non_authority"]["winner_selection"] is False
    assert (outdir / "gepa_candidate" / "manifest.json").exists()
    assert (outdir / "gepa_candidate_result.json").exists()
    assert (outdir / "program_candidate_comparison.json").exists()
    assert (outdir / "program_candidate_state.refinement.json").exists()
    assert (outdir / "program_refinement_episode.json").exists()

    gepa_manifest = json.loads(
        (outdir / "gepa_candidate" / "manifest.json").read_text(encoding="utf-8")
    )
    state = json.loads(
        (outdir / "program_candidate_state.refinement.json").read_text(encoding="utf-8")
    )
    assert (
        state["candidate_identity"]["candidate_id"]
        == gepa_manifest["candidate_assembly"]["candidate_id"]
    )
    assert state["truth_summary"]["comparison_present"] is True
    assert state["truth_summary"]["gepa_refinement_present"] is True
    assert state["truth_summary"]["winner_selected"] is False
    assert _file_hashes(program_root) == before_source_hashes
    assert _file_hashes(tmp_path / "program-gepa") == before_optimizer_hashes


def test_program_refinement_episode_gepa_path_rejects_ambiguous_or_drifted_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    outdir = tmp_path / "refinement-episode"

    with pytest.raises(ProgramRefinementEpisodeError, match="second_candidate_outdir"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="compare one ready GEPA candidate",
            gepa_result_path=gepa_result,
            second_candidate_outdir=outdir / "second",
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="candidate_id"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="compare one drifted GEPA candidate",
            gepa_result_path=_write_ready_gepa_result(
                tmp_path / "drifted", program_root, identity_drift=True
            ),
        )

    assert not (outdir / "gepa_candidate" / "manifest.json").exists()
    assert not (outdir / "program_refinement_episode.json").exists()


def test_program_refinement_episode_rejects_gepa_output_conflicts_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    outdir = tmp_path / "refinement-episode"

    with pytest.raises(
        ProgramRefinementEpisodeError, match="source generated program root"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="compare one ready GEPA candidate",
            gepa_result_path=gepa_result,
            gepa_candidate_outdir=program_root / "gepa_candidate",
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="conflicts"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="compare one ready GEPA candidate",
            gepa_result_path=gepa_result,
            gepa_candidate_result_out=outdir / "gepa_candidate" / "result.json",
        )

    assert not outdir.exists()


def test_program_refinement_episode_records_decision_without_second_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    before_source_hashes = _file_hashes(program_root)
    outdir = tmp_path / "refinement-episode"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "episode",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--outdir",
            str(outdir),
            "--decision-outcome",
            "withhold",
            "--decided-by",
            "operator-test",
            "--rationale",
            "withhold without collecting another local candidate",
            "--no-generate-second-candidate",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["schema_version"] == "program-refinement-episode-v1"
    assert payload["status"] == "decision_recorded"
    assert payload["steps"]["decision_record"]["outcome"] == "withhold"
    assert payload["steps"]["second_candidate"] == {
        "status": "skipped",
        "root_path": None,
        "manifest_path": None,
        "comparison_path": None,
        "comparison_status": None,
    }
    assert payload["effect"]["local_second_candidate_generated"] is False
    assert payload["effect"]["local_comparison_written"] is False
    assert payload["effect"]["external_authority_mutated"] is False
    assert payload["effect"]["winner_selected"] is False
    assert (outdir / "program_refinement_episode.json").exists()
    assert (outdir / "program_candidate_state.refinement.json").exists()
    assert not (outdir / "second_candidate").exists()
    assert not (outdir / "program_candidate_comparison.json").exists()
    state = json.loads(
        (outdir / "program_candidate_state.refinement.json").read_text(encoding="utf-8")
    )
    assert state["truth_summary"]["decision_record_present"] is True
    assert state["truth_summary"]["comparison_present"] is False
    assert _file_hashes(program_root) == before_source_hashes


def test_program_refinement_episode_rejects_second_candidate_without_request_more_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "refinement-episode"

    with pytest.raises(ProgramRefinementEpisodeError, match="request_more_evidence"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="withhold without collecting another local candidate",
            generate_second_candidate=True,
        )

    assert not outdir.exists()


def test_program_refinement_episode_rejects_promotion_plan_without_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "refinement-episode"

    with pytest.raises(
        ProgramRefinementEpisodeError, match="second-candidate comparison"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="withhold without collecting another local candidate",
            generate_second_candidate=False,
            generate_promotion_plan=True,
            promotion_plan_target="local_preferred_candidate",
            promotion_plan_authority_owner="operator-test",
        )

    assert not outdir.exists()


def test_program_refinement_episode_rejects_invalid_promotion_plan_options_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "refinement-episode"

    with pytest.raises(ProgramRefinementEpisodeError, match="require --promotion-plan"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate and local plan only",
            promotion_plan_target="local_preferred_candidate",
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="unsupported"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate and local plan only",
            generate_promotion_plan=True,
            promotion_plan_target="deployment",
            promotion_plan_authority_owner="operator-test",
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="promotion_plan_target"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate and local plan only",
            generate_promotion_plan=True,
            promotion_plan_authority_owner="operator-test",
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="control artifact name"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate and local plan only",
            generate_promotion_plan=True,
            promotion_plan_target="local_preferred_candidate",
            promotion_plan_authority_owner="operator-test",
            promotion_plan_out=outdir / "manifest.json",
        )

    assert not outdir.exists()


def test_program_refinement_episode_rejects_promotion_plan_path_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "refinement-episode"

    with pytest.raises(
        ProgramRefinementEpisodeError, match="source generated program root"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate and local plan only",
            generate_promotion_plan=True,
            promotion_plan_target="local_preferred_candidate",
            promotion_plan_authority_owner="operator-test",
            promotion_plan_out=program_root / "promotion_plan.json",
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="conflicts"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate and local plan only",
            generate_promotion_plan=True,
            promotion_plan_target="local_preferred_candidate",
            promotion_plan_authority_owner="operator-test",
            promotion_plan_out=outdir / "second_candidate" / "promotion_plan.json",
        )

    assert not outdir.exists()


def test_program_refinement_episode_rejects_duplicate_or_source_root_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "refinement-episode"

    with pytest.raises(ProgramRefinementEpisodeError, match="duplicates"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate",
            proposal_out=outdir / "same.json",
            review_out=outdir / "same.json",
        )

    with pytest.raises(
        ProgramRefinementEpisodeError, match="source generated program root"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate",
            proposal_out=program_root / "refinement_proposal.json",
        )

    with pytest.raises(
        ProgramRefinementEpisodeError, match="second_candidate_outdir conflicts"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="collect one bounded second candidate",
            proposal_out=outdir / "sidecar.json",
            second_candidate_outdir=outdir / "sidecar.json" / "second_candidate",
        )
