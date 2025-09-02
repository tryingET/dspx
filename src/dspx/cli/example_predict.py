import dspy
import os

from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env
from dspx.codex_exec_lm import CodexExecLM


def main() -> int:
    # Initialize Codex Exec as the active LM for DSPy.
    load_config_env()
    enable_mlflow_from_env()

    model = os.getenv("CODEX_MODEL", "gpt-5")
    lm = CodexExecLM(
        model_flag=model,
        auto_mode=False,
        dangerously_bypass=True,
        reasoning_effort="minimal",
    )
    dspy.configure(lm=lm)

    qa = dspy.Predict("question -> answer")
    question = (
        "Write a Python function to check if a number is prime, and tell me if 37 is prime."
    )
    result = qa(question=question)
    print(result.answer)

    # Optional: debug CodexExecLM history
    if getattr(lm, "history", None):
        last = lm.history[-1]
        if isinstance(last, dict):
            print("\n--- Debug: History ---")
            print("Model:", last.get("model"))
            print("Usage:", last.get("usage"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
