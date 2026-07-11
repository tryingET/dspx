# summary: "Checks repo direction projections for required AK references and retired artifacts."
# read_when:
#   - "Changing direction read-order requirements or retired direction-file detection."

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Issue:
    path: Path
    message: str


RETIRED_DIRECTION_GLOBS = (
    "next_session_prompt.md",
    "docs/project/*_goals.md",
)

REQUIRED_READ_ORDER = (
    "docs/project/vision.md",
    "docs/project/product-posture.md",
)

REQUIRED_AK_DIRECTION_TEXT = "AK direction"


_RETIRED_READ_ORDER_PATTERN = re.compile(
    r"next_session_prompt\.md|docs/project/[A-Za-z0-9_-]+_goals\.md"
)


def _require_text(root: Path, relpath: str, issues: list[Issue]) -> str | None:
    path = root / relpath
    if not path.exists():
        issues.append(Issue(Path(relpath), "missing required file"))
        return None
    return path.read_text(encoding="utf-8")


def _iter_retired_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for pattern in RETIRED_DIRECTION_GLOBS:
        paths.extend(path for path in root.glob(pattern) if path.exists())
    return sorted(set(paths))


def collect_issues(root: Path) -> list[Issue]:
    root = root.resolve()
    issues: list[Issue] = []

    for path in _iter_retired_paths(root):
        issues.append(
            Issue(
                path.relative_to(root),
                "retired file still exists; use AK direction runtime",
            )
        )

    agents = _require_text(root, "AGENTS.md", issues)
    if agents is None:
        return issues

    for needle in REQUIRED_READ_ORDER:
        if needle not in agents:
            issues.append(
                Issue(Path("AGENTS.md"), f"missing read-order reference: {needle}")
            )

    if REQUIRED_AK_DIRECTION_TEXT not in agents:
        issues.append(
            Issue(
                Path("AGENTS.md"),
                "missing AK direction authority reminder",
            )
        )

    for match in _RETIRED_READ_ORDER_PATTERN.finditer(agents):
        issues.append(
            Issue(
                Path("AGENTS.md"),
                f"retired read-order reference remains: {match.group(0)}",
            )
        )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check DSPx direction-to-execution coherence against AK-native direction posture"
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
