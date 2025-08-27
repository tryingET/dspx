import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import dspy
from config_loader import load_config_env
from tracing import enable_mlflow_from_env
from dspx.services.refine_service import run_refine as service_refine

from codex_exec_lm import CodexExecLM


def add_vibe_path() -> None:
    here = Path(__file__).parent
    vibe_src = here / "submodules" / "vibe-dspy" / "src"
    if vibe_src.is_dir():
        sys.path.insert(0, str(vibe_src))


def wrap_script(signature_code: str) -> str:
    lines = []
    lines.append("# Auto-generated DSPy script (Codex Exec enabled)")
    lines.append("import os")
    lines.append("import dspy")
    lines.append("from codex_exec_lm import CodexExecLM")
    lines.append("")
    lines.append("MODEL = os.getenv('CODEX_MODEL', 'gpt-5')")
    lines.append("lm = CodexExecLM(model_flag=MODEL, auto_mode=False, dangerously_bypass=True, reasoning_effort='minimal')")
    lines.append("dspy.configure(lm=lm)")
    lines.append("")
    lines.append(signature_code)
    lines.append("")
    lines.append("def demo():")
    lines.append("    pass  # TODO: instantiate a Predict module with the generated Signature")
    lines.append("")
    lines.append("if __name__ == '__main__':")
    lines.append("    demo()")
    return "\n".join(lines)


def summarize(pred) -> str:
    parts = []
    parts.append(f"Signature Name: {pred.signature_name}")
    parts.append(f"Description: {pred.task_description}")
    parts.append("Fields:")
    for f in pred.signature_fields:
        parts.append(f"  - {f.role.value}: {f.name} : {f.type.value} — {f.description}")
    return "\n".join(parts)


def make_reward_fn(non_interactive: bool):
    def reward_fn(args, pred):  # args not used; keep signature compatible
        if non_interactive:
            return 1.0
        print("\n=== Review Generated Signature ===")
        print(summarize(pred))
        ans = input("\nAccept this signature? [y/N]: ").strip().lower()
        if ans in {"y", "yes"}:
            return 1.0
        feedback = input("Feedback to improve (enter to keep generic): ").strip()
        if not feedback:
            feedback = "Please improve the signature structure and field descriptions."
        return dspy.Prediction(score=0.0, feedback=feedback)

    return reward_fn


def main(argv: Optional[list[str]] = None) -> int:
    add_vibe_path()
    from signature_generator import SignatureGenerator  # type: ignore

    ap = argparse.ArgumentParser(
        description="Interactive refine of DSPy signature using vibe-dspy + Codex Exec"
    )
    ap.add_argument("prompt", help="Natural language description of the desired functionality")
    ap.add_argument("-n", "--attempts", type=int, default=3, help="Max refinement attempts")
    ap.add_argument("-o", "--out", dest="outfile", help="Write final code to this file")
    ap.add_argument("--wrap-script", action="store_true", help="Wrap final code into a runnable script with Codex Exec config")
    ap.add_argument("--non-interactive", action="store_true", help="Auto-accept first draft (no prompts)")
    args = ap.parse_args(argv)

    # Load config.toml to populate env defaults
    load_config_env()
    # Optionally enable MLflow tracing if configured via env.
    enable_mlflow_from_env()

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
