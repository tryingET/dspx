from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services import program_service
from dspx.services.program_service import ProgramIntent, materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt

runner = CliRunner()


def test_behavior_results_retry_detects_codex_stream_errors() -> None:
    payload = {
        "summary": {"status": "error", "total": 2, "error": 2},
        "examples": [
            {
                "status": "error",
                "error": {
                    "message": 'litellm.BadRequestError: OpenAIException - {"detail":"Stream must be set to true"}'
                },
            },
            {
                "status": "error",
                "error": {"message": "OpenAIException - stream must be set to true"},
            },
        ],
    }

    assert program_service._behavior_results_has_retryable_codex_stream_error(payload)


def test_behavior_results_retry_rejects_mixed_or_non_codex_errors() -> None:
    assert not program_service._behavior_results_has_retryable_codex_stream_error(
        {
            "summary": {"status": "error"},
            "examples": [
                {"status": "error", "error": {"message": "Stream must be set to true"}},
                {
                    "status": "failed",
                    "error": {"message": "Stream must be set to true"},
                },
            ],
        }
    )
    assert not program_service._behavior_results_has_retryable_codex_stream_error(
        {
            "summary": {"status": "error"},
            "examples": [{"status": "error", "error": {"message": "rate limit"}}],
        }
    )


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
    assert (root / "plan.json").exists()
    assert (root / "jury.json").exists()
    assert (root / "jury_selection.json").exists()
    assert (root / "jury_rubric.json").exists()
    assert (root / "promotion_review.json").exists()
    assert (root / "promotion_adjudication_request.json").exists()
    assert (root / "promotion_decision_template.json").exists()
    assert (root / "signature.py").exists()
    assert (root / "module.py").exists()
    assert (root / "program.py").exists()
    assert (root / "eval_smoke.py").exists()
    assert (root / "eval_jury.py").exists()
    assert (root / "eval_promotion.py").exists()
    assert (root / "intent.json").exists()
    assert (root / "execution_episode.json").exists()
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
    assert manifest["program_plan"]["schema_version"] == "program-plan-v1"
    assert manifest["program_plan"]["task_type"] == "single_module"
    inferred_jury = manifest["program_plan"]["evaluation_strategy"]
    assert inferred_jury["mode"] == "jury"
    assert inferred_jury["pool"]["scope"] == "program"
    assert inferred_jury["pool"]["explicit_juror_count"] == 0
    inferred_perspectives = {item["perspective"] for item in inferred_jury["jurors"]}
    assert {
        "correctness",
        "robustness",
        "instruction_following",
        "answer_equivalence",
        "calibration",
        "grounding",
        "constraint_adherence",
    }.issubset(inferred_perspectives)
    assert (
        manifest["program_plan"]["non_authority"]["ranking_pruning_promotion"] is False
    )
    assert manifest["candidate_assembly"]["surface_kinds"] == [
        "plan",
        "jury",
        "jury_selection",
        "jury_rubric",
        "promotion_review",
        "promotion_adjudication_request",
        "promotion_decision_template",
        "intent",
        "module_surfaces",
        "execution_episode",
        "signature",
        "module",
        "program",
        "eval_harness",
        "jury_harness",
        "promotion_harness",
    ]
    assert manifest["candidate_assembly"]["surfaces"][0]["generator"] == "program-gen"
    assert manifest["candidate_assembly"]["surfaces"][1]["path"] == "jury.json"
    assert manifest["candidate_assembly"]["surfaces"][1]["generator"] == "program-gen"
    assert (
        manifest["candidate_assembly"]["surfaces"][2]["path"] == "jury_selection.json"
    )
    assert manifest["candidate_assembly"]["surfaces"][2]["generator"] == "program-gen"
    assert manifest["candidate_assembly"]["surfaces"][3]["path"] == "jury_rubric.json"
    assert manifest["candidate_assembly"]["surfaces"][3]["generator"] == "program-gen"
    assert (
        manifest["candidate_assembly"]["surfaces"][4]["path"] == "promotion_review.json"
    )
    assert manifest["candidate_assembly"]["surfaces"][4]["generator"] == "program-gen"
    assert (
        manifest["candidate_assembly"]["surfaces"][5]["path"]
        == "promotion_adjudication_request.json"
    )
    assert manifest["candidate_assembly"]["surfaces"][5]["generator"] == "program-gen"
    assert (
        manifest["candidate_assembly"]["surfaces"][6]["path"]
        == "promotion_decision_template.json"
    )
    assert manifest["candidate_assembly"]["surfaces"][6]["generator"] == "program-gen"
    assert (
        manifest["candidate_assembly"]["surfaces"][7]["path"] == "module_surfaces.json"
    )
    assert manifest["candidate_assembly"]["surfaces"][7]["generator"] == "program-gen"
    assert (
        manifest["candidate_assembly"]["surfaces"][8]["path"]
        == "execution_episode.json"
    )
    assert manifest["candidate_assembly"]["surfaces"][8]["generator"] == "program-gen"
    assert manifest["candidate_assembly"]["surfaces"][9]["generator"] == "signature-gen"
    assert manifest["candidate_assembly"]["surfaces"][10]["generator"] == "module-gen"
    promotion_review = manifest["program_promotion_review"]
    assert promotion_review["schema_version"] == "program-promotion-review-v1"
    assert promotion_review["promotion_state"] == "not_promoted"
    assert promotion_review["review_required"] is True
    assert promotion_review["adjudicator"] == {
        "kind": "human_operator",
        "id": "local_operator",
        "authority": "required_for_promotion",
        "status": "pending",
    }
    assert promotion_review["promotion_policy"] == {
        "requires_behavioral_evaluation": True,
        "requires_jury_execution": True,
        "requires_adjudicator_decision": True,
        "automatic_promotion": False,
    }
    assert promotion_review["external_authority"]["status"] == "not_exported"
    assert promotion_review["external_authority"]["refs"] == []
    assert "supported_adapters" not in promotion_review["external_authority"]
    assert "no_behavioral_evaluation_episode" in promotion_review["blocking_conditions"]
    assert (
        "no_promotion_adjudicator_decision" in promotion_review["blocking_conditions"]
    )
    assert promotion_review["decision"]["status"] == "pending"
    adjudication_request = manifest["program_promotion_adjudication_request"]
    assert (
        adjudication_request["schema_version"]
        == "program-promotion-adjudication-request-v1"
    )
    assert adjudication_request["status"] == "not_ready_blocked"
    assert adjudication_request["adjudicator"] == promotion_review["adjudicator"]
    assert (
        adjudication_request["external_authority"]
        == promotion_review["external_authority"]
    )
    assert "request_more_evidence" in adjudication_request["allowed_outcomes"]
    assert (
        "no_promotion_adjudicator_decision"
        in adjudication_request["missing_required_evidence"]
    )
    decision_template = manifest["program_promotion_decision_template"]
    assert decision_template == adjudication_request["decision_record_template"]
    assert decision_template["status"] == "pending"
    assert promotion_review["non_authority"]["automatic_promotion"] is False
    assert promotion_review["non_authority"]["ranking_pruning_promotion"] is False
    assert promotion_review["non_authority"]["external_authority_export"] is False
    execution_episode = json.loads(
        (root / "execution_episode.json").read_text(encoding="utf-8")
    )
    assert execution_episode["schema_version"] == "program-execution-episode-v1"
    assert execution_episode == manifest["execution_episode"]
    assert execution_episode["status"] == "passed"
    assert execution_episode["materialization"]["status"] == "passed"
    assert execution_episode["checks"]["compile"]["status"] == "passed"
    assert execution_episode["checks"]["smoke"]["status"] == "passed"
    assert execution_episode["checks"]["examples_binding"]["status"] == "not_applicable"
    assert execution_episode["checks"]["jury_binding"]["status"] == "passed"
    assert execution_episode["checks"]["promotion_binding"]["status"] == "passed"
    assert execution_episode["behavioral_evaluation"]["status"] == "not_applicable"
    assert execution_episode["behavioral_evaluation"]["result_artifact"] is None
    assert execution_episode["oracle_readability"]["status"] == "not_applicable"
    assert execution_episode["oracle_readability"]["oracle_invoked"] is False
    assert execution_episode["non_authority"]["evidence_only"] is True
    assert execution_episode["non_authority"]["oracle_ranking"] is False
    assert execution_episode["non_authority"]["oracle_pruning"] is False
    assert execution_episode["non_authority"]["oracle_promotion"] is False
    assert execution_episode["non_authority"]["external_mutation"] is False
    assert manifest["execution_episode"]["metadata"]["jury"]["returncode"] == 0
    assert manifest["execution_episode"]["metadata"]["promotion"]["returncode"] == 0
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
    assert evidence["jury"]["returncode"] == 0
    assert evidence["promotion"]["returncode"] == 0
    plan_hash = hashlib.sha256((root / "plan.json").read_bytes()).hexdigest()
    jury_hash = hashlib.sha256((root / "jury.json").read_bytes()).hexdigest()
    jury_selection_hash = hashlib.sha256(
        (root / "jury_selection.json").read_bytes()
    ).hexdigest()
    jury_rubric_hash = hashlib.sha256(
        (root / "jury_rubric.json").read_bytes()
    ).hexdigest()
    promotion_review_hash = hashlib.sha256(
        (root / "promotion_review.json").read_bytes()
    ).hexdigest()
    promotion_adjudication_request_hash = hashlib.sha256(
        (root / "promotion_adjudication_request.json").read_bytes()
    ).hexdigest()
    promotion_decision_template_hash = hashlib.sha256(
        (root / "promotion_decision_template.json").read_bytes()
    ).hexdigest()
    module_surfaces_hash = hashlib.sha256(
        (root / "module_surfaces.json").read_bytes()
    ).hexdigest()
    execution_episode_hash = hashlib.sha256(
        (root / "execution_episode.json").read_bytes()
    ).hexdigest()
    assert evidence["plan_hash"] == plan_hash
    assert evidence["jury_hash"] == jury_hash
    assert evidence["jury_selection_hash"] == jury_selection_hash
    assert evidence["jury_rubric_hash"] == jury_rubric_hash
    assert evidence["promotion_review_hash"] == promotion_review_hash
    assert (
        evidence["promotion_adjudication_request_hash"]
        == promotion_adjudication_request_hash
    )
    assert (
        evidence["promotion_decision_template_hash"] == promotion_decision_template_hash
    )
    assert evidence["module_surfaces_hash"] == module_surfaces_hash
    assert evidence["module_surfaces_path"] == "module_surfaces.json"
    assert evidence["execution_episode_hash"] == execution_episode_hash
    assert evidence["execution_episode_path"] == "execution_episode.json"
    assert evidence["surface_hashes"]["module_surfaces.json"] == module_surfaces_hash
    assert (
        evidence["surface_hashes"]["execution_episode.json"] == execution_episode_hash
    )
    assert manifest["request"]["module_surfaces_hash"] == module_surfaces_hash
    assert manifest["request"]["execution_episode_hash"] == execution_episode_hash
    assert manifest["execution_episode_artifact"] == {
        "path": "execution_episode.json",
        "content_hash": execution_episode_hash,
        "schema_version": "program-execution-episode-v1",
    }
    assert receipt["run_summary"]["plan_hash"] == plan_hash
    assert receipt["run_summary"]["jury_hash"] == jury_hash
    assert receipt["run_summary"]["jury_selection_hash"] == jury_selection_hash
    assert receipt["run_summary"]["jury_rubric_hash"] == jury_rubric_hash
    assert receipt["run_summary"]["promotion_review_hash"] == promotion_review_hash
    assert (
        receipt["run_summary"]["promotion_adjudication_request_hash"]
        == promotion_adjudication_request_hash
    )
    assert (
        receipt["run_summary"]["promotion_decision_template_hash"]
        == promotion_decision_template_hash
    )
    assert receipt["run_summary"]["module_surfaces_hash"] == module_surfaces_hash
    assert receipt["run_summary"]["module_surfaces_path"] == "module_surfaces.json"
    assert receipt["run_summary"]["execution_episode_hash"] == execution_episode_hash
    assert receipt["run_summary"]["execution_episode_path"] == "execution_episode.json"
    assert receipt["program_module_surfaces"] == manifest["program_module_surfaces"]
    assert (
        receipt["program_module_surfaces_artifact"]
        == manifest["module_surfaces_artifact"]
    )
    assert (
        receipt["program_execution_episode_artifact"]
        == manifest["execution_episode_artifact"]
    )
    assert receipt["program_plan"]["schema_version"] == "program-plan-v1"
    assert evidence["surface_generation"]["plan"] == "program-gen"
    assert evidence["surface_generation"]["jury"] == "program-gen"
    assert evidence["surface_generation"]["jury_selection"] == "program-gen"
    assert evidence["surface_generation"]["jury_rubric"] == "program-gen"
    assert evidence["surface_generation"]["promotion_review"] == "program-gen"
    assert (
        evidence["surface_generation"]["promotion_adjudication_request"]
        == "program-gen"
    )
    assert (
        evidence["surface_generation"]["promotion_decision_template"] == "program-gen"
    )
    assert evidence["surface_generation"]["module_surfaces"] == "program-gen"
    assert evidence["surface_generation"]["execution_episode"] == "program-gen"
    assert evidence["surface_generation"]["jury_harness"] == "program-gen"
    assert evidence["surface_generation"]["promotion_harness"] == "program-gen"
    assert evidence["surface_generation"]["signature"] == "signature-gen"
    assert evidence["surface_generation"]["module"] == "module-gen"
    assert "plan.json" in evidence["surface_hashes"]
    assert "jury.json" in evidence["surface_hashes"]
    assert "jury_selection.json" in evidence["surface_hashes"]
    assert "jury_rubric.json" in evidence["surface_hashes"]
    assert "promotion_review.json" in evidence["surface_hashes"]
    assert "promotion_adjudication_request.json" in evidence["surface_hashes"]
    assert "promotion_decision_template.json" in evidence["surface_hashes"]
    assert "module_surfaces.json" in evidence["surface_hashes"]
    assert "execution_episode.json" in evidence["surface_hashes"]
    assert "eval_jury.py" in evidence["surface_hashes"]
    assert "eval_promotion.py" in evidence["surface_hashes"]
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
    assert payload["program_plan"]["schema_version"] == "program-plan-v1"
    assert payload["candidate_assembly"]["surfaces"][0]["path"] == "plan.json"
    assert payload["candidate_assembly"]["surfaces"][1]["path"] == "jury.json"
    assert payload["candidate_assembly"]["surfaces"][2]["path"] == "jury_selection.json"
    assert payload["candidate_assembly"]["surfaces"][3]["path"] == "jury_rubric.json"
    assert (
        payload["candidate_assembly"]["surfaces"][4]["path"] == "promotion_review.json"
    )
    assert (
        payload["candidate_assembly"]["surfaces"][5]["path"]
        == "promotion_adjudication_request.json"
    )
    assert (
        payload["candidate_assembly"]["surfaces"][6]["path"]
        == "promotion_decision_template.json"
    )
    assert (
        payload["candidate_assembly"]["surfaces"][7]["path"] == "module_surfaces.json"
    )
    assert (
        payload["candidate_assembly"]["surfaces"][8]["path"] == "execution_episode.json"
    )
    assert payload["candidate_assembly"]["surfaces"][9]["path"] == "signature.py"
    assert any(
        surface["kind"] == "direct_runner" and surface["path"] == "direct_run.py"
        for surface in payload["candidate_assembly"]["surfaces"]
    )
    assert "direct_run.py" in payload["receipt_bundle"]["evidence"]["generated_files"]
    assert (
        payload["receipt_bundle"]["evidence"]["surface_generation"]["direct_runner"]
        == "program-gen"
    )
    assert (outdir / "plan.json").exists()
    assert (outdir / "jury.json").exists()
    assert (outdir / "jury_selection.json").exists()
    assert (outdir / "jury_rubric.json").exists()
    assert (outdir / "promotion_review.json").exists()
    assert (outdir / "promotion_adjudication_request.json").exists()
    assert (outdir / "promotion_decision_template.json").exists()
    assert (outdir / "module_surfaces.json").exists()
    assert (outdir / "execution_episode.json").exists()
    assert (outdir / "signature.py").exists()
    assert (outdir / "module.py").exists()
    assert (outdir / "program.py").exists()
    direct_run_text = (outdir / "direct_run.py").read_text(encoding="utf-8")
    assert "--inputs-root" in direct_run_text
    assert "direct_batch_receipt.json" in direct_run_text
    assert "ThreadPoolExecutor" in direct_run_text
    assert (outdir / "direct_run.py").exists()
    assert (outdir / "eval_jury.py").exists()
    assert (outdir / "eval_promotion.py").exists()
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


