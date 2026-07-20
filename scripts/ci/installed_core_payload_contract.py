# ---
# summary: "Verifies installed Core payload files against the selected wheel's original RECORD."
# read_when:
#   - "Changing exact-wheel installed payload identity or package tamper detection."
# ---

from __future__ import annotations

import base64
import csv
import hashlib
from io import BytesIO, TextIOWrapper
import os
from pathlib import Path, PurePosixPath
import py_compile
import stat
import sys
import tempfile
import zipfile

from installed_core_proof_io import InstalledCoreGoldenPathError


MAX_WHEEL_BYTES = 512 * 1024 * 1024
MAX_INSTALLED_FILE_BYTES = 64 * 1024 * 1024


def _stable_regular_bytes(path: Path, *, label: str, limit: int) -> bytes:
    lexical = path.absolute()
    try:
        before = lexical.lstat()
    except OSError as exc:
        raise InstalledCoreGoldenPathError(f"{label} is unavailable: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise InstalledCoreGoldenPathError(
            f"{label} must be a non-symlink regular file"
        )
    if before.st_size > limit:
        raise InstalledCoreGoldenPathError(f"{label} exceeds {limit} bytes")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lexical, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise InstalledCoreGoldenPathError(f"{label} changed before opening")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise InstalledCoreGoldenPathError(f"{label} exceeds {limit} bytes")
        after = os.fstat(descriptor)
        if (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise InstalledCoreGoldenPathError(f"{label} changed while reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _safe_record_path(value: str) -> PurePosixPath:
    if not value or "\\" in value or value.startswith("/"):
        raise InstalledCoreGoldenPathError("wheel RECORD contains an unsafe path")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise InstalledCoreGoldenPathError("wheel RECORD contains an unsafe path")
    return PurePosixPath(*raw_parts)


def _installed_file_bytes(
    site_root: Path,
    relative: PurePosixPath,
    *,
    expected_size: int,
) -> bytes:
    if expected_size < 0 or expected_size > MAX_INSTALLED_FILE_BYTES:
        raise InstalledCoreGoldenPathError(
            f"wheel RECORD size is invalid for {relative.as_posix()}"
        )
    current = site_root
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            observed = current.lstat()
        except OSError as exc:
            raise InstalledCoreGoldenPathError(
                f"wheel RECORD file is missing from installation: {relative.as_posix()}"
            ) from exc
        if stat.S_ISLNK(observed.st_mode):
            raise InstalledCoreGoldenPathError(
                f"installed wheel payload is symlinked: {relative.as_posix()}"
            )
        final = index == len(relative.parts) - 1
        if final and not stat.S_ISREG(observed.st_mode):
            raise InstalledCoreGoldenPathError(
                f"installed wheel payload is not regular: {relative.as_posix()}"
            )
        if not final and not stat.S_ISDIR(observed.st_mode):
            raise InstalledCoreGoldenPathError(
                f"installed wheel payload parent is not a directory: {relative.as_posix()}"
            )
    raw = _stable_regular_bytes(
        current,
        label=f"installed wheel payload {relative.as_posix()}",
        limit=MAX_INSTALLED_FILE_BYTES,
    )
    if len(raw) != expected_size:
        raise InstalledCoreGoldenPathError(
            f"installed wheel payload size drift: {relative.as_posix()}"
        )
    return raw


def _record_rows(
    wheel_raw: bytes,
) -> tuple[list[tuple[PurePosixPath, str, int | None]], PurePosixPath]:
    try:
        with zipfile.ZipFile(BytesIO(wheel_raw)) as archive:
            archive_files: set[PurePosixPath] = set()
            for info in archive.infolist():
                raw_name = info.filename[:-1] if info.is_dir() else info.filename
                path = _safe_record_path(raw_name)
                if not info.is_dir():
                    if path in archive_files:
                        raise InstalledCoreGoldenPathError(
                            "Core wheel archive path is duplicated"
                        )
                    archive_files.add(path)
            record_paths = [
                path
                for path in archive_files
                if path.as_posix().endswith(".dist-info/RECORD")
            ]
            if len(record_paths) != 1:
                raise InstalledCoreGoldenPathError(
                    "Core wheel must contain exactly one RECORD"
                )
            record_path = record_paths[0]
            with archive.open(record_path.as_posix()) as source:
                reader = csv.reader(TextIOWrapper(source, encoding="utf-8", newline=""))
                rows = list(reader)
    except (UnicodeDecodeError, zipfile.BadZipFile, KeyError, csv.Error) as exc:
        raise InstalledCoreGoldenPathError("Core wheel RECORD is invalid") from exc
    parsed: list[tuple[PurePosixPath, str, int | None]] = []
    seen: set[PurePosixPath] = set()
    self_row_count = 0
    for row in rows:
        if len(row) != 3:
            raise InstalledCoreGoldenPathError("Core wheel RECORD row is malformed")
        path = _safe_record_path(row[0])
        if path in seen:
            raise InstalledCoreGoldenPathError("Core wheel RECORD path is duplicated")
        seen.add(path)
        try:
            size = int(row[2]) if row[2] else None
        except ValueError as exc:
            raise InstalledCoreGoldenPathError(
                "Core wheel RECORD size is invalid"
            ) from exc
        if path == record_path:
            self_row_count += 1
            if row[1] or size is not None:
                raise InstalledCoreGoldenPathError(
                    "Core wheel RECORD self-row is malformed"
                )
        elif not row[1] or size is None:
            raise InstalledCoreGoldenPathError(
                f"wheel RECORD hash/size is missing: {path.as_posix()}"
            )
        parsed.append((path, row[1], size))
    if self_row_count != 1:
        raise InstalledCoreGoldenPathError("Core wheel RECORD self-row is missing")
    if seen != archive_files:
        raise InstalledCoreGoldenPathError(
            "Core wheel RECORD does not close the archive"
        )
    return parsed, record_path


def _verify_source_cache(
    cache_path: Path, *, source_path: Path, relative: Path
) -> None:
    observed = cache_path.lstat()
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise InstalledCoreGoldenPathError(
            f"installed dspx source cache is unsafe: {relative}"
        )
    parts = cache_path.name.split(".")
    cache_tag = sys.implementation.cache_tag
    if (
        cache_tag is None
        or len(parts) not in {3, 4}
        or parts[1] != cache_tag
        or parts[-1] != "pyc"
    ):
        raise InstalledCoreGoldenPathError(
            f"installed dspx source cache name is invalid: {relative}"
        )
    optimize = 0
    if len(parts) == 4:
        if not parts[2].startswith("opt-") or not parts[2][4:].isdigit():
            raise InstalledCoreGoldenPathError(
                f"installed dspx source cache optimization is invalid: {relative}"
            )
        optimize = int(parts[2][4:])
    cache_raw = _stable_regular_bytes(
        cache_path,
        label=f"installed dspx source cache {relative}",
        limit=MAX_INSTALLED_FILE_BYTES,
    )
    if len(cache_raw) < 16:
        raise InstalledCoreGoldenPathError(
            f"installed dspx source cache is truncated: {relative}"
        )
    flags = int.from_bytes(cache_raw[4:8], "little")
    invalidation_modes = {
        0: py_compile.PycInvalidationMode.TIMESTAMP,
        1: py_compile.PycInvalidationMode.UNCHECKED_HASH,
        3: py_compile.PycInvalidationMode.CHECKED_HASH,
    }
    invalidation_mode = invalidation_modes.get(flags)
    if invalidation_mode is None:
        raise InstalledCoreGoldenPathError(
            f"installed dspx source cache flags are invalid: {relative}"
        )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="dspx-pyc-verify-", suffix=".pyc"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        py_compile.compile(
            str(source_path),
            cfile=str(temporary),
            dfile=str(source_path),
            doraise=True,
            optimize=optimize,
            invalidation_mode=invalidation_mode,
        )
        expected_raw = _stable_regular_bytes(
            temporary,
            label="independently compiled dspx source cache",
            limit=MAX_INSTALLED_FILE_BYTES,
        )
    except py_compile.PyCompileError as exc:
        raise InstalledCoreGoldenPathError(
            f"installed dspx source cache could not be reproduced: {relative}"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    if cache_raw != expected_raw:
        raise InstalledCoreGoldenPathError(
            f"installed dspx source cache drift: {relative}"
        )


def _installed_package_paths(
    site_root: Path, *, expected_package_paths: set[PurePosixPath]
) -> set[PurePosixPath]:
    """Return wheel-owned package files after verifying derived bytecode caches."""
    package_root = site_root / "dspx"
    if not package_root.is_dir() or package_root.is_symlink():
        raise InstalledCoreGoldenPathError("installed dspx package root is invalid")
    observed: set[PurePosixPath] = set()
    for directory, dirnames, filenames in os.walk(package_root, followlinks=False):
        parent = Path(directory)
        for name in list(dirnames):
            child = parent / name
            if child.is_symlink():
                raise InstalledCoreGoldenPathError(
                    f"installed dspx package contains a symlink: {child.relative_to(site_root)}"
                )
        for name in filenames:
            child = parent / name
            relative = child.relative_to(site_root)
            if "__pycache__" in relative.parts:
                cache_index = relative.parts.index("__pycache__")
                cache_parent = PurePosixPath(*relative.parts[:cache_index])
                source_stem = child.name.split(".", 1)[0]
                source_path = cache_parent / f"{source_stem}.py"
                if (
                    child.suffix not in {".pyc", ".pyo"}
                    or source_path not in expected_package_paths
                ):
                    raise InstalledCoreGoldenPathError(
                        f"installed dspx package contains undeclared cache content: {relative}"
                    )
                _verify_source_cache(
                    child,
                    source_path=site_root.joinpath(*source_path.parts),
                    relative=relative,
                )
                continue
            if child.suffix in {".pyc", ".pyo"}:
                raise InstalledCoreGoldenPathError(
                    f"installed dspx package contains bytecode outside a source cache: {relative}"
                )
            observed_state = child.lstat()
            if stat.S_ISLNK(observed_state.st_mode) or not stat.S_ISREG(
                observed_state.st_mode
            ):
                raise InstalledCoreGoldenPathError(
                    f"installed dspx package file is unsafe: {relative}"
                )
            observed.add(PurePosixPath(relative.as_posix()))
    return observed


def verify_installed_payload(
    *, wheel_path: Path, site_packages_root: Path
) -> dict[str, object]:
    """Bind every wheel RECORD payload and complete importable package inventory."""

    wheel_raw = _stable_regular_bytes(
        wheel_path, label="installed Core wheel", limit=MAX_WHEEL_BYTES
    )
    site_root = site_packages_root.resolve()
    expected_package_paths: set[PurePosixPath] = set()
    verified_count = 0
    record_rows, record_path = _record_rows(wheel_raw)
    for relative, hash_field, expected_size in record_rows:
        if relative == record_path:
            continue
        if expected_size is None:
            raise InstalledCoreGoldenPathError("wheel RECORD size is missing")
        if not hash_field.startswith("sha256="):
            raise InstalledCoreGoldenPathError(
                f"wheel RECORD hash algorithm is unsupported: {relative.as_posix()}"
            )
        raw = _installed_file_bytes(site_root, relative, expected_size=expected_size)
        expected_digest = hash_field.removeprefix("sha256=")
        actual_digest = (
            base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
        )
        if actual_digest != expected_digest:
            raise InstalledCoreGoldenPathError(
                f"installed wheel payload hash drift: {relative.as_posix()}"
            )
        verified_count += 1
        if relative.parts[0] == "dspx":
            expected_package_paths.add(relative)
    observed_package_paths = _installed_package_paths(
        site_root, expected_package_paths=expected_package_paths
    )
    if observed_package_paths != expected_package_paths:
        missing = sorted(
            path.as_posix() for path in expected_package_paths - observed_package_paths
        )
        unexpected = sorted(
            path.as_posix() for path in observed_package_paths - expected_package_paths
        )
        raise InstalledCoreGoldenPathError(
            f"installed dspx package inventory drift: missing={missing!r}, unexpected={unexpected!r}"
        )
    return {
        "wheel_sha256": hashlib.sha256(wheel_raw).hexdigest(),
        "record_verified_file_count": verified_count,
        "package_inventory_verified": True,
    }
