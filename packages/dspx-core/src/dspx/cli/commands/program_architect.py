from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(no_args_is_help=True)


@app.command("plan")
def plan(
    intent: Path = typer.Option(
        ...,
        "--intent",
        "-i",
        help="Path to a JSON/YAML one-intent program specification",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the non-authoritative architecture candidate plan should be written",
    ),
    portfolio_outdir: Path | None = typer.Option(
        None,
        "--portfolio-outdir",
        help="Optional directory for materializable candidate intent drafts only; does not materialize programs",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print plan JSON"),
) -> None:
    """Plan architecture candidates without materializing or promoting programs."""
    from dspx.services.program_architecture import (
        ProgramArchitectureError,
        build_program_architecture_candidates_from_path,
        write_architecture_intent_portfolio,
        write_program_architecture_candidates,
    )

    try:
        payload = build_program_architecture_candidates_from_path(intent)
        written = write_program_architecture_candidates(payload, out)
        if portfolio_outdir is not None:
            portfolio = write_architecture_intent_portfolio(written, portfolio_outdir)
            written = {
                **written,
                "portfolio": portfolio,
                "effect": {
                    **dict(written.get("effect") or {}),
                    "portfolio_materialized": True,
                    "candidate_materialized": False,
                },
            }
            written = write_program_architecture_candidates(written, out)
    except ProgramArchitectureError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program architecture planning failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("tournament")
def tournament(
    architecture_plan: Optional[Path] = typer.Option(
        None,
        "--architecture-plan",
        help="Path to a program-architecture-candidates-v1 plan JSON",
    ),
    intent: Optional[Path] = typer.Option(
        None,
        "--intent",
        "-i",
        help="Optional intent path; used to build an in-memory architecture plan when --architecture-plan is not supplied",
    ),
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        help="Directory where local candidate programs should be materialized",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the non-authoritative tournament sidecar should be written",
    ),
    candidate_ids: list[str] = typer.Option(
        [],
        "--candidate",
        help="Optional candidate id to materialize; may be supplied multiple times",
    ),
    with_oracle_reports: bool = typer.Option(
        False,
        "--with-oracle-reports",
        help="Write candidate-local Oracle indexes/reports for materialized candidates only",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print tournament JSON"),
) -> None:
    """Materialize planned architecture candidates locally and replay-check receipts."""
    from dspx.services.program_architecture_tournament import (
        ProgramArchitectureTournamentError,
        run_program_architecture_tournament_from_intent_path,
        run_program_architecture_tournament_from_plan_path,
        validate_program_architecture_tournament_output_path,
        write_program_architecture_tournament_result,
    )

    if architecture_plan is None and intent is None:
        typer.echo(
            "Error: either --architecture-plan or --intent is required", err=True
        )
        raise typer.Exit(code=2)
    if architecture_plan is not None and intent is not None:
        typer.echo("Error: use only one of --architecture-plan or --intent", err=True)
        raise typer.Exit(code=2)

    try:
        validate_program_architecture_tournament_output_path(out)
        if architecture_plan is not None:
            result = run_program_architecture_tournament_from_plan_path(
                architecture_plan,
                outdir=outdir,
                candidate_ids=candidate_ids,
                candidate_local_oracle=with_oracle_reports,
            )
        else:
            assert intent is not None
            result = run_program_architecture_tournament_from_intent_path(
                intent,
                outdir=outdir,
                candidate_ids=candidate_ids,
                candidate_local_oracle=with_oracle_reports,
            )
        written = write_program_architecture_tournament_result(result, out)
    except ProgramArchitectureTournamentError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program architecture tournament failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("loop")
def loop(
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        help="Directory where the guided architecture loop artifacts should be written",
    ),
    intent: Optional[Path] = typer.Option(
        None,
        "--intent",
        "-i",
        help="Path to an existing JSON/YAML program-intent-v2 file",
    ),
    prompt: Optional[str] = typer.Option(
        None,
        "--prompt",
        help="Natural-language program request to normalize and run through the architecture loop",
    ),
    request: Optional[Path] = typer.Option(
        None,
        "--request",
        help="Path to a text file containing a natural-language program request",
    ),
    name: Optional[str] = typer.Option(None, "--name", help="Optional program name"),
    input_field: list[str] = typer.Option(
        [],
        "--input",
        help="Explicit input field for prompt/request normalization; may repeat",
    ),
    output_field: list[str] = typer.Option(
        [],
        "--output",
        help="Explicit output field for prompt/request normalization; may repeat",
    ),
    metric: Optional[str] = typer.Option(None, "--metric", help="Optional metric"),
    candidate_ids: list[str] = typer.Option(
        [],
        "--candidate",
        help="Optional candidate id to materialize in the tournament; may repeat",
    ),
    with_oracle_reports: bool = typer.Option(
        False,
        "--with-oracle-reports",
        help="Write candidate-local Oracle indexes/reports for materialized candidates only",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print loop summary JSON"),
) -> None:
    """Run normalize -> plan -> tournament -> recommend as one local guided loop."""
    from dspx.cli.utils import ensure_env
    from dspx.services.program_architecture_workflow import (
        ProgramArchitectureWorkflowError,
        run_program_architecture_loop,
        write_program_architecture_loop_result,
    )

    try:
        ensure_env(None)
        payload = run_program_architecture_loop(
            outdir=outdir,
            intent=intent,
            prompt=prompt,
            request=request,
            name=name,
            inputs=input_field or None,
            outputs=output_field or None,
            metric=metric,
            candidate_ids=candidate_ids,
            with_oracle_reports=with_oracle_reports,
        )
        written = write_program_architecture_loop_result(
            payload,
            outdir.expanduser().resolve() / "program_architect_loop.json",
        )
    except ProgramArchitectureWorkflowError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program architecture loop failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str((outdir.expanduser().resolve() / "program_architect_loop.json")))


@app.command("recommend")
def recommend(
    tournament_sidecar: Path = typer.Option(
        ...,
        "--tournament",
        "--tournament-sidecar",
        help="Path to a program-architecture-tournament-v1 sidecar",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the non-authoritative recommendation sidecar should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print recommendation JSON"),
) -> None:
    """Recommend next moves from tournament evidence without selecting winners."""
    from dspx.services.program_architecture_recommendation import (
        ProgramArchitectureRecommendationError,
        build_program_architecture_recommendation_from_tournament,
        write_program_architecture_recommendation,
    )

    try:
        payload = build_program_architecture_recommendation_from_tournament(
            tournament_sidecar
        )
        written = write_program_architecture_recommendation(payload, out)
    except ProgramArchitectureRecommendationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program architecture recommendation failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))
