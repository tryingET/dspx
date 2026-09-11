"""Real OS synthetic-process bounds; no AK binary, database or provider."""

from __future__ import annotations

from pathlib import Path

import pytest
from soomfon_runtime_helpers import synthetic_runtime
from dspx.services import soomfon_evaluation_ak_runtime as runtime


@pytest.mark.parametrize(
    "case", ["timeout", "oversize", "malformed", "nonzero", "permissions", "hashdrift"]
)
def test_synthetic_runtime_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    body = {
        "timeout": "import time; time.sleep(10)",
        "oversize": "print('x' * 8192)",
        "malformed": "print('not-json')",
        "nonzero": "import sys; print('{}'); sys.exit(7)",
    }.get(case)
    executable = synthetic_runtime(tmp_path, monkeypatch, body)
    monkeypatch.setattr(runtime, "_AK_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(runtime, "_MAX_AK_OUTPUT_BYTES", 4096)
    if case == "permissions":
        executable.chmod(0o755)
    if case == "hashdrift":
        executable.chmod(0o755)
        executable.write_text(executable.read_text() + "\n# changed\n")
        executable.chmod(0o555)
    processes = []
    real_popen = runtime.subprocess.Popen

    def track(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(runtime.subprocess, "Popen", track)
    with pytest.raises(runtime.AKRuntimeIdentityError):
        runtime.run_ak_json(("task", "show", "5061", "--machine"))
    assert all(process.poll() is not None for process in processes)
    if case in {"permissions", "hashdrift"}:
        assert not processes
