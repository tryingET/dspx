# summary: "Evaluates advisory Layer 1/2 transition proposals through Agent Kernel's deterministic read-only verifier."
# read_when:
#   - "Changing Layer 1/2 fixtures, AK verifier commands, proposal metrics, authority boundaries, or evaluation output."

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

AK_VERIFIER_AUTHORITY = "deterministic_ak_direction_controller_verifier"
DSPX_ROLE = "proposal_generation_repair_and_empirical_eval_only"
NO_APPLY_BOUNDARY = "no_apply_authority"
DANGEROUS_TRANSITIONS = {
    "request_owner_route",
    "close_implementation_wave",
    "activate_guidance",
}
DSPY_SIGNATURES = [
    "ExtractLayer12PolicyFacts",
    "DeriveLayer12StateVector",
    "ProposeLayer12Transition",
    "CritiqueAuthorityDrift",
    "CritiqueTheaterTraps",
    "RepairLayer12IR",
]
GENERATED_DSPY_CANDIDATE_PATH = (
    "examples/layer12/generated_direction_controller_program.py"
)
DEFAULT_GENERATED_PROGRAM_EVAL_FIXTURE = "docs/project/layer12/fixtures/proposals/map-position-controls-generated-program-eval.json"

RunCommand = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class Layer12ProposalEvalCase:
    proposal_path: Path
    verifier_output: dict[str, Any]
    plan_output: dict[str, Any]

    @property
    def verdict(self) -> str:
        return str(self.verifier_output.get("verdict") or "unknown")

    @property
    def legal(self) -> bool:
        return bool(self.verifier_output.get("legal"))

    @property
    def proposed_transition(self) -> str | None:
        value = self.verifier_output.get("proposed_transition")
        return str(value) if value is not None else None

    @property
    def apply_performed(self) -> bool:
        return bool(
            self.verifier_output.get("apply_performed")
            or self.plan_output.get("apply_performed")
        )

    @property
    def apply_allowed(self) -> bool:
        return bool(self.plan_output.get("apply_allowed"))


def default_agent_kernel_repo() -> Path:
    return Path.home() / "ai-society/softwareco/owned/agent-kernel"


def default_layer12_fixture_dir(agent_kernel_repo: Path | None = None) -> Path:
    repo = agent_kernel_repo or default_agent_kernel_repo()
    return repo / "docs/project/layer12/fixtures/proposals"


def _run_command(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def _run_json(args: Sequence[str], cwd: Path, runner: RunCommand) -> dict[str, Any]:
    completed = runner(args, cwd)
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(args)}\n{stderr or stdout}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not emit JSON: {' '.join(args)}") from exc


def _repo_owned_arg(agent_kernel_repo: Path, path: Path, *, artifact_kind: str) -> str:
    resolved_repo = agent_kernel_repo.resolve()
    resolved_path = path.resolve()
    try:
        return str(resolved_path.relative_to(resolved_repo))
    except ValueError as exc:
        raise ValueError(
            f"Layer12 {artifact_kind} must be repo-owned by agent-kernel so the "
            "deterministic AK verifier can read it"
        ) from exc


def _proposal_arg(agent_kernel_repo: Path, proposal_path: Path) -> str:
    return _repo_owned_arg(
        agent_kernel_repo, proposal_path, artifact_kind="proposal fixture"
    )


def discover_proposal_fixtures(fixtures_dir: Path) -> list[Path]:
    if not fixtures_dir.exists():
        raise FileNotFoundError(
            f"Layer12 proposal fixture directory not found: {fixtures_dir}"
        )
    return sorted(path for path in fixtures_dir.glob("*.json") if path.is_file())


def _metrics(cases: Iterable[Layer12ProposalEvalCase]) -> dict[str, Any]:
    case_list = list(cases)
    verdict_counts: dict[str, int] = {}
    legal_count = 0
    for case in case_list:
        verdict_counts[case.verdict] = verdict_counts.get(case.verdict, 0) + 1
        if case.legal:
            legal_count += 1
    blocked_count = verdict_counts.get("blocked", 0)
    malformed_count = verdict_counts.get("malformed", 0)
    false_unblock_count = sum(
        1
        for case in case_list
        if case.legal and case.proposed_transition in DANGEROUS_TRANSITIONS
    )
    false_apply_count = sum(1 for case in case_list if case.apply_performed)
    false_apply_allowed_count = sum(1 for case in case_list if case.apply_allowed)
    return {
        "case_count": len(case_list),
        "legal_count": legal_count,
        "blocked_count": blocked_count,
        "malformed_count": malformed_count,
        "verdict_counts": verdict_counts,
        "false_unblock_count": false_unblock_count,
        "false_unblock_rate": (false_unblock_count / len(case_list))
        if case_list
        else 0.0,
        "false_apply_count": false_apply_count,
        "false_apply_allowed_count": false_apply_allowed_count,
    }


