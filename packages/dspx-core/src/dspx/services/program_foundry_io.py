# summary: "Owns foundry path confinement, exclusive workflow locking, and atomic summary projection writes."
# read_when:
#   - "Changing foundry output roots, concurrency control, symlink policy, or summary durability."

from __future__ import annotations

import fcntl
import json
import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

PROGRAM_FOUNDRY_SUMMARY_NAME = "foundry.json"


class ProgramFoundryIOError(ValueError):
    """Raised when foundry filesystem ownership or confinement fails."""


def preflight_foundry_paths(
    *,
    intent_path: Path,
    quality_proposal_path: Path,
    inputs_path: Path,
    outdir: Path,
) -> Path:
    raw_root = outdir.expanduser().absolute()
    if raw_root.is_symlink() or (raw_root.exists() and not raw_root.is_dir()):
        raise ProgramFoundryIOError("foundry outdir must be a real directory path")
    root = raw_root.resolve()
    sources = {
        "intent": intent_path.expanduser().resolve(),
        "quality proposal": quality_proposal_path.expanduser().resolve(),
        "inputs": inputs_path.expanduser().resolve(),
    }
    for label, source in sources.items():
        if source == root or root in source.parents:
            raise ProgramFoundryIOError(
                f"foundry {label} must be outside the foundry outdir"
            )
    for name in ("candidate", "runtime"):
        stage = raw_root / name
        if stage.is_symlink():
            raise ProgramFoundryIOError(f"foundry {name} stage must not be a symlink")
    summary = raw_root / PROGRAM_FOUNDRY_SUMMARY_NAME
    lock_path = raw_root / ".foundry.lock"
    if lock_path.is_symlink():
        raise ProgramFoundryIOError("foundry lock path must not be a symlink")
    if summary.is_symlink() or (summary.exists() and summary.is_dir()):
        raise ProgramFoundryIOError("foundry summary path is invalid")
    return root


@contextmanager
def foundry_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".foundry.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise ProgramFoundryIOError("foundry lock path is unsafe") from exc
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ProgramFoundryIOError("foundry lock path must be a regular file")
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProgramFoundryIOError(
                "another foundry invocation owns this outdir"
            ) from exc
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def write_summary_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(
        f".{target.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
