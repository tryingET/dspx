#!/usr/bin/env python3
# summary: "Builds and gates the bounded module-synthesis quality corpus JSONL log."
# read_when:
#   - "Changing module-synthesis corpus execution, CI budgets, output, or quality gates."

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path
from typing import Any

from dspx.services.module_synthesis_corpus import (
    MODULE_SYNTHESIS_CORPUS_GATE,
    build_module_synthesis_quality_events,
    load_module_synthesis_cases,
    write_module_quality_events_jsonl,
)
from dspx.services.module_synthesis_quality import (
    evaluate_module_quality_gates,
    summarize_module_quality_events,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic module-synthesis quality JSONL log from the "
            "ranked runtime corpus."
        )
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("tests/golden/module_synthesis_cases.json"),
        help="Path to module-synthesis corpus JSON cases.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("generated/ci/module_synthesis_quality.jsonl"),
        help="Output JSONL path for module-synthesis quality events.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=25,
        help="Fail closed if the explicit corpus exceeds this bounded CI budget.",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Optional explicit scratch workspace. Defaults to a temporary directory.",
    )
    return parser.parse_args()


def _build_events_in_workspace(
    cases: list[dict[str, Any]], workspace_root: Path
) -> list[dict[str, Any]]:
    return build_module_synthesis_quality_events(
        cases,
        workspace_root=workspace_root,
    )


def main() -> None:
    args = _parse_args()
    cases = load_module_synthesis_cases(args.cases)
    if args.max_cases < 1:
        raise SystemExit("--max-cases must be at least 1")
    if len(cases) > args.max_cases:
        raise SystemExit(
            f"corpus case count {len(cases)} exceeds bounded CI budget {args.max_cases}"
        )

    started = time.monotonic()
    if args.workspace_root is None:
        with tempfile.TemporaryDirectory(prefix="dspx-module-synthesis-corpus-") as td:
            workspace_root = Path(td)
            events = _build_events_in_workspace(cases, workspace_root)
    else:
        workspace_root = args.workspace_root.expanduser().resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        events = _build_events_in_workspace(cases, workspace_root)

    out_path = write_module_quality_events_jsonl(events, args.out)
    summary = summarize_module_quality_events(events, run_kind="module-gen")
    gates = evaluate_module_quality_gates(summary, gate=MODULE_SYNTHESIS_CORPUS_GATE)

    print(
        f"wrote={out_path} workspace_root={workspace_root} duration_seconds={time.monotonic() - started:.3f} runs_total={summary.get('runs_total', 0)} "
        f"selection_integrity_rate={summary.get('selection_integrity_rate', 0.0):.4f} "
        f"receipt_coverage_rate={summary.get('receipt_coverage_rate', 0.0):.4f} "
        f"gates={'PASS' if gates.get('overall_pass') else 'FAIL'}"
    )

    if not gates.get("overall_pass"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
