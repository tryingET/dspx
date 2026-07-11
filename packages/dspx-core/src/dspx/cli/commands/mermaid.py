# summary: "Implements Typer commands that turn Mermaid workflows into DSPy programs or signatures."
# read_when:
#   - "You are generating DSPy artifacts from Mermaid or changing Mermaid CLI options."

"""Mermaid workflow commands.

Commands for generating DSPy programs and signatures from Mermaid diagrams.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import typer

app = typer.Typer(no_args_is_help=True)


def _read_mermaid(path: Optional[Path]) -> str:
    """Read mermaid diagram from file or stdin."""
    if path and str(path) != "-":
        return Path(path).read_text(encoding="utf-8")
    data = sys.stdin.read()
    if not data:
        raise typer.Exit(code=2)
    return data


@app.command("gen")
def mermaid_gen(
    file: Optional[Path] = typer.Option(
        None, "--file", "-f", help="Mermaid file or - for stdin"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Workflow name (slug)"
    ),
    outdir: Optional[Path] = typer.Option(
        None, "--outdir", "-o", help="Output directory"
    ),
    variants: str = typer.Option(
        "predict,cot,react", "--variants", "-v", help="Comma list"
    ),
) -> None:
    """Generate DSPy programs from a Mermaid workflow diagram."""
    from dspx.services.mermaid_workflow_service import generate_programs

    diagram = _read_mermaid(file)
    vs = [v.strip() for v in variants.split(",") if v.strip()]
    produced = generate_programs(
        diagram, name=name, out_dir=str(outdir) if outdir else None, variants=vs
    )
    for p in produced:
        typer.echo(p)


@app.command("sig")
def mermaid_sig(
    file: Optional[Path] = typer.Option(
        None, "--file", "-f", help="Mermaid file or - for stdin"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Workflow name (slug)"
    ),
    outdir: Optional[Path] = typer.Option(
        None, "--outdir", "-o", help="Output directory"
    ),
    provider: Optional[str] = typer.Option(None, help="Provider name (registry)"),
    use_cli: bool = typer.Option(False, help="Use vibegen/viberefine CLIs"),
    refine: bool = typer.Option(False, help="Use non-interactive viberefine"),
    refine_attempts: int = typer.Option(3, help="Attempts for refine"),
) -> None:
    """Generate DSPy signatures from a Mermaid workflow diagram."""
    # Reuse existing canonical CLI implementation to avoid drift
    from dspx.cli import dspx_mermaid2dspy as legacy

    args: List[str] = []
    if file is not None:
        args.extend(["-f", str(file)])
    if name:
        args.extend(["-n", name])
    if outdir:
        args.extend(["-o", str(outdir)])
    if provider:
        args.extend(["--provider", provider])
    if use_cli:
        args.append("--use-cli")
    if refine:
        args.append("--refine")
        args.extend(["--refine-attempts", str(refine_attempts)])
    rc = legacy.main(args)
    raise typer.Exit(code=rc)
