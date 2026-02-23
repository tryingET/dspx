"""Cache inspection and management commands.

Commands for inspecting, listing, and managing the on-disk cache.
"""

from __future__ import annotations

import json
import time
from typing import Optional

import typer


app = typer.Typer(no_args_is_help=True)


@app.command("info")
def cache_info() -> None:
    """Show cache directory location and statistics."""
    from dspx.cache import cache_dir, cache_enabled

    p = cache_dir()
    enabled = cache_enabled()
    total = 0
    count = 0
    per_kind: dict[str, dict[str, int]] = {}
    now = time.time()
    oldest = None
    newest = None

    if p.exists():
        for f in p.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                    count += 1
                    # per-kind (top-level dir)
                    try:
                        kind = f.relative_to(p).parts[0]
                    except Exception:
                        kind = "_root"
                    d = per_kind.setdefault(kind, {"size": 0, "files": 0})
                    d["size"] += f.stat().st_size
                    d["files"] += 1
                    mt = f.stat().st_mtime
                    if oldest is None or mt < oldest:
                        oldest = mt
                    if newest is None or mt > newest:
                        newest = mt
                except Exception:
                    pass

    typer.echo(f"dir: {p}")
    typer.echo(f"enabled: {str(enabled).lower()}")
    typer.echo(f"files: {count}")
    typer.echo(f"size_bytes: {total}")
    if oldest is not None and newest is not None:
        typer.echo(f"age_oldest_seconds: {int(now - oldest)}")
        typer.echo(f"age_newest_seconds: {int(now - newest)}")

    # per-kind breakdown
    for k in sorted(per_kind.keys()):
        d = per_kind[k]
        typer.echo(f"kind.{k}.files: {d['files']}")
        typer.echo(f"kind.{k}.size_bytes: {d['size']}")


@app.command("list")
def cache_list(
    kind: Optional[str] = typer.Option(None, help="Cache kind to filter"),
) -> None:
    """List cache entries, optionally filtered by kind."""
    from dspx.cache import cache_dir

    base = cache_dir()
    kinds = [kind] if kind else []

    if not kinds:
        # List subdirs under cache dir
        if base.exists():
            for d in sorted([p for p in base.iterdir() if p.is_dir()]):
                kinds.append(d.name)

    for k in kinds:
        d = base / k
        if not d.exists() or not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            key = f.stem
            typer.echo(f"{k}:{key} -> {f}")


@app.command("show")
def cache_show(
    kind: str = typer.Option(
        ..., "--kind", "-k", help="Cache kind (signature/module/...)"
    ),
    key: str = typer.Option(..., "--key", help="Cache key (sha256 hex)"),
) -> None:
    """Show contents of a specific cache entry."""
    from dspx.cache import cache_dir

    f = cache_dir() / kind / f"{key}.json"
    if not f.exists():
        raise typer.Exit(code=2)

    try:
        typer.echo(
            json.dumps(
                json.loads(f.read_text(encoding="utf-8")),
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception:
        typer.echo(f.read_text(encoding="utf-8"))


@app.command("clear")
def cache_clear(
    kind: Optional[str] = typer.Option(
        None, "--kind", "-k", help="Cache kind to clear"
    ),
    key: Optional[str] = typer.Option(
        None, "--key", help="Specific cache key to remove"
    ),
    all_: bool = typer.Option(False, "--all", help="Clear entire cache directory"),
) -> None:
    """Clear cache entries."""
    from dspx.cache import cache_dir

    base = cache_dir()

    if all_:
        # Remove all files under cache dir
        if base.exists():
            for f in base.rglob("*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass
        typer.echo("cleared: all")
        return

    if key and not kind:
        typer.echo("error: --key requires --kind", err=True)
        raise typer.Exit(code=2)

    if kind and key:
        f = base / kind / f"{key}.json"
        if f.exists():
            try:
                f.unlink()
                typer.echo(f"cleared: {kind}:{key}")
                return
            except Exception:
                pass
        raise typer.Exit(code=2)

    if kind and not key:
        d = base / kind
        if d.exists():
            for f in d.glob("*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass
        typer.echo(f"cleared: {kind}")
        return

    raise typer.Exit(code=2)


@app.command("prune")
def cache_prune(
    kind: Optional[str] = typer.Option(None, help="Cache kind to prune"),
    max_size_mb: Optional[float] = typer.Option(
        None, help="Reduce total cache size to at most this many MB"
    ),
    older_than_days: Optional[float] = typer.Option(
        None, help="Delete entries older than this many days"
    ),
    dry_run: bool = typer.Option(False, help="Only print what would be deleted"),
) -> None:
    """Prune cache by age and/or target size (oldest first)."""
    from dspx.cache import cache_dir
    from pathlib import Path as _Path

    base = cache_dir()
    targets: list[tuple[float, int, str]] = []  # (mtime, size, path)
    now = time.time()

    if not base.exists():
        typer.echo("no cache")
        return

    root = base if not kind else base / kind
    for f in root.rglob("*.json"):
        try:
            st = f.stat()
            targets.append((st.st_mtime, st.st_size, str(f)))
        except Exception:
            pass

    # Age prune
    removed = 0
    saved = 0
    keep: set[str] = set()

    if older_than_days is not None:
        cutoff = now - older_than_days * 86400.0
        for mt, sz, path in list(targets):
            if mt < cutoff:
                if not dry_run:
                    try:
                        _Path(path).unlink()
                        removed += 1
                    except Exception:
                        pass
            else:
                keep.add(path)
                saved += sz
    else:
        for _, sz, path in targets:
            keep.add(path)
            saved += sz

    # Size prune
    if max_size_mb is not None and saved > max_size_mb * 1024 * 1024:
        # delete oldest first among kept
        kept_list = sorted([(mt, sz, path) for mt, sz, path in targets if path in keep])
        for mt, sz, path in kept_list:
            if saved <= max_size_mb * 1024 * 1024:
                break
            if not dry_run:
                try:
                    _Path(path).unlink()
                    removed += 1
                except Exception:
                    pass
            saved -= sz

    typer.echo(f"pruned: {removed} files; remaining_bytes: {int(saved)}")
