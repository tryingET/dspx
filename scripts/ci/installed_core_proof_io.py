# summary: "Provides descriptor-confined reads and atomic proof writes for package CI."
# read_when:
#   - "Changing installed Core proof path confinement, size bounds, or publication atomicity."

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_SQLITE_BYTES = 32 * 1024 * 1024


class InstalledCoreGoldenPathError(ValueError):
    """Raised when installed-wheel evidence is missing, unsafe, or misleading."""


def open_root(root: Path) -> int:
    if root.is_symlink():
        raise InstalledCoreGoldenPathError("journey root must not be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise InstalledCoreGoldenPathError(
            f"journey root is not a safely openable directory: {exc}"
        ) from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise InstalledCoreGoldenPathError("journey root must be a directory")
    return descriptor


def open_relative_regular(root_descriptor: int, relative: Path, *, label: str) -> int:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise InstalledCoreGoldenPathError(
            f"{label} path must be confined and relative"
        )
    parent = os.dup(root_descriptor)
    try:
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_NOFOLLOW", 0)
        for component in relative.parts[:-1]:
            next_descriptor = os.open(component, directory_flags, dir_fd=parent)
            os.close(parent)
            parent = next_descriptor
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(relative.parts[-1], file_flags, dir_fd=parent)
    except OSError as exc:
        raise InstalledCoreGoldenPathError(
            f"{label} is missing, escaped, symlinked, or unreadable: {exc}"
        ) from exc
    finally:
        os.close(parent)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise InstalledCoreGoldenPathError(f"{label} must be a regular file")
    return descriptor


def read_bounded_bytes(
    root_descriptor: int,
    relative: Path,
    *,
    label: str,
    limit: int,
) -> bytes:
    descriptor = open_relative_regular(root_descriptor, relative, label=label)
    try:
        file_stat = os.fstat(descriptor)
        if file_stat.st_size > limit:
            raise InstalledCoreGoldenPathError(
                f"{label} exceeds the {limit}-byte limit"
            )
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > limit:
            raise InstalledCoreGoldenPathError(
                f"{label} exceeds the {limit}-byte limit"
            )
        current_stat = os.fstat(descriptor)
        if (
            current_stat.st_dev,
            current_stat.st_ino,
            current_stat.st_size,
            current_stat.st_mtime_ns,
        ) != (
            file_stat.st_dev,
            file_stat.st_ino,
            file_stat.st_size,
            file_stat.st_mtime_ns,
        ):
            raise InstalledCoreGoldenPathError(f"{label} changed during stable read")
        return raw
    finally:
        os.close(descriptor)


def json_artifact(
    root_descriptor: int,
    relative: str,
    *,
    label: str,
) -> tuple[dict[str, Any], str]:
    raw = read_bounded_bytes(
        root_descriptor,
        Path(relative),
        label=label,
        limit=MAX_JSON_BYTES,
    )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstalledCoreGoldenPathError(f"{label} must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise InstalledCoreGoldenPathError(f"{label} must be a JSON object")
    return payload, hashlib.sha256(raw).hexdigest()


def read_bounded_json(root: Path, relative: str, *, label: str) -> dict[str, Any]:
    """Public test helper using the same descriptor-confined JSON reader."""

    root_descriptor = open_root(root)
    try:
        payload, _ = json_artifact(root_descriptor, relative, label=label)
        return payload
    finally:
        os.close(root_descriptor)


def assert_relative_absent(root_descriptor: int, name: str, *, label: str) -> None:
    if not name or "/" in name or name in {".", ".."}:
        raise InstalledCoreGoldenPathError(f"{label} name is invalid")
    try:
        os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise InstalledCoreGoldenPathError(
            f"{label} absence cannot be verified: {exc}"
        ) from exc
    raise InstalledCoreGoldenPathError(f"{label} must be absent")


def root_still_names_descriptor(root: Path, descriptor: int) -> None:
    if root.is_symlink():
        raise InstalledCoreGoldenPathError("journey root was replaced by a symlink")
    try:
        current = root.stat()
    except OSError as exc:
        raise InstalledCoreGoldenPathError(
            f"journey root cannot be revalidated before proof publication: {exc}"
        ) from exc
    pinned = os.fstat(descriptor)
    if (current.st_dev, current.st_ino) != (pinned.st_dev, pinned.st_ino):
        raise InstalledCoreGoldenPathError(
            "journey root identity changed before proof publication"
        )


def write_result_at(
    root_descriptor: int,
    name: str,
    payload: Mapping[str, Any],
) -> None:
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=root_descriptor)
    except OSError as exc:
        raise InstalledCoreGoldenPathError(
            f"proof output cannot be created safely: {exc}"
        ) from exc
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("proof output write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    except Exception:
        os.close(descriptor)
        try:
            os.unlink(name, dir_fd=root_descriptor)
        except OSError:
            pass
        raise
    else:
        os.close(descriptor)
