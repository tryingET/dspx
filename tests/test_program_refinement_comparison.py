from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_promotion_decision import (
    build_program_promotion_decision_record,
    write_program_promotion_decision_record,
)
from dspx.services.program_promotion_refinement import (
    build_program_promotion_refinement,
)
from dspx.services.program_refinement import build_program_refinement_proposal
from dspx.services.program_refinement_candidate import materialize_refinement_candidate
from dspx.services.program_refinement_comparison import (
    build_program_refinement_candidate_comparison,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_full_refinement_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, Path]:
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

    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )
    assert proposal["status"] == "proposed"
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)

    refined_review = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )
    review_path = tmp_path / "promotion" / "promotion_review_refined.json"
    _write_json(review_path, refined_review)

    decision = build_program_promotion_decision_record(
        refined_review_path=review_path,
        outcome="request_more_evidence",
        decided_by="local_operator",
        rationale="Generate one bounded second candidate for observed mismatch.",
    )
    decision_path = tmp_path / "promotion" / "promotion_decision_record.json"
    write_program_promotion_decision_record(decision, decision_path)

    candidate = materialize_refinement_candidate(
        manifest_path=program_root / "manifest.json",
        refinement_proposal_path=proposal_path,
        decision_record_path=decision_path,
        outdir=tmp_path / "program-v2",
    )
    candidate_manifest = Path(str(candidate["candidate"]["manifest_path"]))
    assert candidate_manifest.exists()
    return program_root, candidate_manifest.parent, proposal_path, decision_path