def test_program_service_uses_structured_field_specs_in_signature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="TypedClassifier",
        objective="Classify a support ticket.",
        input_fields=[
            {"name": "ticket_text", "type": "str", "desc": "Raw support ticket"},
        ],
        output_fields=[
            {
                "name": "priority",
                "type": "Literal['low', 'high']",
                "desc": "Priority label",
            },
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "typed")

    root = Path(artifact.root_path)
    signature_code = (root / "signature.py").read_text(encoding="utf-8")
    assert "from typing import Literal" in signature_code
    assert (
        "ticket_text: str = dspy.InputField(desc='Raw support ticket')"
        in signature_code
    )
    assert "priority: Literal['low', 'high'] = dspy.OutputField" in signature_code
    assert artifact.manifest["intent"]["inputs"] == ["ticket_text"]
    assert artifact.manifest["intent"]["outputs"] == ["priority"]
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    assert plan["schema_version"] == "program-plan-v1"
    assert plan["fields"]["inputs"] == [
        {"name": "ticket_text", "type": "str", "desc": "Raw support ticket"}
    ]
    assert plan["fields"]["outputs"] == [
        {
            "name": "priority",
            "type": "Literal['low', 'high']",
            "desc": "Priority label",
        }
    ]
    assert plan["topology"]["kind"] == "single_module"


