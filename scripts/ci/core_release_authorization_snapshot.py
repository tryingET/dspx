#!/usr/bin/env python3
# ---
# summary: "Stages one owner-only immutable input generation for Core authorization."
# ---

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import stat
import tempfile
from typing import cast

from core_release_evidence_io import CoreReleaseEvidenceError, stable_regular_bytes


@dataclass(frozen=True)
class SnapshotInputs:
    repo_root: Path
    trust_checkpoint: Path
    owner_checkpoint: Path
    evidence_bundle: Path
    statement_path: Path
    sigstore_bundle: Path
    subject_path: Path
    receipt_path: Path
    receipt_statement_path: Path
    receipt_sigstore_bundle: Path
    trusted_root_path: Path
    ak_command: str = "ak"
    gh_command: str = "gh"


@dataclass(frozen=True)
class StagedAuthorizationInputs:
    inputs: SnapshotInputs
    signature_path: Path | None


_STAGED_INPUTS = (
    ("evidence_bundle", "evidence-bundle.bin", "evidence bundle", 1024 * 1024 * 1024),
    ("statement_path", "statement.json", "signed statement", 16 * 1024 * 1024),
    (
        "sigstore_bundle",
        "statement-sigstore.json",
        "evidence Sigstore bundle",
        16 * 1024 * 1024,
    ),
    ("subject_path", "subject.whl", "signed subject", 1024 * 1024 * 1024),
    ("receipt_path", "custody-receipt.json", "custody receipt", 16 * 1024 * 1024),
    (
        "receipt_statement_path",
        "custody-statement.json",
        "custody signed statement",
        16 * 1024 * 1024,
    ),
    (
        "receipt_sigstore_bundle",
        "custody-sigstore.json",
        "custody Sigstore bundle",
        16 * 1024 * 1024,
    ),
    (
        "trusted_root_path",
        "trusted-root.json",
        "Sigstore trusted root",
        16 * 1024 * 1024,
    ),
)


def _write_staged(directory_fd: int, name: str, raw: bytes) -> None:
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
        dir_fd=directory_fd,
    )
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise CoreReleaseEvidenceError("authorization snapshot write stalled")
            offset += written
        os.fsync(descriptor)
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.geteuid()
            or stat.S_IMODE(observed.st_mode) != 0o600
        ):
            raise CoreReleaseEvidenceError("authorization snapshot file is unsafe")
    finally:
        os.close(descriptor)


def _verify_directory(directory: Path, directory_fd: int) -> None:
    try:
        path_state = directory.lstat()
        opened_state = os.fstat(directory_fd)
    except OSError as exc:
        raise CoreReleaseEvidenceError(
            "authorization snapshot directory is unavailable"
        ) from exc
    if (
        stat.S_ISLNK(path_state.st_mode)
        or not stat.S_ISDIR(path_state.st_mode)
        or path_state.st_uid != os.geteuid()
        or stat.S_IMODE(path_state.st_mode) != 0o700
        or (path_state.st_dev, path_state.st_ino)
        != (opened_state.st_dev, opened_state.st_ino)
    ):
        raise CoreReleaseEvidenceError("authorization snapshot directory is unsafe")


@contextmanager
def stage_run_inputs(
    inputs: SnapshotInputs, *, signature_path: Path | None = None
) -> Iterator[StagedAuthorizationInputs]:
    """Copy each bounded original once, then expose only the staged generation."""
    directory = Path(tempfile.mkdtemp(prefix="dspx-authorization-snapshot-"))
    directory.chmod(0o700)
    directory_fd = os.open(
        directory,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    names: list[str] = []
    try:
        _verify_directory(directory, directory_fd)
        staged_paths: dict[str, Path] = {}
        for field, name, label, limit in _STAGED_INPUTS:
            original = cast(Path, getattr(inputs, field))
            raw = stable_regular_bytes(original, label=label, limit=limit)
            _write_staged(directory_fd, name, raw)
            names.append(name)
            staged_paths[field] = directory / name
        staged_signature: Path | None = None
        if signature_path is not None:
            raw = stable_regular_bytes(
                signature_path,
                label="owner approval signature",
                limit=1024 * 1024,
            )
            name = "owner-approval.sig"
            _write_staged(directory_fd, name, raw)
            names.append(name)
            staged_signature = directory / name
        os.fsync(directory_fd)
        _verify_directory(directory, directory_fd)
        yield StagedAuthorizationInputs(
            inputs=SnapshotInputs(
                repo_root=inputs.repo_root,
                trust_checkpoint=inputs.trust_checkpoint,
                owner_checkpoint=inputs.owner_checkpoint,
                ak_command=inputs.ak_command,
                gh_command=inputs.gh_command,
                **staged_paths,
            ),
            signature_path=staged_signature,
        )
    finally:
        for name in names:
            try:
                os.unlink(name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        try:
            _verify_directory(directory, directory_fd)
        except CoreReleaseEvidenceError:
            removable = False
        else:
            removable = True
        os.close(directory_fd)
        if removable:
            try:
                directory.rmdir()
            except OSError:
                pass
