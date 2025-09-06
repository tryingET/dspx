from __future__ import annotations
import os
from typing import Dict, List, Optional
import dspy
from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env
from dspx.provider_registry import create_from_env, ensure_default_providers

PROGRAM_NAME = "sample_flow3"


def _configure_lm() -> None:
    load_config_env()
    enable_mlflow_from_env()
    ensure_default_providers()
    lm = create_from_env()
    dspy.configure(lm=lm)


GRAPH = (
    {
        "A": dict(id="A", label="Start", type="process"),
        "B": dict(id="B", label="Is OK?", type="decision"),
        "C": dict(id="C", label="Do Thing", type="process"),
        "D": dict(id="D", label="Fix", type="process"),
        "E": dict(id="E", label="End", type="process"),
    },
    [
        dict(src="C", dst="E", label=None),
        dict(src="D", dst="E", label=None),
    ],
)


from dspx.tools.registry import ensure_default_tools, get_tool


def _react(tools: List[str]):
    ensure_default_tools()
    fns = []
    for t in tools:
        try:
            fns.append(get_tool(t))
        except KeyError:
            continue
    return dspy.ReAct("question -> answer", tools=fns, max_iters=3)


def step_process(instruction: str, input: str) -> str:
    agent = _react(["retrieve_stub", "python_exec_stub"])
    q = f"Step: {instruction}\nInput: {input}\nProduce the step output."
    pred = agent(question=q)
    return getattr(pred, "answer", str(pred))


def step_decision(instruction: str, input: str) -> str:
    agent = _react(["retrieve_stub"])
    q = f"Decision: {instruction}\nInput: {input}\nRespond with the chosen branch label only."
    pred = agent(question=q)
    return getattr(pred, "answer", str(pred))


def _normalize(s: str) -> str:
    return "".join(ch.lower() for ch in s if ch.isalnum())


def _sources(nodes: Dict[str, dict], edges: List[dict]) -> List[str]:
    indeg = {k: 0 for k in nodes}
    for e in edges:
        indeg[e["dst"]] = indeg.get(e["dst"], 0) + 1
    return [k for k, v in indeg.items() if v == 0]


def run_workflow(initial_input: str = "") -> Dict[str, str]:
    nodes, edges = GRAPH
    ctx: Dict[str, str] = {}
    pending: List[str] = _sources(nodes, edges)
    seen: Dict[str, int] = {k: 0 for k in nodes}

    while pending:
        nid = pending.pop(0)
        node = nodes[nid]
        incoming = [e for e in edges if e["dst"] == nid]
        parts = [ctx.get(e["src"], "") for e in incoming]
        input_text = ("\n".join(p for p in parts if p).strip() or initial_input).strip()
        if node["type"] == "decision":
            out = step_decision(node["label"], input_text)
            ctx[nid] = out
            outs = [e for e in edges if e["src"] == nid]
            if not outs:
                continue
            matched = None
            for e in outs:
                el = e["label"] or ""
                if _normalize(el) and _normalize(el) in _normalize(out):
                    matched = e
                    break
            if matched is None:
                matched = outs[0]
            seen[matched["dst"]] += 1
            if seen[matched["dst"]] == len(
                [x for x in edges if x["dst"] == matched["dst"]]
            ):
                pending.append(matched["dst"])
            continue
        else:
            out = step_process(node["label"], input_text)
            ctx[nid] = out
            for e in [x for x in edges if x["src"] == nid]:
                seen[e["dst"]] += 1
                if seen[e["dst"]] == len([x for x in edges if x["dst"] == e["dst"]]):
                    pending.append(e["dst"])
    return ctx


def main():
    _configure_lm()
    result = run_workflow(initial_input=os.getenv("WORKFLOW_INPUT", ""))
    for k, v in result.items():
        print(f"{k}: {v[:200]}")


if __name__ == "__main__":
    main()
