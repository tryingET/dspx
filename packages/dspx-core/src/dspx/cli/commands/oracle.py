"""Oracle CLI commands for behavioral intelligence.

The Oracle provides semantic coordinate space operations for understanding
and reasoning about DSPy program behavior.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(no_args_is_help=True)


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

    # Initialize index
    index = CoordinateIndex(db_path=index_path)
    engine = get_embedding_engine()

    indexed = 0
    errors = 0
    skipped = 0

    if not from_mlflow and not from_receipts:
        typer.echo("Error: Specify --from-mlflow or --from-receipts", err=True)
        raise typer.Exit(code=2)

    if from_receipts:
        # Scan for .meta.json files
        scan_path = path or Path.cwd() / "generated"
        if verbose:
            typer.echo(f"Scanning for receipts in {scan_path}", err=True)

        receipt_files = list(scan_path.rglob("*.meta.json"))
        if verbose:
            typer.echo(f"Found {len(receipt_files)} receipt files", err=True)

        for receipt_file in receipt_files[:limit]:
            try:
                receipt_data = json.loads(receipt_file.read_text(encoding="utf-8"))

                # Check date filter
                created_at = receipt_data.get("created_at", "")
                if created_at:
                    try:
                        created_dt = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00")
                        )
                        if created_dt.replace(tzinfo=None) < since_dt.replace(
                            tzinfo=None
                        ):
                            skipped += 1
                            continue
                    except Exception:
                        pass

                # Embed the receipt
                embedding = engine.embed_receipt(receipt_data)
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
                if verbose:
                    typer.echo(f"Error processing {receipt_file}: {e}", err=True)

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
                                try:
                                    receipt_data = json.loads(
                                        artifact.read_text(encoding="utf-8")
                                    )
                                    embedding = engine.embed_receipt(receipt_data)
                                    if embedding:
                                        if index.upsert(embedding):
                                            indexed += 1
                                        else:
                                            errors += 1
                                except Exception:
                                    errors += 1

                    except Exception as e:
                        if verbose:
                            typer.echo(f"Error processing MLflow run: {e}", err=True)
                        errors += 1

                    if indexed >= limit:
                        break
                if indexed >= limit:
                    break

    stats = index.stats()

    result = {
        "indexed": indexed,
        "errors": errors,
        "skipped": skipped,
        "index_stats": stats,
        "backend": engine.backend,
        "dimension": engine.dimension,
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
