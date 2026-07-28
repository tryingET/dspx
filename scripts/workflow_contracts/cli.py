from __future__ import annotations

import argparse
from pathlib import Path

from .repository import collect_issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check DSPx workflow docs and validation contract surfaces"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root (default: current directory)",
    )
    args = parser.parse_args()

    issues = collect_issues(args.root)
    if not issues:
        print("ok: workflow contract checks passed")
        return 0

    for issue in issues:
        print(f"{issue.path}: {issue.message}")
    return 1
