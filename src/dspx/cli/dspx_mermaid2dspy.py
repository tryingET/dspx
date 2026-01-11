from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sys
import subprocess

from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env
from dspx.services.signatures_service import run_generate as service_generate
from dspx.services.mermaid_workflow_service import parse_mermaid, Node
from dspx.dtos import ProgramGraphSpec, ProgramArtifact


def _read_input(path: Optional[str]) -> str:
    if path and path != "-":
        return Path(path).read_text(encoding="utf-8")
    import sys

    data = sys.stdin.read()
    if not data:
        raise SystemExit("No Mermaid input provided. Pass --file or pipe via stdin.")
    return data


def _class_header(name: str, label: str, nid: str) -> str:
    # Prompt for vibe-dspy SignatureGenerator; we constrain the shape to be stable.
    return (
        "Create a DSPy Signature class for a workflow step.\n"
        f"Step ID: {nid}\n"
        f"Step Label: {label}\n\n"
        "Requirements:\n"
        f"- Class name MUST be {name}.\n"
        "- Inherit from dspy.Signature.\n"
        "- Use dspy.InputField for inputs and dspy.OutputField for outputs.\n"
        "- Inputs: context: str (upstream context)\n"
        "- Outputs: output: str (result of this step)\n"
        "- Include a clear docstring.\n"
        "Output only Python code for the class (include import dspy if needed).\n"
    )


def _run_cli(module: str, args: List[str], env: Optional[dict] = None):
    proc = subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        env=env or os.environ.copy(),
    )
    return proc.returncode, proc.stdout, proc.stderr


def _build_signatures(
    nodes: Dict[str, Node],
    *,
    use_cli: bool = False,
    refine: bool = False,
    refine_attempts: int = 3,
    provider: Optional[str] = None,
) -> Tuple[str, Dict[str, str]]:
    """Generate a signatures.py module and return (source, mapping nid->class)."""
    parts: List[str] = []
    mapping: Dict[str, str] = {}
    for nid, n in nodes.items():
        if n.type == "decision":
            continue
        cls = f"Sig_{nid}"
        prompt = _class_header(cls, n.label or nid, nid)
        if use_cli:
            env = os.environ.copy()
            if provider:
                env["DSPX_PROVIDER"] = provider
            if refine:
                rc, out, err = _run_cli(
                    "dspx.cli.viberefine",
                    (["--non-interactive", "-n", str(refine_attempts), prompt]),
                    env,
                )
            else:
                rc, out, err = _run_cli("dspx.cli.vibegen", ([prompt]), env)
            if rc != 0:
                raise SystemExit(
                    f"CLI generation failed for {nid}: {err.strip()}\nPrompt was: {prompt}"
                )
            code = out
        else:
            code = service_generate(prompt)
        # Ensure class name matches (fallback if generator changed it)
        m = re.search(
            r"class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*dspy\.Signature\s*\)", code
        )
        if not m or m.group(1) != cls:
            # Minimal fix: prepend a correct class stub if generator missed it
            stub = (
                "import dspy\n\n"
                f"class {cls}(dspy.Signature):\n"
                '    """Auto-generated fallback signature.\n'
                "    NOTE: Generator did not return the expected class name; using fallback.\n"
                '    """\n'
                "    context: str = dspy.InputField(desc='Upstream context for this step')\n"
                "    output: str = dspy.OutputField(desc='Result of this step')\n"
            )
            code = stub
        parts.append(code.strip() + "\n")
        mapping[nid] = cls
    src = "\n\n".join(parts)
    if not src.lstrip().startswith("import dspy"):
        src = "import dspy\n\n" + src
    return src, mapping


