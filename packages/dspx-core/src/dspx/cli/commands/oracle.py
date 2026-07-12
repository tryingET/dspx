# summary: "Defines Oracle CLI commands for indexing, searching, comparing, and publishing behavioral evidence."
# read_when:
#   - "Changing Oracle command surfaces, behavioral reports, contracts, publication preflights, or coordinate analysis."

"""Oracle CLI commands for behavioral intelligence.

The Oracle provides semantic coordinate space operations for understanding
and reasoning about DSPy program behavior.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import typer

if TYPE_CHECKING:
    from dspx.coordinates import (
        AttractorReport,
        ContractRegistry,
        CoordinateIndex,
        FrontierReport,
    )

app = typer.Typer(no_args_is_help=True)
program_evidence_app = typer.Typer(no_args_is_help=True)
autoresearch_evidence_app = typer.Typer(no_args_is_help=True)
adjudication_trace_app = typer.Typer(no_args_is_help=True)
app.add_typer(
    program_evidence_app,
    name="program-evidence",
    help="Program Oracle evidence reports",
)
app.add_typer(
    autoresearch_evidence_app,
    name="autoresearch-evidence",
    help="pi-autoresearch Oracle-ready evidence preflight",
)
app.add_typer(
    adjudication_trace_app,
    name="adjudication-trace",
    help="Program adjudication behavior trace publication",
)


def _load_indexable_v2_receipt(receipt_path: Path) -> tuple[dict[str, Any], str | None]:
    """Load a receipt for Oracle indexing and confine any output artifact read."""

    from dspx.run_receipts import load_run_receipt
    from dspx.security import confine_path

    receipt_data = load_run_receipt(receipt_path)
    if receipt_data is None:
        raise ValueError("receipt is not valid JSON object")
    if receipt_data.get("receipt_version") != "v2":
        raise ValueError("receipt_version must be v2 for Oracle indexing")

    output_content = None
    raw_output_path = str(receipt_data.get("output_path") or "").strip()
    if raw_output_path:
        output_path = confine_path(receipt_path.parent, raw_output_path)
        if output_path.exists() and output_path.is_file():
            output_content = output_path.read_text(encoding="utf-8", errors="replace")[
                :10000
            ]
    return receipt_data, output_content


@app.command("backend-status")
def oracle_backend_status(
    index_path: Optional[Path] = typer.Option(
        None,
        "--index-path",
        help="Path to coordinate index database",
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON report"),
) -> None:
    """Report the current Oracle storage/backend posture without mutations."""
    from dspx.services.oracle_backend_status import build_oracle_backend_status

    status = build_oracle_backend_status(index_path=index_path)
    if json_out:
        typer.echo(json.dumps(status, ensure_ascii=False, indent=2))
        return

    typer.echo("=== Oracle Backend Status ===\n")
    typer.echo(f"Status: {status['status']}")
    typer.echo(f"Index backend: {status['coordinate_index']['backend']}")
    typer.echo(f"Index path: {status['coordinate_index']['path']}")
    shared = status["shared_postgres_backend"]
    typer.echo(f"Shared Postgres supported: {shared['supported']}")
    typer.echo(f"Shared Postgres production ready: {shared['production_ready']}")
    typer.echo(
        "Shared publication config ready: "
        f"{shared['publication_config']['publication_ready_configured']}"
    )
    typer.echo(status["summary"])
    typer.echo(f"Next: {status['next_required_action']}")


@app.command("program-semantic-preflight")
def oracle_program_semantic_preflight(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Optional DSPx TOML configuration path",
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON report"),
) -> None:
    """Check program Oracle semantic configuration without making an LM call."""
    from dspx.config_loader import load_config_env
    from dspx.services.program_oracle_semantic_backend import (
        preflight_program_oracle_semantic_backend,
    )

    try:
        load_config_env(str(config) if config is not None else None)
        payload = preflight_program_oracle_semantic_backend().to_dict()
    except Exception as exc:
        typer.echo(f"Error: Oracle semantic preflight failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo("=== Program Oracle Semantic Preflight ===\n")
        typer.echo(f"Status: {payload['status']}")
        typer.echo(f"Backend: {payload['backend_kind']}")
        typer.echo(f"Preferred model: {payload['preferred_model']}")
        typer.echo(f"Configured provider: {payload['configured_provider'] or '-'}")
        typer.echo(f"Configured model: {payload['configured_model'] or '-'}")
        typer.echo("Live verified: false (preflight performs no semantic call)")
    if not payload["ready"]:
        raise typer.Exit(code=2)


@autoresearch_evidence_app.command("publish-preflight")
def oracle_autoresearch_evidence_publish_preflight(
    packet: Path = typer.Option(
        ...,
        "--packet",
        help="Path to autoresearch.oracle_evidence.v1 JSON packet",
    ),
    target: str = typer.Option(
        ...,
        "--target",
        help="Intended shared Oracle target, e.g. shared-postgres",
    ),
    publication_label: str = typer.Option(
        ...,
        "--publication-label",
        help="Publication label such as retained, rejected, or request_more_evidence",
    ),
    publisher_id: str = typer.Option(
        ...,
        "--publisher-id",
        help="Declared publisher/operator/session identity",
    ),
    publisher_role: str = typer.Option(
        ...,
        "--publisher-role",
        help="Declared publisher role such as operator or dspx_tooling",
    ),
    publisher_assertion: str = typer.Option(
        ...,
        "--publisher-assertion",
        help="Publisher custody assertion for the shared empirical publication request",
    ),
    redaction_status: str = typer.Option(
        ...,
        "--redaction-status",
        help="Redaction posture: checked, not_required, redacted, unknown, or contains_sensitive_material",
    ),
    retention_class: str = typer.Option(
        ...,
        "--retention-class",
        help="Retention class such as retained_behavior_memory",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local publication preflight packet should be written",
    ),
    authority_ref: str | None = typer.Option(
        None,
        "--authority-ref",
        help="Required for authority-mirror labels; opaque ref only, not authority mutation",
    ),
    publisher_secret_ref: list[str] = typer.Option(
        [],
        "--publisher-secret-ref",
        help="1Password op:// ref relevant to publisher custody; value is never resolved or persisted",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print preflight JSON"),
) -> None:
    """Write a local preflight packet for pi-autoresearch Oracle evidence."""
    from dspx.services.program_oracle_autoresearch import (
        AutoresearchOraclePublicationPreflightError,
        build_autoresearch_oracle_publication_preflight,
        write_autoresearch_oracle_publication_preflight,
    )

    try:
        preflight = build_autoresearch_oracle_publication_preflight(
            packet_path=packet,
            target=target,
            publication_label=publication_label,
            publisher_id=publisher_id,
            publisher_role=publisher_role,
            publisher_assertion=publisher_assertion,
            redaction_status=redaction_status,
            retention_class=retention_class,
            authority_ref=authority_ref,
            publisher_secret_refs=publisher_secret_ref,
        )
        payload = write_autoresearch_oracle_publication_preflight(preflight, out)
    except AutoresearchOraclePublicationPreflightError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: autoresearch Oracle publication preflight failed: {exc}",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@adjudication_trace_app.command("publish-preflight")
def oracle_adjudication_trace_publish_preflight(
    trace: Path = typer.Option(
        ...,
        "--trace",
        help="Path to program-adjudication-behavior-trace-v1 JSON",
    ),
    target: str = typer.Option(
        ...,
        "--target",
        help="Intended shared Oracle target, e.g. shared-postgres",
    ),
    publication_label: str = typer.Option(
        "adjudication_behavior_trace",
        "--publication-label",
        help="Publication label such as adjudication_behavior_trace or retained",
    ),
    publisher_id: str = typer.Option(
        ...,
        "--publisher-id",
        help="Declared publisher/operator/session identity",
    ),
    publisher_role: str = typer.Option(
        ...,
        "--publisher-role",
        help="Declared publisher role such as operator or dspx_tooling",
    ),
    publisher_assertion: str = typer.Option(
        ...,
        "--publisher-assertion",
        help="Publisher custody assertion for adjudication trace publication",
    ),
    redaction_status: str = typer.Option(
        ...,
        "--redaction-status",
        help="Redaction posture: checked, not_required, redacted, unknown, or contains_sensitive_material",
    ),
    retention_class: str = typer.Option(
        "retained_behavior_memory",
        "--retention-class",
        help="Retention class such as retained_behavior_memory",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local adjudication trace publication preflight should be written",
    ),
    authority_ref: str | None = typer.Option(
        None,
        "--authority-ref",
        help="Required for authority-mirror labels; opaque ref only, not authority mutation",
    ),
    publisher_secret_ref: list[str] = typer.Option(
        [],
        "--publisher-secret-ref",
        help="1Password op:// ref relevant to publisher custody; value is never resolved or persisted",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print preflight JSON"),
) -> None:
    """Write a local preflight packet for adjudication-trace publication."""
    from dspx.services.program_adjudication_publication import (
        ProgramAdjudicationPublicationError,
        build_adjudication_trace_publication_preflight,
        write_adjudication_trace_publication_preflight,
    )

    try:
        packet = build_adjudication_trace_publication_preflight(
            trace_path=trace,
            target=target,
            publication_label=publication_label,
            publisher_id=publisher_id,
            publisher_role=publisher_role,
            publisher_assertion=publisher_assertion,
            redaction_status=redaction_status,
            retention_class=retention_class,
            authority_ref=authority_ref,
            publisher_secret_refs=publisher_secret_ref,
        )
        payload = write_adjudication_trace_publication_preflight(packet, out)
    except ProgramAdjudicationPublicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: adjudication trace publication preflight failed: {exc}",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@adjudication_trace_app.command("publish")
def oracle_adjudication_trace_publish(
    preflight: Path = typer.Option(
        ...,
        "--preflight",
        help="Path to program-adjudication-trace-publication-preflight-v1 JSON",
    ),
    receipt_out: Path = typer.Option(
        ...,
        "--receipt-out",
        help="Path where the local adjudication trace publication receipt should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print receipt JSON"),
) -> None:
    """Explicitly publish preflighted adjudication traces to shared Oracle."""
    from dspx.services.program_adjudication_publication import (
        ProgramAdjudicationPublicationError,
        adjudication_trace_publication_input_paths,
        prepare_adjudication_trace_publication_receipt_output_path,
        publish_adjudication_trace_preflight,
        write_adjudication_trace_publication_receipt,
    )

    try:
        protected_input_paths = adjudication_trace_publication_input_paths(preflight)
        prepare_adjudication_trace_publication_receipt_output_path(
            receipt_out,
            preflight_path=preflight,
            protected_input_paths=protected_input_paths,
        )
        receipt = publish_adjudication_trace_preflight(preflight_path=preflight)
        payload = write_adjudication_trace_publication_receipt(
            receipt,
            receipt_out,
            extra_protected_paths=protected_input_paths,
        )
    except ProgramAdjudicationPublicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: adjudication trace publication failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(receipt_out.expanduser().resolve()))


@program_evidence_app.command("publish-preflight")
def oracle_program_evidence_publish_preflight(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to program-candidate-assembly-v1 manifest.json",
    ),
    target: str = typer.Option(
        ...,
        "--target",
        help="Intended shared Oracle target, e.g. shared-postgres",
    ),
    publication_label: str = typer.Option(
        ...,
        "--publication-label",
        help="Publication label such as retained, rejected, or request_more_evidence",
    ),
    publisher_id: str = typer.Option(
        ...,
        "--publisher-id",
        help="Declared publisher/operator/session identity",
    ),
    publisher_role: str = typer.Option(
        ...,
        "--publisher-role",
        help="Declared publisher role such as operator or dspx_tooling",
    ),
    publisher_assertion: str = typer.Option(
        ...,
        "--publisher-assertion",
        help="Publisher custody assertion for the shared empirical publication request",
    ),
    redaction_status: str = typer.Option(
        ...,
        "--redaction-status",
        help="Redaction posture: checked, not_required, redacted, unknown, or contains_sensitive_material",
    ),
    retention_class: str = typer.Option(
        ...,
        "--retention-class",
        help="Retention class such as retained_behavior_memory",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local publication preflight packet should be written",
    ),
    authority_ref: str | None = typer.Option(
        None,
        "--authority-ref",
        help="Required for authority-mirror labels; opaque ref only, not authority mutation",
    ),
    publisher_secret_ref: list[str] = typer.Option(
        [],
        "--publisher-secret-ref",
        help="1Password op:// ref relevant to publisher custody; value is never resolved or persisted",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print preflight JSON"),
) -> None:
    """Write a local shared-Oracle publication preflight packet without shared writes."""
    from dspx.services.program_oracle_publication_preflight import (
        ProgramOraclePublicationPreflightError,
        build_program_oracle_publication_preflight,
        write_program_oracle_publication_preflight,
    )

    try:
        packet = build_program_oracle_publication_preflight(
            manifest_path=manifest,
            target=target,
            publication_label=publication_label,
            publisher_id=publisher_id,
            publisher_role=publisher_role,
            publisher_assertion=publisher_assertion,
            redaction_status=redaction_status,
            retention_class=retention_class,
            authority_ref=authority_ref,
            publisher_secret_refs=publisher_secret_ref,
        )
        payload = write_program_oracle_publication_preflight(packet, out)
    except ProgramOraclePublicationPreflightError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program Oracle publication preflight failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@program_evidence_app.command("publish")
def oracle_program_evidence_publish(
    preflight: Path = typer.Option(
        ...,
        "--preflight",
        help="Path to program-oracle-shared-publication-preflight-v1 JSON",
    ),
    receipt_out: Path = typer.Option(
        ...,
        "--receipt-out",
        help="Path where the local shared-publication receipt should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print receipt JSON"),
) -> None:
    """Explicitly publish preflighted program evidence to shared Oracle."""
    from dspx.services.program_oracle_publication import (
        ProgramOraclePublicationError,
        prepare_program_oracle_publication_receipt_output_path,
        program_oracle_publication_input_paths,
        publish_program_oracle_preflight,
        write_program_oracle_publication_receipt,
    )

    try:
        protected_input_paths = program_oracle_publication_input_paths(preflight)
        protected_roots = tuple(
            path.parent
            for path in protected_input_paths
            if path.name == "manifest.json"
        )
        prepare_program_oracle_publication_receipt_output_path(
            receipt_out,
            preflight_path=preflight,
            protected_input_paths=protected_input_paths,
        )
        receipt = publish_program_oracle_preflight(preflight_path=preflight)
        payload = write_program_oracle_publication_receipt(
            receipt,
            receipt_out,
            extra_protected_paths=protected_input_paths,
            extra_protected_roots=protected_roots,
        )
    except ProgramOraclePublicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program Oracle publication failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(receipt_out.expanduser().resolve()))


@program_evidence_app.command("report")
def oracle_program_evidence_report(
    index_path: Optional[Path] = typer.Option(
        None,
        "--index-path",
        help="Path to coordinate index database",
    ),
    limit: int = typer.Option(
        1000,
        "--limit",
        help="Maximum number of program Oracle evidence records to read",
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON report"),
) -> None:
    """Report on indexed program Oracle evidence without authority effects."""
    from dspx.services.program_oracle_report import (
        build_program_oracle_evidence_report,
    )

    report = build_program_oracle_evidence_report(index_path=index_path, limit=limit)
    if json_out:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return

    typer.echo("=== Program Oracle Evidence Report ===\n")
    typer.echo(f"Status: {report['status']}")
    typer.echo(f"Index: {report['index_path']}")
    typer.echo(f"Records: {report['total_records']}")
    typer.echo(report["interpretation"]["summary"])


@app.command("branch")
def oracle_branch(
    branch: Optional[str] = typer.Argument(
        None,
        help="Behavioral branch to inspect; omit to list known branches",
    ),
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        help="Path to receipt file or directory (default: generated/)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON report"),
) -> None:
    """List behavioral branches or inspect one branch timeline."""
    from dspx.oracle_time_travel import (
        branch_report,
        format_branch_report,
        format_branch_summaries,
        load_receipt_records,
        summarize_branches,
    )

    records = load_receipt_records(path)
    if not records:
        typer.echo("Error: no receipt files found", err=True)
        raise typer.Exit(code=2)

    if branch is None:
        summaries = summarize_branches(records)
        payload = {"branches": [summary.to_dict() for summary in summaries]}
        if json_out:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            typer.echo(format_branch_summaries(summaries))
        return

    try:
        payload = branch_report(records, branch)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=2)

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(format_branch_report(payload))


@app.command("diff")
def oracle_diff(
    left_branch: str = typer.Argument(..., help="Left branch name"),
    right_branch: str = typer.Argument(..., help="Right branch name"),
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        help="Path to receipt file or directory (default: generated/)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON report"),
) -> None:
    """Compare two behavioral branches using receipt lineage metadata."""
    from dspx.oracle_time_travel import (
        diff_branches,
        format_diff_report,
        load_receipt_records,
    )

    records = load_receipt_records(path)
    if not records:
        typer.echo("Error: no receipt files found", err=True)
        raise typer.Exit(code=2)

    try:
        payload = diff_branches(records, left_branch, right_branch)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=2)

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(format_diff_report(payload))


@app.command("bisect")
def oracle_bisect(
    branch: str = typer.Argument(..., help="Behavioral branch to bisect"),
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        help="Path to receipt file or directory (default: generated/)",
    ),
    bad_outcome: list[str] = typer.Option(
        ["failure", "partial"],
        "--bad-outcome",
        help="Outcome values treated as the bad side of the boundary",
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON report"),
) -> None:
    """Find the first bad behavioral boundary inside a branch."""
    from dspx.oracle_time_travel import (
        bisect_branch,
        format_bisect_report,
        load_receipt_records,
    )

    records = load_receipt_records(path)
    if not records:
        typer.echo("Error: no receipt files found", err=True)
        raise typer.Exit(code=2)

    try:
        payload = bisect_branch(records, branch, bad_outcomes=bad_outcome)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=2)

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(format_bisect_report(payload))


@app.command("index")
def oracle_index(
    from_mlflow: bool = typer.Option(
        False,
        "--from-mlflow",
        help="Index runs from MLflow tracking directory",
    ),
    from_receipts: bool = typer.Option(
        False,
        "--from-receipts",
        help="Index runs from .meta.json receipt files",
    ),
    from_program_evidence: bool = typer.Option(
        False,
        "--from-program-evidence",
        help="Index program-gen oracle_evidence.json files",
    ),
    since: str = typer.Option(
        "30d",
        "--since",
        help="Index runs from this duration ago (e.g., 30d, 7d, 24h)",
    ),
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        help="Path to MLflow tracking dir or receipts directory (default: generated/)",
    ),
    index_path: Optional[Path] = typer.Option(
        None,
        "--index-path",
        help="Path to coordinate index database (default: generated/oracle/coordinates.db)",
    ),
    limit: int = typer.Option(
        1000,
        "--limit",
        min=0,
        help="Maximum number of runs to index",
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON report"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show progress"),
) -> None:
    """Index existing runs into semantic coordinate space.

    Scans MLflow runs or receipt files and creates embeddings for each execution.
    """
    from dspx.coordinates import (
        CoordinateIndex,
        get_embedding_engine,
        parse_since,
        ParseSinceError,
    )

    # Catch parse_since errors
    try:
        since_dt = parse_since(since)
    except ParseSinceError as e:
        typer.echo(f"Error: Invalid --since value: {e}", err=True)
        raise typer.Exit(code=2)

    scanned = 0
    indexed = 0
    errors = 0
    skipped = 0
    error_details: list[dict[str, object]] = []

    if not from_mlflow and not from_receipts and not from_program_evidence:
        typer.echo(
            "Error: Specify --from-mlflow, --from-receipts, or --from-program-evidence",
            err=True,
        )
        raise typer.Exit(code=2)

    # Initialize index only after validating that an explicit mode was selected.
    index = CoordinateIndex(db_path=index_path)
    engine = get_embedding_engine()

    if from_receipts:
        # Scan for .meta.json files
        scan_path = path or Path.cwd() / "generated"
        if verbose:
            typer.echo(f"Scanning for receipts in {scan_path}", err=True)

        receipt_files = list(scan_path.rglob("*.meta.json"))
        if verbose:
            typer.echo(f"Found {len(receipt_files)} receipt files", err=True)

        for receipt_file in receipt_files[:limit]:
            scanned += 1
            try:
                receipt_data, output_content = _load_indexable_v2_receipt(receipt_file)

                # Check date filter
                created_at = receipt_data.get("created_at", "")
                if created_at:
                    try:
                        created_dt = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00")
                        )
                        if created_dt.tzinfo is None:
                            created_dt = created_dt.replace(tzinfo=timezone.utc)
                        if since_dt.tzinfo is None:
                            since_dt = since_dt.replace(tzinfo=timezone.utc)
                        if created_dt.astimezone(timezone.utc) < since_dt.astimezone(
                            timezone.utc
                        ):
                            skipped += 1
                            continue
                    except (ValueError, TypeError):
                        # Malformed or missing timestamp - proceed anyway
                        pass

                # Embed the receipt
                embedding = engine.embed_receipt(
                    receipt_data,
                    output_content=output_content,
                    receipt_path=receipt_file,
                )
                if embedding:
                    if index.upsert(embedding):
                        indexed += 1
                        if verbose and indexed % 50 == 0:
                            typer.echo(f"Indexed {indexed} runs...", err=True)
                    else:
                        errors += 1
                else:
                    skipped += 1

            except Exception as e:
                errors += 1
                error_details.append(
                    {
                        "path": str(receipt_file),
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )
                if verbose:
                    typer.echo(f"Error processing {receipt_file}: {e}", err=True)

    program_non_authority_confirmed: bool | None = None
    if from_program_evidence:
        from dspx.services.program_oracle_index import (
            index_program_oracle_evidence_path,
        )

        scan_path = path or Path.cwd() / "generated"
        if verbose:
            typer.echo(f"Scanning program Oracle evidence in {scan_path}", err=True)
        program_result = index_program_oracle_evidence_path(
            scan_path,
            index_path=index_path,
            limit=limit,
        )
        program_non_authority_confirmed = bool(
            program_result.get("non_authority_confirmed")
        )
        scanned += int(program_result.get("scanned") or 0)
        indexed += int(program_result.get("indexed") or 0)
        skipped += int(program_result.get("skipped") or 0)
        errors += int(program_result.get("errors") or 0)
        raw_error_details = program_result.get("error_details")
        if isinstance(raw_error_details, list):
            error_details.extend(
                item for item in raw_error_details if isinstance(item, dict)
            )

    if from_mlflow:
        # Import yaml once at the beginning
        try:
            import yaml  # noqa: F401
        except ImportError:
            typer.echo(
                "Error: --from-mlflow requires PyYAML. Install with: pip install pyyaml",
                err=True,
            )
            raise typer.Exit(code=2)

        # Scan MLflow tracking directory
        mlflow_path = path or Path.cwd() / "mlruns"
        if verbose:
            typer.echo(f"Scanning MLflow runs in {mlflow_path}", err=True)

        if mlflow_path.exists():
            for exp_dir in mlflow_path.iterdir():
                if not exp_dir.is_dir():
                    continue
                for run_dir in exp_dir.iterdir():
                    if not run_dir.is_dir():
                        continue

                    meta_file = run_dir / "meta.yaml"
                    if not meta_file.exists():
                        continue

                    try:
                        import yaml

                        # Parse MLflow run metadata
                        with open(meta_file) as f:
                            meta = yaml.safe_load(f)

                        # Check date
                        start_time = meta.get("start_time")
                        if start_time:
                            start_dt = datetime.fromtimestamp(
                                start_time / 1000, tz=timezone.utc
                            )
                            if start_dt < since_dt:
                                skipped += 1
                                continue

                        # Look for artifacts with receipts
                        artifacts_dir = run_dir / "artifacts"
                        if artifacts_dir.exists():
                            for artifact in artifacts_dir.rglob("*.meta.json"):
                                scanned += 1
                                try:
                                    receipt_data, output_content = (
                                        _load_indexable_v2_receipt(artifact)
                                    )
                                    embedding = engine.embed_receipt(
                                        receipt_data,
                                        output_content=output_content,
                                        receipt_path=artifact,
                                    )
                                    if embedding:
                                        if index.upsert(embedding):
                                            indexed += 1
                                        else:
                                            errors += 1
                                except (
                                    json.JSONDecodeError,
                                    OSError,
                                    KeyError,
                                    ValueError,
                                ) as e:
                                    # Malformed JSON, file read error, invalid receipt, or missing fields
                                    errors += 1
                                    error_details.append(
                                        {
                                            "path": str(artifact),
                                            "error": str(e),
                                            "error_type": type(e).__name__,
                                        }
                                    )

                    except Exception as e:
                        if verbose:
                            typer.echo(f"Error processing MLflow run: {e}", err=True)
                        errors += 1
                        error_details.append(
                            {
                                "path": str(run_dir),
                                "error": str(e),
                                "error_type": type(e).__name__,
                            }
                        )

                    if indexed >= limit:
                        break
                if indexed >= limit:
                    break

    stats = index.stats()

    result = {
        "scanned": scanned,
        "indexed": indexed,
        "errors": errors,
        "skipped": skipped,
        "error_details": error_details,
        "index_path": str(index.db_path),
        "index_stats": stats,
        "backend": engine.backend,
        "dimension": engine.dimension,
        "non_authority_confirmed": (
            bool(program_non_authority_confirmed) and errors == 0
            if from_program_evidence
            else errors == 0
        ),
    }

    if json_out:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"Indexed {indexed} runs ({errors} errors, {skipped} skipped)")
        typer.echo(f"Backend: {engine.backend}, Dimension: {engine.dimension}")
        typer.echo(f"Total in index: {stats['total']}")


@app.command("search")
def oracle_search(
    input_text: str = typer.Argument(..., help="Input text to search for"),
    top_k: int = typer.Option(5, "--top", "-n", help="Number of results"),
    run_kind: Optional[str] = typer.Option(None, "--kind", help="Filter by run kind"),
    provider: Optional[str] = typer.Option(
        None, "--provider", help="Filter by provider"
    ),
    since: Optional[str] = typer.Option(
        None, "--since", help="Filter by duration ago (e.g., 7d)"
    ),
    index_path: Optional[Path] = typer.Option(
        None, "--index-path", help="Path to coordinate index database"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON results"),
) -> None:
    """Search for similar past executions by input text."""
    from dspx.coordinates import CoordinateIndex, parse_since, ParseSinceError

    index = CoordinateIndex(db_path=index_path)

    since_dt = None
    if since:
        try:
            since_dt = parse_since(since)
        except ParseSinceError as e:
            typer.echo(f"Error: Invalid --since value: {e}", err=True)
            raise typer.Exit(code=2)

    results = index.search_by_text(
        input_text,
        top_k=top_k,
        run_kind=run_kind,
        provider=provider,
        since=since_dt,
    )

    if not results:
        typer.echo("No results found.")
        return

    if json_out:
        typer.echo(
            json.dumps(
                [r.to_dict() for r in results],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        typer.echo(f"Found {len(results)} similar executions:\n")
        for i, r in enumerate(results, 1):
            typer.echo(f"  [{i}] {r.run_id}")
            typer.echo(f"      Similarity: {r.similarity:.3f}")
            typer.echo(f"      Kind: {r.embedding.run_kind}")
            typer.echo(f"      Provider: {r.embedding.provider}")
            input_preview = r.embedding.input_text[:80]
            if len(r.embedding.input_text) > 80:
                input_preview += "..."
            typer.echo(f"      Input: {input_preview}")
            typer.echo("")


@app.command("neighbors")
def oracle_neighbors(
    run_id: str = typer.Argument(..., help="Run ID to find neighbors for"),
    top_k: int = typer.Option(5, "--top", "-n", help="Number of neighbors"),
    same_kind: bool = typer.Option(
        False, "--same-kind", help="Only include runs of same kind"
    ),
    same_provider: bool = typer.Option(
        False, "--same-provider", help="Only include runs from same provider"
    ),
    index_path: Optional[Path] = typer.Option(
        None, "--index-path", help="Path to coordinate index database"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON results"),
) -> None:
    """Show semantic neighbors of a specific run."""
    from dspx.coordinates import CoordinateIndex

    index = CoordinateIndex(db_path=index_path)

    # First check if run exists
    emb = index.get(run_id)
    if emb is None:
        typer.echo(f"Error: Run '{run_id}' not found in index.", err=True)
        raise typer.Exit(code=2)

    neighbors = index.get_neighbors(
        run_id,
        top_k=top_k,
        same_kind=same_kind,
        same_provider=same_provider,
    )

    if not neighbors:
        typer.echo("No neighbors found.")
        return

    if json_out:
        typer.echo(
            json.dumps(
                {
                    "run_id": run_id,
                    "neighbors": [r.to_dict() for r in neighbors],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        typer.echo(f"Neighbors of {run_id}:\n")
        typer.echo(f"  Run: {emb.run_kind} / {emb.provider}")
        input_preview = emb.input_text[:80]
        if len(emb.input_text) > 80:
            input_preview += "..."
        typer.echo(f"  Input: {input_preview}\n")

        for i, n in enumerate(neighbors, 1):
            typer.echo(f"  [{i}] {n.run_id}")
            typer.echo(f"      Distance: {n.distance:.3f}")
            typer.echo(f"      Kind: {n.embedding.run_kind}")
            input_preview = n.embedding.input_text[:60]
            if len(n.embedding.input_text) > 60:
                input_preview += "..."
            typer.echo(f"      Input: {input_preview}")
            typer.echo("")


@app.command("stats")
def oracle_stats(
    index_path: Optional[Path] = typer.Option(
        None, "--index-path", help="Path to coordinate index database"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show statistics about the coordinate index."""
    from dspx.coordinates import CoordinateIndex, get_embedding_engine

    index = CoordinateIndex(db_path=index_path)
    engine = get_embedding_engine()

    stats = index.stats()
    # Use index dimensions, not current engine dimension
    stats["engine_backend"] = engine.backend
    stats["engine_dimension"] = engine.dimension

    if json_out:
        typer.echo(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        typer.echo("=== Oracle Coordinate Index ===\n")
        typer.echo(f"Total runs: {stats['total']}")
        typer.echo(f"Engine backend: {stats['engine_backend']}")
        typer.echo(f"Engine dimension: {stats['engine_dimension']}")
        if stats.get("dimensions"):
            typer.echo(f"Index dimensions: {', '.join(map(str, stats['dimensions']))}")
        typer.echo(f"Schema version: {stats.get('schema_version', 'unknown')}")
        typer.echo(
            f"Embedding version: {stats.get('current_embedding_version', 'unknown')}"
        )

        if stats.get("by_run_kind"):
            typer.echo("\nBy run kind:")
            for kind, count in sorted(stats["by_run_kind"].items()):
                typer.echo(f"  {kind}: {count}")

        if stats.get("by_provider"):
            typer.echo("\nBy provider:")
            for provider, count in sorted(stats["by_provider"].items()):
                typer.echo(f"  {provider}: {count}")


@app.command("cluster")
def oracle_cluster(
    k: int = typer.Option(5, "-k", help="Number of clusters"),
    run_kind: Optional[str] = typer.Option(None, "--kind", help="Filter by run kind"),
    provider: Optional[str] = typer.Option(
        None, "--provider", help="Filter by provider"
    ),
    limit: int = typer.Option(500, "--limit", help="Max embeddings to cluster"),
    index_path: Optional[Path] = typer.Option(
        None, "--index-path", help="Path to coordinate index database"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Cluster executions into behavioral groups."""
    from dspx.coordinates import CoordinateIndex, cluster_from_index

    index = CoordinateIndex(db_path=index_path)

    clusters = cluster_from_index(
        index,
        k=k,
        run_kind=run_kind,
        provider=provider,
        limit=limit,
    )

    if not clusters:
        typer.echo("No clusters found (index may be empty).")
        return

    if json_out:
        typer.echo(
            json.dumps(
                [c.to_dict() for c in clusters],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        typer.echo(f"=== {len(clusters)} Behavioral Clusters ===\n")
        for cluster in clusters:
            typer.echo(f"Cluster {cluster.cluster_id}:")
            typer.echo(f"  Members: {cluster.member_count}")
            typer.echo(f"  Avg internal distance: {cluster.avg_internal_distance:.3f}")
            if cluster.dominant_run_kind:
                typer.echo(f"  Dominant kind: {cluster.dominant_run_kind}")
            if cluster.dominant_provider:
                typer.echo(f"  Dominant provider: {cluster.dominant_provider}")
            if cluster.sample_inputs:
                typer.echo("  Sample inputs:")
                for inp in cluster.sample_inputs[:3]:
                    preview = inp[:50]
                    if len(inp) > 50:
                        preview += "..."
                    typer.echo(f"    - {preview}")
            typer.echo("")


@app.command("drift")
def oracle_drift(
    run_id_a: str = typer.Argument(..., help="First run ID (baseline)"),
    run_id_b: str = typer.Argument(..., help="Second run ID (comparison)"),
    index_path: Optional[Path] = typer.Option(
        None, "--index-path", help="Path to coordinate index database"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Compute drift score between two executions."""
    from dspx.coordinates import CoordinateIndex, drift_score, classify_drift

    index = CoordinateIndex(db_path=index_path)

    emb_a = index.get(run_id_a)
    emb_b = index.get(run_id_b)

    if emb_a is None:
        typer.echo(f"Error: Run '{run_id_a}' not found.", err=True)
        raise typer.Exit(code=2)
    if emb_b is None:
        typer.echo(f"Error: Run '{run_id_b}' not found.", err=True)
        raise typer.Exit(code=2)

    drift = drift_score(emb_a, emb_b)
    classification = classify_drift(drift["overall"])

    result = {
        "baseline": run_id_a,
        "comparison": run_id_b,
        "classification": classification,
        **drift,
    }

    if json_out:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        typer.echo("=== Drift Analysis ===\n")
        typer.echo(f"Baseline: {run_id_a}")
        typer.echo(f"Comparison: {run_id_b}")
        typer.echo(f"\nClassification: {classification.upper()}")
        typer.echo("\nScores:")
        typer.echo(f"  Overall:    {drift['overall']:.3f}")
        typer.echo(f"  Input:      {drift['input_drift']:.3f}")
        typer.echo(f"  Output:     {drift['output_drift']:.3f}")
        typer.echo(f"  Config:     {drift['config_drift']:.3f}")
        typer.echo(f"  Vector:     {drift['vector_distance']:.3f}")


# =============================================================================
# Phase B Commands: Behavioral Topology
# =============================================================================


@app.command("territory")
def oracle_territory(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file for territory map (JSON)"
    ),
    k: int = typer.Option(10, "-k", help="Number of regions to create"),
    min_region_size: int = typer.Option(
        3, "--min-size", help="Minimum embeddings per region"
    ),
    index_path: Optional[Path] = typer.Option(
        None, "--index-path", help="Path to coordinate index database"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show details"),
) -> None:
    """Map behavioral space into regions (stable/unstable/unknown).

    Territory analysis reveals where the system is reliable vs. where
    it needs more testing or investigation.
    """
    from dspx.coordinates import CoordinateIndex, build_territory_map

    index = CoordinateIndex(db_path=index_path)
    territory = build_territory_map(index, k=k, min_region_size=min_region_size)

    if json_out or output:
        data = territory.to_dict()
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            typer.echo(f"Territory map saved to {output}")
        else:
            typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    # Human-readable output
    typer.echo("=== Behavioral Territory Map ===\n")
    typer.echo(f"Total embeddings: {territory.total_embeddings}")
    typer.echo(f"Total regions: {len(territory.regions)}")
    typer.echo(f"Coverage estimate: {territory.coverage:.1%}")
    typer.echo(f"Dimension: {territory.dimension}")
    typer.echo()

    # Summary by type
    stable = territory.get_stable_regions()
    unstable = territory.get_unstable_regions()
    unknown = territory.get_unknown_regions()
    danger = territory.get_danger_regions()

    typer.echo("Region Distribution:")
    typer.echo(f"  Stable:   {len(stable)} ({territory.stable_ratio:.1%})")
    typer.echo(f"  Unstable: {len(unstable)} ({territory.unstable_ratio:.1%})")
    typer.echo(f"  Unknown:  {len(unknown)} ({territory.unknown_ratio:.1%})")
    if danger:
        typer.echo(f"  Danger:   {len(danger)}")
    typer.echo()

    if verbose:
        # Show top regions by type
        if stable:
            typer.echo("Top Stable Regions:")
            for r in sorted(stable, key=lambda x: x.member_count, reverse=True)[:5]:
                typer.echo(
                    f"  {r.region_id}: {r.member_count} members, variance={r.internal_variance:.3f}"
                )
                if r.dominant_run_kind:
                    typer.echo(
                        f"    Kind: {r.dominant_run_kind}, Provider: {r.dominant_provider}"
                    )
            typer.echo()

        if unstable:
            typer.echo("Unstable Regions (need attention):")
            for r in sorted(unstable, key=lambda x: x.internal_variance, reverse=True)[
                :5
            ]:
                typer.echo(
                    f"  {r.region_id}: variance={r.internal_variance:.3f}, {r.member_count} members"
                )
            typer.echo()


# =============================================================================
# Contract Action Handlers (extracted for maintainability)
# =============================================================================


def _load_contract_registry(
    config_path: Optional[Path],
) -> tuple["ContractRegistry", Path]:
    """Load or create contract registry from config file.

    Returns tuple of (registry, config_file_path).
    """
    from dspx.coordinates import (
        ContractRegistry,
        load_contracts,
        create_default_contracts,
    )

    registry = ContractRegistry()
    config_file = config_path or (
        Path.cwd() / "generated" / "oracle" / "contracts.json"
    )

    if config_file.exists():
        contracts = load_contracts(config_file)
        for c in contracts:
            registry.add(c)
    else:
        for c in create_default_contracts():
            registry.add(c)

    return registry, config_file


def _contract_list(registry: "ContractRegistry", json_out: bool) -> None:
    """List all contracts in the registry."""
    contracts = registry.list_all()
    if json_out:
        typer.echo(
            json.dumps([c.to_dict() for c in contracts], ensure_ascii=False, indent=2)
        )
    else:
        typer.echo("=== Behavioral Contracts ===\n")
        for c in contracts:
            status = "✓" if c.enabled else "✗"
            typer.echo(f"  [{status}] {c.name}")
            typer.echo(f"      {c.description}")
            typer.echo(f"      Severity: {c.severity.value}")
            if c.tags:
                typer.echo(f"      Tags: {', '.join(c.tags)}")
            typer.echo()


def _contract_add(
    registry: "ContractRegistry",
    config_file: Path,
    name: str,
    description: Optional[str],
    invariant: Optional[str],
    severity: str,
    tags: Optional[str],
) -> None:
    """Add a new contract to the registry."""
    from dspx.coordinates import Contract, ContractSeverity, save_contracts

    contract = Contract(
        name=name,
        description=description or f"Contract: {name}",
        invariant=invariant or "Custom invariant",
        severity=ContractSeverity(severity),
        tags=tags.split(",") if tags else [],
    )
    registry.add(contract)
    save_contracts(registry.list_all(), config_file)
    typer.echo(f"Contract '{name}' added and saved to {config_file}")


def _contract_verify(
    registry: "ContractRegistry",
    index_path: Optional[Path],
    limit: int,
    tags: Optional[str],
    json_out: bool,
) -> None:
    """Verify contracts against embeddings in the index."""
    from dspx.coordinates import CoordinateIndex

    index = CoordinateIndex(db_path=index_path)
    tags_list = tags.split(",") if tags else None
    result = registry.verify_index(index, limit=limit, tags=tags_list)

    if json_out:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        typer.echo("=== Contract Verification ===\n")
        typer.echo(f"Total checks: {result['total_checks']}")
        typer.echo(f"  Pass:  {result['pass']}")
        typer.echo(f"  Fail:  {result['fail']}")
        typer.echo(f"  Skip:  {result['skip']}")
        typer.echo(f"  Error: {result['error']}")
        typer.echo()

        if result["violations"]:
            typer.echo("Violations by severity:")
            for sev, count in result["violations_by_severity"].items():
                typer.echo(f"  {sev}: {count}")

            if result["violations"][:5]:
                typer.echo("\nSample violations:")
                for v in result["violations"][:5]:
                    typer.echo(f"  - {v['contract_name']}: {v['message']}")


def _contract_set_enabled(
    registry: "ContractRegistry",
    config_file: Path,
    name: str,
    enabled: bool,
) -> None:
    """Enable or disable a contract by name."""
    from dspx.coordinates import save_contracts

    contract = registry.get(name)
    if contract:
        contract.enabled = enabled
        contract.updated_at = datetime.now(timezone.utc).isoformat()
        save_contracts(registry.list_all(), config_file)
        state = "enabled" if enabled else "disabled"
        typer.echo(f"Contract '{name}' {state}")
    else:
        typer.echo(f"Error: Contract '{name}' not found", err=True)
        raise typer.Exit(code=2)


@app.command("contract")
def oracle_contract(
    action: str = typer.Argument(
        "list", help="Action: list, add, verify, enable, disable"
    ),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Contract name"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Contract description"
    ),
    invariant: Optional[str] = typer.Option(
        None, "--invariant", help="Invariant expression"
    ),
    severity: str = typer.Option(
        "error", "--severity", help="Severity: info, warning, error, critical"
    ),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
    config_path: Optional[Path] = typer.Option(
        None, "--config", help="Path to contracts config file"
    ),
    index_path: Optional[Path] = typer.Option(
        None, "--index-path", help="Path to coordinate index database"
    ),
    limit: int = typer.Option(100, "--limit", help="Max embeddings to verify"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Manage and verify behavioral contracts.

    Contracts define invariants that should hold true across executions.
    """
    registry, config_file = _load_contract_registry(config_path)

    if action == "list":
        _contract_list(registry, json_out)

    elif action == "add":
        if not name:
            typer.echo("Error: --name is required for add", err=True)
            raise typer.Exit(code=2)
        _contract_add(
            registry, config_file, name, description, invariant, severity, tags
        )

    elif action == "verify":
        _contract_verify(registry, index_path, limit, tags, json_out)

    elif action == "enable":
        if not name:
            typer.echo("Error: --name is required", err=True)
            raise typer.Exit(code=2)
        _contract_set_enabled(registry, config_file, name, enabled=True)

    elif action == "disable":
        if not name:
            typer.echo("Error: --name is required", err=True)
            raise typer.Exit(code=2)
        _contract_set_enabled(registry, config_file, name, enabled=False)

    else:
        typer.echo(f"Error: Unknown action '{action}'", err=True)
        typer.echo("Valid actions: list, add, verify, enable, disable")
        raise typer.Exit(code=2)


# =============================================================================
# Frontier Action Handlers (extracted for maintainability)
# =============================================================================


def _frontiers_load_and_update(
    load: Path,
    mark_explored: Optional[str],
    explored_by: Optional[str],
    json_out: bool,
) -> None:
    """Load existing frontier report and optionally mark frontier as explored."""
    from dspx.coordinates import FrontierReport

    if not load.exists():
        typer.echo(f"Error: Report file not found: {load}", err=True)
        raise typer.Exit(code=2)

    data = json.loads(load.read_text(encoding="utf-8"))
    report = FrontierReport.from_dict(data)
    typer.echo(f"Loaded report with {len(report.frontiers)} frontiers from {load}")

    if mark_explored:
        if report.mark_explored(mark_explored, by=explored_by):
            typer.echo(f"Marked frontier {mark_explored} as explored")
            load.parent.mkdir(parents=True, exist_ok=True)
            load.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            typer.echo(f"Updated report saved to {load}")
        else:
            typer.echo(f"Error: Frontier {mark_explored} not found in report", err=True)
            raise typer.Exit(code=2)

    progress = report.get_exploration_progress()
    if not json_out:
        typer.echo(f"\nExploration Progress: {progress['progress_pct']:.1f}%")
        typer.echo(f"  Explored: {progress['explored']}/{progress['total_frontiers']}")
        typer.echo(f"  Remaining high-priority: {progress['remaining_high_priority']}")
    else:
        typer.echo(json.dumps(progress, ensure_ascii=False, indent=2))


def _frontiers_show_suggestions(
    index: "CoordinateIndex",
    max_frontiers: int,
    json_out: bool,
) -> None:
    """Display exploration suggestions."""
    from dspx.coordinates import suggest_exploration

    suggestions = suggest_exploration(index, top_k=max_frontiers)
    if json_out:
        typer.echo(json.dumps(suggestions, ensure_ascii=False, indent=2))
    else:
        typer.echo("=== Exploration Suggestions ===\n")
        for i, s in enumerate(suggestions, 1):
            typer.echo(f"[{i}] Priority: {s['priority']:.2f}")
            typer.echo(f"    Target: {s['target']}")
            typer.echo(f"    Reference: {s['reference_run']}")
            typer.echo(f"    Reason: {s['reason']}")
            typer.echo()


def _frontiers_show_report(
    report: "FrontierReport",
    save: Optional[Path],
    json_out: bool,
) -> None:
    """Display or save frontier report."""
    if save:
        save.parent.mkdir(parents=True, exist_ok=True)
        save.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        typer.echo(f"Frontier report saved to {save}")

    if json_out:
        typer.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        typer.echo("=== Behavioral Frontiers ===\n")
        typer.echo(f"Total embeddings: {report.total_embeddings}")
        typer.echo(f"Frontiers found: {len(report.frontiers)}")
        typer.echo(f"Coverage estimate: {report.coverage_estimate:.1%}")
        typer.echo(f"High-priority frontiers: {report.high_priority_count}")
        typer.echo()

        if report.frontiers:
            typer.echo("Top frontiers:")
            for f in report.frontiers[:10]:
                status = "✓" if f.explored else "○"
                typer.echo(
                    f"  [{status}] {f.frontier_id}: distance={f.distance_to_known:.3f}"
                )
                typer.echo(f"        Near: {f.nearest_run_id}")
                typer.echo(f"        Priority: {f.exploration_priority:.2f}")
                if f.suggested_input:
                    typer.echo(f"        Suggestion: {f.suggested_input}")
                typer.echo()


@app.command("frontiers")
def oracle_frontiers(
    max_frontiers: int = typer.Option(
        20, "--max", "-n", help="Maximum frontiers to return"
    ),
    min_distance: float = typer.Option(
        0.3, "--min-distance", help="Minimum distance to consider a frontier"
    ),
    suggest: bool = typer.Option(
        False, "--suggest", help="Show exploration suggestions"
    ),
    save: Optional[Path] = typer.Option(
        None, "--save", help="Save frontier report to JSON file"
    ),
    load: Optional[Path] = typer.Option(
        None, "--load", help="Load existing frontier report to check progress"
    ),
    mark_explored: Optional[str] = typer.Option(
        None, "--mark-explored", help="Mark a frontier as explored by ID"
    ),
    explored_by: Optional[str] = typer.Option(
        None, "--by", help="Who/what explored the frontier"
    ),
    index_path: Optional[Path] = typer.Option(
        None, "--index-path", help="Path to coordinate index database"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Detect frontiers (unexplored input space).

    Frontiers represent the edges of explored behavioral space.
    Identifying them helps discover gaps in test coverage.

    Use --save to persist exploration state and --load to resume tracking.
    """
    from dspx.coordinates import CoordinateIndex, find_frontiers

    if load:
        _frontiers_load_and_update(load, mark_explored, explored_by, json_out)
        return

    index = CoordinateIndex(db_path=index_path)

    if suggest:
        _frontiers_show_suggestions(index, max_frontiers, json_out)
        return

    report = find_frontiers(
        index, max_frontiers=max_frontiers, min_distance=min_distance
    )
    _frontiers_show_report(report, save, json_out)


# =============================================================================
# Attractor Action Handlers (extracted for maintainability)
# =============================================================================


def _attractors_show_health(report: "AttractorReport", json_out: bool) -> None:
    """Display attractor health report."""
    from dspx.coordinates import compute_attractor_health

    health_report = compute_attractor_health(report)
    if json_out:
        typer.echo(json.dumps(health_report, ensure_ascii=False, indent=2))
    else:
        typer.echo("=== Attractor Health Report ===\n")
        typer.echo(f"Status: {health_report['status'].upper()}")
        typer.echo(f"Message: {health_report['message']}")
        typer.echo()
        if health_report.get("recommendations"):
            typer.echo("Recommendations:")
            for r in health_report["recommendations"]:
                typer.echo(f"  - {r}")


def _attractors_show_report(report: "AttractorReport", json_out: bool) -> None:
    """Display attractor report."""
    if json_out:
        typer.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        typer.echo("=== Behavioral Attractors ===\n")
        typer.echo(f"Total embeddings: {report.total_embeddings}")
        typer.echo(f"Attractors found: {len(report.attractors)}")
        typer.echo(
            f"Strong attractors (stability > 0.9): {report.strong_attractor_count}"
        )
        typer.echo(f"Average stability: {report.avg_stability:.2f}")
        typer.echo(f"Coverage: {report.coverage:.1%}")
        typer.echo()

        if report.attractors:
            typer.echo("Top attractors:")
            for a in report.attractors[:10]:
                typer.echo(f"  {a.attractor_id}: stability={a.stability_score:.2f}")
                typer.echo(
                    f"    Members: {a.member_count}, Basin radius: {a.basin_radius:.3f}"
                )
                typer.echo(f"    Convergence: {a.convergence_rate:.3f}")
                if a.dominant_run_kind:
                    typer.echo(
                        f"    Kind: {a.dominant_run_kind}, Provider: {a.dominant_provider}"
                    )
                typer.echo()


@app.command("attractors")
def oracle_attractors(
    min_stability: float = typer.Option(
        0.5, "--min-stability", help="Minimum stability threshold"
    ),
    k: int = typer.Option(10, "-k", help="Number of clusters to analyze"),
    health: bool = typer.Option(False, "--health", help="Show attractor health report"),
    index_path: Optional[Path] = typer.Option(
        None, "--index-path", help="Path to coordinate index database"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Find naturally stable behavioral attractors.

    Attractors are regions where executions naturally converge,
    indicating reliable, repeatable behaviors.
    """
    from dspx.coordinates import CoordinateIndex, find_attractors

    index = CoordinateIndex(db_path=index_path)
    report = find_attractors(index, k=k, min_stability=min_stability)

    if health:
        _attractors_show_health(report, json_out)
    else:
        _attractors_show_report(report, json_out)


@app.command("predict")
def oracle_predict(
    run_id: str = typer.Argument(..., help="Run ID to predict convergence for"),
    k: int = typer.Option(10, "-k", help="Number of clusters for attractor analysis"),
    min_stability: float = typer.Option(
        0.5, "--min-stability", help="Minimum stability threshold for attractors"
    ),
    index_path: Optional[Path] = typer.Option(
        None, "--index-path", help="Path to coordinate index database"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Predict which attractor a run will converge to.

    Uses the attractor landscape to predict behavioral outcomes
    before execution completes. Useful for anticipating behavior
    and identifying potential issues early.
    """
    from dspx.coordinates import (
        CoordinateIndex,
        find_attractors,
        predict_convergence,
    )

    index = CoordinateIndex(db_path=index_path)

    # Get the embedding for the target run
    embedding = index.get(run_id)
    if embedding is None:
        typer.echo(f"Error: Run '{run_id}' not found in index", err=True)
        raise typer.Exit(code=2)

    # Build attractor landscape
    report = find_attractors(index, k=k, min_stability=min_stability)

    if not report.attractors:
        typer.echo("No attractors found - need more execution data", err=True)
        raise typer.Exit(code=1)

    # Make prediction
    prediction = predict_convergence(embedding, report.attractors)

    if json_out:
        typer.echo(json.dumps(prediction, ensure_ascii=False, indent=2))
    else:
        typer.echo("=== Convergence Prediction ===\n")
        typer.echo(f"Run: {run_id}")
        typer.echo(
            f"Predicted attractor: {prediction['predicted_attractor'] or 'None'}"
        )
        typer.echo(
            f"Confidence: {prediction['confidence']:.1%} ({prediction['confidence_level']})"
        )
        typer.echo(f"In basin: {'Yes' if prediction['in_basin'] else 'No'}")
        typer.echo(f"Distance: {prediction['distance']:.4f}")
        typer.echo()

        if prediction.get("expected_behavior"):
            typer.echo("Expected behavior:")
            eb = prediction["expected_behavior"]
            if eb.get("run_kind"):
                typer.echo(f"  Run kind: {eb['run_kind']}")
            if eb.get("provider"):
                typer.echo(f"  Provider: {eb['provider']}")

        if prediction["uncertainty"] > 0.5:
            typer.echo("\n⚠ High uncertainty - prediction may be unreliable")
