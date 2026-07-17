# summary: "Tests integrated receipt-driven foundry continuation and CLI resume states."

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
import dspx.cli.dspx as cli
import dspx.services.program_foundry as base_foundry
import dspx.services.program_foundry_gepa_workflow as workflow


def _proposal(tmp_path: Path, proposal_id: str = "p" * 64) -> Path:
    path = tmp_path / "foundry" / "gepa_experiment_proposal.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"proposal_id": proposal_id}), encoding="utf-8")
    return path


def _run_workflow(*, proposal_path: Path, **kwargs: Any) -> dict[str, Any]:
    return workflow.run_program_foundry_gepa_workflow(
        proposal_path=proposal_path,
        expected_proposal_id="p" * 64,
        **kwargs,
    )


def _install_successful_stages(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dispatch_status: str = "completed",
    disposition: str = "promote_locally",
) -> list[str]:
    calls: list[str] = []

    def execute(**kwargs: Any) -> dict[str, Any]:
        calls.append("execute")
        return {"status": "ok", "proposal_id": "p" * 64, "reused": False}

    def consume(**kwargs: Any) -> dict[str, Any]:
        calls.append("consume")
        return {
            "status": "ok",
            "proposal_id": "p" * 64,
            "comparison_status": "compared",
            "reused": False,
        }

    def jury(**kwargs: Any) -> dict[str, Any]:
        calls.append("jury")
        return {
            "status": "ok",
            "proposal_id": "p" * 64,
            "jury_status": "completed",
            "reused": False,
        }

    def dispatch(**kwargs: Any) -> dict[str, Any]:
        calls.append("dispatch")
        return {
            "status": dispatch_status,
            "disposition": disposition,
            "request_id": "r" * 64,
        }

    monkeypatch.setattr(workflow, "execute_reviewed_program_foundry_gepa", execute)
    monkeypatch.setattr(
        workflow, "consume_successful_program_foundry_gepa_receipt", consume
    )
    monkeypatch.setattr(workflow, "execute_program_foundry_gepa_comparison_jury", jury)
    monkeypatch.setattr(
        workflow, "dispatch_program_foundry_gepa_comparison_adjudicator", dispatch
    )
    return calls


def test_waits_for_explicit_review_without_invoking_any_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal(tmp_path)

    def forbidden(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError("continuation stage must not run before review")

    monkeypatch.setattr(workflow, "execute_reviewed_program_foundry_gepa", forbidden)
    result = _run_workflow(proposal_path=proposal)

    assert result["status"] == "waiting_gepa_review"
    assert result["stages"] == {}
    assert result["non_authority"]["review_declaration_authenticated"] is False


def test_rejects_proposal_not_bound_to_current_foundry_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal(tmp_path, proposal_id="replacement")
    monkeypatch.setattr(
        workflow,
        "execute_reviewed_program_foundry_gepa",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("mismatched proposal must not execute")
        ),
    )

    with pytest.raises(
        workflow.ProgramFoundryGepaWorkflowError,
        match="does not match the current foundry invocation",
    ):
        workflow.run_program_foundry_gepa_workflow(
            proposal_path=proposal,
            expected_proposal_id="p" * 64,
        )


def test_runs_complete_deterministic_chain_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal(tmp_path)
    calls = _install_successful_stages(monkeypatch)

    result = _run_workflow(
        proposal_path=proposal,
        declared_reviewed="p" * 64,
        operator_label="local-operator",
        jury_provider="fixture-provider",
    )

    assert calls == ["execute", "consume", "jury", "dispatch"]
    assert result["status"] == "completed_local_disposition"
    assert result["disposition"] == "promote_locally"
    assert list(result["stages"]) == [
        "gepa_execution",
        "candidate_consumption",
        "comparison_jury",
        "adjudicator_dispatch",
    ]
    assert result["effect"]["external_adjudicator_invoked"] is False
    assert result["non_authority"]["activation_authority"] is False


def test_pending_external_dispatch_is_a_successful_stop_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal(tmp_path)
    calls = _install_successful_stages(
        monkeypatch,
        dispatch_status="pending",
        disposition="pending",
    )

    result = _run_workflow(
        proposal_path=proposal,
        declared_reviewed="p" * 64,
        operator_label="local-operator",
        jury_provider="fixture-provider",
        registration_paths=[tmp_path / "panel.json"],
    )

    assert calls == ["execute", "consume", "jury", "dispatch"]
    assert result["status"] == "waiting_external_adjudicator"
    assert result["disposition"] == "pending"
    assert result["effect"]["external_adjudicator_invoked"] is False


