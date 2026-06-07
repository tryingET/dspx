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
from dspx.services.program_refinement import build_program_refinement_proposal
from dspx.services.program_promotion_refinement import (
    ProgramPromotionRefinementError,
    _identity_matches,
    _load_program_behavior_episode,
    build_program_promotion_refinement,
    write_program_promotion_refinement,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _materialize_program_report_and_proposal(
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

    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)
    return program_root, report_path, proposal_path


def test_program_promotion_refinement_rejects_absolute_behavior_episode_path(
    tmp_path: Path,
) -> None:
    episode = tmp_path / "forged_behavior_episode.json"
    _write_json(
        episode,
        {"schema_version": "program-behavior-episode-v1", "summary": {}},
    )
    manifest = {
        "schema_version": "program-candidate-assembly-v1",
        "behavior_episode_artifact": {"path": str(episode)},
    }
    manifest_path = tmp_path / "candidate" / "manifest.json"
    manifest_path.parent.mkdir()
    _write_json(manifest_path, manifest)

    with pytest.raises(ProgramPromotionRefinementError, match="candidate-relative"):
        _load_program_behavior_episode(manifest, manifest_path)


def test_program_promotion_refinement_rejects_hashless_behavior_episode(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    episode = candidate / "behavior_episode.json"
    _write_json(
        episode,
        {"schema_version": "program-behavior-episode-v1", "summary": {}},
    )
    manifest = {
        "schema_version": "program-candidate-assembly-v1",
        "behavior_episode_artifact": {"path": "behavior_episode.json"},
    }
    manifest_path = candidate / "manifest.json"
    _write_json(manifest_path, manifest)

    with pytest.raises(ProgramPromotionRefinementError, match="content hash"):
        _load_program_behavior_episode(manifest, manifest_path)


def test_program_promotion_refinement_rejects_partial_oracle_identity_match() -> None:
    assert (
        _identity_matches(
            {"candidate_id": "cand-1"},
            {
                "request_id": "req-1",
                "candidate_id": "cand-1",
                "assembly_id": "asm-1",
                "episode_id": "ep-1",
                "receipt_bundle_id": "rb-1",
            },
        )
        is False
    )


def test_program_promotion_refinement_cli_builds_local_review_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    behavior = json.loads(
        (program_root / "behavior_results.json").read_text(encoding="utf-8")
    )
    behavior_episode = json.loads(
        (program_root / "behavior_episode.json").read_text(encoding="utf-8")
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    before = _file_hashes(program_root)
    before_names = sorted(before)
    out_path = tmp_path / "promotion" / "promotion_review_refined.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == "program-promotion-review-refined-v1"
    assert payload["status"] == "review_packet_ready"
    assert payload["promotion_state"] == "not_promoted"
    assert payload["candidate_status"] == "exploratory"
    assert payload["identity"] == {
        "request_id": manifest["request"]["request_id"],
        "candidate_id": manifest["candidate_assembly"]["candidate_id"],
        "assembly_id": manifest["candidate_assembly"]["assembly_id"],
        "episode_id": manifest["execution_episode"]["episode_id"],
        "receipt_bundle_id": manifest["receipt_bundle"]["receipt_bundle_id"],
    }
    assert payload["created_from"]["manifest_path"] == str(
        (program_root / "manifest.json").resolve()
    )
    assert payload["created_from"]["behavior_results_path"] == str(
        (program_root / "behavior_results.json").resolve()
    )
    assert payload["created_from"]["behavior_episode_path"] == str(
        (program_root / "behavior_episode.json").resolve()
    )
    assert payload["created_from"]["oracle_report_path"] == str(report_path.resolve())
    assert payload["created_from"]["refinement_proposal_path"] == str(
        proposal_path.resolve()
    )
    assert payload["created_from"]["original_promotion_review_path"] == str(
        (program_root / "promotion_review.json").resolve()
    )
    assert payload["created_from"][
        "original_promotion_adjudication_request_path"
    ] == str((program_root / "promotion_adjudication_request.json").resolve())
    assert payload["created_from"]["original_promotion_decision_template_path"] == str(
        (program_root / "promotion_decision_template.json").resolve()
    )

    assert payload["evidence_summary"]["behavior"] == {
        "present": True,
        "status": behavior["summary"]["status"],
        "example_count": behavior["summary"]["total"],
        "source_count": behavior_episode["summary"]["source_count"],
        "status_counts": behavior["summary"]["status_counts"],
        "behavior_results_present": True,
        "behavior_episode_present": True,
        "behavior_evidence_kind": "behavior_results",
    }
    assert payload["evidence_summary"]["oracle_report"] == {
        "present": True,
        "status": "ok",
        "total_records": 1,
        "record_matched": True,
    }
    assert payload["evidence_summary"]["refinement_proposal"] == {
        "present": True,
        "status": proposal["status"],
        "proposal_id": proposal["proposal_id"],
    }
    readiness = payload["review_readiness"]
    assert readiness["behavior_evidence_present"] is True
    assert readiness["oracle_report_present"] is True
    assert readiness["refinement_proposal_present"] is True
    assert readiness["model_jury_execution_present"] is False
    assert readiness["adjudicator_decision_present"] is False
    assert readiness["ready_for_adjudicator_review"] is False
    assert readiness["missing_required_evidence"] == [
        "no_model_jury_execution_episode",
        "no_promotion_adjudicator_decision",
    ]
    assert payload["promotion_review_delta"] == {
        "behavioral_evaluation_episode": "satisfied_by_current_behavior_episode",
        "oracle_interpretation": "satisfied_by_explicit_oracle_report",
        "bounded_refinement_proposal": "available_non_authoritative",
        "promotion_authority": "unchanged_required_adjudicator",
    }
    adjudication = payload["adjudication_packet"]
    assert adjudication["status"] == "not_ready_missing_required_evidence"
    assert adjudication["original_allowed_outcomes"] == [
        "promote",
        "withhold",
        "reject",
        "request_more_evidence",
    ]
    assert adjudication["local_packet_recommended_review_outcomes"] == [
        "withhold",
        "reject",
        "request_more_evidence",
    ]
    assert adjudication["forbidden_outcomes_without_explicit_adjudicator"] == [
        "promote"
    ]
    assert "behavior_results.json" in adjudication["evidence_refs"]
    assert payload["non_authority"] == {
        "local_review_packet_only": True,
        "automatic_promotion": False,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "program_mutation": False,
        "new_candidate_generation": False,
        "promotion_authority": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    assert _file_hashes(program_root) == before
    assert sorted(_file_hashes(program_root)) == before_names
    assert not (program_root / "promotion_review_refined.json").exists()
    assert (program_root / "eval_behavior.py").exists()
    assert (program_root / "behavior_episode.json").exists()


def test_program_promotion_refinement_rejects_authority_widened_oracle_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["non_authority"]["oracle_promotion"] = True
    bad_report_path = tmp_path / "oracle" / "bad-report.json"
    _write_json(bad_report_path, report)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(bad_report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--out",
            str(tmp_path / "promotion" / "review.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "oracle_promotion" in (result.stdout + result.stderr)
    assert not (tmp_path / "promotion" / "review.json").exists()


def test_program_promotion_refinement_rejects_authority_widened_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["non_authority"]["promotion_authority"] = True
    bad_proposal_path = tmp_path / "refinement" / "bad-proposal.json"
    _write_json(bad_proposal_path, proposal)

    with pytest.raises(ProgramPromotionRefinementError, match="promotion_authority"):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            refinement_proposal_path=bad_proposal_path,
        )


def test_program_promotion_refinement_rejects_oracle_report_partial_identity_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    record = report["records"][0]
    record["identity"]["request_id"] = manifest["request"]["request_id"]
    record["identity"]["candidate_id"] = "prog-cand-other"
    bad_report_path = tmp_path / "oracle" / "partial-collision-report.json"
    _write_json(bad_report_path, report)

    with pytest.raises(
        ProgramPromotionRefinementError, match="matching manifest identity"
    ):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=bad_report_path,
            refinement_proposal_path=proposal_path,
        )


def test_program_promotion_refinement_rejects_oracle_report_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    record = report["records"][0]
    record["identity"]["receipt_bundle_id"] = "prog-rb-other"
    record["identity"]["episode_id"] = "prog-ep-other"
    record["identity"]["assembly_id"] = "prog-asm-other"
    record["identity"]["candidate_id"] = "prog-cand-other"
    record["identity"]["request_id"] = "prog-req-other"
    bad_report_path = tmp_path / "oracle" / "mismatch-report.json"
    _write_json(bad_report_path, report)

    with pytest.raises(
        ProgramPromotionRefinementError, match="matching manifest identity"
    ):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=bad_report_path,
            refinement_proposal_path=proposal_path,
        )


def test_program_promotion_refinement_rejects_proposal_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["identity"]["candidate_id"] = "prog-cand-other"
    bad_proposal_path = tmp_path / "refinement" / "mismatch-proposal.json"
    _write_json(bad_proposal_path, proposal)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(bad_proposal_path),
            "--out",
            str(tmp_path / "promotion" / "review.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "candidate_id" in (result.stdout + result.stderr)
    assert not (tmp_path / "promotion" / "review.json").exists()


def test_program_promotion_refinement_rejects_output_inside_program_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    packet = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )

    with pytest.raises(ProgramPromotionRefinementError, match="generated program root"):
        write_program_promotion_refinement(
            packet,
            program_root / "promotion_review_refined.json",
        )


def test_program_promotion_refinement_uses_behavior_episode_for_dataset_only_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    dataset_path = tmp_path / "data" / "tickets.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "inputs": {"ticket_text": f"ticket {index}"},
                "outputs": {"urgency": "high" if index % 2 else "low"},
            }
            for index in range(8)
        ],
    )
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="DatasetReviewProgram",
            objective="Classify support ticket urgency.",
            inputs=["ticket_text"],
            outputs=["urgency"],
            metric="exact_match",
            dataset={
                "path": str(dataset_path),
                "input_fields": ["ticket_text"],
                "output_fields": ["urgency"],
                "split": {
                    "strategy": "ratio",
                    "train": 0.5,
                    "validation": 0.25,
                    "test": 0.25,
                    "seed": 7,
                },
            },
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    assert not (program_root / "behavior_results.json").exists()
    behavior_episode = json.loads(
        (program_root / "behavior_episode.json").read_text(encoding="utf-8")
    )
    index_path = tmp_path / "oracle" / "coordinates.db"
    index_result = index_program_oracle_evidence_path(
        program_root,
        index_path=index_path,
    )
    assert index_result["indexed"] == 1
    report = build_program_oracle_evidence_report(index_path=index_path)
    report_path = tmp_path / "oracle" / "program-evidence-report.json"
    _write_json(report_path, report)
    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)
    before = _file_hashes(program_root)

    payload = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )

    assert payload["schema_version"] == "program-promotion-review-refined-v1"
    assert payload["status"] == "review_packet_ready"
    assert payload["created_from"]["behavior_results_path"] is None
    assert payload["created_from"]["behavior_episode_path"] == str(
        (program_root / "behavior_episode.json").resolve()
    )
    expected_status_counts = behavior_episode["summary"]["status_counts"]
    assert payload["evidence_summary"]["behavior"] == {
        "present": True,
        "status": behavior_episode["summary"]["status"],
        "example_count": behavior_episode["summary"]["total"],
        "source_count": behavior_episode["summary"]["source_count"],
        "status_counts": expected_status_counts,
        "behavior_results_present": False,
        "behavior_episode_present": True,
        "behavior_evidence_kind": "behavior_episode",
    }
    assert payload["review_readiness"]["behavior_evidence_present"] is True
    assert payload["review_readiness"]["missing_required_evidence"] == [
        "no_model_jury_execution_episode",
        "no_promotion_adjudicator_decision",
    ]
    assert (
        "behavior_results.json" not in payload["adjudication_packet"]["evidence_refs"]
    )
    assert "behavior_episode.json" in payload["adjudication_packet"]["evidence_refs"]
    assert payload["non_authority"]["promotion_authority"] is False
    assert _file_hashes(program_root) == before


