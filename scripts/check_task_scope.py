#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "packages" / "dspx-core" / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dspx.task_scope import check_task_scope, format_scope_result  # noqa: E402


def _normalize_assignment_style_values(argv: list[str]) -> list[str]:
    prefix_by_flag = {
        "--task-id": ("task_id=",),
        "--mode": ("mode=",),
        "--range": ("rev_range=", "range="),
    }
    normalized = list(argv)
    for index, token in enumerate(normalized[:-1]):
        prefixes = prefix_by_flag.get(token)
        if prefixes is None:
            continue
        value = normalized[index + 1]
        for prefix in prefixes:
            if value.startswith(prefix):
                normalized[index + 1] = value[len(prefix) :]
                break
    return normalized


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check an attested task slice against a file-scope manifest"
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--task-id", type=int, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument(
        "--mode",
        choices=("auto", "head", "working-tree"),
        default="head",
        help=(
            "Check the attested task slice reachable from HEAD, the current "
            "working tree, or auto-select working-tree when the repo is dirty "
            "and HEAD when it is clean"
        ),
    )
    parser.add_argument(
        "--range",
        default="auto",
        help=(
            "Git rev range when --mode=head; use 'auto' to validate the full "
            "task slice from the task-scope manifest introduction through HEAD"
        ),
    )
    parser.add_argument("--json", action="store_true")
    normalized_argv = _normalize_assignment_style_values(
        sys.argv[1:] if argv is None else argv
    )
    return parser.parse_args(normalized_argv)


def main() -> int:
    args = _parse_args()
    result = check_task_scope(
        args.root.resolve(),
        task_id=args.task_id,
        manifest_path=args.manifest.resolve() if args.manifest else None,
        mode=args.mode,
        rev_range=args.range,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "task_id": result.task_id,
                    "mode": result.mode,
                    "changed_files": list(result.changed_files),
                    "skipped": result.skipped,
                    "skip_reason": result.skip_reason,
                    "issues": [
                        {"path": issue.path, "message": issue.message}
                        for issue in result.issues
                    ],
                    "ok": result.ok,
                },
                indent=2,
            )
        )
    else:
        print(format_scope_result(result))
    return 0 if (result.ok or result.skipped) else 1


if __name__ == "__main__":
    raise SystemExit(main())