def _candidate_score_metrics(
    candidate_scores: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    score_count = len(candidate_scores)
    passed_count = sum(1 for score in candidate_scores if score.get("passed") is True)
    failed_count = score_count - passed_count
    false_apply_count = sum(
        1 for score in candidate_scores if score.get("apply_performed") is True
    )
    return {
        "score_count": score_count,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "best_score": max(
            (float(score.get("score") or 0.0) for score in candidate_scores),
            default=0.0,
        ),
        "false_apply_count": false_apply_count,
        "used_as_authority": False,
        "advisory_only": True,
    }


def _generated_proposal_metrics(
    generated_proposals: Sequence[dict[str, Any]], recommended_transition: str | None
) -> dict[str, Any]:
    transition_matches = sum(
        1
        for proposal in generated_proposals
        if proposal.get("transition") == recommended_transition
    )
    false_apply_count = sum(
        1 for proposal in generated_proposals if proposal.get("apply_performed") is True
    )
    verifier_compatible_count = sum(
        1
        for proposal in generated_proposals
        if isinstance(proposal.get("transition"), str)
    )
    candidate_count = sum(
        1
        for proposal in generated_proposals
        if proposal.get("generated_by") == "dspx_generated_dspy_candidate"
    )
    return {
        "generated_count": len(generated_proposals),
        "candidate_count": candidate_count,
        "verifier_compatible_count": verifier_compatible_count,
        "recommended_transition_match_count": transition_matches,
        "false_apply_count": false_apply_count,
    }


def _generated_dspy_candidate_proposal(
    status: dict[str, Any], *, intent: str
) -> dict[str, Any]:
    transition = str(
        status.get("recommended_transition") or "inspect_status_before_proceeding"
    )
    return {
        "surface": "dspx.generated_direction_controller.proposal",
        "intent": intent,
        "proposal_role": "advisory_input_only",
        "generated_by": "dspx_generated_dspy_candidate",
        "program_id": "dspx.generated.direction_controller.v1",
        "transition": transition,
        "apply_performed": False,
        "expected_verifier_command": "ak direction-controller verify --repo . --proposal <saved-proposal.json> -F json",
    }


def evaluate_layer12_proposals(
    *,
    agent_kernel_repo: Path | None = None,
    fixtures_dir: Path | None = None,
    eval_fixture: Path | None = None,
    candidate_proposals: Sequence[Path] = (),
    runner: RunCommand = _run_command,
) -> dict[str, Any]:
    """Evaluate direction-controller proposals through AK's deterministic verifier.

    DSPx owns proposal-generation/eval orchestration here. AK remains the
    authority for direction-to-execution transition legality via read-only
    `ak direction-controller ...` verifier commands.
    """

    ak_repo = (agent_kernel_repo or default_agent_kernel_repo()).resolve()
    fixture_root = (fixtures_dir or default_layer12_fixture_dir(ak_repo)).resolve()
    proposal_paths = discover_proposal_fixtures(fixture_root)
    eval_fixture_path = (
        eval_fixture or ak_repo / DEFAULT_GENERATED_PROGRAM_EVAL_FIXTURE
    ).resolve()
    eval_fixture_arg = _repo_owned_arg(
        ak_repo, eval_fixture_path, artifact_kind="generated-program eval fixture"
    )
    candidate_proposal_args = [
        _proposal_arg(ak_repo, proposal_path) for proposal_path in candidate_proposals
    ]

    status = _run_json(
        ["ak", "direction-controller", "status", "--repo", str(ak_repo), "-F", "json"],
        ak_repo,
        runner,
    )
    blocked_inventory = _run_json(
        [
            "ak",
            "direction-controller",
            "blocked-transitions",
            "--repo",
            str(ak_repo),
            "-F",
            "json",
        ],
        ak_repo,
        runner,
    )

    generated_proposals = []
    for intent in ["proceed"]:
        generated_proposals.append(
            _run_json(
                [
                    "ak",
                    "direction-controller",
                    "propose",
                    "--repo",
                    str(ak_repo),
                    "--intent",
                    intent,
                    "-F",
                    "json",
                ],
                ak_repo,
                runner,
            )
        )
        generated_proposals.append(
            _generated_dspy_candidate_proposal(status, intent=intent)
        )

    cases: list[Layer12ProposalEvalCase] = []
    for proposal_path in proposal_paths:
        proposal_arg = _proposal_arg(ak_repo, proposal_path)
        verifier_output = _run_json(
            [
                "ak",
                "direction-controller",
                "verify",
                "--repo",
                str(ak_repo),
                "--proposal",
                proposal_arg,
                "-F",
                "json",
            ],
            ak_repo,
            runner,
        )
        plan_output = _run_json(
            [
                "ak",
                "direction-controller",
                "plan",
                "--repo",
                str(ak_repo),
                "--proposal",
                proposal_arg,
                "-F",
                "json",
            ],
            ak_repo,
            runner,
        )
        cases.append(
            Layer12ProposalEvalCase(
                proposal_path=proposal_path,
                verifier_output=verifier_output,
                plan_output=plan_output,
            )
        )

    eval_command = [
        "ak",
        "direction-controller",
        "eval",
        "--repo",
        str(ak_repo),
        "--fixture",
        eval_fixture_arg,
        "--summary",
        "-F",
        "json",
    ]
    for proposal_arg in candidate_proposal_args:
        eval_command.extend(["--candidate-proposal", proposal_arg])
    generated_program_eval = _run_json(eval_command, ak_repo, runner)
    candidate_scores = list(generated_program_eval.get("candidate_scores") or [])
    candidate_score_metrics = _candidate_score_metrics(candidate_scores)

    recommended_transition = status.get("recommended_transition")
    return {
        "schema_version": "dspx.direction_controller.proposal_eval.v1",
        "read_only": True,
        "apply_performed": False,
        "authority_boundary": {
            "dspx_role": DSPX_ROLE,
            "legality_authority": AK_VERIFIER_AUTHORITY,
            "apply_boundary": NO_APPLY_BOUNDARY,
            "empirical_output_is_normative": False,
        },
        "agent_kernel_repo": str(ak_repo),
        "fixtures_dir": str(fixture_root),
        "generated_program_eval_fixture": eval_fixture_arg,
        "dspy_program": {
            "signatures": DSPY_SIGNATURES,
            "status": "generated_direction_controller_program_candidate_materialized",
            "candidate_program_id": "dspx.generated.direction_controller.v1",
            "candidate_artifact": GENERATED_DSPY_CANDIDATE_PATH,
            "generated_program_applied": False,
            "production_promoted": False,
        },
        "ak_readbacks": {
            "status_surface": status.get("surface"),
            "recommended_transition": recommended_transition,
            "blocked_transitions_surface": blocked_inventory.get("surface"),
            "blocked_transition_count": blocked_inventory.get(
                "blocked_transition_count"
            ),
        },
        "generated_proposals": [
            {
                "surface": proposal.get("surface"),
                "intent": proposal.get("intent"),
                "transition": proposal.get("transition"),
                "proposal_role": proposal.get("proposal_role"),
                "generated_by": proposal.get("generated_by"),
                "program_id": proposal.get("program_id"),
                "apply_performed": bool(proposal.get("apply_performed")),
                "expected_verifier_command": proposal.get("expected_verifier_command"),
            }
            for proposal in generated_proposals
        ],
        "generated_proposal_metrics": _generated_proposal_metrics(
            generated_proposals,
            str(recommended_transition) if recommended_transition else None,
        ),
        "generated_program_eval": {
            "surface": generated_program_eval.get("surface"),
            "payload_kind": generated_program_eval.get("payload_kind"),
            "passed": generated_program_eval.get("passed"),
            "eval_score": generated_program_eval.get("eval_score"),
            "pass_rate": generated_program_eval.get("pass_rate"),
            "case_count": generated_program_eval.get("case_count"),
            "candidate_score_count": len(candidate_scores),
            "apply_performed": bool(generated_program_eval.get("apply_performed")),
        },
        "candidate_scores": candidate_scores,
        "candidate_score_metrics": candidate_score_metrics,
        "metrics": _metrics(cases),
        "cases": [
            {
                "proposal_path": str(case.proposal_path),
                "proposed_transition": case.proposed_transition,
                "verdict": case.verdict,
                "legal": case.legal,
                "apply_performed": case.apply_performed,
                "apply_allowed": case.apply_allowed,
                "verifier_surface": case.verifier_output.get("surface"),
                "plan_surface": case.plan_output.get("surface"),
                "plan_status": case.plan_output.get("plan_status"),
            }
            for case in cases
        ],
    }
