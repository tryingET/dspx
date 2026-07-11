#!/usr/bin/env python3
# ---
# summary: "Plan and safely delete aged files within an explicitly confirmed artifact root."
# read_when:
#   - "Changing artifact retention, cleanup confinement, or plan-confirmation safeguards."
# ---
"""Inspect or remove aged files below an explicitly confirmed artifact root."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat as stat_module
import time
from typing import TypedDict


class CleanupResult(TypedDict):
    schema_version: str
    root: str
    mode: str
    older_than_days: float
    plan_id: str
    candidate_count: int
    candidate_bytes: int
    candidates: list[str]
    deleted: list[str]


def _validated_root(root: Path) -> Path:
    requested = root.expanduser()
    if requested.is_symlink():
        raise ValueError("artifact root must not be a symlink")
    resolved = requested.resolve(strict=True)
    if not resolved.is_dir() or resolved == Path(resolved.anchor):
        raise ValueError(
            "artifact root must be an existing non-filesystem-root directory"
        )
    if resolved == Path.home().resolve():
        raise ValueError("artifact root must not be the current user's home directory")
    if (resolved / ".git").exists():
        raise ValueError("artifact root must not be a git repository root")
    return resolved


def _validated_age(older_than_days: float) -> float:
    if not math.isfinite(older_than_days) or older_than_days < 0:
        raise ValueError("older-than-days must be a finite non-negative number")
    return older_than_days


def _scan_files(root: Path, *, older_than_days: float) -> list[tuple[Path, int, int]]:
    cutoff_ns = int((time.time() - older_than_days * 86400) * 1e9)
    candidates: list[tuple[Path, int, int]] = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name for name in directories if not (current_path / name).is_symlink()
        ]
        for name in files:
            path = current_path / name
            if path.is_symlink():
                continue
            try:
                resolved = path.resolve(strict=True)
                stat = path.stat()
            except OSError:
                continue
            if not resolved.is_relative_to(root) or not resolved.is_file():
                continue
            if stat.st_mtime_ns <= cutoff_ns:
                candidates.append((resolved, stat.st_size, stat.st_mtime_ns))
    return sorted(candidates, key=lambda row: str(row[0]))


def _plan_id(
    root: Path, *, older_than_days: float, candidates: list[tuple[Path, int, int]]
) -> str:
    payload = {
        "root": str(root),
        "older_than_days": older_than_days,
        "candidates": [
            {"path": str(path), "size": size, "mtime_ns": mtime_ns}
            for path, size, mtime_ns in candidates
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _unlink_confined_file(
    root_fd: int,
    root: Path,
    target: Path,
    *,
    expected_size: int,
    expected_mtime_ns: int,
) -> None:
    """Unlink one relative file through no-follow directory descriptors."""

    relative = target.relative_to(root)
    parts = relative.parts
    if not parts:
        raise ValueError(f"refusing artifact root deletion: {target}")
    parent_fd = os.dup(root_fd)
    try:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        for component in parts[:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_fd
        current = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        if not stat_module.S_ISREG(current.st_mode) or (
            current.st_size,
            current.st_mtime_ns,
        ) != (expected_size, expected_mtime_ns):
            raise ValueError(f"artifact changed after planning: {target}")
        os.unlink(parts[-1], dir_fd=parent_fd)
    finally:
        os.close(parent_fd)


def cleanup(
    root: Path,
    *,
    older_than_days: float,
    apply: bool = False,
    expected_plan_id: str | None = None,
    confirmed_root: Path | None = None,
) -> CleanupResult:
    """Build a dry-run plan or apply the exact current plan after confirmation.

    Only regular files are candidates. Directories and symlinks are never deleted.
    Apply requires both the dry-run plan id and the exact resolved root so a broad or
    changed candidate set cannot be deleted accidentally.
    """

    resolved_root = _validated_root(root)
    age = _validated_age(older_than_days)
    candidates = _scan_files(resolved_root, older_than_days=age)
    plan_id = _plan_id(resolved_root, older_than_days=age, candidates=candidates)

    if apply:
        if expected_plan_id != plan_id:
            raise ValueError(
                "apply requires the unchanged plan-id emitted by a current dry run"
            )
        if confirmed_root is None:
            raise ValueError(
                "apply requires --confirm-root with the exact artifact root"
            )
        confirmed = confirmed_root.expanduser().resolve(strict=True)
        if confirmed != resolved_root:
            raise ValueError("confirmed root does not match the artifact root")

    deleted: list[str] = []
    if apply:
        root_fd = os.open(
            resolved_root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            for target, expected_size, expected_mtime_ns in candidates:
                _unlink_confined_file(
                    root_fd,
                    resolved_root,
                    target,
                    expected_size=expected_size,
                    expected_mtime_ns=expected_mtime_ns,
                )
                deleted.append(str(target))
        finally:
            os.close(root_fd)

    paths = [str(path) for path, _, _ in candidates]
    return {
        "schema_version": "dspx-artifact-cleanup-v1",
        "root": str(resolved_root),
        "mode": "apply" if apply else "dry_run",
        "older_than_days": age,
        "plan_id": plan_id,
        "candidate_count": len(paths),
        "candidate_bytes": sum(size for _, size, _ in candidates),
        "candidates": paths,
        "deleted": deleted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, required=True, help="Configured artifact root"
    )
    parser.add_argument("--older-than-days", type=float, default=7)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the unchanged dry-run plan; requires --plan-id and --confirm-root",
    )
    parser.add_argument("--plan-id", help="Plan id emitted by the reviewed dry run")
    parser.add_argument(
        "--confirm-root",
        type=Path,
        help="Exact artifact root confirmation required with --apply",
    )
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                cleanup(
                    args.root,
                    older_than_days=args.older_than_days,
                    apply=args.apply,
                    expected_plan_id=args.plan_id,
                    confirmed_root=args.confirm_root,
                ),
                indent=2,
            )
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
