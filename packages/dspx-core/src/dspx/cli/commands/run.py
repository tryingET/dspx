# summary: "Defines local receipt replay verification and execution-explanation commands."
# read_when:
#   - "Changing replay safety, receipt checks, deterministic execution, MLflow enrichment, or CLI reporting."

"""Run replay and explain commands.

Commands for replaying and explaining past executions from receipts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import typer


app = typer.Typer(no_args_is_help=True)


@app.command("replay")
def run_replay(
    from_: Path = typer.Option(
        ...,
        "--from",
        "-f",
        help="Path to run receipt (.meta.json)",
    ),
    check_only: bool = typer.Option(
        True,
        "--check-only/--no-check-only",
        help="Verify receipt/output/cache only (default: check-only)",
    ),
    replay_output: Path | None = typer.Option(
        None,
        "--to",
        help="New receipt-local output path (required with --no-check-only)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON report"),
) -> None:
    """Check a receipt or safely replay a supported deterministic local run."""
    from dspx.services.run_replay_service import (
        check_run_receipt,
        execute_run_receipt,
    )

    # Replay checks are local-only by contract.
    prev_mlflow_enable = os.getenv("MLFLOW_ENABLE")
    os.environ["MLFLOW_ENABLE"] = "0"

    try:
        if not check_only and replay_output is None:
            typer.echo("error: --to is required with --no-check-only", err=True)
            raise typer.Exit(code=2)
        if check_only and replay_output is not None:
            typer.echo("error: --to requires --no-check-only", err=True)
            raise typer.Exit(code=2)

        if check_only:
            report = check_run_receipt(from_)
        else:
            assert replay_output is not None
            report = execute_run_receipt(from_, replay_output)
        status = str(report.get("status") or "invalid")

        if json_out:
            typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"status: {status}")
            typer.echo(f"receipt: {report.get('receipt_path')}")
            run_kind = report.get("run_kind")
            if run_kind:
                typer.echo(f"run_kind: {run_kind}")
            output_path = report.get("output_path")
            if output_path:
                typer.echo(f"output: {output_path}")
            checks: dict[str, bool] = {}
            checks_raw = report.get("checks")
            if isinstance(checks_raw, dict):
                for name, value in checks_raw.items():
                    checks[str(name)] = bool(value)
            for name in sorted(checks.keys()):
                typer.echo(f"check.{name}: {'ok' if checks[name] else 'fail'}")
            execution = report.get("execution")
            if isinstance(execution, dict):
                replay_path = execution.get("replay_output")
                if replay_path:
                    typer.echo(f"execution.output: {replay_path}")
                evidence = execution.get("evidence")
                if evidence:
                    typer.echo(f"execution.evidence: {evidence}")
            for warning in report.get("warnings") or []:
                typer.echo(f"warn: {warning}")
            for error in report.get("errors") or []:
                typer.echo(f"error: {error}", err=True)

        if status in {"ok", "executed"}:
            return
        if status == "failed":
            raise typer.Exit(code=1)
        raise typer.Exit(code=2)
    finally:
        if prev_mlflow_enable is None:
            os.environ.pop("MLFLOW_ENABLE", None)
        else:
            os.environ["MLFLOW_ENABLE"] = prev_mlflow_enable


@app.command("explain")
def run_explain(
    from_: Path = typer.Option(
        ...,
        "--from",
        "-f",
        help="Path to run receipt (.meta.json)",
    ),
    with_mlflow: bool = typer.Option(
        False,
        "--with-mlflow",
        help="Best-effort MLflow enrichment (optional)",
    ),
    mlflow_remote_lookup: bool = typer.Option(
        False,
        "--mlflow-remote-lookup",
        help="Attempt bounded remote MLflow lookup when tracking URI is remote",
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON report"),
) -> None:
    """Explain a past execution with full context.

    Shows receipt details, replay checks, and optionally MLflow context.
    """
    from dspx.services.run_explain_service import explain_run_receipt

    prev_mlflow_enable = os.getenv("MLFLOW_ENABLE")
    if not with_mlflow:
        os.environ["MLFLOW_ENABLE"] = "0"

    try:
        report = explain_run_receipt(
            from_,
            with_mlflow=with_mlflow,
            mlflow_remote_lookup=mlflow_remote_lookup,
        )
        status = str(report.get("status") or "invalid")

        if json_out:
            typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"status: {status}")
            typer.echo(f"receipt: {report.get('receipt_path')}")

            local_facts: dict[str, Any] = {}
            local_facts_raw = report.get("local_facts")
            if isinstance(local_facts_raw, dict):
                for key, val in local_facts_raw.items():
                    local_facts[str(key)] = val

            for key in (
                "run_kind",
                "provider",
                "template_version",
                "output_path",
                "cache_file",
            ):
                val = local_facts.get(key)
                if val not in {None, ""}:
                    typer.echo(f"local.{key}: {val}")

            replay_checks_raw = report.get("replay_checks")
            replay_checks: dict[str, bool] = {}
            if isinstance(replay_checks_raw, dict):
                for key, val in replay_checks_raw.items():
                    replay_checks[str(key)] = bool(val)
            for key in sorted(replay_checks.keys()):
                typer.echo(f"replay.{key}: {'ok' if replay_checks[key] else 'fail'}")

            mlflow_ctx: dict[str, Any] = {}
            mlflow_ctx_raw = report.get("mlflow_context")
            if isinstance(mlflow_ctx_raw, dict):
                for key, val in mlflow_ctx_raw.items():
                    mlflow_ctx[str(key)] = val
            typer.echo(f"mlflow.mode: {mlflow_ctx.get('mode') or 'disabled'}")
            if with_mlflow:
                linked = mlflow_ctx.get("linked_runs")
                if isinstance(linked, list):
                    typer.echo(f"mlflow.linked_runs: {len(linked)}")

            for warning in report.get("warnings") or []:
                typer.echo(f"warn: {warning}")
            for err in report.get("errors") or []:
                typer.echo(f"error: {err}", err=True)

        if status == "invalid":
            raise typer.Exit(code=2)
    finally:
        if prev_mlflow_enable is None:
            os.environ.pop("MLFLOW_ENABLE", None)
        else:
            os.environ["MLFLOW_ENABLE"] = prev_mlflow_enable
