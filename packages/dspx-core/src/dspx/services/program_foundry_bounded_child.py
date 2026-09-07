"""POSIX bounded duplex child I/O; transport protection, not a sandbox."""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence


class ChildOutputLimit(ValueError):
    """Child exceeded the captured stdout budget."""


def run_bounded_child(
    argv: Sequence[str],
    *,
    payload: bytes,
    env: Mapping[str, str],
    timeout: float,
    max_output: int,
) -> subprocess.CompletedProcess[bytes]:
    if timeout <= 0 or max_output < 0:
        raise ValueError("invalid child budget")
    process = subprocess.Popen(
        list(argv),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=dict(env),
        close_fds=True,
        start_new_session=True,
    )
    assert process.stdin is not None and process.stdout is not None
    deadline = time.monotonic() + timeout
    output = bytearray()
    pending = memoryview(payload)
    try:
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdin.fileno(), False)
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            if pending:
                selector.register(process.stdin, selectors.EVENT_WRITE)
            else:
                process.stdin.close()
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(list(argv), timeout)
                for key, _ in selector.select(remaining):
                    if key.fileobj is process.stdout:
                        chunk = os.read(
                            process.stdout.fileno(),
                            min(65536, max_output - len(output) + 1),
                        )
                        if not chunk:
                            selector.unregister(process.stdout)
                            process.stdout.close()
                        else:
                            if len(output) + len(chunk) > max_output:
                                raise ChildOutputLimit("child stdout limit exceeded")
                            output.extend(chunk)
                    else:
                        try:
                            written = os.write(process.stdin.fileno(), pending[:65536])
                            pending = pending[written:]
                        except BrokenPipeError:
                            pending = memoryview(b"")
                        if not pending:
                            selector.unregister(process.stdin)
                            process.stdin.close()
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        return subprocess.CompletedProcess(
            list(argv), process.returncode, bytes(output), b""
        )
    finally:
        # Also terminate descendants that closed inherited streams before their leader.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.stdin.close()
        process.stdout.close()
        process.wait(timeout=5)
