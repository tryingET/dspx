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
    assert manifest["candidate_assembly"]["surfaces"][7]["generator"] == "signature-gen"
    assert manifest["candidate_assembly"]["surfaces"][8]["generator"] == "module-gen"
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
    assert promotion_review["authority_bridge"]["status"] == "not_exported"
    assert promotion_review["authority_bridge"]["supported_adapters"] == [
        "agent_kernel"
    ]
    assert promotion_review["authority_bridge"]["external_refs"] == []
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
        adjudication_request["authority_bridge"] == promotion_review["authority_bridge"]
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
    assert manifest["execution_episode"]["status"] == "passed"
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
    assert payload["candidate_assembly"]["surfaces"][7]["path"] == "signature.py"
    assert (outdir / "plan.json").exists()
    assert (outdir / "jury.json").exists()
    assert (outdir / "jury_selection.json").exists()
    assert (outdir / "jury_rubric.json").exists()
    assert (outdir / "promotion_review.json").exists()
    assert (outdir / "promotion_adjudication_request.json").exists()
    assert (outdir / "promotion_decision_template.json").exists()
    assert (outdir / "signature.py").exists()
    assert (outdir / "module.py").exists()
    assert (outdir / "program.py").exists()
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
        "decided_by": "safety_quality_council",
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


def test_program_gen_cli_carries_external_adapter_authority_bridge(
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
                "    kind: external_adapter",
                "    adapter: agent_kernel",
                "    id: AK-1234",
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
        "kind": "external_adapter",
        "id": "AK-1234",
        "authority": "required_for_promotion",
        "status": "pending",
        "adapter": "agent_kernel",
    }
    assert promotion_review["authority_bridge"] == {
        "status": "not_exported",
        "supported_adapters": ["agent_kernel"],
        "external_refs": [
            {
                "adapter": "agent_kernel",
                "id": "AK-1234",
                "status": "not_exported",
                "source": "promotion.adjudicator",
            }
        ],
        "notes": [
            "DSPx core does not call external authority adapters during materialization.",
            "Agent Kernel integration is optional and must be invoked explicitly.",
        ],
    }
    assert promotion_review["promotion_state"] == "not_promoted"
    assert promotion_review["non_authority"]["automatic_promotion"] is False
    assert promotion_review["non_authority"]["ranking_pruning_promotion"] is False
    assert promotion_review["non_authority"]["external_authority_export"] is False
    adjudication_request = json.loads(
        (outdir / "promotion_adjudication_request.json").read_text(encoding="utf-8")
    )
    assert adjudication_request["adjudicator"] == promotion_review["adjudicator"]
    assert (
        adjudication_request["authority_bridge"] == promotion_review["authority_bridge"]
    )
    decision_template = json.loads(
        (outdir / "promotion_decision_template.json").read_text(encoding="utf-8")
    )
    assert decision_template == adjudication_request["decision_record_template"]
    assert decision_template["adjudicator_kind"] == "external_adapter"
    assert decision_template["decided_by"] == "AK-1234"
    assert decision_template["external_authority"] == {
        "adapter": "agent_kernel",
        "id": "AK-1234",
        "status": "not_exported",
    }
    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["intent"]["promotion"]["adjudicator"]["kind"] == "external_adapter"
    assert manifest["program_promotion_review"] == promotion_review
    assert manifest["program_promotion_adjudication_request"] == adjudication_request
    assert manifest["program_promotion_decision_template"] == decision_template
    receipt = json.loads(
        (outdir / "manifest.json.meta.json").read_text(encoding="utf-8")
    )
    assert receipt["program_promotion_review"] == promotion_review
    assert receipt["program_promotion_adjudication_request"] == adjudication_request
    assert receipt["program_promotion_decision_template"] == decision_template


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
