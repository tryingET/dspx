# Auto-generated DSPy script (Codex Exec enabled)
import os
from typing import Optional

import dspy

from dspx.codex_exec_lm import CodexExecLM

# Configure Codex Exec as the LM
MODEL = os.getenv("CODEX_MODEL", "gpt-5")
lm = CodexExecLM(
    model_flag=MODEL,
    auto_mode=True,
    dangerously_bypass=False,
    reasoning_effort="minimal",
)
dspy.configure(lm=lm)


class PythonCodeQa(dspy.Signature):
    """Defines a Q&A signature that accepts a natural language question and a Python code snippet, and returns a concise, accurate answer explaining the code or addressing the question, along with optional reasoning notes and confidence."""

    question: str = dspy.InputField(
        desc="Natural language question about the provided Python code"
    )
    code_snippet: str = dspy.InputField(
        desc="Python code snippet to analyze and answer questions about"
    )
    context_hints: Optional[str] = dspy.InputField(
        desc="Optional extra context (e.g., Python version, libraries, constraints)"
    )
    answer: str = dspy.OutputField(
        desc="Direct, concise answer to the question grounded in the code"
    )
    explanation: Optional[str] = dspy.OutputField(
        desc="Brief reasoning or step-by-step explanation supporting the answer"
    )
    confidence: Optional[float] = dspy.OutputField(
        desc="Confidence score in [0.0, 1.0] for the provided answer"
    )


def demo():
    # Example usage: fill in inputs for your signature
    # qa = dspy.Predict(YourSignatureClass)
    # result = qa(<your_input_fields>=...)  # TODO
    # print(result)
    pass


if __name__ == "__main__":
    demo()
