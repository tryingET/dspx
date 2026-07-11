# summary: "Provides the legacy argparse entry point for DSPx code generation."
# read_when:
#   - "You are maintaining the standalone codegen CLI or its provider and output options."

import argparse
from typing import Optional

from dspx.services.codegen_service import run as run_codegen


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Generate code using DSPy + Codex Exec")
    p.add_argument("spec", help="Short spec of what to generate (quoted)")
    p.add_argument(
        "-l", "--lang", dest="language", help="Language hint, e.g. python, ts, rust"
    )
    p.add_argument(
        "-o", "--out", dest="outfile", help="Write generated code to this file"
    )
    p.add_argument(
        "--print-all",
        action="store_true",
        help="Print full Codex output (not just code block)",
    )
    p.add_argument("--provider", help="Provider name (registry), e.g., codex-exec")
    args = p.parse_args(argv)

    # Optional provider override via env for the registry
    if args.provider:
        import os as _os

        _os.environ["DSPX_PROVIDER"] = args.provider
    code_text = run_codegen(
        args.spec,
        language=args.language,
        outfile=args.outfile,
        print_all=args.print_all,
    )
    if args.outfile:
        print(f"Wrote: {args.outfile}")
    else:
        print(code_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
