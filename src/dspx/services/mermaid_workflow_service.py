from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass
class Node:
    id: str
    label: str
    type: str  # process|decision|io|subroutine|unknown


@dataclass
class Edge:
    src: str
    dst: str
    label: Optional[str] = None


Graph = Tuple[Dict[str, Node], List[Edge]]


def _slug(s: str, n: int = 8) -> str:
    h = hashlib.sha1(s.encode("utf-8")).hexdigest()
    return h[:n]


def _clean_label(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def parse_mermaid(diagram: str) -> Graph:
    lines = []
    for raw in diagram.splitlines():
        t = raw.strip()
        if not t or t.startswith("%%"):
            continue
        if t.lower().startswith("graph ") or t.lower().startswith("flowchart "):
            continue
        lines.append(t)

    nodes: Dict[str, Node] = {}
    edges: List[Edge] = []

    def ensure_node(nid: str, label: Optional[str] = None, ntype: Optional[str] = None) -> None:
        if nid not in nodes:
            nodes[nid] = Node(id=nid, label=_clean_label(label or nid), type=ntype or "unknown")
        else:
            if label:
                nodes[nid].label = _clean_label(label)
            if ntype:
                nodes[nid].type = ntype

    # Patterns for inline node declarations
    # id[Label], id("Label"), id{Label}, id((Label)), id[[Label]] etc.
    node_pat = re.compile(
        r"(?P<id>[A-Za-z][A-Za-z0-9_]*)\s*"  # id
        r"("  # one of the bracketed label forms
        r"\(\((?P<io>[^)]*?)\)\)|"  # ((label))
        r"\((?P<round>[^)]*?)\)|"  # (label)
        r"\[\[(?P<sub>[^\]]*?)\]\]|"  # [[label]]
        r"\[(?P<square>[^\]]*?)\]|"  # [label]
        r"\{(?P<curly>[^}]*)\}"  # {label}
        r")"
    )

    # Edge pattern: A --> B, A --label--> B, A -.- B, etc.
    edge_pat = re.compile(
        r"(?P<src>[A-Za-z][A-Za-z0-9_]*)\s*"  # src id
        r"-[\-.=o]*>\s*"  # arrow
        r"(?P<dst>[A-Za-z][A-Za-z0-9_]*)"
    )
    edge_label_pat = re.compile(r"\|(?P<label>[^|]+?)\|")

    for line in lines:
        # Extract any inline node declarations first
        for m in node_pat.finditer(line):
            nid = m.group("id")
            label = None
            ntype = "unknown"
            if m.group("io") is not None:
                label = m.group("io")
                ntype = "io"
            elif m.group("round") is not None:
                label = m.group("round")
                ntype = "process"
            elif m.group("sub") is not None:
                label = m.group("sub")
                ntype = "subroutine"
            elif m.group("square") is not None:
                label = m.group("square")
                ntype = "process"
            elif m.group("curly") is not None:
                label = m.group("curly")
                ntype = "decision"
            ensure_node(nid, label, ntype)

        # Extract edges
        em = edge_pat.search(line)
        if em:
            src = em.group("src")
            dst = em.group("dst")
            lm = edge_label_pat.search(line)
            elabel = _clean_label(lm.group("label")) if lm else None
            ensure_node(src)
            ensure_node(dst)
            edges.append(Edge(src=src, dst=dst, label=elabel))
            continue

        # Standalone node definitions without edges
        m2 = re.match(r"^([A-Za-z][A-Za-z0-9_]*)$", line)
        if m2:
            ensure_node(m2.group(1))

    return nodes, edges


def _toposort(nodes: Dict[str, Node], edges: List[Edge]) -> List[str]:
    indeg: Dict[str, int] = {nid: 0 for nid in nodes}
    for e in edges:
        indeg[e.dst] = indeg.get(e.dst, 0) + 1
        indeg.setdefault(e.src, 0)
    q = [nid for nid, d in indeg.items() if d == 0]
    out: List[str] = []
    adj: Dict[str, List[str]] = {}
    for e in edges:
        adj.setdefault(e.src, []).append(e.dst)
    while q:
        cur = q.pop(0)
        out.append(cur)
        for v in adj.get(cur, []):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    return out if len(out) == len(nodes) else list(nodes.keys())


def _emit_graph_literal(nodes: Dict[str, Node], edges: List[Edge]) -> str:
    node_lines = []
    for nid, n in nodes.items():
        node_lines.append(
            f"        '{nid}': dict(id='{n.id}', label={n.label!r}, type='{n.type}'),"
        )
    edge_lines = []
    for e in edges:
        if e.label:
            edge_lines.append(
                f"        dict(src='{e.src}', dst='{e.dst}', label={e.label!r}),"
            )
        else:
            edge_lines.append(
                f"        dict(src='{e.src}', dst='{e.dst}', label=None),"
            )
    return (
        "GRAPH = (\n"
        "    {\n" + ("\n".join(node_lines) if node_lines else "") + "\n    },\n"
        "    [\n" + ("\n".join(edge_lines) if edge_lines else "") + "\n    ],\n"
        ")\n"
    )


def _emit_common_header(name: str) -> str:
    return "\n".join(
        [
            "from __future__ import annotations",
            "import os",
            "from typing import Dict, List, Optional",
            "import dspy",
            "from dspx.config_loader import load_config_env",
            "from dspx.tracing import enable_mlflow_from_env",
            "from dspx.provider_registry import create_from_env, ensure_default_providers",
            "",
            f"PROGRAM_NAME = {name!r}",
            "",
            "def _configure_lm() -> None:",
            "    load_config_env()",
            "    enable_mlflow_from_env()",
            "    ensure_default_providers()",
            "    lm = create_from_env()",
            "    dspy.configure(lm=lm)",
            "",
        ]
    )


def _emit_runtime() -> str:
    return "\n".join(
        [
            "from dspx.programs.sixe import SixEExtractor, SixEWriter, to_dict, to_summary",
            "from dspx.storage.sql_store import ensure_schema, insert_six_e, get_db_url",
            "from dspx.tools.registry import ensure_default_tools, get_tool",
            "from dspx.conversation.discord_capture import capture_intent",
            "def _normalize(s: str) -> str:",
            "    return ''.join(ch.lower() for ch in s if ch.isalnum())",
            "",
            "def _sources(nodes: Dict[str, dict], edges: List[dict]) -> List[str]:",
            "    indeg = {k: 0 for k in nodes}",
            "    for e in edges:",
            "        indeg[e['dst']] = indeg.get(e['dst'], 0) + 1",
            "    return [k for k,v in indeg.items() if v == 0]",
            "",
            "def _is_6e_node(nid: str, label: str) -> bool:",
            "    L = label.lower()",
            "    return ('6 elements' in L) or ('6e' in L) or nid.upper().startswith('INIT_6E')",
            "",
            "def _is_conv_node(nid: str, label: str) -> bool:",
            "    L = label.lower()",
            "    return ('conversation' in L) or ('capture' in L) or ('discord' in L)",
            "",
            "def _is_intent_node(nid: str, label: str) -> bool:",
            "    return 'intent' in label.lower()",
            "",
            "def _build_context(base: str = '.') -> str:",
            "    ensure_default_tools()",
            "    parts = []",
            "    # Repo",
            "    try:",
            "        repo = str(get_tool('repo_summary')(base))",
            "        if repo.strip(): parts.append(repo)",
            "    except KeyError:",
            "        pass",
            "    # DB",
            "    try:",
            "        dbs = str(get_tool('db_schema')())",
            "        if dbs.strip(): parts.append(dbs)",
            "    except KeyError:",
            "        pass",
            "    # KB",
            "    try:",
            "        kb = str(get_tool('kb_summary')(base))",
            "        if kb.strip(): parts.append(kb)",
            "    except KeyError:",
            "        pass",
            "    # Ontology",
            "    try:",
            "        onto = str(get_tool('ontology_summary')(base))",
            "        if onto.strip(): parts.append(onto)",
            "    except KeyError:",
            "        pass",
            "    return ('\\n\\n').join(parts)",
            "",
            "def _handle_6e(workflow: str, nid: str, label: str, context: str) -> tuple[str, dict]:",
            "    ensure_schema(get_db_url())",
            "    # First, synthesize a compact 6E doc from intent+context",
            "    # Then extract normalized fields for SQL.",
            "    writer = SixEWriter(use_cot=True)",
            "    # If 'context' already includes an 'Intent:' line, writer will use it; else it will derive from context",
            "    draft = writer(intent='', context=context)",
            "    doc = getattr(draft, 'sixe_doc', str(draft))",
            "    extractor = SixEExtractor(use_cot=True)",
            "    pred = extractor(context=doc)",
            "    rec = to_dict(pred)",
            "    insert_six_e(workflow=workflow, node_id=nid, node_label=label, record=rec, source_input=context, url=get_db_url())",
            "    return to_summary(pred), rec",
            "",
            "def _handle_conv(label: str, input_text: str) -> tuple[str, str]:",
            "    # Merge user input with repo/DB/KB context, then capture intent from Discord transcript if provided.",
            "    ctx_all = _build_context('.')",
            "    convo = (input_text + ('\\n' if input_text and ctx_all else '') + ctx_all).strip()",
            "    intent, accepted = capture_intent(default_text=convo)",
            "    if not accepted:",
            "        # Gate: require acceptance; carry combined context forward to allow later retries.",
            "        return convo, ''",
            "    return convo, intent",
            "",
            "def _handle_intent(label: str, context: str, extras: Dict[str, dict]) -> str:",
            "    # If we already captured a fixed intent during conversation, pass it through.",
            "    for v in extras.values():",
            "        if isinstance(v, dict) and 'intent' in v:",
            "            val = v['intent']",
            "            if isinstance(val, str) and val.strip():",
            "                return val",
            "    # Fallback: naive intent from context.",
            "    mod = dspy.Predict('context -> intent')",
            "    pred = mod(context=context)",
            "    return getattr(pred, 'intent', str(pred))",
            "",
            "def run_workflow(initial_input: str = '') -> Dict[str, str]:",
            "    nodes, edges = GRAPH",
            "    ctx: Dict[str, str] = {}",
            "    extras: Dict[str, dict] = {}",
            "    pending: List[str] = _sources(nodes, edges)",
            "    seen: Dict[str, int] = {k: 0 for k in nodes}",
            "",
            "    while pending:",
            "        nid = pending.pop(0)",
            "        node = nodes[nid]",
            "        incoming = [e for e in edges if e['dst'] == nid]",
            "        parts = [ctx.get(e['src'], '') for e in incoming]",
            "        input_text = ('\\n'.join(p for p in parts if p).strip() or initial_input).strip()",
            "        if node['type'] == 'decision':",
            "            out = step_decision(node['label'], input_text)",
            "            ctx[nid] = out",
            "            outs = [e for e in edges if e['src'] == nid]",
            "            if not outs:",
                "                continue",
            "            matched = None",
            "            for e in outs:",
            "                el = (e['label'] or '')",
            "                if _normalize(el) and _normalize(el) in _normalize(out):",
            "                    matched = e",
            "                    break",
            "            if matched is None:",
            "                matched = outs[0]",
            "            seen[matched['dst']] += 1",
            "            if seen[matched['dst']] == len([x for x in edges if x['dst'] == matched['dst']]):",
            "                pending.append(matched['dst'])",
            "            continue",
            "        else:",
            "            if _is_conv_node(nid, node['label']):",
            "                convo, intent_val = _handle_conv(node['label'], input_text)",
            "                if intent_val:",
            "                    convo = (convo + ('\\n' if convo else '') + f'Intent: {intent_val}').strip()",
            "                    extras.setdefault(nid, {})['intent'] = intent_val",
            "                out = convo or input_text",
            "            elif _is_6e_node(nid, node['label']):",
            "                summary, rec = _handle_6e(PROGRAM_NAME, nid, node['label'], input_text)",
            "                out = summary",
            "                # store structured 6E for downstream consumers like Intent",
            "                extras.setdefault(nid, {})['sixe'] = rec",
            "            elif _is_intent_node(nid, node['label']):",
            "                out = _handle_intent(node['label'], input_text, extras)",
            "            else:",
            "                out = step_process(node['label'], input_text)",
            "            ctx[nid] = out",
            "            for e in [x for x in edges if x['src'] == nid]:",
            "                seen[e['dst']] += 1",
            "                if seen[e['dst']] == len([x for x in edges if x['dst'] == e['dst']]):",
            "                    pending.append(e['dst'])",
            "    return ctx",
            "",
            "def main():",
            "    _configure_lm()",
            "    result = run_workflow(initial_input=os.getenv('WORKFLOW_INPUT', ''))",
            "    for k, v in result.items():",
            "        print(f'{k}: {v[:200]}')",
            "",
            "if __name__ == '__main__':",
            "    main()",
        ]
    )


def _emit_predict_impl() -> str:
    return "\n".join(
        [
            "class StepSignature(dspy.Signature):",
            "    instruction: str = dspy.InputField(desc='Step instruction or guidance')",
            "    input: str = dspy.InputField(desc='Primary input/context for the step')",
            "    output: str = dspy.OutputField(desc='Result of this step')",
            "",
            "def step_process(instruction: str, input: str) -> str:",
            "    mod = dspy.Predict(StepSignature)",
            "    pred = mod(instruction=instruction, input=input)",
            "    return getattr(pred, 'output', str(pred))",
            "",
            "def step_decision(instruction: str, input: str) -> str:",
            "    mod = dspy.Predict('instruction, input -> decision')",
            "    pred = mod(instruction=instruction + ' (respond with a short decision label)', input=input)",
            "    return getattr(pred, 'decision', str(pred))",
        ]
    )


def _emit_cot_impl() -> str:
    return "\n".join(
        [
            "class StepSignature(dspy.Signature):",
            "    instruction: str = dspy.InputField(desc='Step instruction or guidance')",
            "    input: str = dspy.InputField(desc='Primary input/context for the step')",
            "    output: str = dspy.OutputField(desc='Result of this step')",
            "",
            "def step_process(instruction: str, input: str) -> str:",
            "    mod = dspy.ChainOfThought(StepSignature)",
            "    pred = mod(instruction=instruction, input=input)",
            "    return getattr(pred, 'output', str(pred))",
            "",
            "def step_decision(instruction: str, input: str) -> str:",
            "    mod = dspy.ChainOfThought('instruction, input -> decision')",
            "    pred = mod(instruction=instruction + ' (respond with a short decision label)', input=input)",
            "    return getattr(pred, 'decision', str(pred))",
        ]
    )


def _emit_react_impl() -> str:
    return "\n".join(
        [
            "# ReAct variant (tools wiring omitted in this placeholder)",
            "def step_process(instruction: str, input: str) -> str:",
            "    return input",
            "",
            "def step_decision(instruction: str, input: str) -> str:",
            "    return 'Yes'",
        ]
    )


def generate_programs(diagram: str, *, name: Optional[str] = None, out_dir: Optional[str] = None, variants: Optional[Iterable[str]] = None) -> List[str]:
    nodes, edges = parse_mermaid(diagram)
    if not nodes:
        raise ValueError("No nodes parsed from Mermaid diagram")
    order = _toposort(nodes, edges)
    _ = order  # currently unused in codegen, but may be used later

    base = name or f"workflow_{_slug(diagram)}"
    out_root = Path(out_dir or (Path.cwd() / "generated" / "workflows" / base))
    out_root.mkdir(parents=True, exist_ok=True)

    graph_lit = _emit_graph_literal(nodes, edges)

    def build(impl: str, variant: str) -> str:
        parts = [
            _emit_common_header(base),
            graph_lit,
            impl,
            _emit_runtime(),
        ]
        code = "\n\n".join(parts) + ("\n" if not parts[-1].endswith("\n") else "")
        path = out_root / f"program_{variant}.py"
        path.write_text(code, encoding="utf-8")
        return str(path)

    selected = list(variants) if variants else ["predict", "cot", "react"]
    produced: List[str] = []
    for v in selected:
        v = v.strip().lower()
        if v == "predict":
            produced.append(build(_emit_predict_impl(), v))
        elif v == "cot":
            produced.append(build(_emit_cot_impl(), v))
        elif v == "react":
            produced.append(build(_emit_react2_impl(), v))
        elif v == "clarity":
            produced.append(build(_emit_clarity_impl(), v))
        else:
            continue
    # Write a brief README
    readme = []
    readme.append(f"# Generated DSPy Programs for {base}")
    readme.append("")
    readme.append("Variants:")
    for p in produced:
        readme.append(f"- {Path(p).name}")
    readme.append("")
    readme.append("Run example:")
    readme.append("```")
    readme.append(f"uv run python {Path(produced[0]).name}")
    readme.append("```")
    (out_root / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    # Also keep original Mermaid source
    (out_root / "workflow.mmd").write_text(diagram, encoding="utf-8")

    return produced


def _emit_react2_impl() -> str:
    return "\n".join(
        [
            "from dspx.tools.registry import ensure_default_tools, get_tool",
            "",
            "def _react(tools: List[str]):",
            "    ensure_default_tools()",
            "    fns = []",
            "    for t in tools:",
            "        try:",
            "            fns.append(get_tool(t))",
            "        except KeyError:",
            "            continue",
            "    return dspy.ReAct('question -> answer', tools=fns, max_iters=3)",
            "",
            "def step_process(instruction: str, input: str) -> str:",
            "    agent = _react(['retrieve_stub', 'python_exec_stub'])",
            "    q = f'Step: {instruction}\\nInput: {input}\\nProduce the step output.'",
            "    pred = agent(question=q)",
            "    return getattr(pred, 'answer', str(pred))",
            "",
            "def step_decision(instruction: str, input: str) -> str:",
            "    agent = _react(['retrieve_stub'])",
            "    q = f'Decision: {instruction}\\nInput: {input}\\nRespond with the chosen branch label only.'",
            "    pred = agent(question=q)",
            "    return getattr(pred, 'answer', str(pred))",
        ]
    )


def _emit_clarity_impl() -> str:
    return "\n".join(
        [
            "# CLARITY variant using a custom DSPy Module",
            "from dspx.programs.clarity import ClarityStep, ClarityDecision",
            "",
            "def step_process(instruction: str, input: str) -> str:",
            "    mod = ClarityStep(use_cot=True)",
            "    pred = mod(instruction=instruction, input=input)",
            "    return getattr(pred, 'yield_output', str(pred))",
            "",
            "def step_decision(instruction: str, input: str) -> str:",
            "    decider = ClarityDecision(use_cot=True)",
            "    pred = decider(instruction=instruction, input=input)",
            "    return getattr(pred, 'decision', str(pred))",
        ]
    )
