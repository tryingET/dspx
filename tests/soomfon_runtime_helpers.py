"""SYNTHETIC executable fixtures: fd mechanics, NEVER historical AK compatibility."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


def synthetic_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str | None = None
) -> Path:
    from dspx.services import soomfon_evaluation_ak_runtime as runtime

    executable = tmp_path / "synthetic-json-executable"
    if body is None:
        body = """import json, os, sys
fd = int(sys.argv[0].rsplit('/', 1)[1])
print(json.dumps({'synthetic': True, 'inheritable': os.get_inheritable(fd),
                  'payload': {'task': {'id': 5061}}}))
"""
    executable.write_text(f"#!{sys.executable} -I\n" + body, encoding="utf-8")
    executable.chmod(0o555)
    monkeypatch.setattr(runtime, "AK_EXECUTABLE", executable)
    monkeypatch.setattr(
        runtime,
        "AK_EXECUTABLE_SHA256",
        hashlib.sha256(executable.read_bytes()).hexdigest(),
    )
    return executable
