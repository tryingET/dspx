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
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_refinement_decision_path(
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
        rationale="Generate one bounded second candidate for the observed mismatch.",
    )
    decision_path = tmp_path / "promotion" / "promotion_decision_record.json"
    write_program_promotion_decision_record(decision, decision_path)
    return program_root, proposal_path, decision_path


def test_program_refine_generate_candidate_cli_materializes_second_candidate_locally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, proposal_path, decision_path = _materialize_refinement_decision_path(
        tmp_path,
        monkeypatch,
    )
    source_manifest = json.loads(
        (program_root / "manifest.json").read_text(encoding="utf-8")
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    before_source_hashes = _file_hashes(program_root)
    before_proposal_hash = hashlib.sha256(proposal_path.read_bytes()).hexdigest()
    before_decision_hash = hashlib.sha256(decision_path.read_bytes()).hexdigest()
    outdir = tmp_path / "program-v2"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "generate-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--refinement-proposal",
            str(proposal_path),
            "--decision-record",
            str(decision_path),
            "--outdir",
            str(outdir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "program-refinement-candidate-result-v1"
    assert payload["status"] == "materialized"
    assert payload["created_from"] == {
        "manifest_path": str((program_root / "manifest.json").resolve()),
        "refinement_proposal_path": str(proposal_path.resolve()),
        "decision_record_path": str(decision_path.resolve()),
    }
    assert payload["source_identity"] == proposal["identity"] == decision["identity"]
    assert payload["decision"] == {
        "outcome": "request_more_evidence",
        "promotion_state_after_decision": "not_promoted",
    }
    assert (
        payload["applied_patch"]["constraints_added"]
        == proposal["bounded_refinement"]["next_candidate_intent_patch"]["constraints"]
    )
    assert payload["applied_patch"]["allowed_patch_fields"] == ["constraints"]
    assert payload["candidate"]["root_path"] == str(outdir.resolve())
    assert Path(payload["candidate"]["manifest_path"]).exists()
    assert payload["effect"] == {
        "local_second_candidate_generated": True,
        "source_program_files_mutated": False,
        "refinement_proposal_mutated": False,
        "decision_record_mutated": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
    }
    assert payload["non_authority"] == {
        "local_candidate_generation_only": True,
        "automatic_promotion": False,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "external_authority_export": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    candidate_manifest = json.loads((outdir / "manifest.json").read_text())
    assert candidate_manifest["schema_version"] == "program-candidate-assembly-v1"
    assert candidate_manifest["intent"]["constraints"] == [
        *source_manifest["intent"]["constraints"],
        *proposal["bounded_refinement"]["next_candidate_intent_patch"]["constraints"],
    ]
    lineage = candidate_manifest["intent"]["options"]["refinement_lineage"]
    assert lineage["schema_version"] == "program-refinement-candidate-lineage-v1"
    assert lineage["source_identity"] == payload["source_identity"]
    assert lineage["refinement_proposal_id"] == proposal["proposal_id"]
    assert lineage["decision_outcome"] == "request_more_evidence"
    assert lineage["authority"] == "local_refinement_lineage_only_non_authoritative"
    assert candidate_manifest["program_promotion_review"]["promotion_state"] == (
        "not_promoted"
    )
    assert (
        candidate_manifest["execution_episode"]["non_authority"]["external_mutation"]
        is False
    )
    assert (outdir / "eval_examples.py").exists()
    assert (outdir / "eval_behavior.py").exists()
    assert (outdir / "behavior_episode.json").exists()

    assert _file_hashes(program_root) == before_source_hashes
    assert (
        hashlib.sha256(proposal_path.read_bytes()).hexdigest() == before_proposal_hash
    )
    assert (
        hashlib.sha256(decision_path.read_bytes()).hexdigest() == before_decision_hash
    )


def test_program_refine_generate_candidate_rejects_reject_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, proposal_path, decision_path = _materialize_refinement_decision_path(
        tmp_path,
        monkeypatch,
    )
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["outcome"] = "reject"
    bad_decision_path = tmp_path / "promotion" / "reject_decision.json"
    _write_json(bad_decision_path, decision)

    result = runner.invoke(
        app,
        [
            "program-refine",
            "generate-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--refinement-proposal",
            str(proposal_path),
            "--decision-record",
            str(bad_decision_path),
            "--outdir",
            str(tmp_path / "program-rejected"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "request_more_evidence" in (result.stdout + result.stderr)
    assert not (tmp_path / "program-rejected").exists()


def test_program_refine_generate_candidate_rejects_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, proposal_path, decision_path = _materialize_refinement_decision_path(
        tmp_path,
        monkeypatch,
    )
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["identity"]["candidate_id"] = "prog-cand-other"
    bad_decision_path = tmp_path / "promotion" / "mismatch_decision.json"
    _write_json(bad_decision_path, decision)

    result = runner.invoke(
        app,
        [
            "program-refine",
            "generate-candidate",
            "--manifest",
            str(program_root / "manifest.json"),
            "--refinement-proposal",
            str(proposal_path),
            "--decision-record",
            str(bad_decision_path),
            "--outdir",
            str(tmp_path / "program-mismatch"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "candidate_id" in (result.stdout + result.stderr)
    assert not (tmp_path / "program-mismatch").exists()
