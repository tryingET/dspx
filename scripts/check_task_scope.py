#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dspx.task_scope import check_task_scope, format_scope_result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check the latest task slice against an attested file scope manifest"
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--task-id", type=int, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument(
        "--mode",
        choices=("head", "working-tree"),
        default="head",
        help="Check the latest committed slice (head) or the current working tree",
    )
    parser.add_argument(
        "--range",
        default="HEAD^..HEAD",
        help="Git rev range when --mode=head (default: HEAD^..HEAD)",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


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
