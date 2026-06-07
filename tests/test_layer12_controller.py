from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Sequence
from typing import Any

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services.layer12_controller import evaluate_layer12_proposals


def _write_fixture(path: Path, transition: str | None) -> None:
    payload: dict[str, Any] = {"schema_version": 1, "read_only": True}
    if transition is not None:
        payload["transition"] = transition
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fake_ak_runner(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    assert args[0] == "ak"
    assert args[1] == "direction-controller"
    assert "--repo" in args
    assert cwd.exists()
    if args[2] == "status":
        payload = {
            "surface": "ak.direction_controller.status",
            "recommended_transition": "continue_current_execution_task",
        }
    elif args[2] == "blocked-transitions":
        payload = {
            "surface": "ak.direction_controller.blocked_transitions",
            "blocked_transition_count": 2,
        }
    elif args[2] == "propose":
        payload = {
            "surface": "ak.direction_controller.propose",
            "intent": args[args.index("--intent") + 1],
            "proposal_role": "advisory_input_only",
            "generated_by": "deterministic_ak_direction_controller_dry_run",
            "transition": "continue_current_execution_task",
            "apply_performed": False,
            "expected_verifier_command": "ak direction-controller verify --repo . --proposal <saved-proposal.json> -F json",
        }
    elif args[2] == "verify":
        proposal = args[args.index("--proposal") + 1]
        if "legal" in proposal:
            payload = {
                "surface": "ak.direction_controller.verify",
                "proposed_transition": "continue_current_execution_task",
                "verdict": "accepted",
                "legal": True,
                "apply_performed": False,
            }
        elif "malformed" in proposal:
            payload = {
                "surface": "ak.direction_controller.verify",
                "proposed_transition": None,
                "verdict": "malformed",
                "legal": False,
                "apply_performed": False,
            }
        else:
            payload = {
                "surface": "ak.direction_controller.verify",
                "proposed_transition": "request_owner_route",
                "verdict": "blocked",
                "legal": False,
                "apply_performed": False,
            }
    elif args[2] == "plan":
        proposal = args[args.index("--proposal") + 1]
        payload = {
            "surface": "ak.direction_controller.plan",
            "plan_status": "dry_run_plan_ready"
            if "legal" in proposal
            else "blocked_no_plan",
            "apply_allowed": False,
            "apply_performed": False,
        }
    elif args[2] == "eval":
        candidate_refs = [
            args[index + 1]
            for index, value in enumerate(args)
            if value == "--candidate-proposal"
        ]
        candidate_scores = []
        for rank, proposal_ref in enumerate(candidate_refs, start=1):
            passed = "bad" not in proposal_ref
            candidate_scores.append(
                {
                    "candidate_id": proposal_ref.replace("/", "-"),
                    "proposal_ref": proposal_ref,
                    "case_id": f"candidate-proposal-{rank}",
                    "rank": rank,
                    "passed": passed,
                    "score": 1.0 if passed else 0.0,
                    "verdict": "accepted" if passed else "malformed",
                    "transition": "continue_current_execution_task" if passed else None,
                    "boundary_failures": []
                    if passed
                    else [
                        "proposal.ir.map_position_controls.map.map_is_runtime_authority must be false"
                    ],
                    "errors": [] if passed else ["boundary drift"],
                    "warnings": []
                    if passed
                    else ["map_is_runtime_authority must be false"],
                }
            )
        payload = {
            "surface": "ak.direction_controller.eval_summary",
            "payload_kind": "ak_direction_controller_eval_summary",
            "read_only": True,
            "apply_performed": False,
            "passed": all(score["passed"] for score in candidate_scores),
            "eval_score": 1.0 if not candidate_scores else candidate_scores[0]["score"],
            "pass_rate": 1.0 if not candidate_scores else candidate_scores[0]["score"],
            "case_count": 4 + len(candidate_scores),
            "candidate_scores": candidate_scores,
        }
    else:
        raise AssertionError(f"unexpected command: {args}")
    return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")


def test_evaluate_layer12_proposals_uses_direction_controller_as_authority(
    tmp_path: Path,
) -> None:
    ak_repo = tmp_path / "agent-kernel"
    fixtures = ak_repo / "docs/project/layer12/fixtures/proposals"
    fixtures.mkdir(parents=True)
    _write_fixture(fixtures / "legal.json", "continue_current_execution_task")
    _write_fixture(fixtures / "blocked-owner.json", "request_owner_route")
    _write_fixture(fixtures / "malformed.json", None)

    payload = evaluate_layer12_proposals(
        agent_kernel_repo=ak_repo,
        fixtures_dir=fixtures,
        runner=_fake_ak_runner,
    )

    assert payload["schema_version"] == "dspx.direction_controller.proposal_eval.v1"
    assert payload["read_only"] is True
    assert payload["apply_performed"] is False
    assert (
        payload["authority_boundary"]["legality_authority"]
        == "deterministic_ak_direction_controller_verifier"
    )
    assert payload["authority_boundary"]["empirical_output_is_normative"] is False
    assert payload["ak_readbacks"]["status_surface"] == "ak.direction_controller.status"
    assert payload["ak_readbacks"]["blocked_transition_count"] == 2
    assert payload["dspy_program"] == {
        "signatures": [
            "ExtractLayer12PolicyFacts",
            "DeriveLayer12StateVector",
            "ProposeLayer12Transition",
            "CritiqueAuthorityDrift",
            "CritiqueTheaterTraps",
            "RepairLayer12IR",
        ],
        "status": "generated_direction_controller_program_candidate_materialized",
        "candidate_program_id": "dspx.generated.direction_controller.v1",
        "candidate_artifact": "examples/layer12/generated_direction_controller_program.py",
        "generated_program_applied": False,
        "production_promoted": False,
    }
    assert payload["generated_proposals"] == [
        {
            "surface": "ak.direction_controller.propose",
            "intent": "proceed",
            "transition": "continue_current_execution_task",
            "proposal_role": "advisory_input_only",
            "generated_by": "deterministic_ak_direction_controller_dry_run",
            "program_id": None,
            "apply_performed": False,
            "expected_verifier_command": "ak direction-controller verify --repo . --proposal <saved-proposal.json> -F json",
        },
        {
            "surface": "dspx.generated_direction_controller.proposal",
            "intent": "proceed",
            "transition": "continue_current_execution_task",
            "proposal_role": "advisory_input_only",
            "generated_by": "dspx_generated_dspy_candidate",
            "program_id": "dspx.generated.direction_controller.v1",
            "apply_performed": False,
            "expected_verifier_command": "ak direction-controller verify --repo . --proposal <saved-proposal.json> -F json",
        },
    ]
    assert payload["generated_proposal_metrics"] == {
        "generated_count": 2,
        "candidate_count": 1,
        "verifier_compatible_count": 2,
        "recommended_transition_match_count": 2,
        "false_apply_count": 0,
    }
    assert payload["generated_program_eval"] == {
        "surface": "ak.direction_controller.eval_summary",
        "payload_kind": "ak_direction_controller_eval_summary",
        "passed": True,
        "eval_score": 1.0,
        "pass_rate": 1.0,
        "case_count": 4,
        "candidate_score_count": 0,
        "apply_performed": False,
    }
    assert payload["candidate_scores"] == []
    assert payload["candidate_score_metrics"] == {
        "score_count": 0,
        "passed_count": 0,
        "failed_count": 0,
        "best_score": 0.0,
        "false_apply_count": 0,
        "used_as_authority": False,
        "advisory_only": True,
    }
    assert payload["metrics"]["case_count"] == 3
    assert payload["metrics"]["verdict_counts"] == {
        "accepted": 1,
        "blocked": 1,
        "malformed": 1,
    }
    assert payload["metrics"]["false_unblock_count"] == 0
    assert payload["metrics"]["false_apply_count"] == 0
    assert payload["metrics"]["false_apply_allowed_count"] == 0
    assert {case["apply_performed"] for case in payload["cases"]} == {False}
    assert {case["apply_allowed"] for case in payload["cases"]} == {False}
    assert {case["verifier_surface"] for case in payload["cases"]} == {
        "ak.direction_controller.verify"
    }
    assert {case["plan_surface"] for case in payload["cases"]} == {
        "ak.direction_controller.plan"
    }


def test_evaluate_layer12_proposals_consumes_candidate_scores_as_advisory_input(
    tmp_path: Path,
) -> None:
    ak_repo = tmp_path / "agent-kernel"
    fixtures = ak_repo / "docs/project/layer12/fixtures/proposals"
    fixtures.mkdir(parents=True)
    _write_fixture(fixtures / "legal.json", "continue_current_execution_task")
    candidate = fixtures / "candidate.json"
    candidate.write_text(
        json.dumps({"transition": "continue_current_execution_task"}), encoding="utf-8"
    )

    payload = evaluate_layer12_proposals(
        agent_kernel_repo=ak_repo,
        fixtures_dir=fixtures,
        candidate_proposals=[candidate],
        runner=_fake_ak_runner,
    )

    assert payload["candidate_scores"] == [
        {
            "candidate_id": "docs-project-layer12-fixtures-proposals-candidate.json",
            "proposal_ref": "docs/project/layer12/fixtures/proposals/candidate.json",
            "case_id": "candidate-proposal-1",
            "rank": 1,
            "passed": True,
            "score": 1.0,
            "verdict": "accepted",
            "transition": "continue_current_execution_task",
            "boundary_failures": [],
            "errors": [],
            "warnings": [],
        }
    ]
    assert payload["candidate_score_metrics"] == {
        "score_count": 1,
        "passed_count": 1,
        "failed_count": 0,
        "best_score": 1.0,
        "false_apply_count": 0,
        "used_as_authority": False,
        "advisory_only": True,
    }
    assert payload["authority_boundary"]["legality_authority"] == (
        "deterministic_ak_direction_controller_verifier"
    )
    assert payload["authority_boundary"]["empirical_output_is_normative"] is False
    assert payload["apply_performed"] is False


def test_layer12_eval_proposals_cli_emits_json(monkeypatch, tmp_path: Path) -> None:
    fixtures = tmp_path / "agent-kernel/docs/project/layer12/fixtures/proposals"
    fixtures.mkdir(parents=True)
    _write_fixture(fixtures / "legal.json", "continue_current_execution_task")

    def fake_eval(**kwargs):
        return {
            "schema_version": "dspx.direction_controller.proposal_eval.v1",
            "read_only": True,
            "apply_performed": False,
            "authority_boundary": {
                "legality_authority": "deterministic_ak_direction_controller_verifier"
            },
            "metrics": {
                "case_count": 1,
                "verdict_counts": {"accepted": 1},
                "false_unblock_rate": 0.0,
            },
            "generated_proposals": [],
            "cases": [],
        }

    monkeypatch.setattr(
        "dspx.services.layer12_controller.evaluate_layer12_proposals", fake_eval
    )

    result = CliRunner().invoke(
        app,
        [
            "layer12",
            "eval-proposals",
            "--agent-kernel-repo",
            str(tmp_path / "agent-kernel"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "dspx.direction_controller.proposal_eval.v1"
    assert payload["apply_performed"] is False
