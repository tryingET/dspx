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


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


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
    behavior_episode = json.loads(
        (program_root / "behavior_episode.json").read_text(encoding="utf-8")
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
    assert payload["schema_version"] == "program-jury-results-v2"
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
    assert payload["created_from"]["behavior_episode_path"] == str(
        (program_root / "behavior_episode.json").resolve()
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
        "source_count": behavior_episode["summary"]["source_count"],
        "status_counts": behavior["summary"]["status_counts"],
        "behavior_results_present": True,
        "behavior_episode_present": True,
        "behavior_evidence_kind": "behavior_results",
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
        item["evidence_refs"] == ["behavior_results.json", "behavior_episode.json"]
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
    assert "behavior_results.json" in limits_text
    assert "behavior_episode.json" in limits_text
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
    assert (program_root / "eval_behavior.py").exists()
    assert (program_root / "behavior_episode.json").exists()
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()


def test_program_promote_jury_rejects_output_inside_generated_artifact_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_jury_program(tmp_path, monkeypatch, examples=True)
    before = _file_hashes(program_root)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "jury",
            "--manifest",
            str(program_root / "manifest.json"),
            "--out",
            str(program_root / "manifest.json"),
        ],
    )

    assert result.exit_code == 2
    assert "program jury results must not overwrite manifest.json" in result.output
    assert _file_hashes(program_root) == before


def test_program_promote_jury_uses_behavior_episode_for_dataset_only_evidence(
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
            name="TicketDatasetJuryProgram",
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
            jury={
                "selection_model": "perspective_balanced_explicit_pool",
                "minimum_jurors": 2,
                "perspectives": ["correctness", "robustness"],
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
                ],
            },
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    before = _file_hashes(program_root)
    behavior_episode = json.loads(
        (program_root / "behavior_episode.json").read_text(encoding="utf-8")
    )
    assert not (program_root / "behavior_results.json").exists()

    payload = build_program_jury_execution_result(
        manifest_path=program_root / "manifest.json"
    )

    assert payload["schema_version"] == "program-jury-results-v2"
    assert payload["status"] == "executed"
    assert payload["created_from"]["behavior_results_path"] is None
    assert payload["created_from"]["behavior_episode_path"] == str(
        (program_root / "behavior_episode.json").resolve()
    )
    assert payload["behavior_evidence"]["present"] is True
    assert payload["behavior_evidence"]["schema_version"] == (
        "program-behavior-episode-v1"
    )
    assert (
        payload["behavior_evidence"]["behavior_status"]
        == behavior_episode["summary"]["status"]
    )
    assert (
        payload["behavior_evidence"]["example_count"]
        == behavior_episode["summary"]["total"]
    )
    assert (
        payload["behavior_evidence"]["source_count"]
        == behavior_episode["summary"]["source_count"]
    )
    assert payload["behavior_evidence"]["behavior_results_present"] is False
    assert payload["behavior_evidence"]["behavior_episode_present"] is True
    assert payload["behavior_evidence"]["behavior_evidence_kind"] == (
        "behavior_episode"
    )
    assert all(
        item["status"] == "judged"
        and item["evidence_refs"] == ["behavior_episode.json"]
        for item in payload["juror_results"]
    )
    limits = "\n".join(payload["interpretation"]["limits"])
    assert "No example, dataset split" in limits
    assert payload["non_authority"]["promotion_authority"] is False
    assert payload["effect"]["program_files_mutated"] is False
    assert _file_hashes(program_root) == before
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

    assert payload["schema_version"] == "program-jury-results-v2"
    assert payload["status"] == "insufficient_behavior_evidence"
    assert payload["created_from"]["behavior_results_path"] is None
    assert payload["created_from"]["behavior_episode_path"] is None
    assert payload["behavior_evidence"] == {
        "present": False,
        "schema_version": None,
        "behavior_status": "insufficient_behavior_evidence",
        "example_count": 0,
        "source_count": 0,
        "status_counts": {},
        "behavior_results_present": False,
        "behavior_episode_present": False,
        "behavior_evidence_kind": None,
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
