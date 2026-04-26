from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_jury_execution import build_program_jury_execution_result
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")


def _materialize_jury_program(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    examples: bool = True,
) -> Path:
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
        ]
        if examples
        else [],
        jury={
            "selection_model": "perspective_balanced_explicit_pool",
            "minimum_jurors": 3,
            "perspectives": ["correctness", "robustness", "clarity"],
            "jurors": [
                {
                    "id": "correctness_local",
                    "model": "stub",
                    "provider": "stub",
                    "perspective": "correctness",
                },
                {
                    "id": "robustness_local",
                    "model": "stub",
                    "provider": "stub",
                    "perspective": "robustness",
                },
                {
                    "id": "clarity_local",
                    "model": "stub",
                    "provider": "stub",
                    "perspective": "clarity",
                },
            ],
        },
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    return Path(artifact.root_path)


def test_program_promote_jury_cli_writes_local_sidecar_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_jury_program(tmp_path, monkeypatch, examples=True)
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    behavior = json.loads(
        (program_root / "behavior_results.json").read_text(encoding="utf-8")
    )
    before = _file_hashes(program_root)
    out_path = tmp_path / "promotion" / "jury_results.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "jury",
            "--manifest",
            str(program_root / "manifest.json"),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == "program-jury-results-v1"
    assert payload["status"] == "executed"
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
    assert payload["created_from"]["manifest_schema_version"] == (
        "program-candidate-assembly-v1"
    )
    assert payload["created_from"]["jury_path"] == str(
        (program_root / "jury.json").resolve()
    )
    assert payload["created_from"]["jury_selection_path"] == str(
        (program_root / "jury_selection.json").resolve()
    )
    assert payload["created_from"]["jury_rubric_path"] == str(
        (program_root / "jury_rubric.json").resolve()
    )
    assert payload["created_from"]["behavior_results_path"] == str(
        (program_root / "behavior_results.json").resolve()
    )

    assert payload["jury"] == {
        "planned_jury_schema_version": "program-jury-v1",
        "selection_schema_version": "program-jury-selection-v1",
        "rubric_schema_version": "program-jury-rubric-v1",
        "selected_juror_count": 3,
        "selected_perspectives": ["correctness", "robustness", "clarity"],
        "execution_mode": "local_deterministic",
        "provider_backed_model_calls": False,
    }
    assert payload["behavior_evidence"] == {
        "present": True,
        "schema_version": "program-behavior-results-v1",
        "behavior_status": behavior["summary"]["status"],
        "example_count": behavior["summary"]["total"],
        "status_counts": behavior["summary"]["status_counts"],
    }
    assert len(payload["juror_results"]) == 3
    assert {item["juror_id"] for item in payload["juror_results"]} == {
        "correctness_local",
        "robustness_local",
        "clarity_local",
    }
    assert {item["provider"] for item in payload["juror_results"]} == {"stub"}
    assert {item["model"] for item in payload["juror_results"]} == {"stub"}
    assert {item["execution_mode"] for item in payload["juror_results"]} == {
        "local_deterministic"
    }
    assert all(item["status"] == "judged" for item in payload["juror_results"])
    assert all(item["criteria_results"] for item in payload["juror_results"])
    assert all(
        item["evidence_refs"] == ["behavior_results.json"]
        for item in payload["juror_results"]
    )

    aggregate = payload["aggregate"]
    assert aggregate["status"] == "completed"
    assert set(aggregate["judgment_counts"]) >= {
        "supports_promotion",
        "withhold",
        "reject",
        "needs_more_evidence",
    }
    assert sum(aggregate["judgment_counts"].values()) == 3
    assert aggregate["agreement_level"] in {"high", "mixed"}
    assert isinstance(aggregate["disagreement_present"], bool)
    assert "disagreement_present" in aggregate

    limits_text = "\n".join(payload["interpretation"]["limits"])
    assert "eval_examples.py" in limits_text
    assert "behavior_results.json" in limits_text
    assert "not promotion approval" in limits_text
    assert "do not rank" in limits_text
    assert payload["interpretation"]["ready_for_promotion_decision"] is False
    assert payload["effect"] == {
        "local_jury_evidence_only": True,
        "program_files_mutated": False,
        "promotion_review_mutated": False,
        "new_candidate_generated": False,
        "oracle_index_mutated": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
    }
    assert payload["non_authority"] == {
        "local_jury_evidence_only": True,
        "automatic_promotion": False,
        "winner_selection": False,
        "candidate_ranking": False,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "promotion_authority": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    summary_and_rationales = "\n".join(
        [
            payload["aggregate"]["summary"],
            payload["interpretation"]["summary"],
            *(item["rationale"] for item in payload["juror_results"]),
        ]
    ).lower()
    for forbidden in (
        "approved",
        "should deploy",
        "production ready",
        "policy activated",
    ):
        assert forbidden not in summary_and_rationales

    assert _file_hashes(program_root) == before
    assert not (program_root / "jury_results.json").exists()
    assert not (program_root / "eval_behavior.py").exists()
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()


def test_program_jury_execution_degrades_without_behavior_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_jury_program(tmp_path, monkeypatch, examples=False)
    before = _file_hashes(program_root)

    payload = build_program_jury_execution_result(
        manifest_path=program_root / "manifest.json"
    )

    assert payload["schema_version"] == "program-jury-results-v1"
    assert payload["status"] == "insufficient_behavior_evidence"
    assert payload["created_from"]["behavior_results_path"] is None
    assert payload["behavior_evidence"] == {
        "present": False,
        "schema_version": None,
        "behavior_status": "insufficient_behavior_evidence",
        "example_count": 0,
        "status_counts": {},
    }
    assert len(payload["juror_results"]) == 3
    assert all(item["status"] == "unable_to_judge" for item in payload["juror_results"])
    assert all(
        item["judgment"] == "needs_more_evidence" for item in payload["juror_results"]
    )
    assert payload["aggregate"]["status"] == "insufficient_behavior_evidence"
    assert payload["aggregate"]["disagreement_present"] is False
    assert payload["interpretation"]["ready_for_promotion_decision"] is False
    assert payload["effect"]["program_files_mutated"] is False
    assert payload["non_authority"]["automatic_promotion"] is False

    assert _file_hashes(program_root) == before
    assert not (program_root / "behavior_results.json").exists()
    assert not (program_root / "eval_behavior.py").exists()
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()