def _emit_program(
    name: str, nodes: Dict[str, Node], edges: List[dict], mapping: Dict[str, str]
) -> str:
    # Graph literal
    node_lines = []
    for nid, n in nodes.items():
        node_lines.append(
            f"        '{nid}': dict(id='{n.id}', label={n.label!r}, type='{n.type}'),"
        )
    edge_lines = []
    for e in edges:
        el = e.get("label")
        edge_lines.append(
            f"        dict(src='{e['src']}', dst='{e['dst']}', label={el!r}),"
        )

    # Signature mapping literal
    map_lines = []
    for nid, cls in mapping.items():
        map_lines.append(f"    '{nid}': {cls},")

    return "\n".join(
        [
            "from __future__ import annotations",
            "import os",
            "from typing import Dict, List, Optional, Type",
            "import dspy",
            "from dspx.config_loader import load_config_env",
            "from dspx.tracing import enable_mlflow_from_env",
            "from dspx.provider_registry import create_from_env, ensure_default_providers",
            "from signatures import *",
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
            "GRAPH = (",
            "    {",
            *node_lines,
            "    },",
            "    [",
            *edge_lines,
            "    ],",
            ")",
            "",
            "SIGS: Dict[str, Type[dspy.Signature]] = {",
            *map_lines,
            "}",
            "",
            "def _normalize(s: str) -> str:",
            "    return ''.join(ch.lower() for ch in s if ch.isalnum())",
            "",
            "def _sources(nodes: Dict[str, dict], edges: List[dict]) -> List[str]:",
            "    indeg = {k: 0 for k in nodes}",
            "    for e in edges:",
            "        indeg[e['dst']] = indeg.get(e['dst'], 0) + 1",
            "    return [k for k,v in indeg.items() if v == 0]",
            "",
            "def step_process(nid: str, label: str, context: str) -> str:",
            "    Sig = SIGS.get(nid)",
            "    if Sig is None:",
            "        # Fallback: generic 1→1 signature",
            "        mod = dspy.Predict('context -> output')",
            "        pred = mod(context=context)",
            "        return getattr(pred, 'output', str(pred))",
            "    mod = dspy.Predict(Sig)",
            "    pred = mod(context=context)",
            "    return getattr(pred, 'output', str(pred))",
            "",
            "def step_decision(instruction: str, input: str) -> str:",
            "    mod = dspy.Predict('instruction, input -> decision')",
            "    pred = mod(instruction=instruction + ' (respond with a short decision label)', input=input)",
            "    return getattr(pred, 'decision', str(pred))",
            "",
            "def run_workflow(initial_input: str = '') -> Dict[str, str]:",
            "    nodes, edges = GRAPH",
            "    ctx: Dict[str, str] = {}",
            "    pending: List[str] = _sources(nodes, edges)",
            "    seen: Dict[str, int] = {k: 0 for k in nodes}",
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
            "            out = step_process(nid, node['label'], input_text)",
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


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate DSPy program from Mermaid using vibe-dspy signatures (one per node)"
    )
    ap.add_argument("--file", "-f", help="Path to Mermaid file, or '-' to read stdin")
    ap.add_argument("--name", "-n", help="Workflow name (slug)")
    ap.add_argument(
        "--outdir", "-o", help="Output dir (defaults to generated/workflows/<name>)"
    )
    ap.add_argument("--provider", help="Provider name (registry), e.g., codex-exec")
    ap.add_argument(
        "--use-cli",
        action="store_true",
        help="Use CLI tools (vibegen/viberefine) instead of service calls",
    )
    ap.add_argument(
        "--refine",
        action="store_true",
        help="Use viberefine (non-interactive) for signatures",
    )
    ap.add_argument(
        "--refine-attempts",
        type=int,
        default=3,
        help="Attempts for viberefine when --refine is set",
    )
    args = ap.parse_args(argv)

    load_config_env()
    enable_mlflow_from_env()

    if args.provider:
        os.environ["DSPX_PROVIDER"] = args.provider

    diagram = _read_input(args.file)
    nodes, edges = parse_mermaid(diagram)
    if not nodes:
        raise SystemExit("No nodes parsed from Mermaid input.")

    base = args.name or "workflow_vibe"
    out_root = Path(args.outdir or (Path.cwd() / "generated" / "workflows" / base))
    out_root.mkdir(parents=True, exist_ok=True)

    # Build signatures.py
    sig_src, mapping = _build_signatures(
        nodes,
        use_cli=args.use_cli,
        refine=args.refine,
        refine_attempts=args.refine_attempts,
        provider=args.provider,
    )
    (out_root / "signatures.py").write_text(sig_src, encoding="utf-8")

    # Emit program that imports signatures
    prog_src = _emit_program(
        base,
        nodes,
        [e.__dict__ for e in edges],
        mapping,
    )
    (out_root / "program_sigpredict.py").write_text(prog_src, encoding="utf-8")

    # Save Mermaid source
    (out_root / "workflow.mmd").write_text(diagram, encoding="utf-8")

    print("Generated:")
    print(" -", out_root / "signatures.py")
    print(" -", out_root / "program_sigpredict.py")
    print(" -", out_root / "workflow.mmd")
    # Write manifest with content hashes
    try:
        from dspx.cache import sha256_text
        import json as _json

        files = {
            "signatures.py": sha256_text(sig_src),
            "program_sigpredict.py": sha256_text(prog_src),
            "workflow.mmd": sha256_text(diagram),
        }
        manifest = {
            "name": base,
            "files": files,
            "generator": "dspx_mermaid2dspy",
        }
        (out_root / "manifest.json").write_text(
            _json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
    # MLflow: attach artifacts and tags (best-effort)
    try:
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        mlflow = get_mlflow()
        if mlflow is not None:
            # Ensure a run is active and attach standard tags (includes run_group)
            ensure_run_with_standard_tags("mermaid_sig", extra={"program_name": base})
            if mlflow.active_run() is not None:  # type: ignore[attr-defined]
                for fname in [
                    "signatures.py",
                    "program_sigpredict.py",
                    "workflow.mmd",
                    "manifest.json",
                    "program_graph.json",
                    "artifact.json",
                ]:
                    p = out_root / fname
                    if p.exists():
                        try:
                            mlflow.log_artifact(str(p))  # type: ignore[attr-defined]
                        except Exception:
                            pass
    except Exception:
        pass
    # Write program graph and artifact JSON
    try:
        import json as _json

        graph = ProgramGraphSpec(
            mermaid=diagram,
            name=base,
            nodes=[
                {k: getattr(n, k) for k in ("id", "label", "type")}
                for n in nodes.values()
            ],
            edges=[{k: getattr(e, k) for k in ("src", "dst", "label")} for e in edges],
        )
        (out_root / "program_graph.json").write_text(
            _json.dumps(graph.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        files_map = {
            "signatures.py": "signatures.py",
            "program_sigpredict.py": "program_sigpredict.py",
            "workflow.mmd": "workflow.mmd",
        }
        art = ProgramArtifact(
            name=base, files=files_map, metadata={"variants": ["program_sigpredict.py"]}
        )
        (out_root / "artifact.json").write_text(
            _json.dumps(art.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    print("\nRun:")
    print("  cd", out_root)
    print("  uv run python program_sigpredict.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