def test_program_promotion_refinement_degrades_without_behavior_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="NoExamplesProgram",
        objective="Answer a question.",
        inputs=["question"],
        outputs=["answer"],
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    program_root = Path(artifact.root_path)
    assert not (program_root / "behavior_results.json").exists()
    assert not (program_root / "oracle_evidence.json").exists()
    report = build_program_oracle_evidence_report(
        index_path=tmp_path / "oracle" / "coordinates.db"
    )
    report_path = tmp_path / "oracle-report.json"
    _write_json(report_path, report)
    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)
    before = _file_hashes(program_root)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--out",
            str(tmp_path / "promotion" / "promotion_review_refined.json"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "program-promotion-review-refined-v1"
    assert payload["status"] == "insufficient_behavior_evidence"
    assert payload["promotion_state"] == "not_promoted"
    assert payload["created_from"]["behavior_results_path"] is None
    assert payload["created_from"]["behavior_episode_path"] is None
    assert payload["evidence_summary"]["behavior"] == {
        "present": False,
        "status": "insufficient_behavior_evidence",
        "example_count": 0,
        "source_count": 0,
        "status_counts": {},
        "behavior_results_present": False,
        "behavior_episode_present": False,
        "behavior_evidence_kind": None,
    }
    assert payload["evidence_summary"]["oracle_report"] == {
        "present": True,
        "status": "no_program_oracle_evidence",
        "total_records": 0,
        "record_matched": False,
    }
    assert payload["evidence_summary"]["refinement_proposal"]["status"] == (
        "insufficient_behavior_evidence"
    )
    assert payload["review_readiness"]["missing_required_evidence"] == [
        "no_behavioral_evaluation_episode",
        "no_model_jury_execution_episode",
        "no_promotion_adjudicator_decision",
    ]
    assert (
        "behavior_results.json" not in payload["adjudication_packet"]["evidence_refs"]
    )
    assert payload["non_authority"]["automatic_promotion"] is False
    assert _file_hashes(program_root) == before
    assert not (tmp_path / "oracle" / "coordinates.db").exists()
