from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services.layer12_controller import evaluate_layer12_proposals


def _write_fixture(path: Path, transition: str | None) -> None:
    payload = {"schema_version": 1, "read_only": True}
    if transition is not None:
        payload["transition"] = transition
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fake_ak_runner(
    args: list[str] | tuple[str, ...], cwd: Path
) -> subprocess.CompletedProcess[str]:
    assert args[0] == "ak"
    assert "--repo" in args
    assert cwd.exists()
    if args[1:3] == ["layer12", "cockpit"]:
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "surface": "ak.layer12.cockpit",
                    "recommended_transition": "continue_current_execution_task",
                }
            ),
            stderr="",
        )
    if args[1:3] == ["layer12", "illegal-transitions"]:
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "surface": "ak.layer12.illegal_transitions",
                    "blocked_transition_count": 2,
                }
            ),
            stderr="",
        )
    if args[1:3] == ["layer12", "verify-proposal"]:
        proposal = args[args.index("--proposal") + 1]
        if "legal" in proposal:
            payload = {
                "surface": "ak.layer12.verify_proposal",
                "proposed_transition": "continue_current_execution_task",
                "verdict": "accepted",
                "legal": True,
                "apply_performed": False,
            }
        elif "malformed" in proposal:
            payload = {
                "surface": "ak.layer12.verify_proposal",
                "proposed_transition": None,
                "verdict": "malformed",
                "legal": False,
                "apply_performed": False,
            }
        else:
            payload = {
                "surface": "ak.layer12.verify_proposal",
                "proposed_transition": "request_owner_route",
                "verdict": "blocked",
                "legal": False,
                "apply_performed": False,
            }
        return subprocess.CompletedProcess(
            args, 0, stdout=json.dumps(payload), stderr=""
        )
    raise AssertionError(f"unexpected command: {args}")


def test_evaluate_layer12_proposals_uses_ak_verifier_as_authority(
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

    assert payload["read_only"] is True
    assert payload["apply_performed"] is False
    assert (
        payload["authority_boundary"]["legality_authority"]
        == "deterministic_ak_layer12_verifier"
    )
    assert payload["authority_boundary"]["empirical_output_is_normative"] is False
    assert payload["metrics"]["case_count"] == 3
    assert payload["metrics"]["verdict_counts"] == {
        "accepted": 1,
        "blocked": 1,
        "malformed": 1,
    }
    assert payload["metrics"]["false_unblock_count"] == 0
    assert {case["apply_performed"] for case in payload["cases"]} == {False}


def test_layer12_eval_proposals_cli_emits_json(monkeypatch, tmp_path: Path) -> None:
    fixtures = tmp_path / "agent-kernel/docs/project/layer12/fixtures/proposals"
    fixtures.mkdir(parents=True)
    _write_fixture(fixtures / "legal.json", "continue_current_execution_task")

    def fake_eval(**kwargs):
        return {
            "schema_version": "dspx.layer12.proposal_eval.v1",
            "read_only": True,
            "apply_performed": False,
            "authority_boundary": {
                "legality_authority": "deterministic_ak_layer12_verifier"
            },
            "metrics": {
                "case_count": 1,
                "verdict_counts": {"accepted": 1},
                "false_unblock_rate": 0.0,
            },
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
    assert payload["schema_version"] == "dspx.layer12.proposal_eval.v1"
    assert payload["apply_performed"] is False
