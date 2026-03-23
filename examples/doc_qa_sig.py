# Auto-generated DSPy script (Codex Exec enabled)
import os
import dspy
from typing import Optional
from dspx.codex_exec_lm import CodexExecLM
from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env

# Load config.toml (MLflow + Codex defaults) and enable tracing if configured.
load_config_env()
enable_mlflow_from_env()

MODEL = os.getenv("CODEX_MODEL", "gpt-5")
lm = CodexExecLM(
    model_flag=MODEL,
    auto_mode=False,
    dangerously_bypass=True,
    reasoning_effort="minimal",
)
dspy.configure(lm=lm)


class DocumentQASignature(dspy.Signature):
    """Answers a user question using a set of provided documents, optionally limiting retrieval with top_k, and returns the answer, supporting source snippets, and a confidence score."""

    question: str = dspy.InputField(
        desc="The user question to be answered based on the provided documents"
    )
    documents: list[str] = dspy.InputField(
        desc="A list of document strings to search and ground the answer"
    )
    top_k: Optional[int] = dspy.InputField(
        desc="Maximum number of top relevant documents to consider; defaults to 5"
    )
    answer: str = dspy.OutputField(
        desc="The final answer synthesized from the most relevant documents"
    )
    sources: list[str] = dspy.OutputField(
        desc="The document excerpts or identifiers used to support the answer"
    )
    confidence: float = dspy.OutputField(
        desc="A score from 0.0 to 1.0 indicating confidence in the answer"
    )


def demo():
    # Minimal end-to-end example using the generated signature
    qa = dspy.Predict(DocumentQASignature)

    question = "What city is the capital of France?"
    documents = [
        "Paris is the capital and most populous city of France.",
        "Berlin is the capital of Germany.",
        "Madrid is the capital of Spain.",
    ]

    result = qa(question=question, documents=documents)

    print("Question:", question)
    print("Answer:", result.answer)
    try:
        print("Sources:", result.sources)
    except AttributeError:
        # If the model omitted sources, print a placeholder.
        print("Sources: []")
    try:
        print("Confidence:", result.confidence)
    except AttributeError:
        print("Confidence: N/A")


if __name__ == "__main__":
    demo()
