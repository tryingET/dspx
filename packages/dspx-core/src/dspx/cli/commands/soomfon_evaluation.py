"""CLI for the one-shot Soomfon DSPy 3.3 originals evaluation."""

from __future__ import annotations

import json

import typer

from dspx.cli.utils import sanitize_cli_error


app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("evaluate-originals")
def evaluate_originals(
    expected_contract_sha256: str = typer.Option(
        ...,
        "--expected-contract-sha256",
        help="Out-of-band independently reviewed SHA-256 of the frozen contract",
    ),
) -> None:
    """Consume the frozen six-case contract once under crash-durable custody."""
    from dspx.services.soomfon_evaluation_executor import (
        execute_soomfon_evaluation_suite,
    )

    try:
        payload = execute_soomfon_evaluation_suite(
            expected_contract_sha256=expected_contract_sha256
        )
    except Exception as exc:
        typer.echo(
            f"Error: Soomfon evaluation refused: {sanitize_cli_error(exc)}",
            err=True,
        )
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if payload.get("state") != "succeeded":
        raise typer.Exit(code=1)


__all__ = ["app"]
