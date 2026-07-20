# ---
# summary: "Provides bounded artifact IO and archive identity helpers for Core release evidence."
# read_when:
#   - "Changing Core release-evidence artifact hashing, archive inspection, or output publication."
# ---

from __future__ import annotations

from collections.abc import Mapping
from email.parser import BytesParser
from email.policy import default as email_policy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import subprocess
import tarfile
from typing import Any
import zipfile


MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024


class CoreReleaseEvidenceError(ValueError):
    """Raised when package release evidence is incomplete or contradictory."""


def stable_regular_bytes(path: Path, *, label: str, limit: int) -> bytes:
    lexical = path.absolute()
    try:
        before = lexical.lstat()
    except OSError as exc:
        raise CoreReleaseEvidenceError(f"{label} is unavailable: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise CoreReleaseEvidenceError(f"{label} must be a non-symlink regular file")
    if before.st_size > limit:
        raise CoreReleaseEvidenceError(f"{label} exceeds {limit} bytes")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lexical, flags)
    except OSError as exc:
        raise CoreReleaseEvidenceError(
            f"{label} cannot be opened safely: {exc}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise CoreReleaseEvidenceError(f"{label} changed before opening")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise CoreReleaseEvidenceError(f"{label} exceeds {limit} bytes")
        after = os.fstat(descriptor)
        if (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise CoreReleaseEvidenceError(f"{label} changed while reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CoreReleaseEvidenceError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def wheel_metadata(raw: bytes) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.endswith(".dist-info/METADATA")
            ]
            if len(names) != 1:
                raise CoreReleaseEvidenceError(
                    "Core wheel must contain exactly one distribution METADATA file"
                )
            metadata_raw = archive.read(names[0])
    except (zipfile.BadZipFile, KeyError) as exc:
        raise CoreReleaseEvidenceError("Core wheel archive is invalid") from exc
    metadata = BytesParser(policy=email_policy).parsebytes(metadata_raw)
    name = str(metadata.get("Name") or "")
    version = str(metadata.get("Version") or "")
    if not name or not version:
        raise CoreReleaseEvidenceError("Core wheel metadata lacks name or version")
    return name, version


def validate_sdist(raw: bytes, *, expected_name: str, expected_version: str) -> None:
    try:
        with tarfile.open(fileobj=BytesIO(raw), mode="r:gz") as archive:
            roots = {
                member.name.split("/", 1)[0]
                for member in archive.getmembers()
                if member.name and member.name not in {".", "./"}
            }
    except tarfile.TarError as exc:
        raise CoreReleaseEvidenceError("Core sdist archive is invalid") from exc
    normalized = expected_name.replace("-", "_")
    allowed_roots = {
        f"{expected_name}-{expected_version}",
        f"{normalized}-{expected_version}",
    }
    if len(roots) != 1 or next(iter(roots)) not in allowed_roots:
        raise CoreReleaseEvidenceError(
            f"Core sdist root does not match {expected_name} {expected_version}"
        )


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise CoreReleaseEvidenceError(
            f"release evidence output already exists: {path}"
        )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise CoreReleaseEvidenceError(
                    "release evidence output write made no progress"
                )
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
