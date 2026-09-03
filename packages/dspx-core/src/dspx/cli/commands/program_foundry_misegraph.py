# summary: "Typer registration for `dspx foundry import-misegraph-evidence` (verified Misegraph package -> intent/inputs/binding bundle)."
# read_when:
#   - "Changing the CLI surface of the Misegraph evidence importer."

"""Typer registration for the Misegraph evidence importer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import typer


def register_foundry_import_misegraph_command(app: typer.Typer) -> None:
    @app.command("import-misegraph-evidence")
    def import_misegraph_evidence(
        package: Path = typer.Option(
            ...,
            "--package",
            help="misegraph-evidence-package-v1 directory (opened read-only, never written)",
        ),
        answers: Path = typer.Option(
            ...,
            "--answers",
            help=(
                "Operator-authored dspx-misegraph-example-answers-v1 JSON: "
                '{"schema_version": ..., "answers": {"<case-id>": "<expected answer>"}}'
            ),
        ),
        outdir: Path = typer.Option(
            ...,
            "--outdir",
            "-o",
            help=(
                "Directory receiving intent.json, inputs.json, "
                "misegraph-evidence-binding.json, misegraph-import-provenance.json "
                "(no-clobber; outside the package and any Misegraph repo)"
            ),
        ),
        case: Optional[List[str]] = typer.Option(
            None,
            "--case",
            help=(
                "Behavior case id to turn into an intent example (repeatable, ordered); "
                "default: render-text, check-json"
            ),
        ),
        json_out: bool = typer.Option(
            False, "--json", help="Print the import result JSON"
        ),
    ) -> None:
        """Verify a Misegraph evidence package and emit a foundry-ready intent bundle."""
        from dspx.services.program_foundry_misegraph_evidence import (
            MisegraphEvidenceImportError,
            write_import_bundle,
        )

        try:
            payload = write_import_bundle(
                package_dir=package,
                answers_path=answers,
                outdir=outdir,
                cases=list(case) if case else None,
            )
        except MisegraphEvidenceImportError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        except OSError as exc:
            typer.echo(f"Error: import bundle write failed: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        if json_out:
            typer.echo(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            )
        else:
            typer.echo(str(payload["intent_path"]))
            typer.echo(str(payload["inputs_path"]))
            typer.echo(str(payload["binding_path"]))
            typer.echo(f"import_misegraph_evidence_status: {payload.get('status')}")
