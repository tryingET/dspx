from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services.program_service import ProgramIntent, materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt

runner = CliRunner()


def test_program_service_materializes_candidate_assembly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="AnswerQuestion",
        objective="Answer a question from the supplied context.",
        inputs=["context", "question"],
        outputs=["answer", "confidence"],
        constraints=["cite only supplied context"],
        metric="exact_match",
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")

    root = Path(artifact.root_path)
    assert (root / "signature.py").exists()
    assert (root / "module.py").exists()
    assert (root / "program.py").exists()
    assert (root / "eval_smoke.py").exists()
    assert (root / "intent.json").exists()
    assert (root / "manifest.json").exists()
    assert (root / "manifest.json.meta.json").exists()

    signature_code = (root / "signature.py").read_text(encoding="utf-8")
    module_code = (root / "module.py").read_text(encoding="utf-8")
    program_code = (root / "program.py").read_text(encoding="utf-8")
    assert "class AnswerQuestionSignature(dspy.Signature):" in signature_code
    assert "class AnswerQuestionSignature(dspy.Signature):" in module_code
    assert "class AnswerQuestionModule(dspy.Module):" in module_code
    assert "from module import (" in program_code
    assert "def build_program() -> dspy.Module:" in program_code
    compile(program_code, str(root / "program.py"), "exec")

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "program-candidate-assembly-v1"
    assert manifest["candidate_assembly"]["artifact_kind"] == "program"
    assert manifest["candidate_assembly"]["surface_kinds"] == [
        "intent",
        "signature",
        "module",
        "program",
        "eval_harness",
    ]
    assert manifest["candidate_assembly"]["surfaces"][0]["generator"] == "signature-gen"
    assert manifest["candidate_assembly"]["surfaces"][1]["generator"] == "module-gen"
    assert manifest["execution_episode"]["status"] == "passed"
    assert manifest["receipt_bundle"]["status"] == "captured"

    smoke = subprocess.run(
        [sys.executable, "eval_smoke.py"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert smoke.returncode == 0, smoke.stderr
    assert "program smoke ok: AnswerQuestion" in smoke.stdout

    receipt = json.loads((root / "manifest.json.meta.json").read_text(encoding="utf-8"))
    assert receipt["run_kind"] == "program-gen"
    assert receipt["run_summary"]["backend"] == "program_candidate_assembly"
    assert (
        receipt["hash"]
        == hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
    )
    assert (
        receipt["program_candidate_assembly"]["assembly_id"]
        == artifact.metadata["assembly_id"]
    )
    evidence = receipt["program_receipt_bundle"]["evidence"]
    assert evidence["smoke"]["returncode"] == 0
    assert evidence["surface_generation"]["signature"] == "signature-gen"
    assert evidence["surface_generation"]["module"] == "module-gen"
    assert "signature.py" in evidence["surface_hashes"]

    replay = check_run_receipt(root / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert replay["checks"]["output_hash_match"] is True
    assert replay["checks"]["cache_key_recomputes"] is True
    assert replay["checks"]["cache_code_hash_matches_receipt"] is True


def test_program_gen_cli_materializes_from_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent_path = tmp_path / "intent.yaml"
    intent_path.write_text(
        "\n".join(
            [
                "name: ClassifierProgram",
                "objective: Classify a ticket by urgency.",
                "inputs:",
                "  - ticket_text",
                "outputs:",
                "  - urgency",
                "metric: accuracy",
            ]
        ),
        encoding="utf-8",
    )
    outdir = tmp_path / "candidate"

    result = runner.invoke(
        app,
        [
            "program-gen",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--print-manifest",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["intent"]["name"] == "ClassifierProgram"
    assert payload["candidate_assembly"]["entrypoint"] == "program.py"
    assert payload["candidate_assembly"]["surfaces"][0]["path"] == "signature.py"
    assert (outdir / "signature.py").exists()
    assert (outdir / "module.py").exists()
    assert (outdir / "program.py").exists()
    assert (outdir / "manifest.json.meta.json").exists()


def test_program_service_rejects_empty_or_overlapping_io() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ProgramIntent(name="EmptyInputs", objective="x", inputs=[], outputs=["answer"])

    with pytest.raises(ValueError, match="must not overlap"):
        ProgramIntent(
            name="Overlap",
            objective="x",
            inputs=["answer"],
            outputs=["answer"],
        )


def test_program_service_handles_docstring_hostile_objective(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="QuoteHeavy",
        objective='Handle triple quotes """ and newlines\nwithout breaking code.',
        inputs=["text"],
        outputs=["answer"],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "quotes")
    root = Path(artifact.root_path)
    program_code = (root / "program.py").read_text(encoding="utf-8")
    compile(program_code, str(root / "program.py"), "exec")
    smoke = subprocess.run(
        [sys.executable, "eval_smoke.py"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert smoke.returncode == 0, smoke.stderr


def test_program_service_binds_examples_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ExampleBoundProgram",
        objective="Answer from context with a confidence score.",
        inputs=["context", "question"],
        outputs=["answer", "confidence"],
        examples=[
            {
                "inputs": {"context": "Sky is blue.", "question": "What color?"},
                "outputs": {"answer": "blue", "confidence": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "examples")

    root = Path(artifact.root_path)
    assert (root / "examples.json").exists()
    assert (root / "eval_examples.py").exists()

    examples = subprocess.run(
        [sys.executable, "eval_examples.py"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert examples.returncode == 0, examples.stderr
    assert "program examples ok: 1 example(s)" in examples.stdout

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert "examples" in manifest["candidate_assembly"]["surface_kinds"]
    evidence = manifest["receipt_bundle"]["evidence"]
    assert "examples_hash" in evidence
    assert evidence["examples"]["returncode"] == 0
    assert "examples.json" in evidence["generated_files"]


def test_program_gen_cli_rejects_invalid_intent_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent_path = tmp_path / "intent.yaml"
    intent_path.write_text(
        "\n".join(
            [
                "name: BrokenProgram",
                "objective: Broken field names should fail.",
                "inputs:",
                "  - bad-field",
                "outputs:",
                "  - answer",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["program-gen", "--intent", str(intent_path)])

    assert result.exit_code == 2
    combined = (result.stdout + result.stderr).lower()
    assert "valid python identifiers" in combined
