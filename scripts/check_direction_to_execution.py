from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class Issue:
    path: Path
    message: str


def _read(root: Path, relpath: str) -> str:
    return (root / relpath).read_text(encoding="utf-8")


def _require_text(root: Path, relpath: str, issues: list[Issue]) -> str | None:
    path = root / relpath
    if not path.exists():
        issues.append(Issue(Path(relpath), "missing required file"))
        return None
    return path.read_text(encoding="utf-8")


def _extract_marker(
    text: str, label: str, relpath: str, issues: list[Issue]
) -> str | None:
    pattern = rf"{re.escape(label)}\s*`([^`]+)`"
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    issues.append(Issue(Path(relpath), f"missing marker: {label} `...`"))
    return None


def _extract_active_operational_task(
    text: str, relpath: str, issues: list[Issue]
) -> str | None:
    section_match = re.search(
        r"^## Active operating slices\s*$\n(?P<body>.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    section_text = section_match.group("body") if section_match else text
    ids = re.findall(r"AK-(\d+)", section_text)
    if ids:
        return f"AK-{ids[0]}"
    if re.search(
        r"\bno repo-scoped implementation slice\b", section_text, re.IGNORECASE
    ):
        return None
    issues.append(Issue(Path(relpath), "missing active operating-slice AK task ID"))
    return None


def _run_json(cmd: list[str], *, relpath: str, issues: list[Issue]) -> object | None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        issues.append(Issue(Path(relpath), f"missing command: {cmd[0]}"))
        return None
    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        issues.append(
            Issue(Path(relpath), f"command failed: {' '.join(cmd)} :: {stderr}")
        )
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        issues.append(
            Issue(Path(relpath), f"invalid JSON from command {' '.join(cmd)}: {exc}")
        )
        return None


def _run_check(cmd: list[str], *, relpath: str, issues: list[Issue]) -> None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        issues.append(Issue(Path(relpath), f"missing command: {cmd[0]}"))
        return
    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        issues.append(
            Issue(Path(relpath), f"command failed: {' '.join(cmd)} :: {stderr}")
        )


def collect_issues(root: Path) -> list[Issue]:
    root = root.resolve()
    issues: list[Issue] = []

    agents = _require_text(root, "AGENTS.md", issues)
    next_session = _require_text(root, "next_session_prompt.md", issues)
    strategic = _require_text(root, "docs/project/strategic_goals.md", issues)
    tactical = _require_text(root, "docs/project/tactical_goals.md", issues)
    operational = _require_text(root, "docs/project/operational_goals.md", issues)
    if any(
        item is None
        for item in (agents, next_session, strategic, tactical, operational)
    ):
        return issues

    strategic_active = _extract_marker(
        strategic, "Active strategic goal:", "docs/project/strategic_goals.md", issues
    )
    tactical_strategic = _extract_marker(
        tactical, "Active strategic goal:", "docs/project/tactical_goals.md", issues
    )
    tactical_active = _extract_marker(
        tactical, "Active tactical goal:", "docs/project/tactical_goals.md", issues
    )
    operational_active = _extract_marker(
        operational,
        "Active tactical goal:",
        "docs/project/operational_goals.md",
        issues,
    )
    if (
        strategic_active
        and tactical_strategic
        and strategic_active != tactical_strategic
    ):
        issues.append(
            Issue(
                Path("docs/project/tactical_goals.md"),
                f"active strategic goal mismatch with strategic_goals.md ({tactical_strategic} != {strategic_active})",
            )
        )
    if tactical_active and operational_active and tactical_active != operational_active:
        issues.append(
            Issue(
                Path("docs/project/operational_goals.md"),
                f"active tactical goal mismatch with tactical_goals.md ({operational_active} != {tactical_active})",
            )
        )
    required_read_order = [
        "docs/project/vision.md",
        "docs/project/strategic_goals.md",
        "docs/project/tactical_goals.md",
        "docs/project/operational_goals.md",
    ]
    for needle in required_read_order:
        if needle not in agents:
            issues.append(
                Issue(Path("AGENTS.md"), f"missing read-order reference: {needle}")
            )

    first_operational = _extract_active_operational_task(
        operational, "docs/project/operational_goals.md", issues
    )

    objective_match = re.search(
        r"Objective \(one sentence\): Claim `(AK-\d+)`", next_session
    )
    next_session_declares_empty_queue = bool(
        re.search(
            r"Objective \(one sentence\): .*ready queue.*empty",
            next_session,
            flags=re.IGNORECASE,
        )
    )
    if objective_match is None:
        if not next_session_declares_empty_queue:
            issues.append(
                Issue(
                    Path("next_session_prompt.md"),
                    "missing Objective claim marker for active AK task",
                )
            )
        next_session_ak = None
    else:
        next_session_ak = objective_match.group(1)

    if first_operational and next_session_ak and first_operational != next_session_ak:
        issues.append(
            Issue(
                Path("next_session_prompt.md"),
                f"next-session active task mismatch with operational_goals.md ({next_session_ak} != {first_operational})",
            )
        )

    ready_payload = _run_json(
        ["ak", "task", "ready", "-F", "json"],
        relpath="next_session_prompt.md",
        issues=issues,
    )
    if isinstance(ready_payload, list):
        repo_ready: list[dict[str, Any]] = []
        for raw_item in ready_payload:
            if not isinstance(raw_item, dict):
                continue
            item = cast(dict[str, Any], raw_item)
            if item.get("repo") == str(root):
                repo_ready.append(item)
        ready_ids = {
            f"AK-{item['id']}" for item in repo_ready if isinstance(item.get("id"), int)
        }
        if next_session_ak and next_session_ak not in ready_ids:
            issues.append(
                Issue(
                    Path("next_session_prompt.md"),
                    f"next-session active task {next_session_ak} is not currently ready in AK",
                )
            )
        if first_operational and first_operational not in ready_ids:
            issues.append(
                Issue(
                    Path("docs/project/operational_goals.md"),
                    f"active operating slice {first_operational} is not currently ready in AK",
                )
            )
        if ready_ids and next_session_ak is None and next_session_declares_empty_queue:
            issues.append(
                Issue(
                    Path("next_session_prompt.md"),
                    "next-session prompt declares an empty ready queue but AK has ready tasks",
                )
            )
        if ready_ids and first_operational is None:
            issues.append(
                Issue(
                    Path("docs/project/operational_goals.md"),
                    "operational goals declare no active slice but AK has ready tasks",
                )
            )

    _run_check(
        ["ak", "work-items", "check", "--repo", str(root)],
        relpath="governance/work-items.json",
        issues=issues,
    )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check DSPx direction-to-execution coherence across docs, AK, and work-item projections"
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()

    issues = collect_issues(args.root)
    if not issues:
        print("ok: direction-to-execution checks passed")
        return 0

    for issue in issues:
        print(f"{issue.path}: {issue.message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