def test_program_gen_cli_binds_examples_path_relative_to_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    examples_path = tmp_path / "examples.yaml"
    examples_path.write_text(
        "\n".join(
            [
                "- inputs:",
                "    text: hello",
                "  outputs:",
                "    summary: greeting",
            ]
        ),
        encoding="utf-8",
    )
    intent_path = tmp_path / "intent.yaml"
    intent_path.write_text(
        "\n".join(
            [
                "name: SummarizerProgram",
                "objective: Summarize text.",
                "inputs:",
                "  - text",
                "outputs:",
                "  - summary",
                "examples_path: examples.yaml",
            ]
        ),
        encoding="utf-8",
    )
    outdir = tmp_path / "candidate"

    result = runner.invoke(
        app,
        ["program-gen", "--intent", str(intent_path), "--outdir", str(outdir)],
    )

    assert result.exit_code == 0, result.output
    assert (outdir / "examples.json").exists()
    assert (outdir / "eval_examples.py").exists()
    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["intent"]["examples_path"] == str(examples_path.resolve())
    assert manifest["program_plan"]["examples"]["source"] == "examples_path"
    assert manifest["program_plan"]["examples"]["path"] == str(examples_path.resolve())
    assert manifest["program_plan"]["examples"]["count"] == 1
    episode = manifest["execution_episode"]
    assert episode["evaluation_sources"][0]["source_kind"] == "examples_path"
    assert episode["evaluation_sources"][0]["source_path"] == str(
        examples_path.resolve()
    )
    assert episode["evaluation_sources"][0]["input_artifact_path"] == "examples.json"
    assert episode["evaluation_sources"][0]["behavior_results_path"] == (
        "behavior_results.json"
    )
    assert episode["behavior_evidence_summary"]["source_count"] == 1
    assert episode["behavior_evidence_summary"]["total"] == 1
    assert episode["non_authority"]["external_authority_mutated"] is False
    assert episode["non_authority"]["winner_selection"] is False
    assert (
        manifest["request"]["plan_hash"]
        == hashlib.sha256((outdir / "plan.json").read_bytes()).hexdigest()
    )
    assert manifest["receipt_bundle"]["evidence"]["examples"]["returncode"] == 0


