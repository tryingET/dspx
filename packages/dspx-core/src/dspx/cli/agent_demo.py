# summary: "Provides a minimal argparse entry point for running the DSPx ReAct agent service."
# read_when:
#   - "You are using or changing the standalone agent demo CLI."

from __future__ import annotations

import argparse
from typing import List, Optional

from dspx.services.agent_service import run as run_agent


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Run a minimal ReAct agent with optional tools"
    )
    p.add_argument("question", help="User question for the agent")
    p.add_argument(
        "--tools",
        help="Comma-separated tool names (e.g., retrieve_stub,python_exec_stub)",
    )
    p.add_argument("--provider", help="Provider name (registry), e.g., codex-exec")
    p.add_argument("--iters", type=int, default=3, help="Max ReAct iterations")
    args = p.parse_args(argv)

    # Optional provider override
    if args.provider:
        import os

        os.environ["DSPX_PROVIDER"] = args.provider

    tools = [s.strip() for s in args.tools.split(",")] if args.tools else []
    answer = run_agent(args.question, tools=tools, max_iters=args.iters)
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
