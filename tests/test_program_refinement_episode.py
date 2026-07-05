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
from dspx.services import program_refinement_episode as episode_service
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_jury_execution import (
    build_program_jury_execution_result,
    write_program_jury_execution_result,
)
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


def _assert_no_episode_sidecars(outdir: Path) -> None:
    for name in (
        "refinement_proposal.json",
        "promotion_review_refined.json",
        "promotion_decision_record.json",
        "program_candidate_comparison.json",
        "gepa_candidate_result.json",
        "promotion_plan.json",
        "meta_adjudication_plan.json",
        "external_authority_export_preflight.json",
        "program_candidate_state.refinement.json",
        "program_refinement_episode.json",
    ):
        assert not (outdir / name).exists(), name


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


def _model_jury_evidence_ref(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "schema_version": json.loads(path.read_text(encoding="utf-8")).get(
            "schema_version"
        ),
    }


def _model_jury_result_for_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    assembly = manifest.get("candidate_assembly") or {}
    root = Path(str(assembly["root_path"]))
    manifest_path = root / "manifest.json"
    jury_path = root / "jury.json"
    selection_path = root / "jury_selection.json"
    rubric_path = root / "jury_rubric.json"
    evidence_entries = [
        _model_jury_evidence_ref(path)
        for path in (root / "behavior_results.json", root / "behavior_episode.json")
        if path.exists()
    ]
    return {
        "schema_version": "program-model-jury-results-v1",
        "status": "executed",
        "identity": _identity(manifest),
        "created_from": {
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "jury_path": str(jury_path.resolve()),
            "jury_sha256": hashlib.sha256(jury_path.read_bytes()).hexdigest(),
            "jury_selection_path": str(selection_path.resolve()),
            "jury_selection_sha256": hashlib.sha256(
                selection_path.read_bytes()
            ).hexdigest(),
            "jury_rubric_path": str(rubric_path.resolve()),
            "jury_rubric_sha256": hashlib.sha256(rubric_path.read_bytes()).hexdigest(),
        },
        "jury": {
            "execution_mode": "provider_backed_model",
            "provider_backed_model_calls": True,
            "selected_juror_count": 1,
        },
        "adjudicator": {
            "repo": "target-repo",
            "promotion_authority": False,
        },
        "evidence": {"entry_count": len(evidence_entries), "entries": evidence_entries},
        "juror_results": [
            {
                "juror_id": "authority_agent",
                "status": "judged",
                "judgment": {"outcome": "request_more_evidence"},
            }
        ],
        "aggregate": {
            "judgment_counts": {
                "supports_review_evidence": 0,
                "withhold": 0,
                "reject": 0,
                "request_more_evidence": 1,
                "failed": 0,
            },
            "recommendation": "request_more_evidence",
            "unique_improvement_requests": ["add more target evidence"],
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


def _write_local_jury_results(program_root: Path, out_path: Path) -> Path:
    result = build_program_jury_execution_result(
        manifest_path=program_root / "manifest.json"
    )
    write_program_jury_execution_result(result, out_path)
    return out_path


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


def test_program_refinement_episode_writes_export_preflight_as_state_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    before_source_hashes = _file_hashes(program_root)
    outdir = tmp_path / "refinement-episode"
    preflight_path = outdir / "external_authority_export_preflight.json"

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
            "write a local export preflight without applying authority",
            "--no-generate-second-candidate",
            "--external-ref",
            "AK-LOCAL-PREFLIGHT",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["status"] == "decision_recorded"
    assert payload["created_from"]["external_ref"] == "AK-LOCAL-PREFLIGHT"
    assert payload["created_from"]["export_preflight_path"] == str(
        preflight_path.resolve()
    )
    preflight_step = payload["steps"]["external_authority_export_preflight"]
    assert preflight_step["status"] in {"ready_not_applied", "incomplete_preflight"}
    assert preflight_step["path"] == str(preflight_path.resolve())
    assert preflight_step["state_evidence_present"] is True
    assert preflight_step["ready_for_future_apply"] is False
    assert preflight_step["evidence_only"] is True
    assert payload["effect"]["external_authority_export_preflight_written"] is True
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["external_authority_mutated"] is False
    assert payload["non_authority"]["external_authority_export_preflight_only"] is True
    assert payload["non_authority"]["promotion_authority"] is False

    preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
    before_preflight_hash = hashlib.sha256(preflight_path.read_bytes()).hexdigest()
    assert preflight_payload["effect"]["ak_called"] is False
    assert preflight_payload["effect"]["external_authority_mutated"] is False
    assert preflight_payload["preflight"]["ready_for_future_apply"] is False
    assert preflight_payload["created_from"]["decision_record_path"] == str(
        (outdir / "promotion_decision_record.json").resolve()
    )

    state = json.loads(
        (outdir / "program_candidate_state.refinement.json").read_text(encoding="utf-8")
    )
    preflight = state["promotion_state"]["external_authority_export_preflight"]
    assert preflight["present"] is True
    assert (
        preflight["schema_version"] == "program-external-authority-export-preflight-v1"
    )
    assert preflight["status"] in {"ready_not_applied", "incomplete_preflight"}
    assert preflight["ak_called"] is False
    assert preflight["ready_for_future_apply"] is False
    assert state["truth_summary"]["ak_called"] is False
    assert state["truth_summary"]["ready_for_future_apply"] is False
    assert state["artifact_hashes"]["export_preflight_sha256"] == before_preflight_hash
    assert _file_hashes(program_root) == before_source_hashes


def test_program_refinement_episode_revalidates_export_preflight_before_workflow_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "episode-export-preflight-drift"
    preflight_path = outdir / "external_authority_export_preflight.json"
    original_write_state = episode_service.write_program_candidate_state

    def tamper_preflight_after_state(*args: Any, **kwargs: Any) -> dict[str, Any]:
        state_payload = original_write_state(*args, **kwargs)
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        preflight["effect"]["ak_called"] = True
        _write_json(preflight_path, preflight)
        return state_payload

    monkeypatch.setattr(
        episode_service,
        "write_program_candidate_state",
        tamper_preflight_after_state,
    )

    with pytest.raises(ProgramRefinementEpisodeError, match="ak_called false"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="reject drifted export preflight before workflow summary",
            generate_second_candidate=False,
            external_ref="AK-LOCAL-PREFLIGHT",
        )

    _assert_no_episode_sidecars(outdir)


def test_program_refinement_episode_rejects_export_preflight_options_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "episode-export-preflight-missing-ref"

    with pytest.raises(ProgramRefinementEpisodeError, match="external_ref"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="reject export preflight output without external ref",
            generate_second_candidate=False,
            export_preflight_out=outdir / "export_preflight.json",
        )

    assert not (outdir / "program_refinement_episode.json").exists()


def test_program_refinement_episode_rejects_export_preflight_output_overlap_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "episode-export-preflight-overlap"
    overlap = outdir / "same.json"

    with pytest.raises(ProgramRefinementEpisodeError, match="duplicates sidecar"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="reject output overwrite of generated state",
            generate_second_candidate=False,
            external_ref="AK-LOCAL-PREFLIGHT",
            export_preflight_out=overlap,
            state_out=overlap,
        )

    assert not (outdir / "program_refinement_episode.json").exists()


def test_program_refinement_episode_rejects_oracle_report_output_overlap_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    before_report_hash = hashlib.sha256(report_path.read_bytes()).hexdigest()
    outdir = tmp_path / "episode-oracle-report-overlap"

    with pytest.raises(
        ProgramRefinementEpisodeError, match="protected input oracle_report"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="reject output overwrite of required oracle report input",
            generate_second_candidate=False,
            proposal_out=report_path,
        )

    assert hashlib.sha256(report_path.read_bytes()).hexdigest() == before_report_hash
    assert not (outdir / "program_refinement_episode.json").exists()


def test_program_refinement_episode_rejects_export_preflight_for_generated_state_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)

    with pytest.raises(ProgramRefinementEpisodeError, match="source-candidate scoped"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=tmp_path / "episode-export-preflight-gepa",
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="reject source-scoped export preflight for generated candidate state",
            gepa_result_path=gepa_result,
            external_ref="AK-LOCAL-PREFLIGHT",
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="source-candidate scoped"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=tmp_path / "episode-export-preflight-plan",
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="reject source-scoped export preflight for planned candidate state",
            generate_promotion_plan=True,
            promotion_plan_target="local_preferred_candidate",
            promotion_plan_authority_owner="operator-test",
            external_ref="AK-LOCAL-PREFLIGHT",
        )


def test_program_refinement_episode_consumes_local_jury_results_as_state_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    jury_path = _write_local_jury_results(
        program_root, tmp_path / "promotion" / "jury_results.json"
    )
    before_source_hashes = _file_hashes(program_root)
    before_jury_hash = hashlib.sha256(jury_path.read_bytes()).hexdigest()
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
            "consume already-produced local jury evidence only",
            "--no-generate-second-candidate",
            "--jury-results",
            str(jury_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["status"] == "decision_recorded"
    assert payload["created_from"]["jury_results_path"] == str(jury_path.resolve())
    assert payload["steps"]["jury_results"] == {
        "status": "included",
        "path": str(jury_path.resolve()),
        "state_evidence_present": True,
        "generated_by_episode": False,
        "jury_status": None,
        "evidence_only": True,
    }
    assert payload["steps"]["model_jury_results"]["status"] == "skipped"
    assert payload["effect"]["local_second_candidate_generated"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["non_authority"]["promotion_authority"] is False

    state = json.loads(
        (outdir / "program_candidate_state.refinement.json").read_text(encoding="utf-8")
    )
    assert state["promotion_state"]["jury_results"]["present"] is True
    assert state["promotion_state"]["jury_results"]["schema_version"] == (
        "program-jury-results-v2"
    )
    assert state["truth_summary"]["jury_results_present"] is True
    assert "run_local_jury_sidecar" not in state["truth_summary"]["required_next_steps"]
    assert state["artifact_hashes"]["jury_results_sha256"] == before_jury_hash
    assert _file_hashes(program_root) == before_source_hashes
    assert hashlib.sha256(jury_path.read_bytes()).hexdigest() == before_jury_hash


def test_program_refinement_episode_can_generate_local_jury_results_as_state_evidence(
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
            "generate local jury evidence inside the guided episode",
            "--no-generate-second-candidate",
            "--run-local-jury",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    jury_path = outdir / "jury_results.json"
    assert jury_path.exists()
    jury_payload = json.loads(jury_path.read_text(encoding="utf-8"))
    assert jury_payload["schema_version"] == "program-jury-results-v2"
    assert jury_payload["jury"]["execution_mode"] == "local_deterministic"
    assert jury_payload["jury"]["provider_backed_model_calls"] is False
    assert jury_payload["effect"]["external_authority_mutated"] is False
    assert jury_payload["non_authority"]["promotion_authority"] is False
    assert payload["created_from"]["jury_results_path"] == str(jury_path.resolve())
    assert payload["created_from"]["jury_results_generated"] is True
    assert payload["steps"]["jury_results"] == {
        "status": "generated",
        "path": str(jury_path.resolve()),
        "state_evidence_present": True,
        "generated_by_episode": True,
        "jury_status": jury_payload["status"],
        "evidence_only": True,
    }
    assert str(jury_path.resolve()) in payload["generated_sidecars"]
    assert payload["effect"]["local_jury_results_written"] is True
    assert payload["effect"]["local_jury_provider_called"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["non_authority"]["local_jury_evidence_only"] is True
    assert payload["non_authority"]["promotion_authority"] is False

    state = json.loads(
        (outdir / "program_candidate_state.refinement.json").read_text(encoding="utf-8")
    )
    assert state["promotion_state"]["jury_results"]["present"] is True
    assert (
        state["artifact_hashes"]["jury_results_sha256"]
        == hashlib.sha256(jury_path.read_bytes()).hexdigest()
    )
    assert _file_hashes(program_root) == before_source_hashes


def test_program_refinement_episode_revalidates_local_jury_before_workflow_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "episode-jury-summary-drift"
    original_write_state = episode_service.write_program_candidate_state

    def tampering_state_writer(*args: Any, **kwargs: Any) -> dict[str, Any]:
        state = original_write_state(*args, **kwargs)
        jury_path = outdir / "jury_results.json"
        jury_payload = json.loads(jury_path.read_text(encoding="utf-8"))
        jury_payload["effect"]["external_authority_mutated"] = True
        _write_json(jury_path, jury_payload)
        return state

    monkeypatch.setattr(
        episode_service, "write_program_candidate_state", tampering_state_writer
    )

    with pytest.raises(
        ProgramRefinementEpisodeError, match="external_authority_mutated"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="revalidate local jury evidence before workflow summary",
            generate_second_candidate=False,
            run_local_jury=True,
        )

    _assert_no_episode_sidecars(outdir)
    assert not (outdir / "jury_results.json").exists()


def test_program_refinement_episode_rejects_ambiguous_or_unsafe_local_jury_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    jury_path = _write_local_jury_results(
        program_root, tmp_path / "promotion" / "jury_results.json"
    )

    with pytest.raises(ProgramRefinementEpisodeError, match="cannot be combined"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=tmp_path / "episode-ambiguous-jury",
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="reject ambiguous generated and supplied jury evidence",
            generate_second_candidate=False,
            run_local_jury=True,
            jury_results_path=jury_path,
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="requires run_local_jury"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=tmp_path / "episode-unused-jury-out",
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="reject inert jury output path",
            generate_second_candidate=False,
            jury_results_out=tmp_path / "jury_results.json",
        )

    with pytest.raises(
        ProgramRefinementEpisodeError, match="source generated program root"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=tmp_path / "episode-jury-inside-source",
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="reject generated jury output inside the candidate root",
            generate_second_candidate=False,
            run_local_jury=True,
            jury_results_out=program_root / "jury_results.json",
        )
    _assert_no_episode_sidecars(tmp_path / "episode-jury-inside-source")


def test_program_refinement_episode_rolls_back_generated_local_jury_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "episode-jury-failure"
    (program_root / "jury.json").write_text('{"schema_version":"tampered"}\n')

    with pytest.raises(ProgramRefinementEpisodeError, match="schema_version"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="rollback stale partial episode sidecars after jury failure",
            generate_second_candidate=False,
            run_local_jury=True,
        )

    _assert_no_episode_sidecars(outdir)
    assert not (outdir / "jury_results.json").exists()


def test_program_refinement_episode_can_write_meta_adjudication_plan(
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
            "capture local adjudication preflight plan without authority",
            "--no-generate-second-candidate",
            "--run-local-jury",
            "--meta-adjudication-plan",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    plan_path = outdir / "meta_adjudication_plan.json"
    assert plan_path.exists()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["schema_version"] == "program-meta-adjudication-plan-v1"
    assert plan["status"] == "planned_not_executed"
    assert plan["lifecycle_state"] == "meta_adjudication_plan_ready"
    assert plan["effect"]["provider_called"] is False
    assert plan["effect"]["ak_mutated"] is False
    assert plan["non_authority"]["promotion_authority"] is False
    assert plan["sidecars"]["oracle_report"]["status"] == "present"
    assert plan["sidecars"]["jury_results"]["status"] == "present"
    assert plan["sidecars"]["review"]["status"] == "present"
    assert plan["sidecars"]["decision_record"]["status"] == "present"

    meta_step = payload["steps"]["meta_adjudication_plan"]
    assert meta_step["status"] == "planned_not_executed"
    assert meta_step["path"] == str(plan_path.resolve())
    assert meta_step["lifecycle_state"] == "meta_adjudication_plan_ready"
    assert meta_step["evidence_only"] is True
    assert str(plan_path.resolve()) in payload["generated_sidecars"]
    assert payload["effect"]["local_meta_adjudication_plan_written"] is True
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["non_authority"]["local_meta_adjudication_plan_only"] is True
    assert payload["non_authority"]["promotion_authority"] is False
    assert _file_hashes(program_root) == before_source_hashes


def test_program_refinement_episode_revalidates_meta_adjudication_plan_before_workflow_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "episode-meta-summary-drift"
    original_write_state = episode_service.write_program_candidate_state

    def tampering_state_writer(*args: Any, **kwargs: Any) -> dict[str, Any]:
        state = original_write_state(*args, **kwargs)
        meta_path = outdir / "meta_adjudication_plan.json"
        meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
        meta_payload["effect"]["provider_called"] = True
        _write_json(meta_path, meta_payload)
        return state

    monkeypatch.setattr(
        episode_service, "write_program_candidate_state", tampering_state_writer
    )

    with pytest.raises(ProgramRefinementEpisodeError, match="effect flags"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="revalidate meta-adjudication plan before workflow summary",
            generate_second_candidate=False,
            run_local_jury=True,
            generate_meta_adjudication_plan=True,
        )

    _assert_no_episode_sidecars(outdir)
    assert not (outdir / "jury_results.json").exists()
    assert not (outdir / "meta_adjudication_plan.json").exists()


def test_program_refinement_episode_rejects_unsafe_meta_adjudication_plan_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)

    with pytest.raises(ProgramRefinementEpisodeError, match="requires"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=tmp_path / "episode-unused-meta-out",
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="reject inert meta plan output path",
            generate_second_candidate=False,
            meta_adjudication_plan_out=tmp_path / "meta-plan.json",
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="source-candidate scoped"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=tmp_path / "episode-meta-gepa",
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="reject source-scoped meta plan for GEPA state",
            gepa_result_path=gepa_result,
            generate_meta_adjudication_plan=True,
        )

    with pytest.raises(
        ProgramRefinementEpisodeError, match="source generated program root"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=tmp_path / "episode-meta-inside-source",
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="reject meta plan output inside source candidate",
            generate_second_candidate=False,
            generate_meta_adjudication_plan=True,
            meta_adjudication_plan_out=program_root / "meta_adjudication_plan.json",
        )
    _assert_no_episode_sidecars(tmp_path / "episode-meta-inside-source")


def test_program_refinement_episode_rolls_back_meta_adjudication_plan_on_later_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    outdir = tmp_path / "episode-meta-rollback"

    with pytest.raises(ProgramRefinementEpisodeError, match="manifest.json"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="rollback meta plan when later state write fails",
            generate_second_candidate=False,
            run_local_jury=True,
            generate_meta_adjudication_plan=True,
            state_out=outdir / "manifest.json",
        )

    _assert_no_episode_sidecars(outdir)
    assert not (outdir / "jury_results.json").exists()
    assert not (outdir / "meta_adjudication_plan.json").exists()


def test_program_refinement_episode_rejects_invalid_local_jury_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    jury_path = _write_local_jury_results(
        program_root, tmp_path / "promotion" / "jury_results.json"
    )
    bad_jury = json.loads(jury_path.read_text(encoding="utf-8"))
    bad_jury["identity"] = {**bad_jury["identity"], "candidate_id": "wrong"}
    bad_jury_path = tmp_path / "promotion" / "bad_jury_results.json"
    _write_json(bad_jury_path, bad_jury)

    identity_drift_outdir = tmp_path / "episode-jury-identity-drift"
    with pytest.raises(ProgramRefinementEpisodeError, match="identity"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=identity_drift_outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="reject stale local jury evidence",
            generate_second_candidate=False,
            jury_results_path=bad_jury_path,
        )
    _assert_no_episode_sidecars(identity_drift_outdir)

    bad_jury = json.loads(jury_path.read_text(encoding="utf-8"))
    bad_jury["non_authority"] = {
        **bad_jury["non_authority"],
        "promotion_authority": True,
    }
    bad_jury_path = tmp_path / "promotion" / "bad_jury_authority.json"
    _write_json(bad_jury_path, bad_jury)

    authority_drift_outdir = tmp_path / "episode-jury-authority-drift"
    with pytest.raises(ProgramRefinementEpisodeError, match="non-authority"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=authority_drift_outdir,
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="reject authority-widened local jury evidence",
            generate_second_candidate=False,
            jury_results_path=bad_jury_path,
        )
    _assert_no_episode_sidecars(authority_drift_outdir)


def test_program_refinement_episode_rejects_jury_output_overlap_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    jury_path = _write_local_jury_results(
        program_root, tmp_path / "promotion" / "jury_results.json"
    )
    before_jury_hash = hashlib.sha256(jury_path.read_bytes()).hexdigest()

    with pytest.raises(ProgramRefinementEpisodeError, match="protected input"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=tmp_path / "episode-jury-overlap",
            decision_outcome="withhold",
            decided_by="operator-test",
            rationale="reject output overwrite of local jury input",
            generate_second_candidate=False,
            jury_results_path=jury_path,
            state_out=jury_path,
        )

    assert hashlib.sha256(jury_path.read_bytes()).hexdigest() == before_jury_hash
    assert not (
        tmp_path / "episode-jury-overlap" / "program_refinement_episode.json"
    ).exists()


def test_program_refinement_episode_consumes_model_jury_results_as_local_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    model_jury_path = tmp_path / "promotion" / "model_jury_results.json"
    _write_json(model_jury_path, _model_jury_result_for_manifest(manifest))
    before_source_hashes = _file_hashes(program_root)
    before_model_jury_hash = hashlib.sha256(model_jury_path.read_bytes()).hexdigest()
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
            "consume already-produced provider-backed review evidence only",
            "--model-jury-results",
            str(model_jury_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    model_step = payload["steps"]["model_jury_results"]
    assert model_step == {
        "status": "included",
        "path": str(model_jury_path.resolve()),
        "review_evidence_present": True,
        "state_evidence_present": True,
        "evidence_only": True,
    }
    assert payload["created_from"]["model_jury_results_path"] == str(
        model_jury_path.resolve()
    )
    assert payload["effect"]["winner_selected"] is False
    assert payload["non_authority"]["promotion_authority"] is False
    assert payload["non_authority"]["automatic_promotion"] is False

    review = json.loads((outdir / "promotion_review_refined.json").read_text())
    review_model_jury = review["evidence_summary"]["model_jury_results"]
    assert review_model_jury["present"] is True
    assert review_model_jury["path"] == str(model_jury_path.resolve())
    assert review_model_jury["sha256"] == before_model_jury_hash
    assert review_model_jury["schema_version"] == "program-model-jury-results-v1"
    assert (
        review["promotion_review_delta"]["model_jury_execution"]
        == "satisfied_by_explicit_model_jury_results"
    )

    state = json.loads(
        (outdir / "program_candidate_state.refinement.json").read_text(encoding="utf-8")
    )
    assert state["promotion_state"]["model_jury_results"]["present"] is True
    assert state["truth_summary"]["model_jury_results_present"] is True
    assert (
        state["artifact_hashes"]["model_jury_results_sha256"] == before_model_jury_hash
    )
    assert _file_hashes(program_root) == before_source_hashes
    assert (
        hashlib.sha256(model_jury_path.read_bytes()).hexdigest()
        == before_model_jury_hash
    )


def test_program_refinement_episode_rejects_invalid_model_jury_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    bad_model_jury = _model_jury_result_for_manifest(manifest)
    bad_model_jury["identity"] = {**bad_model_jury["identity"], "candidate_id": "wrong"}
    bad_model_jury_path = tmp_path / "promotion" / "bad_model_jury_results.json"
    _write_json(bad_model_jury_path, bad_model_jury)

    identity_drift_outdir = tmp_path / "episode-identity-drift"
    with pytest.raises(ProgramRefinementEpisodeError, match="identity"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=identity_drift_outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="reject stale model-jury evidence",
            model_jury_results_path=bad_model_jury_path,
        )
    _assert_no_episode_sidecars(identity_drift_outdir)

    bad_model_jury = _model_jury_result_for_manifest(manifest)
    bad_model_jury["effect"] = {
        **bad_model_jury["effect"],
        "external_authority_mutated": True,
    }
    bad_model_jury_path = tmp_path / "promotion" / "bad_model_jury_authority.json"
    _write_json(bad_model_jury_path, bad_model_jury)

    authority_drift_outdir = tmp_path / "episode-authority-drift"
    with pytest.raises(ProgramRefinementEpisodeError, match="effect"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=authority_drift_outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="reject authority-widened model-jury evidence",
            model_jury_results_path=bad_model_jury_path,
        )
    _assert_no_episode_sidecars(authority_drift_outdir)


def test_program_refinement_episode_revalidates_model_jury_before_workflow_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    model_jury_path = tmp_path / "promotion" / "model_jury_results.json"
    _write_json(model_jury_path, _model_jury_result_for_manifest(manifest))
    outdir = tmp_path / "episode-model-jury-summary-drift"
    original_write_state = episode_service.write_program_candidate_state

    def tampering_state_writer(*args: Any, **kwargs: Any) -> dict[str, Any]:
        state = original_write_state(*args, **kwargs)
        model_jury_payload = json.loads(model_jury_path.read_text(encoding="utf-8"))
        model_jury_payload["effect"]["external_authority_mutated"] = True
        _write_json(model_jury_path, model_jury_payload)
        return state

    monkeypatch.setattr(
        episode_service, "write_program_candidate_state", tampering_state_writer
    )

    with pytest.raises(
        ProgramRefinementEpisodeError, match="external_authority_mutated"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="revalidate model-jury evidence before workflow summary",
            model_jury_results_path=model_jury_path,
        )

    _assert_no_episode_sidecars(outdir)


def test_program_refinement_episode_rejects_model_jury_output_overlap_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    model_jury_path = tmp_path / "promotion" / "model_jury_results.json"
    _write_json(model_jury_path, _model_jury_result_for_manifest(manifest))
    before_model_jury_hash = hashlib.sha256(model_jury_path.read_bytes()).hexdigest()

    with pytest.raises(ProgramRefinementEpisodeError, match="protected input"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=tmp_path / "episode-overlap",
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="reject output overwrite of evidence input",
            model_jury_results_path=model_jury_path,
            review_out=model_jury_path,
        )

    assert (
        hashlib.sha256(model_jury_path.read_bytes()).hexdigest()
        == before_model_jury_hash
    )
    assert not (
        tmp_path / "episode-overlap" / "program_refinement_episode.json"
    ).exists()


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
            "collect one bounded second candidate, local jury, and local plan only",
            "--run-local-jury",
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
    assert payload["steps"]["jury_results"]["status"] == "generated"
    assert payload["steps"]["jury_results"]["state_evidence_present"] is True
    assert payload["effect"]["local_promotion_plan_written"] is True
    assert payload["effect"]["local_jury_results_written"] is True
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
    assert state["truth_summary"]["jury_results_present"] is True
    assert state["truth_summary"]["oracle_report_present"] is False
    assert state["truth_summary"]["winner_selected"] is False
    assert state["evidence_state"]["oracle_report"]["present"] is False
    assert state["promotion_state"]["promotion_plan"]["allowed_for_apply"] is False
    assert state["created_from"]["source_manifest_path"] == str(
        (program_root / "manifest.json").resolve()
    )
    assert (outdir / "jury_results.json").exists()
    assert not (program_root / "promotion_plan.json").exists()
    assert not (program_root / "jury_results.json").exists()
    assert not (second_candidate / "promotion_plan.json").exists()
    assert not (second_candidate / "jury_results.json").exists()
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


def test_program_refinement_episode_revalidates_gepa_result_before_workflow_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, report_path = _materialize_program_and_report(tmp_path, monkeypatch)
    gepa_result = _write_ready_gepa_result(tmp_path, program_root)
    outdir = tmp_path / "refinement-episode"
    original_workflow = (
        episode_service.materialize_and_compare_gepa_refinement_candidate
    )

    def tampered_gepa_workflow(**kwargs: Any) -> dict[str, Any]:
        workflow = original_workflow(**kwargs)
        result_path = Path(str(kwargs["gepa_candidate_result_out"])).resolve()
        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        result_payload["effect"]["external_authority_mutated"] = True
        _write_json(result_path, result_payload)
        return workflow

    monkeypatch.setattr(
        episode_service,
        "materialize_and_compare_gepa_refinement_candidate",
        tampered_gepa_workflow,
    )

    with pytest.raises(
        ProgramRefinementEpisodeError, match="external_authority_mutated"
    ):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="compare one ready GEPA candidate",
            gepa_result_path=gepa_result,
        )

    assert not (outdir / "program_refinement_episode.json").exists()
    _assert_no_episode_sidecars(outdir)


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

    with pytest.raises(
        ProgramRefinementEpisodeError, match="identity does not match|candidate_id"
    ):
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
    _assert_no_episode_sidecars(outdir)


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

    with pytest.raises(ProgramRefinementEpisodeError, match="protected input"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="compare one ready GEPA candidate",
            gepa_result_path=gepa_result,
            gepa_candidate_result_out=gepa_result,
        )

    with pytest.raises(ProgramRefinementEpisodeError, match="protected input"):
        run_program_refinement_episode(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            sidecar_outdir=outdir,
            decision_outcome="request_more_evidence",
            decided_by="operator-test",
            rationale="compare one ready GEPA candidate",
            gepa_result_path=gepa_result,
            gepa_candidate_outdir=gepa_result.parent,
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

    for protected_name in (
        "manifest.json",
        "plan.json",
        "intent.json",
        "dataset_manifest.json",
        "eval_train.py",
    ):
        with pytest.raises(
            ProgramRefinementEpisodeError, match="control artifact name"
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
                promotion_plan_out=outdir / protected_name,
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
