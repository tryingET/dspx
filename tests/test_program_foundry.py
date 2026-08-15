# summary: "Tests accepted-envelope foundry orchestration, terminal-stage reuse, locking, confinement, and fail-closed partial handling."

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine
from dspx.provider_contract import (
    EffectDisposition,
    ProviderRequest,
    ProviderResult,
)
import dspx.services.program_foundry as foundry
from dspx.services.program_foundry_io import foundry_lock
from dspx.services.program_quality_contract import (
    set_quality_proposal_decision,
    write_accepted_program_intent,
    write_quality_proposal,
)
from dspx.services.program_quality_conversation import propose_program_quality_criteria


class _QualityLM:
    model = "openai/gpt-5.6-sol"

    def invoke(self, request: ProviderRequest) -> ProviderResult:
        payload = {
            "metric": "concept_coverage",
            "quality_criteria": [
                {
                    "id": "helpful_response",
                    "output_field": "response",
                    "evaluator": "concept_coverage",
                    "required_concept_groups": [["resolution", "next step"]],
                    "forbidden_concepts": [],
                    "min_score": 1.0,
                }
            ],
            "rationale": "Require a useful resolution or next step.",
            "clarifying_questions": [],
        }
        return ProviderResult(
            text=json.dumps(payload),
            model=self.model,
            effect_disposition=EffectDisposition.COMPLETED_SUCCESS,
        )


def _quality_artifacts(
    intent_path: Path,
    proposal_path: Path,
    *,
    accepted: bool = True,
) -> None:
    proposal = propose_program_quality_criteria(
        "Route a support ticket and draft a helpful response with rationale.",
        lm=_QualityLM(),
    )
    if accepted:
        proposal = set_quality_proposal_decision(proposal, decision="accept")
        write_quality_proposal(proposal, proposal_path)
        write_accepted_program_intent(proposal, intent_path)
    else:
        write_quality_proposal(proposal, proposal_path)
        intent_path.write_text(
            json.dumps(proposal["candidate_intent"], sort_keys=True),
            encoding="utf-8",
        )


def _env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv(
        "DSPX_REPLAY_FIXTURE_JSON",
        '{"response":"Provide a resolution and next step"}',
    )
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _inputs(path: Path, value: str = "Server unavailable") -> None:
    path.write_text(json.dumps({"inputs": {"ticket_text": value}}), encoding="utf-8")


def _semantic_payload(*, indeterminate: bool = False) -> dict:
    return {
        "schema_version": "program-runtime-oracle-semantic-v1",
        "status": "degraded" if indeterminate else "ok",
        "request_sha256": "b" * 64,
        "source_binding": {"runtime_episode": {"sha256": "c" * 64}},
        "semantic_result": {
            "execution_status": "effect_indeterminate"
            if indeterminate
            else "replayed_fixture",
            "preferred_model": "codex/gpt-5.6-luna",
            "executed_model": None,
        },
        "effect": {
            "semantic_backend_invoked": None if indeterminate else True,
            "effect_disposition": "indeterminate"
            if indeterminate
            else "terminal_result_recorded",
            "live_call_succeeded": None if indeterminate else False,
        },
        "non_authority": {
            "promotion_authority": False,
            "activation_authority": False,
        },
    }


def _semantic_stub(**kwargs):
    out = Path(kwargs["out_path"])
    payload = _semantic_payload()
    if not out.exists():
        out.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _successful_semantic_stub(**kwargs):
    episode = Path(kwargs["runtime_episode_path"]).resolve()
    root = episode.parent
    out = Path(kwargs["out_path"])
    request_sha256 = "d" * 64
    source_binding = {
        name: {"path": str(path.resolve()), "sha256": _sha256(path)}
        for name, path in {
            "runtime_episode": episode,
            "behavior_results": root / "behavior_results.json",
            "oracle_evidence": root / "oracle_evidence.json",
            "runtime_receipt": root / "runtime_episode.json.meta.json",
        }.items()
    }
    payload = {
        "schema_version": "program-runtime-oracle-semantic-v1",
        "status": "ok",
        "request_sha256": request_sha256,
        "source_binding": source_binding,
        "semantic_result": {
            "schema_version": "dspx-program-oracle-semantic-result-v1",
            "authority": "local_empirical_advisory_only",
            "request_sha256": request_sha256,
            "backend_kind": "fixture-replay",
            "preferred_model": "codex/gpt-5.6-luna",
            "configured_provider": None,
            "configured_model": None,
            "executed_provider": None,
            "executed_model": None,
            "execution_status": "replayed_fixture",
            "live_call_succeeded": False,
            "fixture_sha256": "e" * 64,
            "error": None,
            "analysis": {
                "observations": ["The response omitted an explicit next step."],
                "failure_attractors": ["Generic resolution language."],
                "quality_contract_violations": ["next-step coverage failed"],
                "hypotheses": ["A stronger instruction may improve coverage."],
                "recommended_experiments": [
                    "Use GEPA to test an instruction that requires one explicit next step."
                ],
                "evidence_refs": ["runtime_episode"],
                "confidence": 0.8,
            },
        },
        "effect": {
            "semantic_backend_invoked": True,
            "effect_disposition": "terminal_result_recorded",
            "live_call_succeeded": False,
        },
        "non_authority": {
            "promotion_authority": False,
            "activation_authority": False,
        },
    }
    if not out.exists():
        out.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _run(*, root: Path, intent: Path, proposal: Path, inputs: Path) -> dict:
    return foundry.run_program_foundry(
        intent_path=intent,
        quality_proposal_path=proposal,
        inputs_path=inputs,
        outdir=root,
        skip_oracle_index=True,
    )


