# summary: "Runs a minimal DSPy ReAct question-answering agent with optional registered tools."
# read_when:
#   - "Changing agent signatures, provider setup, tool resolution, iteration limits, or answer extraction."

from __future__ import annotations

from typing import List, Optional

import dspy

from ..provider_registry import create_from_env
from ..tools.registry import ensure_default_tools, get_tool
from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env


class AgentQuestionAnswer(dspy.Signature):
    """Answer a user question with optional tool use."""

    question: str = dspy.InputField(desc="user question")
    answer: str = dspy.OutputField(desc="agent answer")


def run(question: str, *, tools: Optional[List[str]] = None, max_iters: int = 3) -> str:
    """Run a minimal ReAct agent with optional tools.

    Returns the agent's answer text.
    """
    # Configure env + tracing
    load_config_env()
    enable_mlflow_from_env()

    # LM provider
    lm = create_from_env()
    dspy.configure(lm=lm)

    tool_fns = []
    if tools:
        ensure_default_tools()
        for name in tools:
            try:
                tool_fns.append(get_tool(name))
            except KeyError:
                # Skip unknown tool names
                continue

    agent = dspy.ReAct(AgentQuestionAnswer, tools=tool_fns, max_iters=max_iters)
    pred = agent(question=question)
    return getattr(pred, "answer", str(pred))