def test_program_service_binds_examples_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    real_run = program_service.subprocess.run
    subprocess_calls: list[list[str]] = []

    def spy_run(
        command: list[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        command_text = [str(part) for part in command]
        command_names = [Path(part).name for part in command_text]
        assert "ak" not in command_names
        assert "oracle" not in command_names
        env = kwargs.get("env")
        if (
            env is not None
            and len(command_text) == 2
            and Path(command_text[1]).name.startswith("eval_")
        ):
            assert isinstance(env, dict)
            source_root = str(Path(program_service.__file__).resolve().parents[2])
            assert source_root in str(env.get("PYTHONPATH", ""))
        subprocess_calls.append(command_text)
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(program_service.subprocess, "run", spy_run)
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
    assert "create_from_env(default='dspy-lm-auth')" in (
        root / "eval_examples.py"
    ).read_text(encoding="utf-8")
    assert (root / "behavior_results.json").exists()
    assert (root / "eval_behavior.py").exists()
    assert (root / "behavior_episode.json").exists()
    assert (root / "oracle_evidence.json").exists()
    assert (root / "execution_episode.json").exists()
    module_code = (root / "module.py").read_text(encoding="utf-8")
    assert "DEMO_EXAMPLES =" in module_code
    assert "self.predict.demos = _build_demos()" in module_code
    assert "answer: str = dspy.OutputField" in module_code

    behavior_results = json.loads(
        (root / "behavior_results.json").read_text(encoding="utf-8")
    )
    assert behavior_results["schema_version"] == "program-behavior-results-v1"
    assert behavior_results["intent_name"] == "ExampleBoundProgram"
    assert behavior_results["input_fields"] == ["context", "question"]
    assert behavior_results["output_fields"] == ["answer", "confidence"]
    assert behavior_results["authority"] == "behavior_evidence_only_non_authoritative"
    assert behavior_results["non_authority"]["promotion_authority"] is False
    assert behavior_results["non_authority"]["oracle_ranking"] is False
    assert behavior_results["non_authority"]["external_authority_mutated"] is False
    assert behavior_results["non_authority"]["winner_selection"] is False
    assert behavior_results["summary"]["total"] == 1
    assert behavior_results["summary"]["status"] in {
        "passed",
        "failed",
        "error",
        "degraded",
        "executed",
    }
    record = behavior_results["examples"][0]
    assert record["inputs"] == {"context": "Sky is blue.", "question": "What color?"}
    assert record["expected_outputs"] == {"answer": "blue", "confidence": "high"}
    assert "observed_outputs" in record
    assert record["status"] in {
        "passed",
        "failed",
        "error",
        "degraded_no_comparable_output",
        "executed",
    }

    behavior_hash = hashlib.sha256(
        (root / "behavior_results.json").read_bytes()
    ).hexdigest()
    behavior_episode = json.loads(
        (root / "behavior_episode.json").read_text(encoding="utf-8")
    )
    behavior_episode_hash = hashlib.sha256(
        (root / "behavior_episode.json").read_bytes()
    ).hexdigest()
    assert behavior_episode["schema_version"] == "program-behavior-episode-v1"
    assert behavior_episode["authority"] == "behavior_evidence_only_non_authoritative"
    assert behavior_episode["non_authority"]["winner_selection"] is False
    assert behavior_episode["summary"]["source_count"] == 1
    assert behavior_episode["sources"][0]["source_kind"] == "inline_examples"
    assert behavior_episode["sources"][0]["behavior_results_path"] == (
        "behavior_results.json"
    )
    assert behavior_episode["sources"][0]["behavior_results_hash"] == behavior_hash
    oracle_evidence = json.loads(
        (root / "oracle_evidence.json").read_text(encoding="utf-8")
    )
    assert oracle_evidence["schema_version"] == "program-oracle-evidence-v1"
    assert oracle_evidence["evidence_kind"] == "program_execution_episode"
    assert oracle_evidence["authority"] == "oracle_readability_only_non_authoritative"
    assert oracle_evidence["non_authority"] == {
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "governance_authority": False,
        "external_mutation": False,
    }
    assert oracle_evidence["identity"] == {
        "request_id": artifact.metadata["request_id"],
        "candidate_id": artifact.metadata["candidate_id"],
        "assembly_id": artifact.metadata["assembly_id"],
        "episode_id": artifact.metadata["episode_id"],
        "receipt_bundle_id": artifact.metadata["receipt_bundle_id"],
    }
    assert oracle_evidence["intent"] == {
        "name": "ExampleBoundProgram",
        "objective": "Answer from context with a confidence score.",
        "task_type": "single_module",
        "metric": "unspecified",
        "constraints": [],
    }
    assert oracle_evidence["io"] == {
        "inputs": ["context", "question"],
        "outputs": ["answer", "confidence"],
    }
    assert oracle_evidence["behavior"]["result_path"] == "behavior_results.json"
    assert oracle_evidence["behavior"]["result_hash"] == behavior_hash
    assert oracle_evidence["behavior"]["summary"] == behavior_results["summary"]
    assert (
        oracle_evidence["behavior"]["statuses"]
        == behavior_results["summary"]["status_counts"]
    )
    assert oracle_evidence["oracle_facets"]["task_type"] == "single_module"
    assert oracle_evidence["oracle_facets"]["metric"] == "unspecified"
    assert oracle_evidence["oracle_facets"]["input_fields"] == [
        "context",
        "question",
    ]
    assert oracle_evidence["oracle_facets"]["output_fields"] == [
        "answer",
        "confidence",
    ]
    assert oracle_evidence["oracle_facets"]["has_examples"] is True
    assert oracle_evidence["oracle_facets"]["example_count"] == 1
    assert "schema_version=program-oracle-evidence-v1" in oracle_evidence["oracle_text"]
    assert "oracle_ranking=false" in oracle_evidence["oracle_text"]
    assert oracle_evidence["behavior"]["evidence_summary"] == {
        "status": behavior_results["summary"]["status"],
        "source_count": 1,
        "executed_source_count": 1,
        "total": 1,
        "passed": behavior_results["summary"]["passed"],
        "failed": behavior_results["summary"]["failed"],
        "error": behavior_results["summary"]["error"],
        "degraded": behavior_results["summary"]["degraded"],
        "no_examples_source_count": 0,
        "status_counts": {behavior_results["summary"]["status"]: 1},
        "source_statuses": [
            {
                "kind": "examples",
                "source_kind": "inline_examples",
                "split": None,
                "status": behavior_results["summary"]["status"],
                "count": 1,
                "behavior_results_path": "behavior_results.json",
            }
        ],
    }
    assert oracle_evidence["oracle_facets"]["evidence_source_count"] == 1
    assert oracle_evidence["oracle_facets"]["behavior_source_kinds"] == [
        "inline_examples"
    ]
    assert oracle_evidence["oracle_facets"]["total_evaluation_count"] == 1
    assert oracle_evidence["oracle_facets"]["has_dataset_splits"] is False
    assert "behavior.evidence_source_count=1" in oracle_evidence["oracle_text"]
    assert "behavior.source_kinds=inline_examples" in oracle_evidence["oracle_text"]
    assert {
        "kind": "behavior_results",
        "path": "behavior_results.json",
        "content_hash": behavior_hash,
        "source_kind": "inline_examples",
    } in oracle_evidence["source_artifacts"]

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
    assert "behavior_results" in manifest["candidate_assembly"]["surface_kinds"]
    assert "behavior_harness" in manifest["candidate_assembly"]["surface_kinds"]
    assert "behavior_episode" in manifest["candidate_assembly"]["surface_kinds"]
    assert "oracle_evidence" in manifest["candidate_assembly"]["surface_kinds"]
    oracle_hash = hashlib.sha256(
        (root / "oracle_evidence.json").read_bytes()
    ).hexdigest()
    assert manifest["request"]["behavior_results_hash"] == behavior_hash
    assert manifest["request"]["behavior_episode_hash"] == behavior_episode_hash
    assert manifest["request"]["oracle_evidence_hash"] == oracle_hash
    assert manifest["execution_episode"]["behavior_results"] == {
        "path": "behavior_results.json",
        "content_hash": behavior_hash,
        "summary": behavior_results["summary"],
    }
    assert manifest["execution_episode"]["oracle_evidence"] == {
        "path": "oracle_evidence.json",
        "content_hash": oracle_hash,
        "summary": manifest["oracle_readability"]["summary"],
        "facets": manifest["oracle_readability"]["facets"],
    }
    execution_episode = json.loads(
        (root / "execution_episode.json").read_text(encoding="utf-8")
    )
    execution_episode_hash = hashlib.sha256(
        (root / "execution_episode.json").read_bytes()
    ).hexdigest()
    assert execution_episode == manifest["execution_episode"]
    assert execution_episode["schema_version"] == "program-execution-episode-v1"
    assert execution_episode["checks"]["examples_binding"] == {
        "status": "passed",
        "examples_count": 1,
        "artifact_refs": ["examples.json", "eval_examples.py"],
    }
    assert (
        execution_episode["behavioral_evaluation"]["status"]
        == behavior_results["summary"]["status"]
    )
    assert execution_episode["behavioral_evaluation"]["result_artifact"] == (
        "behavior_results.json"
    )
    assert execution_episode["behavioral_evaluation"]["result_hash"] == behavior_hash
    assert (
        execution_episode["behavioral_evaluation"]["summary"]
        == behavior_results["summary"]
    )
    assert execution_episode["behavior_orchestration"]["status"] == "passed"
    assert execution_episode["behavior_orchestration"]["harness"] == "eval_behavior.py"
    assert execution_episode["behavior_orchestration"]["result_artifact"] == (
        "behavior_episode.json"
    )
    assert execution_episode["behavior_orchestration"]["result_hash"] == (
        behavior_episode_hash
    )
    assert (
        execution_episode["behavior_orchestration"]["summary"]
        == (behavior_episode["summary"])
    )
    assert execution_episode["oracle_readability"]["status"] == "captured"
    assert execution_episode["oracle_readability"]["oracle_invoked"] is False
    assert execution_episode["oracle_readability"]["result_artifact"] == (
        "oracle_evidence.json"
    )
    assert execution_episode["oracle_readability"]["result_hash"] == oracle_hash
    examples_hash = hashlib.sha256((root / "examples.json").read_bytes()).hexdigest()
    assert execution_episode["evaluation_sources"] == [
        {
            "kind": "examples",
            "source_kind": "inline_examples",
            "source_path": None,
            "input_artifact_path": "examples.json",
            "input_artifact_hash": examples_hash,
            "behavior_results_path": "behavior_results.json",
            "behavior_results_hash": behavior_hash,
            "status": behavior_results["summary"]["status"],
            "count": 1,
            "summary": behavior_results["summary"],
            "metric": "unspecified",
            "provider": behavior_results["provider"],
            "harness": {
                "path": "eval_examples.py",
                "status": "passed",
                "returncode": 0,
            },
        }
    ]
    assert execution_episode["behavior_evidence_summary"] == {
        "status": behavior_results["summary"]["status"],
        "source_count": 1,
        "executed_source_count": 1,
        "total": 1,
        "passed": behavior_results["summary"]["passed"],
        "failed": behavior_results["summary"]["failed"],
        "error": behavior_results["summary"]["error"],
        "degraded": behavior_results["summary"]["degraded"],
        "no_examples_source_count": 0,
        "status_counts": {behavior_results["summary"]["status"]: 1},
        "source_statuses": [
            {
                "kind": "examples",
                "source_kind": "inline_examples",
                "split": None,
                "status": behavior_results["summary"]["status"],
                "count": 1,
                "behavior_results_path": "behavior_results.json",
            }
        ],
    }
    assert execution_episode["runtime_conditions"] == {
        "runtime": {},
        "metric": "unspecified",
        "providers": {"examples": behavior_results["provider"]},
    }
    assert execution_episode["non_authority"] == {
        "evidence_only": True,
        "oracle_role": "not_invoked",
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "ranking_pruning_promotion": False,
        "promotion_authority": False,
        "oracle_authority": False,
        "winner_selection": False,
        "automatic_promotion": False,
        "governance_authority": False,
        "ak_mutation": False,
        "governance_mutation": False,
        "external_mutation": False,
        "external_authority_mutated": False,
    }
    assert manifest["oracle_readability"]["path"] == "oracle_evidence.json"
    assert manifest["oracle_readability"]["content_hash"] == oracle_hash
    assert manifest["oracle_readability"]["summary"]["content_hash"] == oracle_hash
    assert manifest["oracle_readability"]["facets"] == oracle_evidence["oracle_facets"]
    assert (
        manifest["execution_episode"]["behavior_status"]
        == behavior_results["summary"]["status"]
    )
    assert manifest["program_promotion_review"]["promotion_state"] == "not_promoted"
    assert (
        "no_model_jury_execution_episode"
        in manifest["program_promotion_review"]["blocking_conditions"]
    )
    assert (
        "no_promotion_adjudicator_decision"
        in manifest["program_promotion_review"]["blocking_conditions"]
    )
    assert (
        "no_behavioral_evaluation_episode"
        not in manifest["program_promotion_review"]["blocking_conditions"]
    )
    assert (
        manifest["program_promotion_review"]["non_authority"][
            "ranking_pruning_promotion"
        ]
        is False
    )
    evidence = manifest["receipt_bundle"]["evidence"]
    assert "examples_hash" in evidence
    assert evidence["behavior_results_hash"] == behavior_hash
    assert evidence["behavior_summary"] == behavior_results["summary"]
    assert evidence["behavior_results"] == behavior_results
    assert evidence["behavior_episode_hash"] == behavior_episode_hash
    assert evidence["behavior_episode_path"] == "behavior_episode.json"
    assert evidence["behavior_episode"] == behavior_episode
    assert evidence["execution_episode_hash"] == execution_episode_hash
    assert evidence["execution_episode_path"] == "execution_episode.json"
    assert evidence["oracle_evidence_hash"] == oracle_hash
    assert evidence["oracle_evidence_path"] == "oracle_evidence.json"
    assert (
        evidence["oracle_readability_summary"]
        == manifest["oracle_readability"]["summary"]
    )
    assert evidence["oracle_readability_facets"] == oracle_evidence["oracle_facets"]
    assert evidence["oracle_readability"] == {
        "path": "oracle_evidence.json",
        "content_hash": oracle_hash,
        "summary": manifest["oracle_readability"]["summary"],
        "facets": oracle_evidence["oracle_facets"],
    }
    assert evidence["surface_generation"]["execution_episode"] == "program-gen"
    assert evidence["surface_generation"]["behavior_harness"] == "program-gen"
    assert evidence["surface_generation"]["behavior_episode"] == "program-gen"
    assert evidence["surface_generation"]["oracle_evidence"] == "program-gen"
    assert (
        evidence["surface_hashes"]["execution_episode.json"] == execution_episode_hash
    )
    assert evidence["surface_hashes"]["oracle_evidence.json"] == oracle_hash
    assert evidence["examples"]["returncode"] == 0
    assert "examples.json" in evidence["generated_files"]
    assert "behavior_results.json" in evidence["generated_files"]
    assert "eval_behavior.py" in evidence["generated_files"]
    assert "behavior_episode.json" in evidence["generated_files"]
    assert "oracle_evidence.json" in evidence["generated_files"]
    assert "execution_episode.json" in evidence["generated_files"]

    receipt = json.loads((root / "manifest.json.meta.json").read_text(encoding="utf-8"))
    assert receipt["run_summary"]["behavior_results_hash"] == behavior_hash
    assert receipt["run_summary"]["behavior_summary"] == behavior_results["summary"]
    assert receipt["run_summary"]["behavior_episode_hash"] == behavior_episode_hash
    assert receipt["run_summary"]["behavior_episode_path"] == "behavior_episode.json"
    assert receipt["run_summary"]["execution_episode_hash"] == execution_episode_hash
    assert receipt["run_summary"]["execution_episode_path"] == "execution_episode.json"
    assert receipt["run_summary"]["oracle_evidence_hash"] == oracle_hash
    assert (
        receipt["run_summary"]["oracle_readability_summary"]
        == manifest["oracle_readability"]["summary"]
    )
    assert (
        receipt["run_summary"]["oracle_readability_facets"]
        == oracle_evidence["oracle_facets"]
    )
    assert (
        receipt["program_execution_episode_artifact"]
        == manifest["execution_episode_artifact"]
    )
    assert receipt["program_behavior_results"] == behavior_results
    assert receipt["program_behavior_episode"] == behavior_episode
    assert receipt["program_oracle_evidence"] == oracle_evidence
    assert receipt["program_oracle_readability"] == manifest["oracle_readability"]

    replay = check_run_receipt(root / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert replay["checks"]["program_manifest_json_object"] is True
    assert replay["checks"]["program_evidence_artifacts_declared"] is True
    assert replay["checks"]["program_execution_episode_exists"] is True
    assert replay["checks"]["program_execution_episode_hash_match"] is True
    assert replay["checks"]["program_behavior_results_exists"] is True
    assert replay["checks"]["program_behavior_results_hash_match"] is True
    assert replay["checks"]["program_oracle_evidence_exists"] is True
    assert replay["checks"]["program_oracle_evidence_hash_match"] is True
    assert replay["program_execution_episode_hash"] == execution_episode_hash
    assert replay["program_behavior_results_hash"] == behavior_hash
    assert replay["program_oracle_evidence_hash"] == oracle_hash
    assert replay["error_codes"] == []

    assert subprocess_calls
    assert all(
        "ak" not in [Path(part).name for part in command]
        and "oracle" not in [Path(part).name for part in command]
        for command in subprocess_calls
    )


def test_program_replay_detects_behavior_result_artifact_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayEvidenceProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        metric="exact_match",
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    replay = check_run_receipt(root / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert replay["checks"]["program_behavior_results_hash_match"] is True
    assert replay["checks"]["program_oracle_evidence_hash_match"] is True

    behavior_path = root / "behavior_results.json"
    behavior_payload = json.loads(behavior_path.read_text(encoding="utf-8"))
    behavior_payload["summary"]["status"] = "drifted"
    behavior_path.write_text(
        json.dumps(behavior_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    drift = check_run_receipt(root / "manifest.json.meta.json")

    assert drift["status"] == "failed"
    assert drift["checks"]["output_hash_match"] is True
    assert drift["checks"]["program_behavior_results_exists"] is True
    assert drift["checks"]["program_behavior_results_hash_match"] is False
    assert drift["checks"]["program_oracle_evidence_hash_match"] is True
    assert "program_evidence_hash_mismatch" in drift["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_hash_mismatch"
        and detail.get("check") == "program_behavior_results_hash_match"
        for detail in drift["error_details"]
    )


def test_program_replay_detects_oracle_evidence_artifact_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayOracleEvidenceProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        metric="exact_match",
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    oracle_path = root / "oracle_evidence.json"
    oracle_payload = json.loads(oracle_path.read_text(encoding="utf-8"))
    oracle_payload["oracle_text"] = "drifted oracle evidence"
    oracle_path.write_text(
        json.dumps(oracle_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    drift = check_run_receipt(root / "manifest.json.meta.json")

    assert drift["status"] == "failed"
    assert drift["checks"]["output_hash_match"] is True
    assert drift["checks"]["program_oracle_evidence_exists"] is True
    assert drift["checks"]["program_oracle_evidence_hash_match"] is False
    assert drift["checks"]["program_behavior_results_hash_match"] is True
    assert "program_evidence_hash_mismatch" in drift["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_hash_mismatch"
        and detail.get("check") == "program_oracle_evidence_hash_match"
        for detail in drift["error_details"]
    )


def test_program_replay_detects_execution_episode_artifact_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayExecutionEpisodeProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    episode_path = root / "execution_episode.json"
    episode_payload = json.loads(episode_path.read_text(encoding="utf-8"))
    episode_payload["status"] = "drifted"
    episode_path.write_text(
        json.dumps(episode_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    drift = check_run_receipt(root / "manifest.json.meta.json")

    assert drift["status"] == "failed"
    assert drift["checks"]["output_hash_match"] is True
    assert drift["checks"]["program_execution_episode_exists"] is True
    assert drift["checks"]["program_execution_episode_hash_match"] is False
    assert drift["checks"]["program_behavior_results_hash_match"] is True
    assert drift["checks"]["program_oracle_evidence_hash_match"] is True
    assert "program_evidence_hash_mismatch" in drift["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_hash_mismatch"
        and detail.get("check") == "program_execution_episode_hash_match"
        for detail in drift["error_details"]
    )


def test_program_replay_detects_missing_execution_episode_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayMissingExecutionEpisodeProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    (root / "execution_episode.json").unlink()

    missing = check_run_receipt(root / "manifest.json.meta.json")

    assert missing["status"] == "failed"
    assert missing["checks"]["output_hash_match"] is True
    assert missing["checks"]["program_execution_episode_exists"] is False
    assert missing["checks"]["program_behavior_results_exists"] is True
    assert "program_evidence_artifact_missing" in missing["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_artifact_missing"
        and detail.get("check") == "program_execution_episode_exists"
        for detail in missing["error_details"]
    )


def test_program_replay_detects_execution_episode_declaration_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayExecutionDeclarationMismatchProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["execution_episode_artifact"]["content_hash"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    mismatch = check_run_receipt(root / "manifest.json.meta.json")

    assert mismatch["status"] == "failed"
    assert mismatch["checks"]["output_hash_match"] is False
    assert mismatch["checks"]["program_execution_episode_exists"] is True
    assert (
        mismatch["checks"]["program_execution_episode_declaration_consistent"] is False
    )
    assert "program_evidence_declaration_mismatch" in mismatch["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_declaration_mismatch"
        and detail.get("check") == "program_execution_episode_declaration_consistent"
        for detail in mismatch["error_details"]
    )


def test_program_replay_detects_missing_program_evidence_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayMissingEvidenceProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    (root / "behavior_results.json").unlink()

    missing = check_run_receipt(root / "manifest.json.meta.json")

    assert missing["status"] == "failed"
    assert missing["checks"]["output_hash_match"] is True
    assert missing["checks"]["program_behavior_results_exists"] is False
    assert missing["checks"]["program_oracle_evidence_exists"] is True
    assert "program_evidence_artifact_missing" in missing["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_artifact_missing"
        and detail.get("check") == "program_behavior_results_exists"
        for detail in missing["error_details"]
    )


def test_program_replay_detects_program_evidence_declaration_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayDeclarationMismatchProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["execution_episode"]["behavior_results"]["content_hash"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    mismatch = check_run_receipt(root / "manifest.json.meta.json")

    assert mismatch["status"] == "failed"
    assert mismatch["checks"]["output_hash_match"] is False
    assert mismatch["checks"]["program_behavior_results_exists"] is True
    assert (
        mismatch["checks"]["program_behavior_results_declaration_consistent"] is False
    )
    assert "program_evidence_declaration_mismatch" in mismatch["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_declaration_mismatch"
        and detail.get("check") == "program_behavior_results_declaration_consistent"
        for detail in mismatch["error_details"]
    )


def test_program_gen_cli_materializes_explicit_perspectives_without_bound_jurors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent_path = tmp_path / "intent.yaml"
    intent_path.write_text(
        "\n".join(
            [
                "name: ReviewProgram",
                "objective: Create review-only transition artifacts from source text.",
                "inputs:",
                "  - source_text",
                "outputs:",
                "  - review_packet_json",
                "jury:",
                "  selection_model: perspective_balanced_explicit_pool",
                "  minimum_jurors: 3",
                "  perspectives:",
                "    - source_grounding",
                "    - authority_boundaries",
                "    - transition_artifact_quality",
            ]
        ),
        encoding="utf-8",
    )
    outdir = tmp_path / "candidate"

    result = runner.invoke(
        app,
        ["program-gen", "--intent", str(intent_path), "--outdir", str(outdir)],
    )

    assert result.exit_code == 0, result.output
    jury = json.loads((outdir / "jury.json").read_text(encoding="utf-8"))
    assert jury["perspectives"] == [
        "source_grounding",
        "authority_boundaries",
        "transition_artifact_quality",
    ]
    assert jury["pool"]["explicit_juror_count"] == 0
    assert jury["pool"]["explicit_perspective_count"] == 3
    assert jury["pool"]["explicit_perspective_juror_count"] == 3
    assert jury["jurors"][:3] == [
        {
            "id": "explicit_source_grounding",
            "model": None,
            "perspective": "source_grounding",
            "source": "explicit_perspective",
            "reason": "declared in jury.perspectives without a bound juror model",
        },
        {
            "id": "explicit_authority_boundaries",
            "model": None,
            "perspective": "authority_boundaries",
            "source": "explicit_perspective",
            "reason": "declared in jury.perspectives without a bound juror model",
        },
        {
            "id": "explicit_transition_artifact_quality",
            "model": None,
            "perspective": "transition_artifact_quality",
            "source": "explicit_perspective",
            "reason": "declared in jury.perspectives without a bound juror model",
        },
    ]
    selection = json.loads((outdir / "jury_selection.json").read_text(encoding="utf-8"))
    assert selection["selected_perspectives"] == [
        "source_grounding",
        "authority_boundaries",
        "transition_artifact_quality",
    ]
    assert [item["id"] for item in selection["selected_jurors"]] == [
        "explicit_source_grounding",
        "explicit_authority_boundaries",
        "explicit_transition_artifact_quality",
    ]
    rubric = json.loads((outdir / "jury_rubric.json").read_text(encoding="utf-8"))
    assert [item["criteria"] for item in rubric["juror_rubrics"]] == [
        ["source_refs_preserved", "source_identity_not_invented"],
        ["canonical_mutation_forbidden", "review_authority_explicit"],
        ["artifact_family_clarity", "proposal_reviewability"],
    ]


def test_program_gen_cli_carries_explicit_jury_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent_path = tmp_path / "intent.yaml"
    intent_path.write_text(
        "\n".join(
            [
                "name: JuryProgram",
                "objective: Answer with evidence.",
                "inputs:",
                "  - question",
                "outputs:",
                "  - answer",
                "jury:",
                "  selection_model: perspective_balanced_explicit_pool",
                "  minimum_jurors: 3",
                "  perspectives:",
                "    - correctness",
                "    - robustness",
                "    - clarity",
                "  jurors:",
                "    - id: correctness_local",
                "      model: local-small",
                "      perspective: correctness",
                "    - id: robustness_remote",
                "      model: remote-large",
                "      provider: pi-rpc",
                "      perspective: robustness",
                "    - id: clarity_local",
                "      model: local-medium",
                "      perspective: clarity",
                "promotion:",
                "  adjudicator:",
                "    kind: ai_council",
                "    id: safety_quality_council",
                "    members:",
                "      - safety_agent",
                "      - quality_agent",
            ]
        ),
        encoding="utf-8",
    )
    outdir = tmp_path / "candidate"

    result = runner.invoke(
        app,
        ["program-gen", "--intent", str(intent_path), "--outdir", str(outdir)],
    )

    assert result.exit_code == 0, result.output
    plan = json.loads((outdir / "plan.json").read_text(encoding="utf-8"))
    jury = plan["evaluation_strategy"]
    assert json.loads((outdir / "jury.json").read_text(encoding="utf-8")) == jury
    assert jury["schema_version"] == "program-jury-v1"
    assert jury["mode"] == "jury"
    assert jury["minimum_jurors"] == 3
    assert jury["perspectives"] == ["correctness", "robustness", "clarity"]
    assert jury["jurors"][0] == {
        "id": "correctness_local",
        "model": "local-small",
        "perspective": "correctness",
        "source": "explicit_user",
    }
    assert jury["jurors"][1] == {
        "id": "robustness_remote",
        "model": "remote-large",
        "perspective": "robustness",
        "provider": "pi-rpc",
        "source": "explicit_user",
    }
    assert jury["jurors"][2] == {
        "id": "clarity_local",
        "model": "local-medium",
        "perspective": "clarity",
        "source": "explicit_user",
    }
    selection = json.loads((outdir / "jury_selection.json").read_text(encoding="utf-8"))
    assert selection["schema_version"] == "program-jury-selection-v1"
    assert selection["status"] == "selected"
    assert selection["selected_juror_count"] == 3
    assert selection["selected_perspectives"] == [
        "correctness",
        "robustness",
        "clarity",
    ]
    assert [item["id"] for item in selection["selected_jurors"]] == [
        "correctness_local",
        "robustness_remote",
        "clarity_local",
    ]
    assert selection["authority"] == "selection_contract_only_non_authoritative"
    rubric = json.loads((outdir / "jury_rubric.json").read_text(encoding="utf-8"))
    assert rubric["schema_version"] == "program-jury-rubric-v1"
    assert rubric["selected_juror_count"] == 3
    assert [item["perspective"] for item in rubric["juror_rubrics"]] == [
        "correctness",
        "robustness",
        "clarity",
    ]
    assert rubric["juror_rubrics"][0]["criteria"] == [
        "answer_correctness",
        "objective_satisfaction",
    ]
    assert rubric["authority"] == "rubric_contract_only_non_authoritative"
    assert jury["status"] == "planned_not_executed"
    assert jury["authority"] == "advisory_evidence_only"
    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["intent"]["jury"]["minimum_jurors"] == 3
    receipt = json.loads(
        (outdir / "manifest.json.meta.json").read_text(encoding="utf-8")
    )
    promotion_review = json.loads(
        (outdir / "promotion_review.json").read_text(encoding="utf-8")
    )
    assert promotion_review["adjudicator"] == {
        "kind": "ai_council",
        "id": "safety_quality_council",
        "authority": "required_for_promotion",
        "status": "pending",
        "members": ["safety_agent", "quality_agent"],
    }
    assert promotion_review["decision"]["status"] == "pending"
    assert (
        "no_promotion_adjudicator_decision" in promotion_review["blocking_conditions"]
    )
    adjudication_request = json.loads(
        (outdir / "promotion_adjudication_request.json").read_text(encoding="utf-8")
    )
    assert adjudication_request["adjudicator"] == promotion_review["adjudicator"]
    decision_template = json.loads(
        (outdir / "promotion_decision_template.json").read_text(encoding="utf-8")
    )
    assert decision_template == {
        "schema_version": "program-promotion-decision-v1",
        "status": "pending",
        "outcome": None,
        "decided_by": None,
        "adjudicator_ref": "safety_quality_council",
        "adjudicator_kind": "ai_council",
        "rationale": None,
        "evidence_refs": [],
    }
    assert adjudication_request["decision_record_template"] == decision_template
    assert receipt["program_plan"]["evaluation_strategy"] == jury
    assert receipt["program_jury_selection"] == selection
    assert receipt["program_jury_rubric"] == rubric
    assert receipt["program_promotion_review"] == promotion_review
    assert receipt["program_promotion_adjudication_request"] == adjudication_request
    assert receipt["program_promotion_decision_template"] == decision_template


def test_program_gen_cli_preserves_external_authority_refs_without_adapter_coupling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    real_run = program_service.subprocess.run
    subprocess_calls: list[list[str]] = []

    def spy_run(
        command: list[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        command_text = [str(part) for part in command]
        command_names = [Path(part).name for part in command_text]
        assert "ak" not in command_names
        subprocess_calls.append(command_text)
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(program_service.subprocess, "run", spy_run)
    intent_path = tmp_path / "intent.yaml"
    intent_path.write_text(
        "\n".join(
            [
                "name: ExternalAuthorityProgram",
                "objective: Answer with portable local evidence only.",
                "inputs:",
                "  - question",
                "outputs:",
                "  - answer",
                "promotion:",
                "  adjudicator:",
                "    kind: human_operator",
                "    id: local_operator",
                "  external_authority:",
                "    refs:",
                "      - system: agent_kernel",
                "        ref: AK-1234",
                "        role: optional_authority_export_target",
            ]
        ),
        encoding="utf-8",
    )
    outdir = tmp_path / "candidate"

    result = runner.invoke(
        app,
        ["program-gen", "--intent", str(intent_path), "--outdir", str(outdir)],
    )

    assert result.exit_code == 0, result.output
    assert subprocess_calls
    assert all(
        "ak" not in [Path(part).name for part in command]
        for command in subprocess_calls
    )
    promotion_review = json.loads(
        (outdir / "promotion_review.json").read_text(encoding="utf-8")
    )
    assert promotion_review["adjudicator"] == {
        "kind": "human_operator",
        "id": "local_operator",
        "authority": "required_for_promotion",
        "status": "pending",
    }
    assert promotion_review["external_authority"] == {
        "status": "not_exported",
        "refs": [
            {
                "system": "agent_kernel",
                "ref": "AK-1234",
                "role": "optional_authority_export_target",
                "status": "not_exported",
                "source": "promotion.external_authority.refs",
            }
        ],
        "notes": [
            "External authority references are preserved as opaque metadata.",
            "DSPx core does not validate, call, or mutate external authority systems.",
        ],
    }
    assert "supported_adapters" not in promotion_review["external_authority"]
    assert promotion_review["promotion_state"] == "not_promoted"
    assert promotion_review["non_authority"]["automatic_promotion"] is False
    assert promotion_review["non_authority"]["ranking_pruning_promotion"] is False
    assert promotion_review["non_authority"]["external_authority_export"] is False
    adjudication_request = json.loads(
        (outdir / "promotion_adjudication_request.json").read_text(encoding="utf-8")
    )
    assert adjudication_request["adjudicator"] == promotion_review["adjudicator"]
    assert (
        adjudication_request["external_authority"]
        == promotion_review["external_authority"]
    )
    decision_template = json.loads(
        (outdir / "promotion_decision_template.json").read_text(encoding="utf-8")
    )
    assert decision_template == adjudication_request["decision_record_template"]
    assert decision_template["adjudicator_kind"] == "human_operator"
    assert decision_template["adjudicator_ref"] == "local_operator"
    assert decision_template["decided_by"] is None
    assert "external_authority" not in decision_template
    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["intent"]["promotion"]["external_authority"]["refs"][0]["ref"]
        == "AK-1234"
    )
    assert manifest["program_promotion_review"] == promotion_review
    assert manifest["program_promotion_adjudication_request"] == adjudication_request
    assert manifest["program_promotion_decision_template"] == decision_template
    receipt = json.loads(
        (outdir / "manifest.json.meta.json").read_text(encoding="utf-8")
    )
    assert receipt["program_promotion_review"] == promotion_review
    assert receipt["program_promotion_adjudication_request"] == adjudication_request
    assert receipt["program_promotion_decision_template"] == decision_template


def test_program_service_rejects_external_adapter_as_adjudicator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="WrongLayerProgram",
        objective="Preserve the adjudicator versus adapter boundary.",
        inputs=["question"],
        outputs=["answer"],
        promotion={"adjudicator": {"kind": "external_adapter", "id": "AK-1234"}},
    )

    with pytest.raises(ValueError, match="decision actor/process"):
        materialize_program_from_intent(intent, outdir=tmp_path / "wrong-layer")


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
