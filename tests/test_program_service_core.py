# summary: "Tests core program candidate assembly, generated surfaces, receipts, and intent validation."
# read_when:
#   - "Changing program materialization, candidate manifests, generated surfaces, or replay metadata."

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

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


def test_codex_stream_compatibility_retry_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_PROGRAM_CODEX_STREAM_COMPAT_RETRY", "0")
    assert not program_service._codex_stream_compatibility_retry_enabled()


def test_codex_stream_compatibility_retry_preserves_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DSPX_PROGRAM_CODEX_STREAM_COMPAT_RETRY", raising=False)
    assert program_service._codex_stream_compatibility_retry_enabled()


@pytest.mark.slow
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
    assert (root / "intent_normalization.json").exists()
    assert (root / "program_runtime_outcomes.json").exists()
    assert (root / "program_runtime_traces.json").exists()
    assert (root / "program_tool_contracts.json").exists()
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
    assert (
        manifest["intent_normalization"]["schema_version"]
        == "program-intent-normalization-v1"
    )
    assert (
        manifest["intent_normalization"]["materialization_gate"]["status"]
        == "emitted_before_candidate_materialization"
    )
    assert manifest["pre_materialization_review"] == {
        "status": "emitted_before_candidate_materialization",
        "path": "intent_normalization.json",
        "content_hash": manifest["request"]["intent_normalization_hash"],
        "assumption_count": len(manifest["intent_normalization"]["assumptions"]),
        "missing_evidence_count": len(
            manifest["intent_normalization"]["missing_evidence"]
        ),
        "generation_risk_count": len(
            manifest["intent_normalization"]["generation_risks"]
        ),
        "topology_candidate_count": len(
            manifest["intent_normalization"]["generation_assumptions_preview"][
                "topology_candidates"
            ]
        ),
        "capability_boundary_keys": [
            "custom_modules",
            "program_of_thought",
            "react",
            "react_v2",
            "retrievers",
            "tools",
        ],
        "blocks_materialization": False,
        "non_authority": manifest["intent_normalization"]["non_authority"],
    }
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
        "runtime_outcomes",
        "runtime_traces",
        "tool_contracts",
        "execution_episode",
        "capability_registry",
        "generated_module_policy",
        "intent_normalization",
        "signature",
        "module",
        "program",
        "direct_runner",
        "eval_harness",
        "jury_harness",
        "promotion_harness",
    ]
    surfaces_by_kind = {
        surface["kind"]: surface
        for surface in manifest["candidate_assembly"]["surfaces"]
    }
    assert surfaces_by_kind["jury"]["path"] == "jury.json"
    assert surfaces_by_kind["jury_selection"]["path"] == "jury_selection.json"
    assert surfaces_by_kind["jury_rubric"]["path"] == "jury_rubric.json"
    assert surfaces_by_kind["promotion_review"]["path"] == "promotion_review.json"
    assert surfaces_by_kind["promotion_adjudication_request"]["path"] == (
        "promotion_adjudication_request.json"
    )
    assert surfaces_by_kind["promotion_decision_template"]["path"] == (
        "promotion_decision_template.json"
    )
    assert surfaces_by_kind["module_surfaces"]["path"] == "module_surfaces.json"
    assert surfaces_by_kind["runtime_outcomes"]["path"] == (
        "program_runtime_outcomes.json"
    )
    assert surfaces_by_kind["runtime_traces"]["path"] == "program_runtime_traces.json"
    assert surfaces_by_kind["runtime_traces"]["status"] == "no_runtime_traces_captured"
    assert surfaces_by_kind["tool_contracts"]["path"] == "program_tool_contracts.json"
    assert surfaces_by_kind["execution_episode"]["path"] == "execution_episode.json"
    assert surfaces_by_kind["capability_registry"]["path"] == (
        "program_capability_registry.json"
    )
    assert surfaces_by_kind["generated_module_policy"]["path"] == (
        "generated_module_policy.json"
    )
    assert surfaces_by_kind["intent_normalization"]["path"] == (
        "intent_normalization.json"
    )
    assert surfaces_by_kind["signature"]["generator"] == "signature-gen"
    assert surfaces_by_kind["module"]["generator"] == "module-gen"
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
    runtime_outcomes_hash = hashlib.sha256(
        (root / "program_runtime_outcomes.json").read_bytes()
    ).hexdigest()
    tool_contracts_hash = hashlib.sha256(
        (root / "program_tool_contracts.json").read_bytes()
    ).hexdigest()
    execution_episode_hash = hashlib.sha256(
        (root / "execution_episode.json").read_bytes()
    ).hexdigest()
    generated_module_policy_hash = hashlib.sha256(
        (root / "generated_module_policy.json").read_bytes()
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
    assert evidence["runtime_outcomes_hash"] == runtime_outcomes_hash
    assert evidence["runtime_outcomes_path"] == "program_runtime_outcomes.json"
    assert evidence["tool_contracts_hash"] == tool_contracts_hash
    assert evidence["tool_contracts_path"] == "program_tool_contracts.json"
    assert evidence["generated_module_policy_hash"] == generated_module_policy_hash
    assert evidence["generated_module_policy_path"] == "generated_module_policy.json"
    assert evidence["execution_episode_hash"] == execution_episode_hash
    assert evidence["execution_episode_path"] == "execution_episode.json"
    assert evidence["surface_hashes"]["module_surfaces.json"] == module_surfaces_hash
    assert (
        evidence["surface_hashes"]["program_runtime_outcomes.json"]
        == runtime_outcomes_hash
    )
    assert (
        evidence["surface_hashes"]["program_tool_contracts.json"] == tool_contracts_hash
    )
    assert (
        evidence["surface_hashes"]["execution_episode.json"] == execution_episode_hash
    )
    assert manifest["request"]["module_surfaces_hash"] == module_surfaces_hash
    assert manifest["request"]["runtime_outcomes_hash"] == runtime_outcomes_hash
    assert manifest["request"]["tool_contracts_hash"] == tool_contracts_hash
    assert (
        manifest["request"]["generated_module_policy_hash"]
        == generated_module_policy_hash
    )
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
    assert receipt["run_summary"]["runtime_outcomes_hash"] == runtime_outcomes_hash
    assert (
        receipt["run_summary"]["runtime_outcomes_path"]
        == "program_runtime_outcomes.json"
    )
    assert receipt["run_summary"]["tool_contracts_hash"] == tool_contracts_hash
    assert (
        receipt["run_summary"]["tool_contracts_path"] == "program_tool_contracts.json"
    )
    assert (
        receipt["run_summary"]["generated_module_policy_hash"]
        == generated_module_policy_hash
    )
    assert (
        receipt["run_summary"]["generated_module_policy_path"]
        == "generated_module_policy.json"
    )
    assert receipt["run_summary"]["execution_episode_hash"] == execution_episode_hash
    assert receipt["run_summary"]["execution_episode_path"] == "execution_episode.json"
    assert receipt["program_module_surfaces"] == manifest["program_module_surfaces"]
    assert (
        receipt["program_module_surfaces_artifact"]
        == manifest["module_surfaces_artifact"]
    )
    assert receipt["program_runtime_outcomes"] == manifest["program_runtime_outcomes"]
    assert (
        receipt["program_runtime_outcomes_artifact"]
        == manifest["runtime_outcomes_artifact"]
    )
    assert receipt["program_tool_contracts"] == manifest["program_tool_contracts"]
    assert (
        receipt["program_tool_contracts_artifact"]
        == manifest["tool_contracts_artifact"]
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
    assert evidence["surface_generation"]["runtime_outcomes"] == "program-gen"
    assert evidence["surface_generation"]["tool_contracts"] == "program-gen"
    assert evidence["surface_generation"]["capability_registry"] == "program-gen"
    assert evidence["surface_generation"]["generated_module_policy"] == "program-gen"
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
    assert "program_runtime_outcomes.json" in evidence["surface_hashes"]
    assert "program_tool_contracts.json" in evidence["surface_hashes"]
    assert "program_capability_registry.json" in evidence["surface_hashes"]
    assert "generated_module_policy.json" in evidence["surface_hashes"]
    assert "execution_episode.json" in evidence["surface_hashes"]
    assert "eval_jury.py" in evidence["surface_hashes"]
    assert "eval_promotion.py" in evidence["surface_hashes"]
    assert "signature.py" in evidence["surface_hashes"]

    replay = check_run_receipt(root / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert replay["checks"]["output_hash_match"] is True
    assert replay["checks"]["cache_key_recomputes"] is True
    assert replay["checks"]["cache_code_hash_matches_receipt"] is True
    assert replay["checks"]["program_runtime_outcomes_semantic_valid"] is True
    assert replay["checks"]["program_tool_contracts_semantic_valid"] is True


@pytest.mark.slow
def test_program_service_refuses_non_empty_outdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="AnswerQuestion",
        objective="Answer a question from context.",
        inputs=["question"],
        outputs=["answer"],
    )
    outdir = tmp_path / "program"
    outdir.mkdir()
    (outdir / "program.py").write_text("# existing\n")

    with pytest.raises(ValueError, match="program-gen outdir already exists"):
        materialize_program_from_intent(intent, outdir=outdir)

    assert (outdir / "program.py").read_text() == "# existing\n"
    assert not (outdir / "manifest.json").exists()


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


@pytest.mark.slow
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


@pytest.mark.slow
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
