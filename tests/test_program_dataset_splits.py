# summary: "Tests program dataset split materialization, behavior evidence, quality aggregation, and replay integrity."
# read_when:
#   - "Changing dataset ingestion, split strategies, evaluation artifacts, or dataset replay checks."

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

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


def _ratio_intent(
    dataset_path: Path, *, seed: int = 42, declared_quality: bool = False
) -> ProgramIntent:
    return ProgramIntent(
        name="TicketDatasetProgram",
        objective="Classify support ticket urgency.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        metric="exact_match",
        constraints=["use only the supplied ticket text"],
        quality_criteria=[
            {
                "id": "urgency_quality",
                "output_field": "urgency",
                "evaluator": "concept_coverage",
                "required_concept_groups": [["high", "low"]],
                "forbidden_concepts": ["unknown"],
                "min_score": 1.0,
            }
        ]
        if declared_quality
        else [],
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
        subprocess_calls.append(command_text)
        return cast(Any, real_run)(command, *args, **kwargs)

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
        assert "create_from_env()" in (
            root / f"eval_{split}.py"
        ).read_text(encoding="utf-8")
        assert (root / f"behavior_results.{split}.json").exists()
    assert (root / "eval_behavior.py").exists()
    assert (root / "behavior_episode.json").exists()
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
    assert "behavior_harness" in manifest["candidate_assembly"]["surface_kinds"]
    assert "behavior_episode" in manifest["candidate_assembly"]["surface_kinds"]
    assert "oracle_evidence" in manifest["candidate_assembly"]["surface_kinds"]
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
    behavior_episode = json.loads(
        (root / "behavior_episode.json").read_text(encoding="utf-8")
    )
    behavior_episode_hash = _hash(root / "behavior_episode.json")
    assert behavior_episode["schema_version"] == "program-behavior-episode-v1"
    assert behavior_episode["summary"]["source_count"] == 3
    assert [source["split"] for source in behavior_episode["sources"]] == [
        "train",
        "validation",
        "test",
    ]
    assert all(
        source["quality_evaluation"]
        == {
            "status": "not_declared",
            "criteria_declared": False,
            "evaluations_total": 0,
            "evaluations_passed": 0,
            "evaluations_failed": 0,
            "quality_approved": False,
        }
        for source in behavior_episode["sources"]
    )
    assert behavior_episode["quality_evaluation"] == {
        "status": "not_declared",
        "criteria_declared": False,
        "evaluations_total": 0,
        "evaluations_passed": 0,
        "evaluations_failed": 0,
        "quality_approved": False,
    }
    assert manifest["request"]["behavior_episode_hash"] == behavior_episode_hash
    assert manifest["execution_episode"]["behavior_orchestration"]["status"] == (
        "passed"
    )
    assert manifest["execution_episode"]["behavior_orchestration"]["result_hash"] == (
        behavior_episode_hash
    )
    evaluation_sources = manifest["execution_episode"]["evaluation_sources"]
    assert [source["split"] for source in evaluation_sources] == [
        "train",
        "validation",
        "test",
    ]
    assert {source["source_kind"] for source in evaluation_sources} == {"dataset_split"}
    for source in evaluation_sources:
        split = source["split"]
        assert source["kind"] == "dataset_split"
        assert source["source_artifact_path"] == f"splits/{split}.jsonl"
        assert source["source_artifact_hash"] == _hash(
            root / "splits" / f"{split}.jsonl"
        )
        assert source["dataset_manifest_path"] == "dataset_manifest.json"
        assert source["dataset_manifest_hash"] == dataset_manifest_hash
        assert source["behavior_results_path"] == f"behavior_results.{split}.json"
        assert source["behavior_results_hash"] == _hash(
            root / f"behavior_results.{split}.json"
        )
        assert source["count"] == dataset["split"]["counts"][split]
        assert source["summary"]["total"] == dataset["split"]["counts"][split]
        assert source["metric"] == "exact_match"
        assert source["harness"]["path"] == f"eval_{split}.py"
        assert source["harness"]["status"] == "passed"
    evidence_summary = manifest["execution_episode"]["behavior_evidence_summary"]
    assert evidence_summary["source_count"] == 3
    assert evidence_summary["total"] == 10
    assert evidence_summary["no_examples_source_count"] == 0
    assert manifest["execution_episode"]["runtime_conditions"]["metric"] == (
        "exact_match"
    )
    assert (root / "oracle_evidence.json").exists()
    oracle_evidence = json.loads(
        (root / "oracle_evidence.json").read_text(encoding="utf-8")
    )
    oracle_hash = _hash(root / "oracle_evidence.json")
    assert manifest["request"]["oracle_evidence_hash"] == oracle_hash
    assert oracle_evidence["schema_version"] == "program-oracle-evidence-v1"
    assert oracle_evidence["oracle_facets"]["has_examples"] is False
    assert oracle_evidence["oracle_facets"]["has_dataset_splits"] is True
    assert oracle_evidence["oracle_facets"]["dataset_split_count"] == 3
    assert oracle_evidence["oracle_facets"]["evidence_source_count"] == 3
    assert oracle_evidence["oracle_facets"]["behavior_source_kinds"] == [
        "dataset_split"
    ]
    assert oracle_evidence["oracle_facets"]["total_evaluation_count"] == 10
    assert oracle_evidence["behavior"]["result_path"] is None
    assert oracle_evidence["behavior"]["result_hash"] is None
    assert oracle_evidence["behavior"]["evidence_summary"] == evidence_summary
    assert [
        source["behavior_results_path"]
        for source in oracle_evidence["behavior"]["evaluation_sources"]
    ] == [
        "behavior_results.train.json",
        "behavior_results.validation.json",
        "behavior_results.test.json",
    ]
    assert {
        "kind": "dataset_manifest",
        "path": "dataset_manifest.json",
        "content_hash": dataset_manifest_hash,
    } in oracle_evidence["source_artifacts"]
    assert any(
        artifact.get("kind") == "behavior_results"
        and artifact.get("split") == "validation"
        and artifact.get("path") == "behavior_results.validation.json"
        for artifact in oracle_evidence["source_artifacts"]
    )
    assert "behavior.source_kinds=dataset_split" in oracle_evidence["oracle_text"]
    assert manifest["execution_episode"]["non_authority"]["winner_selection"] is False
    assert (
        manifest["execution_episode"]["non_authority"]["external_authority_mutated"]
        is False
    )
    assert manifest["program_promotion_review"]["promotion_state"] == "not_promoted"
    promotion_review = manifest["program_promotion_review"]
    assert (
        "no_behavioral_evaluation_episode"
        not in promotion_review["blocking_conditions"]
    )
    behavior_requirement = next(
        requirement
        for requirement in promotion_review["evidence_requirements"]
        if requirement["name"] == "behavioral_evaluation_episode"
    )
    assert behavior_requirement["status"] == "satisfied_by_current_behavior_episode"
    assert behavior_requirement["artifact_refs"] == [
        "behavior_results.train.json",
        "behavior_results.validation.json",
        "behavior_results.test.json",
    ]
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


def test_program_dataset_behavior_episode_aggregates_declared_quality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    dataset_path = tmp_path / "data" / "tickets.jsonl"
    _write_jsonl(dataset_path, _ticket_rows())
    monkeypatch.setenv("DSPX_REPLAY_FIXTURE_JSON", json.dumps({"urgency": "high"}))

    passed = materialize_program_from_intent(
        _ratio_intent(dataset_path, declared_quality=True),
        outdir=tmp_path / "quality-passed",
    )
    passed_episode = json.loads(
        (Path(passed.root_path) / "behavior_episode.json").read_text()
    )
    assert [
        source["quality_evaluation"]["evaluations_total"]
        for source in passed_episode["sources"]
    ] == [7, 1, 2]
    assert passed_episode["quality_evaluation"] == {
        "status": "passed",
        "criteria_declared": True,
        "evaluations_total": 10,
        "evaluations_passed": 10,
        "evaluations_failed": 0,
        "quality_approved": False,
    }

    tiny_path = tmp_path / "data" / "tiny-quality.jsonl"
    _write_jsonl(tiny_path, _ticket_rows(1))
    tiny = materialize_program_from_intent(
        _ratio_intent(tiny_path, declared_quality=True),
        outdir=tmp_path / "quality-empty-splits",
    )
    tiny_episode = json.loads(
        (Path(tiny.root_path) / "behavior_episode.json").read_text()
    )
    assert [
        source["quality_evaluation"]["criteria_declared"]
        for source in tiny_episode["sources"]
    ] == [True, True, True]
    tiny_statuses = [
        source["quality_evaluation"]["status"] for source in tiny_episode["sources"]
    ]
    assert tiny_statuses.count("passed") == 1
    assert tiny_statuses.count("not_declared") == 2
    assert tiny_episode["quality_evaluation"]["criteria_declared"] is True
    assert tiny_episode["quality_evaluation"]["evaluations_total"] == 1

    monkeypatch.setenv("DSPX_REPLAY_FIXTURE_JSON", json.dumps({"urgency": "unknown"}))
    failed = materialize_program_from_intent(
        _ratio_intent(dataset_path, declared_quality=True),
        outdir=tmp_path / "quality-failed",
    )
    failed_episode = json.loads(
        (Path(failed.root_path) / "behavior_episode.json").read_text()
    )
    assert failed_episode["quality_evaluation"] == {
        "status": "failed",
        "criteria_declared": True,
        "evaluations_total": 10,
        "evaluations_passed": 0,
        "evaluations_failed": 10,
        "quality_approved": False,
    }


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
    dataset: dict[str, Any] = {
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
