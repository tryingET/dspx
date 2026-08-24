"""Pinned, descriptor-executed read-only Agent Kernel runtime."""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import stat
import subprocess
import time
from pathlib import Path
from typing import NoReturn

AK_EXECUTABLE = Path(
    "/home/tryinget/.local/libexec/agent-kernel/"
    "c6297eccf67a3762ef01269f67e87eaa8828f127/ak-bin"
)
AK_EXECUTABLE_SHA256 = (
    "61f6290115262e0319c3b178f053d74a486a3eba881aaa13739c1db45f0f6b91"
)
AK_EXECUTABLE_MODE = 0o555
_MAX_AK_EXECUTABLE_BYTES = 64 * 1024 * 1024
_MAX_AK_OUTPUT_BYTES = 256 * 1024
_AK_TIMEOUT_SECONDS = 5.0


class AKRuntimeIdentityError(RuntimeError):
    """Pinned AK runtime or bounded query execution rejected."""


def _reject() -> NoReturn:
    raise AKRuntimeIdentityError("canonical AK runtime rejected")


def _stat_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _open_verified_ak_executable() -> tuple[int, os.stat_result]:
    """Open and hash the exact executable without following a final symlink."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(AK_EXECUTABLE, flags)
    except OSError:
        _reject()
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != AK_EXECUTABLE_MODE
            or before.st_size <= 0
            or before.st_size > _MAX_AK_EXECUTABLE_BYTES
        ):
            _reject()
        digest = hashlib.sha256()
        size = 0
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            size += len(block)
            digest.update(block)
        after_hash = os.fstat(fd)
        if (
            size != before.st_size
            or digest.hexdigest() != AK_EXECUTABLE_SHA256
            or _stat_identity(after_hash) != _stat_identity(before)
        ):
            _reject()
        os.lseek(fd, 0, os.SEEK_SET)
        return fd, before
    except BaseException:
        os.close(fd)
        raise


def run_ak_json(arguments: tuple[str, ...]) -> object:
    """Execute one exact read-only query through the already-verified fd."""

    allowed = {
        ("task", "show"),
        ("task", "contract"),
        ("evidence", "task"),
        ("evidence", "show"),
    }
    if len(arguments) < 3 or arguments[:2] not in allowed:
        _reject()
    fd, before = _open_verified_ak_executable()
    process: subprocess.Popen[bytes] | None = None
    selector = selectors.DefaultSelector()
    output = bytearray()
    try:
        process = subprocess.Popen(
            [f"/proc/self/fd/{fd}", *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            close_fds=True,
            pass_fds=(fd,),
        )
        if process.stdout is None:  # pragma: no cover - Popen contract
            _reject()
        stdout_fd = process.stdout.fileno()
        os.set_blocking(stdout_fd, False)
        selector.register(stdout_fd, selectors.EVENT_READ)
        deadline = time.monotonic() + _AK_TIMEOUT_SECONDS
        eof = False
        while not eof:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _reject()
            events = selector.select(remaining)
            if not events:
                _reject()
            for key, _mask in events:
                try:
                    chunk = os.read(
                        key.fd,
                        min(64 * 1024, _MAX_AK_OUTPUT_BYTES + 1 - len(output)),
                    )
                except BlockingIOError:
                    continue
                if not chunk:
                    eof = True
                    break
                output.extend(chunk)
                if len(output) > _MAX_AK_OUTPUT_BYTES:
                    _reject()
        returncode = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        if returncode != 0 or not output:
            _reject()
    except (OSError, subprocess.TimeoutExpired):
        _reject()
    finally:
        selector.close()
        if process is not None and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass
        try:
            after = os.fstat(fd)
        except OSError:
            os.close(fd)
            _reject()
        os.close(fd)
        if _stat_identity(after) != _stat_identity(before):
            _reject()
    try:
        return json.loads(bytes(output))
    except (UnicodeError, json.JSONDecodeError):
        _reject()


__all__ = [
    "AK_EXECUTABLE",
    "AK_EXECUTABLE_MODE",
    "AK_EXECUTABLE_SHA256",
    "AKRuntimeIdentityError",
    "run_ak_json",
]
