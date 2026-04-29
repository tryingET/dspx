from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from dspx.services import program_service
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _ticket_rows(count: int = 10) -> list[dict[str, object]]:
    return [
        {
            "inputs": {
                "ticket_text": f"ticket {index} server down"
                if index % 2
                else f"ticket {index} password reset"
            },
            "outputs": {"urgency": "high" if index % 2 else "low"},
        }
        for index in range(count)
    ]


def _ratio_intent(dataset_path: Path, *, seed: int = 42) -> ProgramIntent:
    return ProgramIntent(
        name="TicketDatasetProgram",
        objective="Classify support ticket urgency.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        metric="exact_match",
        constraints=["use only the supplied ticket text"],
        dataset={
            "path": str(dataset_path),
            "input_fields": ["ticket_text"],
            "output_fields": ["urgency"],
            "split": {
                "strategy": "ratio",
                "train": 0.7,
                "validation": 0.15,
                "test": 0.15,
                "seed": seed,
            },
        },
    )


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_program_gen_materializes_ratio_dataset_splits_and_replay_checks_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    dataset_path = tmp_path / "data" / "tickets.jsonl"
    _write_jsonl(dataset_path, _ticket_rows())
    real_run = program_service.subprocess.run
    subprocess_calls: list[list[str]] = []

    def spy_run(
        command: list[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        command_text = [str(part) for part in command]
        command_names = [Path(part).name for part in command_text]
        assert "ak" not in command_names
        assert "oracle" not in command_names
        assert "program-refine" not in command_names
        assert "program-promote" not in command_names
        assert "eval_behavior.py" not in command_names
        subprocess_calls.append(command_text)
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(program_service.subprocess, "run", spy_run)

    artifact = materialize_program_from_intent(
        _ratio_intent(dataset_path),
        outdir=tmp_path / "program",
    )
    root = Path(artifact.root_path)

    assert (root / "dataset_manifest.json").exists()
    for split in ("train", "validation", "test"):
        assert (root / "splits" / f"{split}.jsonl").exists()
        assert (root / f"eval_{split}.py").exists()
        assert "create_from_env(default='dspy-lm-auth')" in (
            root / f"eval_{split}.py"
        ).read_text(encoding="utf-8")
        assert (root / f"behavior_results.{split}.json").exists()
    assert not (root / "eval_behavior.py").exists()
    assert not (root / "refinement_proposal.json").exists()
    assert not (root / "candidate_comparison.json").exists()
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()
    assert subprocess_calls

    dataset = json.loads((root / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert dataset["schema_version"] == "program-dataset-manifest-v1"
    assert dataset["status"] == "materialized"
    assert dataset["source"]["kind"] == "dataset_path"
    assert dataset["source"]["content_hash"] == _hash(dataset_path)
    assert dataset["source"]["record_count"] == 10
    assert dataset["split"]["strategy"] == "ratio"
    assert dataset["split"]["seed"] == 42
    assert dataset["split"]["counts"] == {"train": 7, "validation": 1, "test": 2}
    assert dataset["fields"] == {"inputs": ["ticket_text"], "outputs": ["urgency"]}
    assert dataset["authority"] == "dataset_split_evidence_only_non_authoritative"
    assert dataset["non_authority"] == {
        "optimization_authority": False,
        "promotion_authority": False,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    for split, count in dataset["split"]["counts"].items():
        artifact_payload = dataset["artifacts"][split]
        assert artifact_payload["path"] == f"splits/{split}.jsonl"
        assert artifact_payload["record_count"] == count
        assert artifact_payload["content_hash"] == _hash(
            root / "splits" / f"{split}.jsonl"
        )
        assert artifact_payload["eval_harness"] == f"eval_{split}.py"
        assert artifact_payload["eval_harness_hash"] == _hash(root / f"eval_{split}.py")
        assert artifact_payload["behavior_results"] == f"behavior_results.{split}.json"
        assert artifact_payload["behavior_results_hash"] == _hash(
            root / f"behavior_results.{split}.json"
        )
        behavior = json.loads(
            (root / f"behavior_results.{split}.json").read_text(encoding="utf-8")
        )
        assert behavior["schema_version"] == "program-behavior-results-v1"
        assert behavior["dataset_split"] == split
        assert behavior["dataset_manifest_path"] == "dataset_manifest.json"
        assert behavior["summary"]["total"] == count
        assert behavior["authority"] == "behavior_evidence_only_non_authoritative"
        assert len(behavior["examples"]) == count
        if count:
            record = behavior["examples"][0]
            assert "inputs" in record
            assert "expected_outputs" in record
            assert "observed_outputs" in record
            assert record["status"] in {
                "passed",
                "failed",
                "error",
                "degraded_no_comparable_output",
                "executed",
            }

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((root / "manifest.json.meta.json").read_text(encoding="utf-8"))
    dataset_manifest_hash = _hash(root / "dataset_manifest.json")
    assert manifest["request"]["dataset_manifest_hash"] == dataset_manifest_hash
    assert manifest["dataset_manifest"] == dataset
    assert manifest["dataset_manifest_artifact"] == {
        "path": "dataset_manifest.json",
        "content_hash": dataset_manifest_hash,
        "schema_version": "program-dataset-manifest-v1",
    }
    assert "dataset_manifest" in manifest["candidate_assembly"]["surface_kinds"]
    assert (
        "dataset_split_behavior_results"
        in manifest["candidate_assembly"]["surface_kinds"]
    )
    assert "module_surfaces" in manifest["candidate_assembly"]["surface_kinds"]
    assert (root / "module_surfaces.json").exists()
    surface_kinds = {
        surface["kind"] for surface in manifest["candidate_assembly"]["surfaces"]
    }
    assert "dataset_split_validation" in surface_kinds
    assert "dataset_split_harness_validation" in surface_kinds
    assert "dataset_split_behavior_results_validation" in surface_kinds
    assert (
        manifest["execution_episode"]["checks"]["dataset_binding"]["status"] == "passed"
    )
    assert manifest["execution_episode"]["dataset_evaluation"]["status"] == "captured"
    assert manifest["program_promotion_review"]["promotion_state"] == "not_promoted"
    assert receipt["run_summary"]["dataset_manifest_hash"] == dataset_manifest_hash
    assert receipt["program_dataset_manifest"] == dataset
    assert (
        receipt["program_dataset_split_evidence"] == manifest["dataset_split_evidence"]
    )

    replay = check_run_receipt(root / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert replay["checks"]["program_module_surfaces_hash_match"] is True
    assert replay["checks"]["program_dataset_manifest_hash_match"] is True
    assert replay["checks"]["program_dataset_split_validation_hash_match"] is True
    assert (
        replay["checks"]["program_dataset_split_behavior_results_validation_hash_match"]
        is True
    )

    validation_behavior_path = root / "behavior_results.validation.json"
    behavior_payload = json.loads(validation_behavior_path.read_text(encoding="utf-8"))
    behavior_payload["summary"]["status"] = "drifted"
    validation_behavior_path.write_text(
        json.dumps(behavior_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    drift = check_run_receipt(root / "manifest.json.meta.json")
    assert drift["status"] == "failed"
    assert drift["checks"]["output_hash_match"] is True
    assert (
        drift["checks"]["program_dataset_split_behavior_results_validation_hash_match"]
        is False
    )
    assert "program_evidence_hash_mismatch" in drift["error_codes"]


def test_program_dataset_ratio_split_is_deterministic_by_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    dataset_path = tmp_path / "data" / "tickets.jsonl"
    _write_jsonl(dataset_path, _ticket_rows(20))

    first = materialize_program_from_intent(
        _ratio_intent(dataset_path, seed=42), outdir=tmp_path / "program-a"
    )
    second = materialize_program_from_intent(
        _ratio_intent(dataset_path, seed=42), outdir=tmp_path / "program-b"
    )
    third = materialize_program_from_intent(
        _ratio_intent(dataset_path, seed=99), outdir=tmp_path / "program-c"
    )

    first_root = Path(first.root_path)
    second_root = Path(second.root_path)
    third_root = Path(third.root_path)
    first_hashes = {
        split: _hash(first_root / "splits" / f"{split}.jsonl")
        for split in ("train", "validation", "test")
    }
    second_hashes = {
        split: _hash(second_root / "splits" / f"{split}.jsonl")
        for split in ("train", "validation", "test")
    }
    third_hashes = {
        split: _hash(third_root / "splits" / f"{split}.jsonl")
        for split in ("train", "validation", "test")
    }
    assert first_hashes == second_hashes
    assert any(first_hashes[split] != third_hashes[split] for split in first_hashes)


def test_program_dataset_supports_empty_splits_truthfully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    dataset_path = tmp_path / "data" / "tiny.jsonl"
    _write_jsonl(dataset_path, _ticket_rows(1))

    artifact = materialize_program_from_intent(
        _ratio_intent(dataset_path, seed=42), outdir=tmp_path / "program"
    )
    root = Path(artifact.root_path)
    dataset = json.loads((root / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert dataset["split"]["counts"] == {"train": 0, "validation": 0, "test": 1}
    for split in ("train", "validation"):
        behavior = json.loads(
            (root / f"behavior_results.{split}.json").read_text(encoding="utf-8")
        )
        assert behavior["summary"]["total"] == 0
        assert behavior["summary"]["status"] == "no_examples"
        assert behavior["examples"] == []


def test_program_dataset_explicit_split_files_are_loaded_without_ratio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    train_path = tmp_path / "data" / "train.jsonl"
    validation_path = tmp_path / "data" / "validation.jsonl"
    test_path = tmp_path / "data" / "test.jsonl"
    _write_jsonl(train_path, _ticket_rows(2))
    _write_jsonl(validation_path, _ticket_rows(1))
    _write_jsonl(test_path, _ticket_rows(3))
    intent = ProgramIntent(
        name="ExplicitDatasetProgram",
        objective="Classify support ticket urgency.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        datasets={
            "train": str(train_path),
            "validation": str(validation_path),
            "test": str(test_path),
        },
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    dataset = json.loads((root / "dataset_manifest.json").read_text(encoding="utf-8"))

    assert dataset["source"]["kind"] == "explicit_splits"
    assert dataset["split"]["strategy"] == "explicit_splits"
    assert "ratios" not in dataset["split"]
    assert dataset["split"]["counts"] == {"train": 2, "validation": 1, "test": 3}
    assert dataset["source"]["splits"]["train"]["content_hash"] == _hash(train_path)
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"


@pytest.mark.parametrize(
    ("rows", "dataset_patch", "message"),
    [
        ([{"outputs": {"urgency": "high"}}], {}, "missing object inputs"),
        ([{"inputs": {"ticket_text": "x"}}], {}, "missing object outputs"),
        (
            [
                {
                    "inputs": {"ticket_text": "x", "extra": "y"},
                    "outputs": {"urgency": "high"},
                }
            ],
            {},
            "unknown input fields",
        ),
        (
            [
                {
                    "inputs": {"ticket_text": "x"},
                    "outputs": {"urgency": "high", "other": "z"},
                }
            ],
            {},
            "unknown output fields",
        ),
        (
            _ticket_rows(2),
            {
                "split": {
                    "strategy": "ratio",
                    "train": 0.6,
                    "validation": 0.3,
                    "test": 0.3,
                }
            },
            "sum to 1.0",
        ),
    ],
)
def test_program_dataset_invalid_inputs_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, object]],
    dataset_patch: dict[str, object],
    message: str,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    dataset_path = tmp_path / "data" / "bad.jsonl"
    _write_jsonl(dataset_path, rows)
    dataset = {
        "path": str(dataset_path),
        "input_fields": ["ticket_text"],
        "output_fields": ["urgency"],
        "split": {
            "strategy": "ratio",
            "train": 0.7,
            "validation": 0.15,
            "test": 0.15,
            "seed": 42,
        },
    }
    dataset.update(dataset_patch)
    intent = ProgramIntent(
        name="InvalidDatasetProgram",
        objective="Reject invalid dataset inputs.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        dataset=dataset,
    )

    with pytest.raises(ValueError, match=message):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")
    assert not (tmp_path / "program" / "dataset_manifest.json").exists()
