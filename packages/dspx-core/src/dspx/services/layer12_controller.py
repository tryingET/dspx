from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

AK_VERIFIER_AUTHORITY = "deterministic_ak_layer12_verifier"
DSPX_ROLE = "proposal_generation_repair_and_empirical_eval_only"
NO_APPLY_BOUNDARY = "no_apply_authority"

RunCommand = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class Layer12ProposalEvalCase:
    proposal_path: Path
    verifier_output: dict[str, Any]

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
        if case.legal
        and case.proposed_transition
        in {"request_owner_route", "close_implementation_wave", "activate_guidance"}
    )
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
    }


def evaluate_layer12_proposals(
    *,
    agent_kernel_repo: Path | None = None,
    fixtures_dir: Path | None = None,
    runner: RunCommand = _run_command,
) -> dict[str, Any]:
    """Evaluate Layer12 transition proposals against AK's deterministic verifier.

    DSPx owns proposal/eval orchestration here. AK remains the authority for
    transition legality via read-only `ak layer12 ...` verifier commands.
    """

    ak_repo = (agent_kernel_repo or default_agent_kernel_repo()).resolve()
    fixture_root = (fixtures_dir or default_layer12_fixture_dir(ak_repo)).resolve()
    proposal_paths = discover_proposal_fixtures(fixture_root)

    cockpit = _run_json(
        ["ak", "layer12", "cockpit", "--repo", str(ak_repo), "-F", "json"],
        ak_repo,
        runner,
    )
    illegal_inventory = _run_json(
        ["ak", "layer12", "illegal-transitions", "--repo", str(ak_repo), "-F", "json"],
        ak_repo,
        runner,
    )

    cases: list[Layer12ProposalEvalCase] = []
    for proposal_path in proposal_paths:
        verifier_output = _run_json(
            [
                "ak",
                "layer12",
                "verify-proposal",
                "--repo",
                str(ak_repo),
                "--proposal",
                _proposal_arg(ak_repo, proposal_path),
                "-F",
                "json",
            ],
            ak_repo,
            runner,
        )
        cases.append(
            Layer12ProposalEvalCase(
                proposal_path=proposal_path, verifier_output=verifier_output
            )
        )

    return {
        "schema_version": "dspx.layer12.proposal_eval.v1",
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
        "dspy_skeleton": {
            "signatures": [
                "ExtractLayer12PolicyFacts",
                "DeriveLayer12StateVector",
                "ProposeLayer12Transition",
                "CritiqueAuthorityDrift",
                "CritiqueTheaterTraps",
                "RepairLayer12IR",
            ],
            "status": "skeleton_eval_harness",
        },
        "ak_readbacks": {
            "cockpit_surface": cockpit.get("surface"),
            "recommended_transition": cockpit.get("recommended_transition"),
            "illegal_transition_surface": illegal_inventory.get("surface"),
            "blocked_transition_count": illegal_inventory.get(
                "blocked_transition_count"
            ),
        },
        "metrics": _metrics(cases),
        "cases": [
            {
                "proposal_path": str(case.proposal_path),
                "proposed_transition": case.proposed_transition,
                "verdict": case.verdict,
                "legal": case.legal,
                "apply_performed": bool(case.verifier_output.get("apply_performed")),
                "verifier_surface": case.verifier_output.get("surface"),
            }
            for case in cases
        ],
    }