def test_imports_optional_owner_completion_only_after_pending_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal(tmp_path)
    calls = _install_successful_stages(
        monkeypatch,
        dispatch_status="pending",
        disposition="pending",
    )
    registration = tmp_path / "panel.json"
    completion = tmp_path / "completion.json"
    policy = tmp_path / "policy.json"

    def imported(**kwargs: Any) -> dict[str, Any]:
        calls.append("completion")
        assert kwargs["declared_request_id"] == "r" * 64
        return {
            "status": "completed",
            "disposition": "reject_locally",
            "reused": False,
        }

    monkeypatch.setattr(
        workflow, "import_program_foundry_gepa_adjudicator_completion", imported
    )
    result = _run_workflow(
        proposal_path=proposal,
        declared_reviewed="p" * 64,
        operator_label="local-operator",
        jury_provider="fixture-provider",
        registration_paths=[registration],
        owner_completion_path=completion,
        verifier_policy_path=policy,
        trusted_policy_sha256="d" * 64,
        declared_request_id="r" * 64,
        expected_owner_receipt_id="owner-receipt",
    )

    assert calls == ["execute", "consume", "jury", "dispatch", "completion"]
    assert result["status"] == "completed_local_disposition"
    assert result["disposition"] == "reject_locally"
    assert "adjudicator_completion" in result["stages"]


def test_partial_completion_inputs_fail_before_any_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal(tmp_path)

    def forbidden(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError("stage must not run for partial completion inputs")

    monkeypatch.setattr(workflow, "execute_reviewed_program_foundry_gepa", forbidden)
    with pytest.raises(
        workflow.ProgramFoundryGepaWorkflowError,
        match="completion import requires completion",
    ):
        _run_workflow(
            proposal_path=proposal,
            declared_reviewed="p" * 64,
            operator_label="local-operator",
            jury_provider="fixture-provider",
            owner_completion_path=tmp_path / "completion.json",
        )


def test_new_effect_attempt_without_receipt_blocks_and_never_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal(tmp_path)
    experiment = proposal.parent / "gepa-experiment"
    calls: list[str] = []

    def interrupted(**kwargs: Any) -> dict[str, Any]:
        calls.append("execute")
        experiment.mkdir()
        (experiment / "attempt.json").write_text("{}", encoding="utf-8")
        raise RuntimeError("effect may have occurred")

    def forbidden(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError("downstream stage must not run")

    monkeypatch.setattr(workflow, "execute_reviewed_program_foundry_gepa", interrupted)
    monkeypatch.setattr(
        workflow, "consume_successful_program_foundry_gepa_receipt", forbidden
    )
    result = _run_workflow(
        proposal_path=proposal,
        declared_reviewed="p" * 64,
        operator_label="local-operator",
    )

    assert calls == ["execute"]
    assert result["status"] == "blocked_indeterminate"
    assert result["blocked_stage"] == "gepa_execution"
    assert result["disposition"] == "indeterminate_no_replay"


def test_preexisting_attempt_without_receipt_remains_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal(tmp_path)
    experiment = proposal.parent / "gepa-experiment"
    experiment.mkdir()
    (experiment / "attempt.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        workflow,
        "execute_reviewed_program_foundry_gepa",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError("attempt cannot be replayed")
        ),
    )
    result = _run_workflow(
        proposal_path=proposal,
        declared_reviewed="p" * 64,
        operator_label="local-operator",
    )

    assert result["status"] == "blocked_indeterminate"
    assert result["blocked_stage"] == "gepa_execution"


def test_degraded_consumption_requires_review_without_invoking_jury(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal(tmp_path)
    _install_successful_stages(monkeypatch)
    monkeypatch.setattr(
        workflow,
        "consume_successful_program_foundry_gepa_receipt",
        lambda **kwargs: {
            "status": "degraded",
            "proposal_id": "p" * 64,
            "comparison_status": "insufficient_evidence",
            "reused": False,
        },
    )
    monkeypatch.setattr(
        workflow,
        "execute_program_foundry_gepa_comparison_jury",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("degraded comparison must not invoke jury")
        ),
    )

    result = _run_workflow(
        proposal_path=proposal,
        declared_reviewed="p" * 64,
        operator_label="local-operator",
        jury_provider="fixture-provider",
    )

    assert result["status"] == "require_review"
    assert result["disposition"] == "candidate_comparison_degraded"
    assert "comparison_jury" not in result["stages"]


def test_ordinary_dispatch_failure_is_normalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal(tmp_path)
    _install_successful_stages(monkeypatch)
    monkeypatch.setattr(
        workflow,
        "dispatch_program_foundry_gepa_comparison_adjudicator",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("registration drifted")),
    )

    with pytest.raises(
        workflow.ProgramFoundryGepaWorkflowError,
        match="adjudicator dispatch failed: registration drifted",
    ):
        _run_workflow(
            proposal_path=proposal,
            declared_reviewed="p" * 64,
            operator_label="local-operator",
            jury_provider="fixture-provider",
        )


