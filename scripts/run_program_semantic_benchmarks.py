#!/usr/bin/env python3
"""Run semantic benchmarks through generated DSPx program-loop candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dspx.services.program_semantic_benchmark import (
    load_program_semantic_corpus,
    run_program_semantic_benchmark,
    write_program_semantic_result,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("benchmarks/semantic/program-corpus-v1.json"),
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path("generated/ci/program-semantic-benchmark"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("generated/ci/program-semantic-benchmark-result.json"),
    )
    parser.add_argument(
        "--result-schema",
        type=Path,
        default=Path("benchmarks/semantic/program-result-schema-v1.json"),
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--provider")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.live and not args.provider:
        print("error: --live requires --provider", file=sys.stderr)
        return 2
    if not args.live and args.provider:
        print("error: --provider is accepted only with --live", file=sys.stderr)
        return 2
    try:
        corpus = load_program_semantic_corpus(args.corpus)
        result = run_program_semantic_benchmark(
            corpus,
            corpus_path=args.corpus,
            work_root=args.work_root,
            result_path=args.out,
            mode="live" if args.live else "offline",
            provider=args.provider,
        )
        write_program_semantic_result(
            result, args.out, result_schema_path=args.result_schema
        )
    except Exception as exc:
        from dspx.provider_runtime import sanitize_text

        print(f"error: {sanitize_text(str(exc), limit=240)}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["threshold_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
