# summary: "Tests program-gen CLI materialization and example-backed behavioral evidence artifacts."
# read_when:
#   - "Changing program-gen CLI output, example binding, behavior evidence, or receipt contents."

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services import program_service
from dspx.services.program_service import ProgramIntent, materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt

runner = CliRunner()


@pytest.mark.slow
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
        payload["candidate_assembly"]["surfaces"][8]["path"]
        == "program_runtime_outcomes.json"
    )
    assert (
        payload["candidate_assembly"]["surfaces"][9]["path"]
        == "program_runtime_traces.json"
    )
    assert (
        payload["candidate_assembly"]["surfaces"][10]["path"]
        == "program_tool_contracts.json"
    )
    assert (
        payload["candidate_assembly"]["surfaces"][11]["path"]
        == "execution_episode.json"
    )
    assert (
        payload["candidate_assembly"]["surfaces"][12]["path"]
        == "program_capability_registry.json"
    )
    assert (
        payload["candidate_assembly"]["surfaces"][13]["path"]
        == "generated_module_policy.json"
    )
    assert (
        payload["candidate_assembly"]["surfaces"][14]["path"]
        == "intent_normalization.json"
    )
    assert payload["candidate_assembly"]["surfaces"][15]["path"] == "signature.py"
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
    assert (outdir / "intent_normalization.json").exists()
    assert (outdir / "signature.py").exists()
    assert (outdir / "module.py").exists()
    assert (outdir / "program.py").exists()
    direct_run_text = (outdir / "direct_run.py").read_text(encoding="utf-8")
    compile(direct_run_text, str(outdir / "direct_run.py"), "exec")
    assert "--inputs-root" in direct_run_text
    assert "--config" in direct_run_text
    assert "--preflight" in direct_run_text
    assert "generated-dspy-direct-run-preflight-v1" in direct_run_text
    assert "model_call_performed': False" in direct_run_text
    assert "direct_batch_receipt.json" in direct_run_text
    assert "ThreadPoolExecutor" in direct_run_text
    assert "def _apply_runtime_config_env(data: object) -> None:" in direct_run_text
    assert "_set_env_from_config(provider, 'name', 'DSPX_PROVIDER')" in direct_run_text
    assert (
        "_set_env_from_config(lm_auth, 'model', 'DSPX_LM_AUTH_MODEL')"
        in direct_run_text
    )
    assert (
        "configure_observability(run_name='program-runtime', run_kind='program-runtime')"
        in direct_run_text
    )
    assert "def _write_direct_run_receipt(" in direct_run_text
    assert "def _redact_url(value: object) -> str | None:" in direct_run_text
    assert (
        "'tracking_uri': _redact_url(os.getenv('MLFLOW_TRACKING_URI') or None)"
        in direct_run_text
    )
    assert (
        "'MLFLOW_TRACKING_URI': _redact_url(os.getenv('MLFLOW_TRACKING_URI') or None)"
        in direct_run_text
    )
    assert "status='failed'" in direct_run_text
    assert (outdir / "direct_run.py").exists()
    assert (outdir / "eval_jury.py").exists()
    assert (outdir / "eval_promotion.py").exists()
    assert (outdir / "manifest.json.meta.json").exists()


@pytest.mark.slow
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


@pytest.mark.slow
def test_program_service_binds_examples_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    real_run = program_service.subprocess.run
    subprocess_calls: list[list[str]] = []

    def spy_run(
        command: list[str], *args: Any, **kwargs: Any
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
            assert source_root in str(
                cast(dict[str, object], env).get("PYTHONPATH", "")
            )
        subprocess_calls.append(command_text)
        return cast(
            subprocess.CompletedProcess[str], real_run(command, *args, **kwargs)
        )

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
    eval_behavior_source = (root / "eval_behavior.py").read_text(encoding="utf-8")
    assert "DSPX_PROGRAM_HARNESS_TIMEOUT" in eval_behavior_source
    assert "timeout=_harness_timeout_seconds()" in eval_behavior_source
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
    runtime_traces_hash = hashlib.sha256(
        (root / "program_runtime_traces.json").read_bytes()
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
    assert (
        behavior_episode["sources"][0]["quality_evaluation"]
        == behavior_results["quality_evaluation"]
    )
    assert (
        behavior_episode["quality_evaluation"] == behavior_results["quality_evaluation"]
    )
    assert behavior_episode["quality_evaluation"]["quality_approved"] is False
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
    assert oracle_evidence["runtime_traces"]["path"] == "program_runtime_traces.json"
    assert oracle_evidence["runtime_traces"]["content_hash"] == runtime_traces_hash
    assert oracle_evidence["runtime_traces"]["module_call_count"] >= 1
    assert "module_calls" not in oracle_evidence["runtime_traces"]
    assert "final_outputs" not in oracle_evidence["runtime_traces"]
    assert oracle_evidence["runtime_traces"]["coverage"][
        "source_record_coverage_status"
    ] in {"complete", "partial", "not_applicable_no_records"}
    assert "runtime_traces.status=" in oracle_evidence["oracle_text"]
    assert {
        "kind": "behavior_results",
        "path": "behavior_results.json",
        "content_hash": behavior_hash,
        "source_kind": "inline_examples",
    } in oracle_evidence["source_artifacts"]
    assert {
        "kind": "runtime_traces",
        "path": "program_runtime_traces.json",
        "content_hash": runtime_traces_hash,
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
    assert evidence["surface_generation"]["capability_registry"] == "program-gen"
    assert evidence["surface_generation"]["generated_module_policy"] == "program-gen"
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
    assert "program_capability_registry.json" in evidence["generated_files"]
    assert "generated_module_policy.json" in evidence["generated_files"]
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