def test_new_terminal_receipt_after_exception_is_revalidated_without_effect_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal(tmp_path)
    experiment = proposal.parent / "gepa-experiment"
    calls = 0

    def commit_then_release_failure(**kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            experiment.mkdir()
            (experiment / "attempt.json").write_text("{}", encoding="utf-8")
            (experiment / "execution-receipt.json").write_text("{}", encoding="utf-8")
            raise OSError("lock release failed")
        return {"status": "ok", "proposal_id": "p" * 64, "reused": True}

    monkeypatch.setattr(
        workflow,
        "execute_reviewed_program_foundry_gepa",
        commit_then_release_failure,
    )
    monkeypatch.setattr(
        workflow,
        "consume_successful_program_foundry_gepa_receipt",
        lambda **kwargs: {
            "status": "ok",
            "proposal_id": "p" * 64,
            "comparison_status": "compared",
            "reused": True,
        },
    )
    result = _run_workflow(
        proposal_path=proposal,
        declared_reviewed="p" * 64,
        operator_label="local-operator",
    )

    assert calls == 2
    assert result["status"] == "waiting_jury_provider"
    assert result["stages"]["gepa_execution"]["reused"] is True


def test_foundry_cli_projects_integrated_continuation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    intent = tmp_path / "intent.json"
    quality = tmp_path / "quality.json"
    inputs = tmp_path / "inputs.json"
    outdir = tmp_path / "foundry"
    for path in (intent, quality, inputs):
        path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "ensure_env", lambda value: None)
    monkeypatch.setattr(
        base_foundry,
        "run_program_foundry",
        lambda **kwargs: {
            "status": "ok",
            "workflow_path": str(outdir / "foundry.json"),
            "stages": {
                "gepa_experiment_proposal": {
                    "status": "proposal_ready_for_review",
                    "path": str(outdir / "gepa_experiment_proposal.json"),
                    "proposal_id": "p" * 64,
                }
            },
        },
    )
    monkeypatch.setattr(
        workflow,
        "run_program_foundry_gepa_workflow",
        lambda **kwargs: {
            "status": "completed_local_disposition",
            "disposition": "promote_locally",
        },
    )

    result = CliRunner().invoke(
        app,
        [
            "foundry",
            "--intent",
            str(intent),
            "--quality-proposal",
            str(quality),
            "--inputs",
            str(inputs),
            "--outdir",
            str(outdir),
            "--declare-gepa-reviewed",
            "p" * 64,
            "--operator-label",
            "local-operator",
            "--jury-provider",
            "fixture-provider",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["continuation_status"] == "completed_local_disposition"
    assert payload["gepa_continuation"]["disposition"] == "promote_locally"


def test_foundry_cli_never_continues_a_stale_unbound_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    intent = tmp_path / "intent.json"
    quality = tmp_path / "quality.json"
    inputs = tmp_path / "inputs.json"
    outdir = tmp_path / "foundry"
    outdir.mkdir()
    for path in (intent, quality, inputs):
        path.write_text("{}", encoding="utf-8")
    (outdir / "gepa_experiment_proposal.json").write_text(
        json.dumps({"proposal_id": "old"}), encoding="utf-8"
    )
    monkeypatch.setattr(cli, "ensure_env", lambda value: None)
    monkeypatch.setattr(
        base_foundry,
        "run_program_foundry",
        lambda **kwargs: {
            "status": "behavior_failed",
            "workflow_path": str(outdir / "foundry.json"),
            "stages": {"gepa_experiment_proposal": {"status": "not_requested"}},
        },
    )
    monkeypatch.setattr(
        workflow,
        "run_program_foundry_gepa_workflow",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("stale proposal must not continue")
        ),
    )

    result = CliRunner().invoke(
        app,
        [
            "foundry",
            "--intent",
            str(intent),
            "--quality-proposal",
            str(quality),
            "--inputs",
            str(inputs),
            "--outdir",
            str(outdir),
            "--declare-gepa-reviewed",
            "old",
            "--operator-label",
            "local-operator",
        ],
    )

    assert result.exit_code == 2
    assert (
        "requires this invocation to explicitly produce or revalidate" in result.output
    )
