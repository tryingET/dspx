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
from dspx.services.program_refinement import (
    ProgramRefinementError,
    build_program_refinement_proposal,
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


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _materialize_program_with_report(
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
        program_root, index_path=index_path
    )
    assert index_result["indexed"] == 1
    assert index_result["errors"] == 0

    report = build_program_oracle_evidence_report(index_path=index_path)
    report_path = tmp_path / "oracle" / "program-evidence-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return program_root, report_path


def test_program_refinement_cli_proposes_from_manifest_behavior_and_oracle_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path = _materialize_program_with_report(tmp_path, monkeypatch)
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    behavior = json.loads(
        (program_root / "behavior_results.json").read_text(encoding="utf-8")
    )
    before = _file_hashes(program_root)
    before_names = sorted(before)
    out_path = tmp_path / "refinement" / "refinement_proposal.json"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "propose",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == "program-refinement-proposal-v1"
    assert payload["status"] in {"proposed", "no_refinement_needed"}
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
    assert payload["created_from"]["oracle_report_path"] == str(report_path.resolve())
    assert payload["created_from"]["behavior_results_path"] == str(
        (program_root / "behavior_results.json").resolve()
    )

    evidence_summary = payload["evidence_summary"]
    assert evidence_summary["behavior_status"] == behavior["summary"]["status"]
    assert evidence_summary["example_count"] == behavior["summary"]["total"]
    assert evidence_summary["status_counts"] == behavior["summary"]["status_counts"]
    assert evidence_summary["oracle_report_status"] == "ok"
    assert evidence_summary["oracle_report_total_records"] == 1
    assert evidence_summary["oracle_report_record_matched"] is True

    if behavior["summary"]["status"] == "failed":
        assert payload["status"] == "proposed"
        assert "mismatch:urgency" in evidence_summary["failure_signals"]
        bounded = payload["bounded_refinement"]
        assert bounded["refinement_kind"] == "proposal_only"
        assert bounded["target_surfaces"]
        assert bounded["proposed_changes"]
        assert bounded["proposed_changes"][0]["change_type"] == "tighten_output_mapping"
        assert (
            "Preserve declared inputs and outputs."
            in bounded["next_candidate_intent_patch"]["constraints"]
        )

    limitations_text = "\n".join(payload["limitations"])
    assert "eval_examples.py" in limitations_text
    assert "No dataset split" in limitations_text
    assert payload["non_authority"] == {
        "proposal_only": True,
        "applies_changes": False,
        "generates_candidate": False,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "promotion_authority": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    after = _file_hashes(program_root)
    assert after == before
    assert sorted(after) == before_names
    assert not (program_root / "refinement_proposal.json").exists()
    assert len(list(tmp_path.glob("program*"))) == 1


def test_program_refinement_proposes_from_dataset_split_evidence_without_inline_examples(
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
            for index in range(6)
        ],
    )
    intent = ProgramIntent(
        name="TicketDatasetProgram",
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
            },
        },
    )
    artifact = materialize_program_from_intent(
        intent, outdir=tmp_path / "dataset-program"
    )
    program_root = Path(artifact.root_path)
    assert not (program_root / "behavior_results.json").exists()
    assert (program_root / "behavior_results.train.json").exists()
    assert (program_root / "oracle_evidence.json").exists()
    index_path = tmp_path / "oracle" / "coordinates.db"
    index_result = index_program_oracle_evidence_path(
        program_root, index_path=index_path
    )
    assert index_result["indexed"] == 1
    report = build_program_oracle_evidence_report(index_path=index_path)
    report_path = tmp_path / "oracle" / "program-evidence-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    before = _file_hashes(program_root)

    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )

    assert proposal["schema_version"] == "program-refinement-proposal-v1"
    assert proposal["status"] in {"proposed", "no_refinement_needed"}
    assert proposal["created_from"]["behavior_results_path"] is None
    evidence_summary = proposal["evidence_summary"]
    assert evidence_summary["example_count"] == 0
    assert evidence_summary["behavior_source_kinds"] == ["dataset_split"]
    assert evidence_summary["evidence_source_count"] == 3
    assert evidence_summary["total_evaluation_count"] == 6
    assert evidence_summary["oracle_report_record_matched"] is True
    assert evidence_summary["oracle_report_evidence_source_count"] == 3
    assert evidence_summary["oracle_report_total_evaluation_count"] == 6
    assert "Dataset split evidence" in "\n".join(proposal["limitations"])
    assert proposal["non_authority"]["generates_candidate"] is False
    assert _file_hashes(program_root) == before
    assert not (program_root / "refinement_proposal.json").exists()


def test_program_refinement_rejects_authority_widened_oracle_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path = _materialize_program_with_report(tmp_path, monkeypatch)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["non_authority"]["oracle_ranking"] = True
    bad_report_path = tmp_path / "oracle" / "bad-report.json"
    bad_report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-refine",
            "propose",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(bad_report_path),
            "--out",
            str(tmp_path / "refinement" / "proposal.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "oracle_ranking" in (result.stdout + result.stderr)
    assert not (tmp_path / "refinement" / "proposal.json").exists()


def test_program_refinement_rejects_oracle_report_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path = _materialize_program_with_report(tmp_path, monkeypatch)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    record = report["records"][0]
    record["identity"]["receipt_bundle_id"] = "prog-rb-other"
    record["identity"]["episode_id"] = "prog-ep-other"
    record["identity"]["assembly_id"] = "prog-asm-other"
    record["identity"]["candidate_id"] = "prog-cand-other"
    bad_report_path = tmp_path / "oracle" / "mismatch-report.json"
    bad_report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    with pytest.raises(ProgramRefinementError, match="matching manifest identity"):
        build_program_refinement_proposal(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=bad_report_path,
        )


def test_program_refinement_degrades_without_behavior_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="NoExamplesProgram",
        objective="Answer a short question.",
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
    assert report["status"] == "no_program_oracle_evidence"
    report_path = tmp_path / "oracle-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    before = _file_hashes(program_root)

    result = runner.invoke(
        app,
        [
            "program-refine",
            "propose",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--out",
            str(tmp_path / "refinement" / "refinement_proposal.json"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "program-refinement-proposal-v1"
    assert payload["status"] == "insufficient_behavior_evidence"
    assert payload["created_from"]["behavior_results_path"] is None
    assert payload["evidence_summary"]["example_count"] == 0
    assert payload["evidence_summary"]["failure_signals"] == []
    assert payload["evidence_summary"]["oracle_report_status"] == (
        "no_program_oracle_evidence"
    )
    assert payload["evidence_summary"]["oracle_report_record_matched"] is False
    assert payload["bounded_refinement"]["target_surfaces"] == []
    assert payload["bounded_refinement"]["proposed_changes"] == []
    assert (
        "Add declared examples"
        in payload["bounded_refinement"]["next_candidate_intent_patch"][
            "bounded_next_questions"
        ][0]
    )
    assert _file_hashes(program_root) == before
    assert not (tmp_path / "oracle" / "coordinates.db").exists()
