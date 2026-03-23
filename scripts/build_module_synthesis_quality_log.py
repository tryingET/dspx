#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

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
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cases = load_module_synthesis_cases(args.cases)

    with tempfile.TemporaryDirectory(prefix="dspx-module-synthesis-corpus-") as td:
        events = build_module_synthesis_quality_events(
            cases,
            workspace_root=Path(td),
        )

    out_path = write_module_quality_events_jsonl(events, args.out)
    summary = summarize_module_quality_events(events, run_kind="module-gen")
    gates = evaluate_module_quality_gates(summary, gate=MODULE_SYNTHESIS_CORPUS_GATE)

    print(
        f"wrote={out_path} runs_total={summary.get('runs_total', 0)} "
        f"selection_integrity_rate={summary.get('selection_integrity_rate', 0.0):.4f} "
        f"receipt_coverage_rate={summary.get('receipt_coverage_rate', 0.0):.4f} "
        f"gates={'PASS' if gates.get('overall_pass') else 'FAIL'}"
    )

    if not gates.get("overall_pass"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
