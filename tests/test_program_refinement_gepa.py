from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")


def _hash_tree(root: Path) -> dict[str, str]:
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


def _ticket_rows(count: int) -> list[dict[str, object]]:
    return [
        {
            "inputs": {"ticket_text": f"ticket {index}"},
            "outputs": {"urgency": "high" if index % 2 else "low"},
        }
        for index in range(count)
    ]


def _fake_gepa(
    monkeypatch: pytest.MonkeyPatch, *, output_manifest: object = "default"
) -> list[dict[str, Any]]:
    import dspx.services.program_refinement_gepa as gepa_service

    calls: list[dict[str, Any]] = []

    class FakeResult:
        def __init__(
            self, out_dir: Path, input_keys: list[str], output_keys: list[str]
        ):
            self.out_dir = out_dir
            self.input_keys = input_keys
            self.output_keys = output_keys
            self.chosen_output_keys = output_keys
            self.metric = "exact"
            self.output_weights: dict[str, float] = {}
            self.student_provider = "stub"
            self.reflection_provider = "stub"

    def fake_run_gepa_optimize(**kwargs: Any) -> FakeResult:
        out_dir = Path(kwargs["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        if output_manifest != "missing":
            manifest_payload = (
                {
                    "created_by": "fake_gepa_for_test",
                    "program": str(kwargs["program_path"]),
                    "dataset": {
                        "train": str(kwargs["train_path"]),
                        "val": str(kwargs.get("val_path")),
                    },
                }
                if output_manifest == "default"
                else output_manifest
            )
            text = (
                manifest_payload
                if isinstance(manifest_payload, str)
                else json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n"
            )
            (out_dir / "manifest.json").write_text(str(text), encoding="utf-8")
        calls.append(kwargs)
        return FakeResult(
            out_dir=out_dir,
            input_keys=list(kwargs["input_keys"]),
            output_keys=list(kwargs["output_keys"]),
        )

    monkeypatch.setattr(gepa_service, "run_gepa_optimize", fake_run_gepa_optimize)
    return calls


def test_program_refine_optimize_gepa_rejects_paths_that_overlap_source_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    calls = _fake_gepa(monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="TicketProgram",
            objective="Classify support ticket urgency.",
            inputs=["ticket_text"],
            outputs=["urgency"],
            examples=[
                {
                    "inputs": {"ticket_text": "Server is down"},
                    "outputs": {"urgency": "high"},
                }
            ],
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    before = _hash_tree(program_root)

    cases = [
        (
            program_root,
            tmp_path / "refinement" / "gepa_refinement_result.json",
            "GEPA output directory must be outside source candidate root",
        ),
        (
            program_root / "gepa-output",
            tmp_path / "refinement" / "gepa_refinement_result.json",
            "GEPA output directory must be outside source candidate root",
        ),
        (
            tmp_path,
            tmp_path / "refinement" / "gepa_refinement_result.json",
            "GEPA output directory must not contain source candidate root",
        ),
        (
            tmp_path / "program-gepa",
            program_root / "gepa_refinement_result.json",
            "GEPA result sidecar path must be outside source candidate root",
        ),
        (
            tmp_path / "program-gepa",
            tmp_path / "program-gepa" / "gepa_refinement_result.json",
            "GEPA result sidecar path must not overlap the GEPA output directory",
        ),
    ]
    for outdir, result_path, message in cases:
        result = runner.invoke(
            app,
            [
                "program-refine",
                "optimize-gepa",
                "--manifest",
                str(program_root / "manifest.json"),
                "--outdir",
                str(outdir),
                "--result-out",
                str(result_path),
                "--json",
            ],
        )

        assert result.exit_code == 2
        assert message in (result.stdout + result.stderr)
        assert not result_path.exists()
        assert _hash_tree(program_root) == before
    assert calls == []


def test_program_refine_optimize_gepa_rejects_symlinked_output_into_source_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    calls = _fake_gepa(monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="TicketProgram",
            objective="Classify support ticket urgency.",
            inputs=["ticket_text"],
            outputs=["urgency"],
            examples=[
                {
                    "inputs": {"ticket_text": "Server is down"},
                    "outputs": {"urgency": "high"},
                }
            ],
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    before = _hash_tree(program_root)
    symlink = tmp_path / "candidate-link"
    try:
        symlink.symlink_to(program_root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    result = runner.invoke(
        app,
        [
            "program-refine",
            "optimize-gepa",
            "--manifest",
            str(program_root / "manifest.json"),
            "--outdir",
            str(symlink / "gepa-output"),
            "--result-out",
            str(tmp_path / "refinement" / "gepa_refinement_result.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "GEPA output directory must be outside source candidate root" in (
        result.stdout + result.stderr
    )
    assert _hash_tree(program_root) == before
    assert calls == []


def test_program_refine_optimize_gepa_inline_examples_writes_sidecar_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    calls = _fake_gepa(monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="TicketProgram",
            objective="Classify support ticket urgency.",
            inputs=["ticket_text"],
            outputs=["urgency"],
            metric="exact_match",
            examples=[
                {
                    "inputs": {"ticket_text": "Server is down for all users"},
                    "outputs": {"urgency": "high"},
                }
            ],
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    before = _hash_tree(program_root)
    result_path = tmp_path / "refinement" / "gepa_refinement_result.json"
    outdir = tmp_path / "program-gepa"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "optimize-gepa",
            "--manifest",
            str(program_root / "manifest.json"),
            "--outdir",
            str(outdir),
            "--result-out",
            str(result_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert result_path.exists()
    assert json.loads(result_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == "program-refinement-gepa-result-v1"
    assert payload["status"] == "degraded"
    assert payload["source_identity"]["candidate_id"]
    assert payload["evidence_inputs"]["source"] == "inline_examples"
    assert payload["evidence_inputs"]["train_examples_count"] == 1
    assert payload["evidence_inputs"]["validation_examples_count"] == 1
    assert payload["evidence_inputs"]["held_out_validation"] is False
    assert "not held out" in "\n".join(payload["evidence_inputs"]["limitations"])
    assert payload["created_from"]["behavior_results_path"] == str(
        (program_root / "behavior_results.json").resolve()
    )
    assert payload["gepa"]["attempted"] is True
    assert payload["gepa"]["status"] == "completed"
    assert payload["gepa"]["metric"] == "exact_match"
    assert payload["gepa"]["optimizer_metric"] == "exact"
    assert payload["gepa"]["prepared_inputs"]["train_csv_sha256"]
    assert payload["gepa"]["prepared_inputs"]["validation_csv_sha256"]
    assert payload["candidate"] is None
    assert payload["gepa_output"]["candidate_assembly_manifest"] is False
    assert payload["gepa_output"]["manifest_present"] is True
    assert payload["gepa_output"]["manifest_valid"] is True
    assert payload["gepa_output"]["manifest_sha256"]
    assert (
        payload["gepa_output"]["manifest_kind"] == "dspy_gepa_optimizer_output_manifest"
    )
    assert payload["gepa_output"]["readiness"] == {
        "status": "optimizer_output_hash_bound_not_candidate",
        "ready_for_future_candidate_materializer": True,
        "blockers": [
            "no_program_candidate_assembly_materializer_in_this_command",
            "candidate_field_remains_null_until_explicit_materializer_lands",
        ],
    }
    assert (outdir / "manifest.json").exists()
    assert payload["effect"] == {
        "local_gepa_candidate_generated": False,
        "source_program_files_mutated": False,
        "source_dataset_artifacts_mutated": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
    }
    assert payload["non_authority"] == {
        "local_refinement_only": True,
        "automatic_promotion": False,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "winner_selection": False,
        "external_authority_export": False,
        "governance_authority": False,
        "external_mutation": False,
    }
    assert _hash_tree(program_root) == before
    assert not (program_root / "gepa_refinement_result.json").exists()
    assert (program_root / "eval_behavior.py").exists()
    assert (program_root / "behavior_episode.json").exists()
    assert not (outdir / "eval_behavior.py").exists()
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()
    assert calls and Path(calls[0]["train_path"]).name == "train.csv"


@pytest.mark.parametrize(
    ("output_manifest", "expected_blocker"),
    [
        ("missing", "optimizer_output_manifest_missing"),
        ("{not json", "optimizer_output_manifest_invalid_json"),
        (["not", "object"], "optimizer_output_manifest_not_object"),
    ],
)
def test_program_refine_optimize_gepa_degrades_when_optimizer_manifest_unverified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output_manifest: object,
    expected_blocker: str,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    calls = _fake_gepa(monkeypatch, output_manifest=output_manifest)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="TicketProgram",
            objective="Classify support ticket urgency.",
            inputs=["ticket_text"],
            outputs=["urgency"],
            metric="exact_match",
            examples=[
                {
                    "inputs": {"ticket_text": "Server is down for all users"},
                    "outputs": {"urgency": "high"},
                }
            ],
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    before = _hash_tree(program_root)
    result_path = tmp_path / "refinement" / "gepa_refinement_result.json"

    result = runner.invoke(
        app,
        [
            "program-refine",
            "optimize-gepa",
            "--manifest",
            str(program_root / "manifest.json"),
            "--outdir",
            str(tmp_path / "program-gepa"),
            "--result-out",
            str(result_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "gepa_output_unverified"
    assert payload["gepa"]["status"] == "completed"
    assert payload["candidate"] is None
    assert payload["gepa_output"]["candidate_assembly_manifest"] is False
    assert payload["gepa_output"]["manifest_valid"] is False
    assert payload["gepa_output"]["readiness"]["status"] == (
        "optimizer_output_unverified_not_candidate"
    )
    assert (
        payload["gepa_output"]["readiness"]["ready_for_future_candidate_materializer"]
        is False
    )
    assert expected_blocker in payload["gepa_output"]["readiness"]["blockers"]
    assert "not hash-bound" in "\n".join(payload["gepa"]["notes"])
    assert json.loads(result_path.read_text(encoding="utf-8")) == payload
    assert _hash_tree(program_root) == before
    assert calls and Path(calls[0]["train_path"]).name == "train.csv"


def test_program_refine_optimize_gepa_uses_manifest_dataset_splits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    _fake_gepa(monkeypatch)
    dataset_path = tmp_path / "data" / "tickets.jsonl"
    _write_jsonl(dataset_path, _ticket_rows(4))
    artifact = materialize_program_from_intent(
        ProgramIntent(
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
                    "seed": 7,
                },
            },
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    before = _hash_tree(program_root)
    assert (program_root / "dataset_manifest.json").exists()
    assert (program_root / "splits" / "train.jsonl").exists()
    assert (program_root / "splits" / "validation.jsonl").exists()
    assert (program_root / "behavior_results.train.json").exists()
    assert (program_root / "behavior_results.validation.json").exists()

    result = runner.invoke(
        app,
        [
            "program-refine",
            "optimize-gepa",
            "--manifest",
            str(program_root / "manifest.json"),
            "--outdir",
            str(tmp_path / "program-gepa"),
            "--result-out",
            str(tmp_path / "refinement" / "gepa_refinement_result.json"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["evidence_inputs"]["source"] == "manifest_dataset_splits"
    assert payload["evidence_inputs"]["train_examples_count"] == 2
    assert payload["evidence_inputs"]["validation_examples_count"] == 1
    assert payload["evidence_inputs"]["held_out_validation"] is True
    assert payload["created_from"]["dataset_manifest_path"] == str(
        (program_root / "dataset_manifest.json").resolve()
    )
    assert payload["created_from"]["train_dataset_path"] == str(
        (program_root / "splits" / "train.jsonl").resolve()
    )
    assert payload["created_from"]["validation_dataset_path"] == str(
        (program_root / "splits" / "validation.jsonl").resolve()
    )
    assert payload["created_from"]["train_behavior_results_path"] == str(
        (program_root / "behavior_results.train.json").resolve()
    )
    assert payload["created_from"]["validation_behavior_results_path"] == str(
        (program_root / "behavior_results.validation.json").resolve()
    )
    assert payload["non_authority"]["winner_selection"] is False
    assert payload["effect"]["source_dataset_artifacts_mutated"] is False
    assert _hash_tree(program_root) == before


def test_program_refine_optimize_gepa_explicit_jsonl_paths_and_malformed_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    _fake_gepa(monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="TicketProgram",
            objective="Classify support ticket urgency.",
            inputs=["ticket_text"],
            outputs=["urgency"],
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    train = tmp_path / "data" / "train.jsonl"
    validation = tmp_path / "data" / "validation.jsonl"
    _write_jsonl(train, _ticket_rows(2))
    _write_jsonl(validation, _ticket_rows(1))

    result = runner.invoke(
        app,
        [
            "program-refine",
            "optimize-gepa",
            "--manifest",
            str(program_root / "manifest.json"),
            "--outdir",
            str(tmp_path / "program-gepa"),
            "--result-out",
            str(tmp_path / "refinement" / "gepa_refinement_result.json"),
            "--train",
            str(train),
            "--validation",
            str(validation),
            "--max-metric-calls",
            "2",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["evidence_inputs"]["source"] == "explicit_dataset_files"
    assert payload["evidence_inputs"]["train_examples_count"] == 2
    assert payload["evidence_inputs"]["validation_examples_count"] == 1
    assert payload["created_from"]["train_dataset_path"] == str(train.resolve())
    assert payload["created_from"]["validation_dataset_path"] == str(
        validation.resolve()
    )

    bad_train = tmp_path / "data" / "bad.jsonl"
    bad_train.write_text('{"inputs":{"ticket_text":"x"}}\n', encoding="utf-8")
    bad = runner.invoke(
        app,
        [
            "program-refine",
            "optimize-gepa",
            "--manifest",
            str(program_root / "manifest.json"),
            "--outdir",
            str(tmp_path / "program-gepa-bad"),
            "--result-out",
            str(tmp_path / "refinement" / "bad.json"),
            "--train",
            str(bad_train),
            "--validation",
            str(validation),
            "--json",
        ],
    )

    assert bad.exit_code == 2
    assert "missing object outputs" in (bad.stdout + bad.stderr)
    assert not (tmp_path / "refinement" / "bad.json").exists()


def test_program_refine_optimize_gepa_degrades_without_examples(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    calls = _fake_gepa(monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="NoEvidenceProgram",
            objective="Answer a question.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)

    result = runner.invoke(
        app,
        [
            "program-refine",
            "optimize-gepa",
            "--manifest",
            str(program_root / "manifest.json"),
            "--outdir",
            str(tmp_path / "program-gepa"),
            "--result-out",
            str(tmp_path / "refinement" / "gepa_refinement_result.json"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "insufficient_behavior_evidence"
    assert payload["gepa"]["attempted"] is False
    assert payload["gepa"]["status"] == "insufficient_behavior_evidence"
    assert payload["candidate"] is None
    assert calls == []
