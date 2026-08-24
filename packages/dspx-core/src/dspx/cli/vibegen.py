# summary: "CLI entrypoint for generating DSPy signatures with an optional typed-stub script wrapper."
# read_when:
#   - "Changing vibegen arguments, provider selection, generated output, or script wrapping."

import argparse
from pathlib import Path
from typing import Optional

from dspx.services.signatures_service import run_generate as service_generate


def wrap_script(signature_code: str) -> str:
    """Wrap a generated signature into a credential-free typed-stub script."""
    lines = []
    lines.append("# Auto-generated DSPy script (typed stub)")
    lines.append("import dspy")
    lines.append("from dspx.provider_registry import create")
    lines.append("")
    lines.append("lm = create('stub')")
    lines.append("dspy.configure(lm=lm)")
    lines.append("")
    lines.append(signature_code)
    lines.append("")
    lines.append("def demo():")
    lines.append("    # Example usage: fill in inputs for your signature")
    lines.append("    # qa = dspy.Predict(YourSignatureClass)")
    lines.append("    # result = qa(<your_input_fields>=...)  # TODO")
    lines.append("    # print(result)")
    lines.append("    pass")
    lines.append("")
    lines.append("if __name__ == '__main__':")
    lines.append("    demo()")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    from dspx.cli.shared import ensure_env_and_tracing

    ap = argparse.ArgumentParser(
        description="Generate a DSPy signature using the native DSPx generator"
    )
    ap.add_argument(
        "prompt", help="Natural language description of the desired functionality"
    )
    ap.add_argument(
        "-o", "--out", dest="outfile", help="Write generated code to this file"
    )
    ap.add_argument(
        "--wrap-script",
        action="store_true",
        help="Wrap the signature in a credential-free typed-stub script",
    )
    ap.add_argument("--provider", choices=["stub"], help="Supported provider")
    args = ap.parse_args(argv)

    ensure_env_and_tracing()

    # Optional provider override via env for the registry
    if args.provider:
        import os

        os.environ["DSPX_PROVIDER"] = args.provider

    # Use service layer to generate signature code
    code = service_generate(args.prompt)
    if args.wrap_script:
        code = wrap_script(code)

    if args.outfile:
        out_path = Path(args.outfile)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(code, encoding="utf-8")
        print(f"Wrote: {out_path}")
    else:
        print(code)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
