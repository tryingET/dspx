"""Typer registration for the receipt-bound foundry comparison-jury command."""

from __future__ import annotations

import json
from pathlib import Path

import typer


def register_foundry_jury_command(app: typer.Typer) -> None:
    @app.command("jury-foundry-gepa-comparison")
    def jury_foundry_gepa_comparison(
        receipt: Path = typer.Option(
            ...,
            "--receipt",
            help="Canonical successful foundry GEPA consumption-receipt.json",
        ),
        provider: str = typer.Option(
            ...,
            "--provider",
            help=(
                "Explicit provider for program-specific juror calls; task-local "
                "families: foundry-dspy-lm-auth-codex, "
                "foundry-dspy-lm-auth-github-copilot, foundry-dspy-lm-auth-xai, "
                "foundry-dspy-lm-auth-local-vllm (endpoint from "
                "DSPX_LOCAL_VLLM_BASE_URL, default http://127.0.0.1:2456/v1)"
            ),
        ),
        adjudicator_id: str = typer.Option(
            "local_foundry_adjudicator",
            "--adjudicator-id",
            help="Local downstream adjudicator id recorded without transition authority",
        ),
        adjudicator_kind: str = typer.Option(
            "local_foundry_adjudicator",
            "--adjudicator-kind",
            help="Local downstream adjudicator kind",
        ),
        adjudicator_repo: str | None = typer.Option(
            None,
            "--adjudicator-repo",
            help="Owning repo for downstream adjudication, when known",
        ),
        max_jurors: int | None = typer.Option(
            None,
            "--max-jurors",
            help="Optional positive bound on selected program-specific jurors",
        ),
        owner_source_root: Path | None = typer.Option(
            None,
            "--owner-source-root",
            help="Exact maintained dspy-lm-auth source root for the task-local provider",
        ),
        execution_task_id: int | None = typer.Option(
            None,
            "--execution-task-id",
            help="Claimed DSPx AK task revalidated before every task-local provider call",
        ),
        execution_claimant: str | None = typer.Option(
            None,
            "--execution-claimant",
            help="Exact AK claimed_by identity required for every task-local provider call",
        ),
        model: str | None = typer.Option(
            None,
            "--model",
            help=(
                "Reviewed model for the task-local provider family "
                "(Codex default gpt-5.4; GitHub Copilot default gemini-3.7-flash; "
                "xAI default grok-4.6; local vLLM default "
                "local/Qwen3.8-27B-AEON-NVFP4-FP8)"
            ),
        ),
        codex_model: str | None = typer.Option(
            None,
            "--codex-model",
            help="Codex-family alias of --model (foundry-dspy-lm-auth-codex only)",
        ),
        reasoning_effort: str | None = typer.Option(
            None,
            "--reasoning-effort",
            help=(
                "Bounded Codex reasoning effort (default xhigh); "
                "not applicable to the GitHub Copilot, xAI, or local vLLM families"
            ),
        ),
        json_out: bool = typer.Option(False, "--json", help="Print jury receipt JSON"),
    ) -> None:
        """Run one receipt-bound program-specific jury without transition authority."""
        from dspx.services.program_foundry_gepa_comparison_jury import (
            ProgramFoundryGepaComparisonJuryError,
            execute_program_foundry_gepa_comparison_jury,
        )

        try:
            payload = execute_program_foundry_gepa_comparison_jury(
                consumption_receipt_path=receipt,
                provider=provider,
                adjudicator_id=adjudicator_id,
                adjudicator_kind=adjudicator_kind,
                adjudicator_repo=adjudicator_repo,
                max_jurors=max_jurors,
                owner_source_root=owner_source_root,
                execution_task_id=execution_task_id,
                execution_claimant=execution_claimant,
                codex_model=codex_model,
                reasoning_effort=reasoning_effort,
                model=model,
            )
        except ProgramFoundryGepaComparisonJuryError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        except Exception as exc:
            typer.echo(
                "Error: one or more comparison-jury provider calls may have "
                f"occurred: {exc}",
                err=True,
            )
            raise typer.Exit(code=3) from exc
        if json_out:
            typer.echo(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            )
        else:
            typer.echo(str(receipt.parent / "comparison-jury-receipt.json"))
            typer.echo(f"foundry_gepa_comparison_jury_status: {payload.get('status')}")
        if payload.get("status") == "blocked_indeterminate":
            raise typer.Exit(code=3)
        if payload.get("status") != "ok":
            raise typer.Exit(code=1)
