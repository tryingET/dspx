from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Issue:
    path: Path
    message: str


RETIRED_DIRECTION_FILES = (
    "next_session_prompt.md",
    "docs/project/operational_goals.md",
)


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


def collect_issues(root: Path) -> list[Issue]:
    root = root.resolve()
    issues: list[Issue] = []

    for relpath in RETIRED_DIRECTION_FILES:
        if (root / relpath).exists():
            issues.append(
                Issue(Path(relpath), "retired AK-native direction file still exists")
            )

    agents = _require_text(root, "AGENTS.md", issues)
    strategic = _require_text(root, "docs/project/strategic_goals.md", issues)
    tactical = _require_text(root, "docs/project/tactical_goals.md", issues)
    if any(item is None for item in (agents, strategic, tactical)):
        return issues

    assert agents is not None
    assert strategic is not None
    assert tactical is not None

    strategic_active = _extract_marker(
        strategic, "Active strategic goal:", "docs/project/strategic_goals.md", issues
    )
    tactical_strategic = _extract_marker(
        tactical, "Active strategic goal:", "docs/project/tactical_goals.md", issues
    )
    _extract_marker(
        tactical, "Active tactical goal:", "docs/project/tactical_goals.md", issues
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

    required_read_order = [
        "docs/project/vision.md",
        "docs/project/strategic_goals.md",
        "docs/project/tactical_goals.md",
    ]
    for needle in required_read_order:
        if needle not in agents:
            issues.append(
                Issue(Path("AGENTS.md"), f"missing read-order reference: {needle}")
            )
    for retired in RETIRED_DIRECTION_FILES:
        if retired in agents:
            issues.append(
                Issue(
                    Path("AGENTS.md"),
                    f"retired read-order reference remains: {retired}",
                )
            )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check DSPx direction-to-execution coherence across AK-native direction docs"
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
