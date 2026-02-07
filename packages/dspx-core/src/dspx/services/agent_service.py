from __future__ import annotations

from typing import List, Optional

import dspy

from ..provider_registry import create_from_env, ensure_default_providers
from ..tools.registry import ensure_default_tools, get_tool
from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env


def run(question: str, *, tools: Optional[List[str]] = None, max_iters: int = 3) -> str:
    """Run a minimal ReAct agent with optional tools.

    Returns the agent's answer text.
    """
    # Configure env + tracing
    load_config_env()
    enable_mlflow_from_env()

    # LM provider
    ensure_default_providers()
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

    agent = dspy.ReAct("question -> answer", tools=tool_fns, max_iters=max_iters)
    pred = agent(question=question)
    return getattr(pred, "answer", str(pred))
