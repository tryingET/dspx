# Auto-generated DSPy script using the typed hard-cutover stub provider.
from typing import Optional

import dspy

from dspx.provider_registry import create

# The T2 support matrix is intentionally offline and stub-only.
dspy.configure(lm=create("stub"))


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
