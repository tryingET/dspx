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


def _proposal_arg(agent_kernel_repo: Path, proposal_path: Path) -> str:
    resolved_repo = agent_kernel_repo.resolve()
    resolved_proposal = proposal_path.resolve()
    try:
        return str(resolved_proposal.relative_to(resolved_repo))
    except ValueError as exc:
        raise ValueError(
            "Layer12 proposal fixtures must be repo-owned by agent-kernel so the "
            "deterministic AK verifier can read them"
        ) from exc


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
    return {
        "generated_count": len(generated_proposals),
        "verifier_compatible_count": verifier_compatible_count,
        "recommended_transition_match_count": transition_matches,
        "false_apply_count": false_apply_count,
    }


def evaluate_layer12_proposals(
    *,
    agent_kernel_repo: Path | None = None,
    fixtures_dir: Path | None = None,
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

    generated_proposals = [
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
        for intent in ["proceed"]
    ]

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
        "dspy_program": {
            "signatures": DSPY_SIGNATURES,
            "status": "direction_controller_proposal_generation_eval_extension",
            "generated_program_applied": False,
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
                "apply_performed": bool(proposal.get("apply_performed")),
                "expected_verifier_command": proposal.get("expected_verifier_command"),
            }
            for proposal in generated_proposals
        ],
        "generated_proposal_metrics": _generated_proposal_metrics(
            generated_proposals,
            str(recommended_transition) if recommended_transition else None,
        ),
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