def test_program_refine_compare_candidates_cli_writes_local_sidecar_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, candidate_root, proposal_path, decision_path = (
        _materialize_full_refinement_path(tmp_path, monkeypatch)
    )
    source_manifest = json.loads(
        (program_root / "manifest.json").read_text(encoding="utf-8")
    )
    candidate_manifest = json.loads(
        (candidate_root / "manifest.json").read_text(encoding="utf-8")
    )
    source_behavior = json.loads(
        (program_root / "behavior_results.json").read_text(encoding="utf-8")
    )
    candidate_behavior = json.loads(
        (candidate_root / "behavior_results.json").read_text(encoding="utf-8")
    )
    before_source_hashes = _file_hashes(program_root)
    before_candidate_hashes = _file_hashes(candidate_root)
    out_path = tmp_path / "refinement" / "candidate_comparison.json"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "compare-candidates",
            "--source-manifest",
            str(program_root / "manifest.json"),
            "--candidate-manifest",
            str(candidate_root / "manifest.json"),
            "--refinement-proposal",
            str(proposal_path),
            "--decision-record",
            str(decision_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == "program-refinement-candidate-comparison-v1"
    assert payload["status"] == "compared"
    assert payload["source_identity"] == {
        "request_id": source_manifest["request"]["request_id"],
        "candidate_id": source_manifest["candidate_assembly"]["candidate_id"],
        "assembly_id": source_manifest["candidate_assembly"]["assembly_id"],
        "episode_id": source_manifest["execution_episode"]["episode_id"],
        "receipt_bundle_id": source_manifest["receipt_bundle"]["receipt_bundle_id"],
    }
    assert payload["candidate_identity"] == {
        "request_id": candidate_manifest["request"]["request_id"],
        "candidate_id": candidate_manifest["candidate_assembly"]["candidate_id"],
        "assembly_id": candidate_manifest["candidate_assembly"]["assembly_id"],
        "episode_id": candidate_manifest["execution_episode"]["episode_id"],
        "receipt_bundle_id": candidate_manifest["receipt_bundle"]["receipt_bundle_id"],
    }
    assert payload["source_identity"] != payload["candidate_identity"]
    assert payload["created_from"]["source_manifest_schema_version"] == (
        "program-candidate-assembly-v1"
    )
    assert payload["created_from"]["candidate_manifest_schema_version"] == (
        "program-candidate-assembly-v1"
    )
    assert payload["created_from"]["source_behavior_results_path"] == str(
        (program_root / "behavior_results.json").resolve()
    )
    assert payload["created_from"]["candidate_behavior_results_path"] == str(
        (candidate_root / "behavior_results.json").resolve()
    )

    lineage = payload["lineage"]
    assert lineage["candidate_declares_refinement_lineage"] is True
    assert lineage["source_identity_matches_candidate_lineage"] is True
    assert lineage["decision_outcome"] == "request_more_evidence"
    assert lineage["refinement_proposal_id"]
    assert lineage["proposal_input_present"] is True
    assert lineage["decision_record_input_present"] is True

    comparison = payload["behavior_comparison"]
    assert comparison["source"]["behavior_results_present"] is True
    assert (
        comparison["source"]["behavior_status"] == source_behavior["summary"]["status"]
    )
    assert comparison["source"]["example_count"] == source_behavior["summary"]["total"]
    assert (
        comparison["source"]["status_counts"]
        == source_behavior["summary"]["status_counts"]
    )
    assert comparison["candidate"]["behavior_results_present"] is True
    assert (
        comparison["candidate"]["behavior_status"]
        == candidate_behavior["summary"]["status"]
    )
    assert (
        comparison["candidate"]["example_count"]
        == candidate_behavior["summary"]["total"]
    )
    assert (
        comparison["candidate"]["status_counts"]
        == candidate_behavior["summary"]["status_counts"]
    )
    delta = comparison["delta"]
    assert set(delta) >= {
        "source_failed_count",
        "candidate_failed_count",
        "failed_count_delta",
        "source_error_count",
        "candidate_error_count",
        "error_count_delta",
        "source_degraded_count",
        "candidate_degraded_count",
        "degraded_count_delta",
        "status_changed",
        "failure_signals_removed",
        "failure_signals_added",
        "failure_signals_persisted",
    }
    assert isinstance(payload["interpretation"]["improvement_observed"], bool)
    assert isinstance(payload["interpretation"]["needs_more_evidence"], bool)
    limits = "\n".join(payload["interpretation"]["limits"])
    assert "eval_examples.py" in limits
    assert "example-backed" in limits
    assert "not a promotion, ranking, or approval" in limits
    assert payload["effect"] == {
        "local_comparison_only": True,
        "source_program_files_mutated": False,
        "candidate_program_files_mutated": False,
        "new_candidate_generated": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
    }
    assert payload["non_authority"] == {
        "local_comparison_only": True,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "winner_selection": False,
        "automatic_promotion": False,
        "program_mutation": False,
        "new_candidate_generation": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    forbidden_text = json.dumps(payload, sort_keys=True).lower()
    assert "winner" not in payload["interpretation"]["summary"].lower()
    assert "best" not in forbidden_text
    assert "approved" not in forbidden_text
    assert "should deploy" not in forbidden_text
    assert _file_hashes(program_root) == before_source_hashes
    assert _file_hashes(candidate_root) == before_candidate_hashes
    assert not (program_root / "candidate_comparison.json").exists()
    assert not (candidate_root / "candidate_comparison.json").exists()
    assert not (program_root / "eval_behavior.py").exists()
    assert not (candidate_root / "eval_behavior.py").exists()
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()


def test_program_refine_compare_candidates_degrades_without_behavior_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    source = materialize_program_from_intent(
        ProgramIntent(
            name="NoExamplesSource",
            objective="Answer a question.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    candidate = materialize_program_from_intent(
        ProgramIntent(
            name="NoExamplesCandidate",
            objective="Answer a question.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program-v2",
    )
    source_root = Path(source.root_path)
    candidate_root = Path(candidate.root_path)
    before_source = _file_hashes(source_root)
    before_candidate = _file_hashes(candidate_root)

    payload = build_program_refinement_candidate_comparison(
        source_manifest_path=source_root / "manifest.json",
        candidate_manifest_path=candidate_root / "manifest.json",
    )

    assert payload["schema_version"] == "program-refinement-candidate-comparison-v1"
    assert payload["status"] == "insufficient_behavior_evidence"
    assert payload["behavior_comparison"]["source"] == {
        "behavior_results_present": False,
        "behavior_status": "insufficient_behavior_evidence",
        "example_count": 0,
        "status_counts": {},
        "failure_signals": [],
    }
    assert payload["behavior_comparison"]["candidate"] == {
        "behavior_results_present": False,
        "behavior_status": "insufficient_behavior_evidence",
        "example_count": 0,
        "status_counts": {},
        "failure_signals": [],
    }
    assert payload["interpretation"]["improvement_observed"] is False
    assert payload["interpretation"]["needs_more_evidence"] is True
    assert payload["lineage"]["candidate_declares_refinement_lineage"] is False
    assert payload["lineage"]["source_identity_matches_candidate_lineage"] is None
    assert _file_hashes(source_root) == before_source
    assert _file_hashes(candidate_root) == before_candidate
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()


def test_program_refine_compare_candidates_detects_lineage_source_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, candidate_root, _proposal_path, _decision_path = (
        _materialize_full_refinement_path(tmp_path, monkeypatch)
    )
    candidate_manifest_path = candidate_root / "manifest.json"
    candidate_manifest = json.loads(candidate_manifest_path.read_text(encoding="utf-8"))
    candidate_manifest["intent"]["options"]["refinement_lineage"]["source_identity"][
        "candidate_id"
    ] = "prog-cand-other"
    candidate_manifest_path.write_text(
        json.dumps(candidate_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    before_source = _file_hashes(program_root)
    before_candidate = _file_hashes(candidate_root)

    payload = build_program_refinement_candidate_comparison(
        source_manifest_path=program_root / "manifest.json",
        candidate_manifest_path=candidate_manifest_path,
    )

    assert payload["status"] == "compared"
    assert payload["lineage"]["candidate_declares_refinement_lineage"] is True
    assert payload["lineage"]["source_identity_matches_candidate_lineage"] is False
    assert _file_hashes(program_root) == before_source
    assert _file_hashes(candidate_root) == before_candidate


def _materialize_refinement_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path]:
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

    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )
    assert proposal["status"] == "proposed"
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)

    refined_review = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )
    review_path = tmp_path / "promotion" / "promotion_review_refined.json"
    _write_json(review_path, refined_review)

    decision = build_program_promotion_decision_record(
        refined_review_path=review_path,
        outcome="request_more_evidence",
        decided_by="local_operator",
        rationale="Generate one bounded second candidate for observed mismatch.",
    )
    decision_path = tmp_path / "promotion" / "promotion_decision_record.json"
    write_program_promotion_decision_record(decision, decision_path)
    return program_root, proposal_path, decision_path


def test_program_refine_generate_and_compare_cli_is_explicit_local_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, proposal_path, decision_path = _materialize_refinement_inputs(
        tmp_path,
        monkeypatch,
    )
    before_source_hashes = _file_hashes(program_root)
    before_proposal_hash = hashlib.sha256(proposal_path.read_bytes()).hexdigest()
    before_decision_hash = hashlib.sha256(decision_path.read_bytes()).hexdigest()
    outdir = tmp_path / "program-v2"
    comparison_out = tmp_path / "refinement" / "candidate_comparison.json"
    workflow_out = tmp_path / "refinement" / "generate_and_compare_result.json"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "generate-and-compare",
            "--manifest",
            str(program_root / "manifest.json"),
            "--refinement-proposal",
            str(proposal_path),
            "--decision-record",
            str(decision_path),
            "--outdir",
            str(outdir),
            "--comparison-out",
            str(comparison_out),
            "--workflow-out",
            str(workflow_out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert workflow_out.exists()
    assert json.loads(workflow_out.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == (
        "program-refinement-generate-and-compare-result-v1"
    )
    assert payload["status"] == "materialized_and_compared"
    assert payload["generation"]["schema_version"] == (
        "program-refinement-candidate-result-v1"
    )
    assert payload["generation"]["status"] == "materialized"
    assert payload["generation"]["candidate"]["root_path"] == str(outdir.resolve())
    assert payload["comparison_sidecar"]["path"] == str(comparison_out.resolve())
    assert payload["comparison_sidecar"]["schema_version"] == (
        "program-refinement-candidate-comparison-v1"
    )
    assert payload["comparison_sidecar"]["status"] == "compared"
    assert payload["comparison_sidecar"]["behavior_delta"]
    assert payload["effect"] == {
        "local_second_candidate_generated": True,
        "local_comparison_written": True,
        "source_program_files_mutated": False,
        "comparison_mutated_source_candidate": False,
        "comparison_mutated_refinement_candidate": False,
        "third_candidate_generated": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
    }
    assert payload["non_authority"] == {
        "local_generation_and_comparison_only": True,
        "program_gen_automation": False,
        "automatic_promotion": False,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "winner_selection": False,
        "external_authority_export": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    comparison = json.loads(comparison_out.read_text(encoding="utf-8"))
    assert comparison["schema_version"] == "program-refinement-candidate-comparison-v1"
    assert comparison["lineage"]["proposal_input_present"] is True
    assert comparison["lineage"]["decision_record_input_present"] is True
    assert comparison["lineage"]["source_identity_matches_candidate_lineage"] is True
    assert comparison["effect"]["new_candidate_generated"] is False
    assert comparison["non_authority"]["winner_selection"] is False
    assert (outdir / "manifest.json").exists()
    assert (outdir / "eval_examples.py").exists()
    assert not (outdir / "eval_behavior.py").exists()
    assert not (program_root / "eval_behavior.py").exists()
    assert _file_hashes(program_root) == before_source_hashes
    assert (
        hashlib.sha256(proposal_path.read_bytes()).hexdigest() == before_proposal_hash
    )
    assert (
        hashlib.sha256(decision_path.read_bytes()).hexdigest() == before_decision_hash
    )
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()
