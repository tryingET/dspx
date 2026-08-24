"""No-follow private filesystem custody for Soomfon evaluation artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import secrets
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

_MAX_STAGE_FILES = 128
_MAX_STAGE_BYTES = 32 * 1024 * 1024


class SoomfonCustodyError(RuntimeError):
    """A protected candidate or private custody path is unsafe."""


def _safe_component_mode(info: os.stat_result, *, managed: bool) -> bool:
    mode = stat.S_IMODE(info.st_mode)
    if managed:
        return info.st_uid == os.geteuid() and mode == 0o700
    return info.st_uid in {0, os.geteuid()} and mode & 0o022 == 0


def ensure_private_tree(path: Path) -> tuple[Path, int]:
    """Walk/create an absolute directory using no-follow dirfd operations."""

    absolute = path.expanduser().absolute()
    if not absolute.is_absolute():
        raise SoomfonCustodyError("private state path is not absolute")
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    current_fd = os.open("/", flags)
    current = Path("/")
    managed = False
    try:
        parts = absolute.parts[1:]
        for index, part in enumerate(parts):
            created = False
            try:
                next_fd = os.open(part, flags, dir_fd=current_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
                else:
                    os.fsync(current_fd)
                    created = True
                next_fd = os.open(part, flags, dir_fd=current_fd)
            except OSError as exc:
                raise SoomfonCustodyError(
                    "private state component is unavailable"
                ) from exc
            info = os.fstat(next_fd)
            managed = (
                managed
                or created
                or current == Path(pwd.getpwuid(os.geteuid()).pw_dir) / ".local/state"
            )
            if not stat.S_ISDIR(info.st_mode) or not _safe_component_mode(
                info, managed=managed or index == len(parts) - 1
            ):
                os.close(next_fd)
                raise SoomfonCustodyError("private state component is unsafe")
            os.close(current_fd)
            current_fd = next_fd
            current /= part
        return absolute, current_fd
    except Exception:
        os.close(current_fd)
        raise


def open_private_directory(path: Path) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise SoomfonCustodyError("private directory is unavailable") from exc
    info = os.fstat(fd)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        os.close(fd)
        raise SoomfonCustodyError("private directory identity is invalid")
    return fd


def write_private_bytes_exclusive(path: Path, content: bytes) -> None:
    """Publish one private file without following or replacing a destination."""

    descriptor_parts = path.parent.parts
    if (
        len(descriptor_parts) == 5
        and descriptor_parts[:4] == ("/", "proc", "self", "fd")
        and descriptor_parts[4].isdigit()
    ):
        parent_fd = os.dup(int(descriptor_parts[4]))
        parent_info = os.fstat(parent_fd)
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != os.geteuid()
            or stat.S_IMODE(parent_info.st_mode) != 0o700
        ):
            os.close(parent_fd)
            raise SoomfonCustodyError("descriptor-bound output directory is invalid")
    else:
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        parent_fd = os.open(path.parent, flags)
    temporary_name = f".{path.name}.{secrets.token_hex(12)}.tmp"
    descriptor = -1
    published = False
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        written = 0
        while written < len(content):
            count = os.write(descriptor, content[written:])
            if count <= 0:
                raise OSError("private runtime write made no progress")
            written += count
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(
            temporary_name,
            path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
        published = True
        os.unlink(temporary_name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except Exception:
        if published:
            try:
                os.unlink(path.name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)


def write_private_json_exclusive(path: Path, payload: object) -> str:
    raw = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
    write_private_bytes_exclusive(path, raw)
    return hashlib.sha256(raw).hexdigest()


def _safe_relative_path(raw: object) -> PurePosixPath:
    if not isinstance(raw, str):
        raise SoomfonCustodyError("candidate surface path is invalid")
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise SoomfonCustodyError("candidate surface path escapes")
    return path


def stable_source_bytes(path: Path, *, expected_sha256: str | None = None) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise SoomfonCustodyError("candidate source file is unavailable") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_STAGE_BYTES:
            raise SoomfonCustodyError("candidate source file is invalid")
        raw = bytearray()
        while len(raw) <= _MAX_STAGE_BYTES:
            chunk = os.read(fd, min(65536, _MAX_STAGE_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(raw) != before.st_size:
        raise SoomfonCustodyError("candidate source changed while read")
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise SoomfonCustodyError("candidate source hash drifted")
    return bytes(raw)


def _write_staged_file(root: Path, relative: PurePosixPath, raw: bytes) -> Path:
    parent, parent_fd = ensure_private_tree(root.joinpath(*relative.parts[:-1]))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(relative.name, flags, 0o600, dir_fd=parent_fd)
        try:
            offset = 0
            while offset < len(raw):
                written = os.write(fd, raw[offset:])
                if written <= 0:
                    raise SoomfonCustodyError("candidate stage write was incomplete")
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return parent / relative.name


def stage_candidate(case: Mapping[str, Any], stage_root: Path) -> Path:
    source_manifest = Path(case["manifest_path"])
    source_root = source_manifest.parent
    manifest = case["manifest_payload"]
    surfaces = manifest.get("candidate_assembly", {}).get("surfaces")
    if not isinstance(surfaces, list) or not 1 <= len(surfaces) <= _MAX_STAGE_FILES:
        raise SoomfonCustodyError("candidate surface inventory is invalid")
    stage, stage_fd = ensure_private_tree(stage_root)
    os.close(stage_fd)
    copied: set[PurePosixPath] = set()
    total = 0
    for surface in surfaces:
        if not isinstance(surface, dict):
            raise SoomfonCustodyError("candidate surface entry is invalid")
        relative = _safe_relative_path(surface.get("path"))
        expected = surface.get("content_hash")
        if relative in copied or not isinstance(expected, str):
            raise SoomfonCustodyError("candidate surface inventory is ambiguous")
        raw = stable_source_bytes(
            source_root.joinpath(*relative.parts), expected_sha256=expected
        )
        total += len(raw)
        if total > _MAX_STAGE_BYTES:
            raise SoomfonCustodyError("candidate staged payload exceeds its bound")
        _write_staged_file(stage, relative, raw)
        copied.add(relative)
    manifest_raw = stable_source_bytes(
        source_manifest, expected_sha256=case["manifest_sha256"]
    )
    _write_staged_file(stage, PurePosixPath("manifest.json"), manifest_raw)
    receipt_path = Path(case["manifest_receipt_path"])
    receipt_raw = stable_source_bytes(
        receipt_path, expected_sha256=case["manifest_receipt_sha256"]
    )
    _write_staged_file(stage, PurePosixPath("manifest.json.meta.json"), receipt_raw)
    fsync_private_tree(stage)
    return stage / "manifest.json"


def fsync_private_tree(root: Path) -> None:
    paths = [root, *root.rglob("*")]
    if len(paths) > _MAX_STAGE_FILES * 4:
        raise SoomfonCustodyError("private tree file count exceeds its bound")
    total = 0
    directories: list[Path] = []
    for path in paths:
        info = path.lstat()
        if info.st_uid != os.geteuid() or stat.S_ISLNK(info.st_mode):
            raise SoomfonCustodyError("private tree identity is unsafe")
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISREG(info.st_mode):
            if mode != 0o600 or info.st_nlink != 1:
                raise SoomfonCustodyError("private tree file identity is unsafe")
            total += info.st_size
            if total > _MAX_STAGE_BYTES * 2:
                raise SoomfonCustodyError("private tree byte count exceeds its bound")
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                observed = os.fstat(fd)
                if (
                    observed.st_dev,
                    observed.st_ino,
                    observed.st_mode,
                    observed.st_uid,
                    observed.st_nlink,
                    observed.st_size,
                ) != (
                    info.st_dev,
                    info.st_ino,
                    info.st_mode,
                    info.st_uid,
                    info.st_nlink,
                    info.st_size,
                ):
                    raise SoomfonCustodyError("private tree file identity changed")
                os.fsync(fd)
            finally:
                os.close(fd)
        elif stat.S_ISDIR(info.st_mode):
            if mode != 0o700:
                raise SoomfonCustodyError("private tree directory mode is unsafe")
            directories.append(path)
        else:
            raise SoomfonCustodyError("private tree type is unsafe")
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True
    ):
        fd = open_private_directory(directory)
        try:
            observed = os.fstat(fd)
            expected = directory.lstat()
            if (observed.st_dev, observed.st_ino) != (
                expected.st_dev,
                expected.st_ino,
            ):
                raise SoomfonCustodyError("private tree directory identity changed")
            os.fsync(fd)
        finally:
            os.close(fd)


__all__ = [
    "SoomfonCustodyError",
    "ensure_private_tree",
    "fsync_private_tree",
    "open_private_directory",
    "stable_source_bytes",
    "stage_candidate",
    "write_private_bytes_exclusive",
    "write_private_json_exclusive",
]
