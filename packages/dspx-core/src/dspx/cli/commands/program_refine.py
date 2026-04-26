from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True)


@app.command("propose")
def propose(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to program-gen manifest.json",
    ),
    oracle_report: Path = typer.Option(
        ...,
        "--oracle-report",
        help="Path to explicit Oracle program-evidence report JSON",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local refinement proposal artifact should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print proposal JSON"),
) -> None:
    """Propose a bounded program refinement without applying changes."""
    from dspx.services.program_refinement import (
        ProgramRefinementError,
        build_program_refinement_proposal,
        write_program_refinement_proposal,
    )

    try:
        proposal = build_program_refinement_proposal(
            manifest_path=manifest,
            oracle_report_path=oracle_report,
        )
        payload = write_program_refinement_proposal(proposal, out)
    except ProgramRefinementError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program refinement proposal failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))
