#!/usr/bin/env python3
# summary: "Builds the deterministic provider corpus log and evaluates signature quality gates."
# read_when:
#   - "Changing signature provider corpus inputs, event output, or gate reporting."

from __future__ import annotations

import argparse
from pathlib import Path

from dspx.services.signature_quality import (
    evaluate_quality_gates,
    summarize_quality_events,
)
from dspx.services.signature_quality_corpus import (
    PROVIDER_CORPUS_GATE,
    build_provider_corpus_quality_events,
    load_provider_corpus_cases,
    write_quality_events_jsonl,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic signature-quality JSONL log from the provider corpus."
        )
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("tests/golden/signature_provider_cases.json"),
        help="Path to provider corpus JSON cases.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("generated/ci/signature_provider_quality.jsonl"),
        help="Output JSONL path for quality events.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    cases = load_provider_corpus_cases(args.cases)
    events = build_provider_corpus_quality_events(cases)
    out_path = write_quality_events_jsonl(events, args.out)

    summary = summarize_quality_events(events, run_kind="signature-gen")
    gates = evaluate_quality_gates(summary, gate=PROVIDER_CORPUS_GATE)

    providers = ",".join(summary.get("providers") or [])
    print(
        f"wrote={out_path} runs_total={summary.get('runs_total', 0)} "
        f"providers={providers} gates={'PASS' if gates.get('overall_pass') else 'FAIL'}"
    )


if __name__ == "__main__":
    main()
