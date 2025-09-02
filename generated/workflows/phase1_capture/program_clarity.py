from __future__ import annotations
import os
from typing import Dict, List, Optional
import dspy
from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env
from dspx.provider_registry import create_from_env, ensure_default_providers

PROGRAM_NAME = 'phase1_capture'

def _configure_lm() -> None:
    load_config_env()
    enable_mlflow_from_env()
    ensure_default_providers()
    lm = create_from_env()
    dspy.configure(lm=lm)


GRAPH = (
    {
        'START': dict(id='START', label='[User has need]', type='process'),
        'CONV': dict(id='CONV', label='Discord Conversation', type='process'),
        'INIT_6E': dict(id='INIT_6E', label='Extract Initial 6 Elements', type='process'),
        'INTENT': dict(id='INTENT', label='Create Intent', type='process'),
        'end': dict(id='end', label='end', type='unknown'),
    },
    [
        dict(src='START', dst='CONV', label=None),
        dict(src='CONV', dst='INIT_6E', label=None),
        dict(src='INIT_6E', dst='INTENT', label=None),
    ],
)


# CLARITY variant using a custom DSPy Module
from dspx.programs.clarity import ClarityStep, ClarityDecision

def step_process(instruction: str, input: str) -> str:
    mod = ClarityStep(use_cot=True)
    pred = mod(instruction=instruction, input=input)
    return getattr(pred, 'yield_output', str(pred))

def step_decision(instruction: str, input: str) -> str:
    decider = ClarityDecision(use_cot=True)
    pred = decider(instruction=instruction, input=input)
    return getattr(pred, 'decision', str(pred))

from dspx.programs.sixe import SixEExtractor, SixEWriter, to_dict, to_summary
from dspx.storage.sql_store import ensure_schema, insert_six_e, get_db_url
from dspx.tools.registry import ensure_default_tools, get_tool
from dspx.conversation.discord_capture import capture_intent
def _normalize(s: str) -> str:
    return ''.join(ch.lower() for ch in s if ch.isalnum())

def _sources(nodes: Dict[str, dict], edges: List[dict]) -> List[str]:
    indeg = {k: 0 for k in nodes}
    for e in edges:
        indeg[e['dst']] = indeg.get(e['dst'], 0) + 1
    return [k for k,v in indeg.items() if v == 0]

def _is_6e_node(nid: str, label: str) -> bool:
    L = label.lower()
    return ('6 elements' in L) or ('6e' in L) or nid.upper().startswith('INIT_6E')

def _is_conv_node(nid: str, label: str) -> bool:
    L = label.lower()
    return ('conversation' in L) or ('capture' in L) or ('discord' in L)

def _is_intent_node(nid: str, label: str) -> bool:
    return 'intent' in label.lower()

def _build_context(base: str = '.') -> str:
    ensure_default_tools()
    parts = []
    # Repo
    try:
        repo = str(get_tool('repo_summary')(base))
        if repo.strip(): parts.append(repo)
    except KeyError:
        pass
    # DB
    try:
        dbs = str(get_tool('db_schema')())
        if dbs.strip(): parts.append(dbs)
    except KeyError:
        pass
    # KB
    try:
        kb = str(get_tool('kb_summary')(base))
        if kb.strip(): parts.append(kb)
    except KeyError:
        pass
    # Ontology
    try:
        onto = str(get_tool('ontology_summary')(base))
        if onto.strip(): parts.append(onto)
    except KeyError:
        pass
    return ('\n\n').join(parts)

def _handle_6e(workflow: str, nid: str, label: str, context: str) -> tuple[str, dict]:
    ensure_schema(get_db_url())
    # First, synthesize a compact 6E doc from intent+context
    # Then extract normalized fields for SQL.
    writer = SixEWriter(use_cot=True)
    # If 'context' already includes an 'Intent:' line, writer will use it; else it will derive from context
    draft = writer(intent='', context=context)
    doc = getattr(draft, 'sixe_doc', str(draft))
    extractor = SixEExtractor(use_cot=True)
    pred = extractor(context=doc)
    rec = to_dict(pred)
    insert_six_e(workflow=workflow, node_id=nid, node_label=label, record=rec, source_input=context, url=get_db_url())
    return to_summary(pred), rec

def _handle_conv(label: str, input_text: str) -> tuple[str, str]:
    # Merge user input with repo/DB/KB context, then capture intent from Discord transcript if provided.
    ctx_all = _build_context('.')
    convo = (input_text + ('\n' if input_text and ctx_all else '') + ctx_all).strip()
    intent, accepted = capture_intent(default_text=convo)
    if not accepted:
        # Gate: require acceptance; carry combined context forward to allow later retries.
        return convo, ''
    return convo, intent

def _handle_intent(label: str, context: str, extras: Dict[str, dict]) -> str:
    # If we already captured a fixed intent during conversation, pass it through.
    for v in extras.values():
        if isinstance(v, dict) and 'intent' in v:
            val = v['intent']
            if isinstance(val, str) and val.strip():
                return val
    # Fallback: naive intent from context.
    mod = dspy.Predict('context -> intent')
    pred = mod(context=context)
    return getattr(pred, 'intent', str(pred))

def run_workflow(initial_input: str = '') -> Dict[str, str]:
    nodes, edges = GRAPH
    ctx: Dict[str, str] = {}
    extras: Dict[str, dict] = {}
    pending: List[str] = _sources(nodes, edges)
    seen: Dict[str, int] = {k: 0 for k in nodes}

    while pending:
        nid = pending.pop(0)
        node = nodes[nid]
        incoming = [e for e in edges if e['dst'] == nid]
        parts = [ctx.get(e['src'], '') for e in incoming]
        input_text = ('\n'.join(p for p in parts if p).strip() or initial_input).strip()
        if node['type'] == 'decision':
            out = step_decision(node['label'], input_text)
            ctx[nid] = out
            outs = [e for e in edges if e['src'] == nid]
            if not outs:
                continue
            matched = None
            for e in outs:
                el = (e['label'] or '')
                if _normalize(el) and _normalize(el) in _normalize(out):
                    matched = e
                    break
            if matched is None:
                matched = outs[0]
            seen[matched['dst']] += 1
            if seen[matched['dst']] == len([x for x in edges if x['dst'] == matched['dst']]):
                pending.append(matched['dst'])
            continue
        else:
            if _is_conv_node(nid, node['label']):
                ctx_all = _build_context('.')
                combined = (input_text + ('\n' if input_text and ctx_all else '') + ctx_all).strip()
                out = combined or input_text
            elif _is_6e_node(nid, node['label']):
                summary, rec = _handle_6e(PROGRAM_NAME, nid, node['label'], input_text)
                out = summary
                # store structured 6E for downstream consumers like Intent
                extras.setdefault(nid, {})['sixe'] = rec
            elif _is_intent_node(nid, node['label']):
                out = _handle_intent(node['label'], input_text, extras)
            else:
                out = step_process(node['label'], input_text)
            ctx[nid] = out
            for e in [x for x in edges if x['src'] == nid]:
                seen[e['dst']] += 1
                if seen[e['dst']] == len([x for x in edges if x['dst'] == e['dst']]):
                    pending.append(e['dst'])
    return ctx

def main():
    _configure_lm()
    result = run_workflow(initial_input=os.getenv('WORKFLOW_INPUT', ''))
    for k, v in result.items():
        print(f'{k}: {v[:200]}')

if __name__ == '__main__':
    main()
