import sys

import dspy
import os
from config_loader import load_config_env
from tracing import enable_mlflow_from_env

from codex_exec_lm import CodexExecLM


def main() -> int:
    # Initialize Codex Exec as the active LM for DSPy.
    # Load config.toml to populate env (MLflow + Codex defaults)
    load_config_env()
    # Optionally enable MLflow tracing if configured via env.
    enable_mlflow_from_env()

    # Default to GPT‑5 with minimal reasoning and full bypass.
    # Override model via CODEX_MODEL if needed.
    model = os.getenv("CODEX_MODEL", "gpt-5")
    lm = CodexExecLM(
        model_flag=model,
        auto_mode=False,  # prefer explicit bypass per user's flags
        dangerously_bypass=True,
        reasoning_effort="minimal",
    )
    dspy.configure(lm=lm)

    # A simple Predict module: maps question -> answer.
    qa = dspy.Predict("question -> answer")

    # Example coding question that benefits from execution.
    question = (
        "Write a Python function to check if a number is prime, "
        "and tell me if 37 is prime."
    )

    result = qa(question=question)

    # DSPy returns a structured object with the field name from the signature.
    print(result.answer)

    # Optional: peek into CodexExecLM call history (last run).
    if getattr(lm, "history", None):
        print("\n--- Debug: History ---")
        # Print the most recent DSPy entry
        last = lm.history[-1]
        if isinstance(last, dict):
            print("Type: DSPy LM Entry")
            print("Model:", last.get("model"))
            print("Usage:", last.get("usage"))
        # Find the most recent CodexExecResult entry (our wrapper)
        for entry in reversed(lm.history):
            if hasattr(entry, "prompt"):
                print("--- Latest CodexExec Call ---")
                print("Prompt:\n", entry.prompt)
                print("Command:", " ".join(entry.command))
                print("Exit Code:", entry.returncode)
                if entry.stdout:
                    print("--- codex stdout (truncated) ---\n", entry.stdout[:800])
                if entry.stderr:
                    print("--- codex stderr (truncated) ---\n", entry.stderr[:800])
                break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
