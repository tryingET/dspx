# summary: "Owns no-follow reads, descriptor identity checks, and immutable writes for foundry GEPA proposals."
# read_when:
#   - "Changing GEPA proposal file safety, locked-root access, or immutable reuse."

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping

_MAX_JSON_BYTES = 500_000


class ProgramFoundryGepaProposalError(ValueError):
    """Raised when semantic evidence cannot lawfully form a GEPA proposal."""


def read_regular_bytes(path: Path, *, label: str) -> bytes:
    target = path.expanduser().absolute()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        raise ProgramFoundryGepaProposalError(
            f"{label} must be an existing regular non-symlink file: {target}"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProgramFoundryGepaProposalError(
                f"{label} must be a regular file: {target}"
            )
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read(_MAX_JSON_BYTES + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > _MAX_JSON_BYTES:
        raise ProgramFoundryGepaProposalError(
            f"{label} exceeds the {_MAX_JSON_BYTES}-byte safety bound"
        )
    return raw


def sha256_regular_file(path: Path, *, label: str) -> str:
    return hashlib.sha256(read_regular_bytes(path, label=label)).hexdigest()


def read_root_relative_bytes(
    root_descriptor: int, relative_path: str, *, label: str
) -> bytes:
    parts = Path(relative_path).parts
    if len(parts) not in {1, 2} or any(part in {"", ".", ".."} for part in parts):
        raise ProgramFoundryGepaProposalError(f"{label} has an unsafe foundry path")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        if len(parts) == 1:
            descriptor = os.open(
                parts[0],
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=root_descriptor,
            )
        else:
            directory = os.open(parts[0], directory_flags, dir_fd=root_descriptor)
            try:
                descriptor = os.open(
                    parts[1],
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory,
                )
            finally:
                os.close(directory)
    except OSError as exc:
        raise ProgramFoundryGepaProposalError(
            f"{label} must remain a regular file under the locked foundry root"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProgramFoundryGepaProposalError(f"{label} must be a regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read(_MAX_JSON_BYTES + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > _MAX_JSON_BYTES:
        raise ProgramFoundryGepaProposalError(
            f"{label} exceeds the {_MAX_JSON_BYTES}-byte safety bound"
        )
    return raw


def assert_path_descriptor_identity(path: Path, descriptor: int, *, label: str) -> None:
    try:
        path_stat = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ProgramFoundryGepaProposalError(
            f"{label} path no longer identifies the locked artifact"
        ) from exc
    descriptor_stat = os.fstat(descriptor)
    if (path_stat.st_dev, path_stat.st_ino) != (
        descriptor_stat.st_dev,
        descriptor_stat.st_ino,
    ):
        raise ProgramFoundryGepaProposalError(
            f"{label} path no longer identifies the locked artifact"
        )


def write_or_reuse_program_foundry_gepa_proposal(
    *,
    payload: Mapping[str, Any],
    out_path: Path,
    foundry_root_descriptor: int,
) -> tuple[dict[str, Any], str]:
    """Write one immutable proposal, or reuse only exact canonical bytes."""

    target = out_path.expanduser().absolute()
    if target.is_symlink():
        raise ProgramFoundryGepaProposalError(
            "GEPA proposal path must not be a symlink"
        )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    encoded = rendered.encode("utf-8")
    if target.name != "gepa_experiment_proposal.json":
        raise ProgramFoundryGepaProposalError("GEPA proposal filename is invalid")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(
            target.name,
            flags,
            0o600,
            dir_fd=foundry_root_descriptor,
        )
    except FileExistsError:
        existing = read_root_relative_bytes(
            foundry_root_descriptor,
            target.name,
            label="existing GEPA proposal",
        )
        if existing != encoded:
            raise ProgramFoundryGepaProposalError(
                "existing GEPA proposal drifted; use a new foundry outdir for another selection"
            )
        loaded = json.loads(existing.decode("utf-8"))
        if not isinstance(loaded, dict):  # pragma: no cover - byte equality invariant
            raise ProgramFoundryGepaProposalError("existing GEPA proposal is invalid")
        return loaded, "reused"
    except OSError as exc:
        raise ProgramFoundryGepaProposalError("GEPA proposal path is unsafe") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    os.fsync(foundry_root_descriptor)
    return dict(payload), "created"