def test_foundry_runs_and_reuses_terminal_candidate_runtime_and_semantics(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    intent = tmp_path / "accepted-intent.json"
    proposal = tmp_path / "accepted-proposal.json"
    inputs = tmp_path / "inputs.json"
    root = tmp_path / "foundry"
    _quality_artifacts(intent, proposal)
    _inputs(inputs)
    monkeypatch.setattr(foundry, "run_program_runtime_oracle_semantics", _semantic_stub)

    first = _run(root=root, intent=intent, proposal=proposal, inputs=inputs)
    second = _run(root=root, intent=intent, proposal=proposal, inputs=inputs)

    assert first["status"] == "behavior_failed"
    assert first["stages"]["candidate"]["disposition"] == "created"
    assert first["stages"]["runtime"]["disposition"] == "created"
    assert first["stages"]["oracle_semantic"]["disposition"] == "created"
    assert second["status"] == "behavior_failed"
    assert second["stages"]["candidate"]["disposition"] == "reused"
    assert second["stages"]["runtime"]["disposition"] == "reused"
    assert second["stages"]["oracle_semantic"]["disposition"] == "reused"
    assert second["stages"]["oracle_semantic"]["contract_valid"] is True
    assert (
        second["bindings"]["candidate_manifest_sha256"]
        == first["bindings"]["candidate_manifest_sha256"]
    )
    assert (
        second["bindings"]["runtime_episode_id"]
        == first["bindings"]["runtime_episode_id"]
    )
    assert (root / "foundry.json").exists()
    semantic_path = root / "runtime" / "program_oracle_semantic.json"
    semantic_path.unlink()
    external_semantic = tmp_path / "external-semantic.json"
    external_semantic.write_text("{}", encoding="utf-8")
    semantic_path.symlink_to(external_semantic)
    with pytest.raises(foundry.ProgramFoundryError, match="must not be a symlink"):
        _run(root=root, intent=intent, proposal=proposal, inputs=inputs)


def test_foundry_validates_complete_accepted_envelope_and_candidate_binding(
    tmp_path: Path,
) -> None:
    intent = tmp_path / "intent.json"
    proposal = tmp_path / "proposal.json"
    inputs = tmp_path / "inputs.json"
    root = tmp_path / "foundry"
    _quality_artifacts(intent, proposal, accepted=False)
    _inputs(inputs)

    with pytest.raises(foundry.ProgramFoundryError, match="acceptance is invalid"):
        _run(root=root, intent=intent, proposal=proposal, inputs=inputs)
    assert not (root / "candidate").exists()

    intent.unlink()
    proposal.unlink()
    _quality_artifacts(intent, proposal)
    intent_payload = json.loads(intent.read_text(encoding="utf-8"))
    intent_payload["objective"] = "Tampered objective"
    intent.write_text(json.dumps(intent_payload), encoding="utf-8")
    with pytest.raises(foundry.ProgramFoundryError, match="does not match"):
        _run(root=root, intent=intent, proposal=proposal, inputs=inputs)
    assert not (root / "candidate").exists()


def test_foundry_never_replays_partial_candidate_stage(
    tmp_path: Path, monkeypatch
) -> None:
    intent = tmp_path / "intent.json"
    proposal = tmp_path / "proposal.json"
    inputs = tmp_path / "inputs.json"
    root = tmp_path / "foundry"
    _quality_artifacts(intent, proposal)
    _inputs(inputs)
    (root / "candidate").mkdir(parents=True)
    monkeypatch.setattr(
        foundry,
        "run_generate_from_intent_path",
        lambda *args, **kwargs: pytest.fail("partial candidate must not regenerate"),
    )

    with pytest.raises(foundry.ProgramFoundryError, match="candidate stage is partial"):
        _run(root=root, intent=intent, proposal=proposal, inputs=inputs)


def test_foundry_never_replays_partial_runtime_stage(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    intent = tmp_path / "intent.json"
    proposal = tmp_path / "proposal.json"
    inputs = tmp_path / "inputs.json"
    root = tmp_path / "foundry"
    _quality_artifacts(intent, proposal)
    _inputs(inputs)
    foundry.run_generate_from_intent_path(intent, outdir=root / "candidate")
    (root / "runtime").mkdir()
    monkeypatch.setattr(
        foundry,
        "run_program_runtime_episode",
        lambda **kwargs: pytest.fail("partial runtime must not execute again"),
    )

    with pytest.raises(foundry.ProgramFoundryError, match="runtime stage is partial"):
        _run(root=root, intent=intent, proposal=proposal, inputs=inputs)


def test_foundry_input_drift_never_replays_terminal_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    intent = tmp_path / "intent.json"
    proposal = tmp_path / "proposal.json"
    inputs = tmp_path / "inputs.json"
    root = tmp_path / "foundry"
    _quality_artifacts(intent, proposal)
    _inputs(inputs, "Original")
    monkeypatch.setattr(foundry, "run_program_runtime_oracle_semantics", _semantic_stub)
    _run(root=root, intent=intent, proposal=proposal, inputs=inputs)
    _inputs(inputs, "Changed")
    monkeypatch.setattr(
        foundry,
        "run_program_runtime_episode",
        lambda **kwargs: pytest.fail("terminal runtime must not be replayed"),
    )

    with pytest.raises(foundry.ProgramFoundryError, match="runtime inputs drifted"):
        _run(root=root, intent=intent, proposal=proposal, inputs=inputs)


def test_foundry_classifies_indeterminate_semantics_and_preserves_effect(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    intent = tmp_path / "intent.json"
    proposal = tmp_path / "proposal.json"
    inputs = tmp_path / "inputs.json"
    root = tmp_path / "foundry"
    _quality_artifacts(intent, proposal)
    _inputs(inputs)
    monkeypatch.setattr(
        foundry,
        "run_program_runtime_oracle_semantics",
        lambda **kwargs: _semantic_payload(indeterminate=True),
    )

    payload = _run(root=root, intent=intent, proposal=proposal, inputs=inputs)

    semantic = payload["stages"]["oracle_semantic"]
    assert payload["status"] == "blocked_indeterminate"
    assert semantic["contract_valid"] is True
    assert semantic["effect"]["effect_disposition"] == "indeterminate"
    assert semantic["non_authority"]["promotion_authority"] is False


def test_foundry_semantic_swap_race_is_rejected_by_nofollow_callee(
    tmp_path: Path, monkeypatch
) -> None:
    from dspx.services.program_runtime_oracle_semantic import (
        ProgramRuntimeOracleSemanticError,
        run_program_runtime_oracle_semantics as real_semantic,
    )

    _env(tmp_path, monkeypatch)
    intent = tmp_path / "intent.json"
    proposal = tmp_path / "proposal.json"
    inputs = tmp_path / "inputs.json"
    root = tmp_path / "foundry"
    external = tmp_path / "external-semantic.json"
    _quality_artifacts(intent, proposal)
    _inputs(inputs)
    external.write_text("DO_NOT_TOUCH", encoding="utf-8")

    def swap_then_call(**kwargs):
        Path(kwargs["out_path"]).symlink_to(external)
        return real_semantic(**kwargs)

    monkeypatch.setattr(foundry, "run_program_runtime_oracle_semantics", swap_then_call)

    with pytest.raises(ProgramRuntimeOracleSemanticError, match="non-symlink"):
        _run(root=root, intent=intent, proposal=proposal, inputs=inputs)
    assert external.read_text(encoding="utf-8") == "DO_NOT_TOUCH"


def test_foundry_lock_and_symlink_confinement_fail_before_effects(
    tmp_path: Path, monkeypatch
) -> None:
    intent = tmp_path / "intent.json"
    proposal = tmp_path / "proposal.json"
    inputs = tmp_path / "inputs.json"
    root = tmp_path / "foundry"
    _quality_artifacts(intent, proposal)
    _inputs(inputs)
    monkeypatch.setattr(
        foundry,
        "run_generate_from_intent_path",
        lambda *args, **kwargs: pytest.fail("confinement failure must precede effects"),
    )

    with foundry_lock(root):
        with pytest.raises(ValueError, match="another foundry invocation"):
            _run(root=root, intent=intent, proposal=proposal, inputs=inputs)
    lock_path = root / ".foundry.lock"
    lock_path.unlink()
    external_lock = tmp_path / "external-lock"
    external_lock.write_text("", encoding="utf-8")
    lock_path.symlink_to(external_lock)
    with pytest.raises(ValueError, match="lock path must not be a symlink"):
        _run(root=root, intent=intent, proposal=proposal, inputs=inputs)
    lock_path.unlink()

    external = tmp_path / "external"
    external.mkdir()
    (root / "candidate").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="must not be a symlink"):
        _run(root=root, intent=intent, proposal=proposal, inputs=inputs)


def test_foundry_writes_and_reuses_bounded_oracle_to_gepa_proposal(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    intent = tmp_path / "intent.json"
    proposal = tmp_path / "quality-proposal.json"
    inputs = tmp_path / "inputs.json"
    root = tmp_path / "foundry"
    _quality_artifacts(intent, proposal)
    _inputs(inputs)
    monkeypatch.setattr(
        foundry, "run_program_runtime_oracle_semantics", _successful_semantic_stub
    )

    first = foundry.run_program_foundry(
        intent_path=intent,
        quality_proposal_path=proposal,
        inputs_path=inputs,
        outdir=root,
        skip_oracle_index=True,
        gepa_recommendation_index=0,
        gepa_max_metric_calls=3,
    )
    second = foundry.run_program_foundry(
        intent_path=intent,
        quality_proposal_path=proposal,
        inputs_path=inputs,
        outdir=root,
        skip_oracle_index=True,
        gepa_recommendation_index=0,
        gepa_max_metric_calls=3,
    )

    stage = first["stages"]["gepa_experiment_proposal"]
    assert stage["status"] == "proposal_ready_for_review"
    assert stage["disposition"] == "created"
    assert second["stages"]["gepa_experiment_proposal"]["disposition"] == "reused"
    sidecar = json.loads(
        (root / "gepa_experiment_proposal.json").read_text(encoding="utf-8")
    )
    assert sidecar["selection"]["selection_explicitly_requested"] is True
    assert sidecar["selection"]["gepa_fit_asserted"] is False
    assert sidecar["gepa_plan"]["max_metric_calls"] == 3
    assert sidecar["gepa_plan"]["execution_requires_explicit_operator_review"] is True
    assert sidecar["effect"]["gepa_invoked"] is False
    assert sidecar["effect"]["gepa_model_calls_made"] is False
    assert sidecar["non_authority"]["may_invoke_gepa"] is False
    assert (
        sidecar["candidate_binding"]["manifest_sha256"]
        == first["bindings"]["candidate_manifest_sha256"]
    )
    assert not (root / "gepa-experiment").exists()


def test_foundry_gepa_proposal_rejects_unselected_or_drifted_semantics(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    intent = tmp_path / "intent.json"
    proposal = tmp_path / "quality-proposal.json"
    inputs = tmp_path / "inputs.json"
    root = tmp_path / "foundry"
    _quality_artifacts(intent, proposal)
    _inputs(inputs)
    monkeypatch.setattr(
        foundry, "run_program_runtime_oracle_semantics", _successful_semantic_stub
    )

    with pytest.raises(ValueError, match="outside Oracle recommended_experiments"):
        foundry.run_program_foundry(
            intent_path=intent,
            quality_proposal_path=proposal,
            inputs_path=inputs,
            outdir=root,
            skip_oracle_index=True,
            gepa_recommendation_index=1,
        )
    assert not (root / "gepa_experiment_proposal.json").exists()

    semantic_path = root / "runtime" / "program_oracle_semantic.json"
    semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
    semantic["source_binding"]["behavior_results"]["sha256"] = "0" * 64
    semantic_path.write_text(json.dumps(semantic), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from the persisted sidecar"):
        foundry.run_program_foundry(
            intent_path=intent,
            quality_proposal_path=proposal,
            inputs_path=inputs,
            outdir=root,
            skip_oracle_index=True,
            gepa_recommendation_index=0,
        )


def test_foundry_cli_is_registered(monkeypatch, tmp_path: Path) -> None:
    intent = tmp_path / "intent.json"
    proposal = tmp_path / "proposal.json"
    inputs = tmp_path / "inputs.json"
    _quality_artifacts(intent, proposal)
    _inputs(inputs)
    monkeypatch.setattr(
        foundry,
        "run_program_foundry",
        lambda **kwargs: {
            "status": "ok",
            "workflow_path": str(tmp_path / "foundry" / "foundry.json"),
            "stages": {},
        },
    )

    result = CliRunner().invoke(
        app,
        [
            "foundry",
            "--intent",
            str(intent),
            "--quality-proposal",
            str(proposal),
            "--inputs",
            str(inputs),
            "--outdir",
            str(tmp_path / "foundry"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "ok"
