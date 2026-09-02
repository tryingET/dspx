"""Pinned descriptor-executed AK reader for foundry jury call authority."""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import stat
import subprocess
import time
from pathlib import Path
from typing import Any, NoReturn

AK_EXECUTABLE = Path(
    "/home/tryinget/.local/libexec/agent-kernel/"
    "cdeef5bfedcb1b19ee18921008f876ecd05eb8ca/ak-bin"
)
AK_EXECUTABLE_SHA256 = (
    "056873b145604fb94da799aa4b8d442f86356eaeddd3c001752e19ac14dd53da"
)
AK_EXECUTABLE_MODE = 0o555
_MAX_EXECUTABLE_BYTES = 64 * 1024 * 1024
_MAX_OUTPUT_BYTES = 256 * 1024
_TIMEOUT_SECONDS = 5.0


class FoundryJuryAKRuntimeError(RuntimeError):
    """The pinned AK runtime or bounded task read was rejected."""


def _reject() -> NoReturn:
    raise FoundryJuryAKRuntimeError("foundry jury canonical AK runtime rejected")


def _identity(info: os.stat_result) -> tuple[int, ...]:
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


def _open_verified_executable() -> tuple[int, os.stat_result]:
    try:
        descriptor = os.open(AK_EXECUTABLE, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        _reject()
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != AK_EXECUTABLE_MODE
            or not 0 < before.st_size <= _MAX_EXECUTABLE_BYTES
        ):
            _reject()
        digest = hashlib.sha256()
        size = 0
        for block in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
            size += len(block)
            digest.update(block)
        after_hash = os.fstat(descriptor)
        if (
            size != before.st_size
            or digest.hexdigest() != AK_EXECUTABLE_SHA256
            or _identity(after_hash) != _identity(before)
        ):
            _reject()
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor, before
    except BaseException:
        os.close(descriptor)
        raise


def run_ak_task_show(task_id: int) -> dict[str, Any]:
    """Read one task through the exact already-opened AK executable."""

    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 1:
        _reject()
    descriptor, before = _open_verified_executable()
    process: subprocess.Popen[bytes] | None = None
    selector = selectors.DefaultSelector()
    output = bytearray()
    try:
        process = subprocess.Popen(
            [
                f"/proc/self/fd/{descriptor}",
                "task",
                "show",
                str(task_id),
                "-F",
                "json",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            close_fds=True,
            pass_fds=(descriptor,),
        )
        if process.stdout is None:  # pragma: no cover - Popen contract
            _reject()
        stdout_descriptor = process.stdout.fileno()
        os.set_blocking(stdout_descriptor, False)
        selector.register(stdout_descriptor, selectors.EVENT_READ)
        deadline = time.monotonic() + _TIMEOUT_SECONDS
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
                        min(64 * 1024, _MAX_OUTPUT_BYTES + 1 - len(output)),
                    )
                except BlockingIOError:
                    continue
                if not chunk:
                    eof = True
                    break
                output.extend(chunk)
                if len(output) > _MAX_OUTPUT_BYTES:
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
            after = os.fstat(descriptor)
        except OSError:
            os.close(descriptor)
            _reject()
        os.close(descriptor)
        if _identity(after) != _identity(before):
            _reject()
    try:
        value = json.loads(bytes(output))
    except (UnicodeError, json.JSONDecodeError):
        _reject()
    if not isinstance(value, dict):
        _reject()
    return {str(key): item for key, item in value.items()}
