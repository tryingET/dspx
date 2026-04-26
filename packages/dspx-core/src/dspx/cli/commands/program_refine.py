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


@app.command("compare-candidates")
def compare_candidates(
    source_manifest: Path = typer.Option(
        ...,
        "--source-manifest",
        help="Path to source program-candidate-assembly-v1 manifest.json",
    ),
    candidate_manifest: Path = typer.Option(
        ...,
        "--candidate-manifest",
        help="Path to refinement candidate program-candidate-assembly-v1 manifest.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local candidate comparison sidecar should be written",
    ),
    refinement_proposal: Path | None = typer.Option(
        None,
        "--refinement-proposal",
        help="Optional program-refinement-proposal-v1 lineage input",
    ),
    decision_record: Path | None = typer.Option(
        None,
        "--decision-record",
        help="Optional program-promotion-decision-record-v1 lineage input",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print comparison JSON"),
) -> None:
    """Compare existing source and refinement candidates without authority effects."""
    from dspx.services.program_refinement_comparison import (
        ProgramRefinementComparisonError,
        build_program_refinement_candidate_comparison,
        write_program_refinement_candidate_comparison,
    )

    try:
        comparison = build_program_refinement_candidate_comparison(
            source_manifest_path=source_manifest,
            candidate_manifest_path=candidate_manifest,
            refinement_proposal_path=refinement_proposal,
            decision_record_path=decision_record,
        )
        payload = write_program_refinement_candidate_comparison(comparison, out)
    except ProgramRefinementComparisonError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program refinement candidate comparison failed: {exc}",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("generate-candidate")
def generate_candidate(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to source program-gen manifest.json",
    ),
    refinement_proposal: Path = typer.Option(
        ...,
        "--refinement-proposal",
        help="Path to program-refinement-proposal-v1 JSON",
    ),
    decision_record: Path = typer.Option(
        ...,
        "--decision-record",
        help="Path to local program-promotion-decision-record-v1 JSON",
    ),
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        help="Directory where the second candidate assembly is materialized",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print candidate result JSON"),
) -> None:
    """Generate one explicit local second candidate from a request-more-evidence path."""
    from dspx.services.program_refinement_candidate import (
        ProgramRefinementCandidateError,
        materialize_refinement_candidate,
    )

    try:
        payload = materialize_refinement_candidate(
            manifest_path=manifest,
            refinement_proposal_path=refinement_proposal,
            decision_record_path=decision_record,
            outdir=outdir,
        )
    except ProgramRefinementCandidateError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program refinement candidate generation failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(outdir.expanduser().resolve()))
