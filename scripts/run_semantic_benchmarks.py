#!/usr/bin/env python3
# ---
# summary: "Run the semantic corpus with offline fixtures or an explicit live provider."
# read_when:
#   - "Changing semantic benchmark inputs, live-provider controls, or result emission."
# ---
"""Run the DSPx semantic corpus offline or with an explicitly selected provider."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dspx.provider_runtime import invoke_provider
from dspx.services.semantic_benchmark import (
    load_semantic_corpus,
    run_semantic_benchmark,
    write_result,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", type=Path, default=Path("benchmarks/semantic/corpus-v1.json")
    )
    parser.add_argument(
        "--out", type=Path, default=Path("generated/ci/semantic-benchmark-result.json")
    )
    parser.add_argument(
        "--result-schema",
        type=Path,
        default=Path("benchmarks/semantic/result-schema-v1.json"),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly allow provider-backed execution; absent means offline fixtures only.",
    )
    parser.add_argument(
        "--provider",
        help="Required registry provider for --live; rejected during offline execution.",
    )
    parser.add_argument("--max-tokens", type=int, default=160)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.live and not args.provider:
        print("error: --live requires --provider", file=sys.stderr)
        return 2
    if not args.live and args.provider:
        print("error: --provider is accepted only with --live", file=sys.stderr)
        return 2
    if args.max_tokens < 1 or args.max_tokens > 4096:
        print("error: --max-tokens must be between 1 and 4096", file=sys.stderr)
        return 2

    try:
        corpus = load_semantic_corpus(args.corpus)
        invoker = None
        if args.live:
            from dspx.provider_registry import create, ensure_default_providers

            ensure_default_providers()
            lm: Any = create(args.provider)

            def call(prompt: str) -> str:
                text, _usage = invoke_provider(
                    lm, prompt=prompt, max_tokens=args.max_tokens
                )
                return text

            invoker = call
        result = run_semantic_benchmark(
            corpus,
            mode="live" if args.live else "offline",
            provider=args.provider,
            invoke=invoker,
        )
        write_result(result, args.out, result_schema_path=args.result_schema)
    except Exception as exc:
        from dspx.provider_runtime import sanitize_text

        print(f"error: {sanitize_text(str(exc), limit=240)}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["threshold_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
