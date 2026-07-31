#!/usr/bin/env python3
# ---
# summary: "Boundedly scans public Core release archives for secret-shaped expanded content."
# read_when:
#   - "Changing public evidence disclosure or nested wheel/sdist scanning."
# ---

from __future__ import annotations

from io import BytesIO
from pathlib import PurePosixPath
import re
import stat
import tarfile
import zipfile

from core_release_evidence_io import MAX_ARTIFACT_BYTES, CoreReleaseEvidenceError

MAX_ARCHIVE_MEMBERS = 10_000
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
_SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bgh[oprsu]_[A-Za-z0-9_]{32,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(
        rb"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|bearer)\b"
        rb"\s*[:=]\s*['\"]?[A-Za-z0-9+/_.=-]{12,}"
    ),
)


def secret_matches(raw: bytes) -> list[str]:
    return [
        pattern.pattern.decode("ascii", errors="replace")
        for pattern in _SECRET_PATTERNS
        if pattern.search(raw)
    ]


def _safe_member(name: str, label: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise CoreReleaseEvidenceError(f"{label} member path is unsafe")


def _scan_zip(raw: bytes, label: str) -> list[str]:
    findings: list[str] = []
    expanded = 0
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_MEMBERS:
                raise CoreReleaseEvidenceError(f"{label} has too many members")
            for entry in entries:
                _safe_member(entry.filename, label)
                if entry.is_dir():
                    continue
                mode = entry.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if entry.flag_bits & 0x1 or file_type not in {0, stat.S_IFREG}:
                    raise CoreReleaseEvidenceError(
                        f"{label} contains encrypted or non-regular members"
                    )
                expanded += entry.file_size
                if (
                    entry.file_size > MAX_ARTIFACT_BYTES
                    or expanded > MAX_EXPANDED_BYTES
                ):
                    raise CoreReleaseEvidenceError(
                        f"{label} expanded size exceeds limit"
                    )
                if secret_matches(archive.read(entry)):
                    findings.append(entry.filename)
    except zipfile.BadZipFile as exc:
        raise CoreReleaseEvidenceError(f"{label} is not a valid ZIP") from exc
    return findings


def _scan_tar(raw: bytes, label: str) -> list[str]:
    findings: list[str] = []
    expanded = 0
    try:
        with tarfile.open(fileobj=BytesIO(raw), mode="r:gz") as archive:
            entries = archive.getmembers()
            if len(entries) > MAX_ARCHIVE_MEMBERS:
                raise CoreReleaseEvidenceError(f"{label} has too many members")
            for entry in entries:
                _safe_member(entry.name, label)
                if entry.isdir():
                    continue
                if not entry.isfile():
                    raise CoreReleaseEvidenceError(
                        f"{label} contains non-regular members"
                    )
                expanded += entry.size
                if entry.size > MAX_ARTIFACT_BYTES or expanded > MAX_EXPANDED_BYTES:
                    raise CoreReleaseEvidenceError(
                        f"{label} expanded size exceeds limit"
                    )
                member = archive.extractfile(entry)
                if member is None:
                    raise CoreReleaseEvidenceError(f"{label} member cannot be read")
                if secret_matches(member.read()):
                    findings.append(entry.name)
    except (tarfile.TarError, EOFError) as exc:
        raise CoreReleaseEvidenceError(f"{label} is not a valid gzip tar") from exc
    return findings


def scan_nested_release_archive(name: str, raw: bytes) -> list[str]:
    if name.endswith(".whl"):
        return _scan_zip(raw, f"public wheel {name}")
    if name.endswith(".tar.gz"):
        return _scan_tar(raw, f"public sdist {name}")
    return []
