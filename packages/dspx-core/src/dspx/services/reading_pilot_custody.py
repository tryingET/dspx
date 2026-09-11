"""Cooperative worker-to-parent custody, not provider or hostile-UID authentication."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import sys
import time
from typing import Literal

from dspx.services.reading_pilot_verification import PilotContract, write_private


class ProviderObservationConflict(ValueError):
    """Observation bytes disagree with independently retained custody."""


@dataclass(frozen=True)
class ChildOutcome:
    status: Literal["returned", "failed", "effect_indeterminate"]
    observed_digest: str | None = None


def _environment(
    root: Path, *, case: str | None, contract: PilotContract
) -> dict[str, str]:
    # Clean BEFORE site hooks/imports; descriptor selection is never environmental.
    env = {
        "PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "HOME": str(root / "home"),
        "TMPDIR": str(root / "tmp"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        "DSPX_CACHE_DIR": str(root / "cache"),
        "DSPX_CACHE_ENABLE": "0",
        "DSPY_CACHEDIR": str(root / "cache" / "dspy"),
        "MLFLOW_ENABLE": "0",
        "DSPX_POLICY_MAX_TIMEOUT": str(contract.route.timeout_seconds),
        "DSPX_POLICY_DISALLOWED_CAPS": "network.read",
    }
    if case is None:
        env.update(
            DSPX_PROVIDER="stub",
            DSPX_POLICY_ALLOWED_PROVIDERS="stub",
            DSPX_POLICY_ALLOW_NETWORK_MUTATE="0",
            DSPX_POLICY_DISALLOWED_CAPS="network.read,network.mutate",
        )
    else:
        env.update(
            DSPX_PROVIDER="openai-compatible",
            DSPX_POLICY_ALLOWED_PROVIDERS="openai-compatible",
            DSPX_POLICY_ALLOW_NETWORK_MUTATE="1",
            DSPX_OPENAI_COMPAT_MODEL=contract.route.model,
            DSPX_OPENAI_COMPAT_API_BASE=contract.route.base_url,
            DSPX_OPENAI_COMPAT_TIMEOUT=str(contract.route.timeout_seconds),
        )
    return env


def _receive(fd: int, deadline: float) -> str:
    """Drain concurrently with execution; at most 66 bytes, mandatory EOF/deadline."""
    payload = bytearray()
    os.set_blocking(fd, False)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise TimeoutError
        chunk = os.read(fd, 66 - len(payload))
        if not chunk:
            break
        payload.extend(chunk)
        if len(payload) > 65:
            raise ValueError("oversized custody payload")
    if re.fullmatch(rb"[0-9a-f]{64}\n", payload) is None:
        raise ValueError("invalid custody payload")
    return payload[:64].decode("ascii")


def _kill_reap(process: subprocess.Popen) -> None:
    # Also kill descendants retaining a pipe after their group leader has exited.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    finally:
        process.wait()


def _child(root: Path, contract: PilotContract, case: str | None) -> ChildOutcome:
    label = case or "prepare"
    process = None
    reader = writer = None
    try:
        log = root / f"{label}.log"
        write_private(log, b"")
        args = [sys.executable, "-m", "dspx.services.reading_pilot", label, str(root)]
        if case is not None:
            reader, writer = os.pipe()
            args.append(str(writer))
        deadline = time.monotonic() + contract.route.worker_deadline_seconds
        with log.open("ab") as output:
            process = subprocess.Popen(
                args,
                cwd=root,
                env=_environment(root, case=case, contract=contract),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=output,
                pass_fds=() if writer is None else (writer,),
                start_new_session=True,
                umask=0o077,
            )
            if writer is not None:
                os.close(writer)
                writer = None
            digest = None if reader is None else _receive(reader, deadline)
            code = process.wait(timeout=max(0, deadline - time.monotonic()))
        if code != 0:
            _kill_reap(process)
            return ChildOutcome("failed")
        return ChildOutcome("returned", digest)
    except BaseException:
        if process is not None:
            _kill_reap(process)
        return ChildOutcome("effect_indeterminate" if case else "failed")
    finally:
        for fd in (reader, writer):
            if fd is not None:
                os.close(fd)
