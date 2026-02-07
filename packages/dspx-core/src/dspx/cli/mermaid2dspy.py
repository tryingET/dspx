from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from dspx.services.mermaid_workflow_service import generate_programs


def _read_input(path: str | None) -> str:
    if path and path != "-":
        return Path(path).read_text(encoding="utf-8")
    import sys

    data = sys.stdin.read()
    if not data:
        raise SystemExit("No Mermaid input provided. Pass --file or pipe via stdin.")
    return data


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Generate DSPy programs from a Mermaid flowchart"
    )
    p.add_argument(
        "spec",
        nargs="?",
        help="Inline Mermaid text (optional if --file or stdin provided)",
    )
    p.add_argument("--file", "-f", help="Path to Mermaid .mmd file or '-' for stdin")
    p.add_argument("--name", "-n", help="Workflow name (slug)")
    p.add_argument(
        "--outdir",
        "-o",
        help="Output directory root (defaults to generated/workflows/<name>)",
    )
    p.add_argument(
        "--variants",
        "-v",
        default="predict,cot,react",
        help="Comma-separated variants to generate: predict,cot,react",
    )
    args = p.parse_args(argv)

    if args.spec:
        diagram = args.spec
    else:
        diagram = _read_input(args.file)

    variants = [v.strip() for v in (args.variants or "").split(",") if v.strip()]
    out = generate_programs(
        diagram, name=args.name, out_dir=args.outdir, variants=variants
    )

    print("Generated:")
    for pth in out:
        print(" -", pth)
    # Print a quick hint
    if out:
        d = str(Path(out[0]).parent)
        print("\nRun one:")
        print(f"  uv run python {Path(out[0]).name}")
        print(f"  (in directory: {d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
