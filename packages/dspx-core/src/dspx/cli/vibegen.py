import argparse
from pathlib import Path
from typing import Optional

from dspx.services.signatures_service import run_generate as service_generate


def wrap_script(signature_code: str) -> str:
    """Wrap a generated signature into a runnable DSPy script using CodexExecLM."""
    lines = []
    lines.append("# Auto-generated DSPy script (Codex Exec enabled)")
    lines.append("import os")
    lines.append("import dspy")
    lines.append("from dspx.codex_exec_lm import CodexExecLM")
    lines.append("")
    lines.append("# Configure Codex Exec as the LM")
    lines.append("MODEL = os.getenv('CODEX_MODEL', 'gpt-5')")
    lines.append(
        "lm = CodexExecLM(model_flag=MODEL, auto_mode=True, dangerously_bypass=False, reasoning_effort='minimal')"
    )
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
        help="Wrap the signature in a runnable script that configures Codex Exec",
    )
    ap.add_argument("--provider", help="Provider name (registry), e.g., codex-exec")
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
