import argparse
import os
from typing import Optional


from dspx.services.refine_service import run_refine as service_refine


def wrap_script(signature_code: str) -> str:
    lines = []
    lines.append("# Auto-generated DSPy script (Codex Exec enabled)")
    lines.append("import os")
    lines.append("import dspy")
    lines.append("from dspx.codex_exec_lm import CodexExecLM")
    lines.append("")
    lines.append("MODEL = os.getenv('CODEX_MODEL', 'gpt-5')")
    lines.append(
        "lm = CodexExecLM(model_flag=MODEL, auto_mode=True, dangerously_bypass=False, reasoning_effort='minimal')"
    )
    lines.append("dspy.configure(lm=lm)")
    lines.append("")
    lines.append(signature_code)
    lines.append("")
    lines.append("def demo():")
    lines.append(
        "    pass  # TODO: instantiate a Predict module with the generated Signature"
    )
    lines.append("")
    lines.append("if __name__ == '__main__':")
    lines.append("    demo()")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    from dspx.cli.shared import ensure_env_and_tracing

    ap = argparse.ArgumentParser(
        description="Interactive refine of DSPy signature using native DSPx generation"
    )
    ap.add_argument(
        "prompt", help="Natural language description of the desired functionality"
    )
    ap.add_argument(
        "-n", "--attempts", type=int, default=3, help="Max refinement attempts"
    )
    ap.add_argument("-o", "--out", dest="outfile", help="Write final code to this file")
    ap.add_argument(
        "--wrap-script",
        action="store_true",
        help="Wrap final code into a runnable script with Codex Exec",
    )
    ap.add_argument(
        "--non-interactive",
        action="store_true",
        help="Auto-accept first draft (no prompts)",
    )
    ap.add_argument("--provider", help="Provider name (registry), e.g., codex-exec")
    args = ap.parse_args(argv)

    ensure_env_and_tracing()

    # Provider override via env for the registry
    if args.provider:
        os.environ["DSPX_PROVIDER"] = args.provider

    code = service_refine(
        args.prompt,
        outfile=args.outfile,
        attempts=args.attempts,
        wrap_script=args.wrap_script,
        non_interactive=args.non_interactive,
    )
    if args.outfile:
        print(f"Wrote: {args.outfile}")
    else:
        print(code)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
