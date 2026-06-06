from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (
    _REPO_ROOT / "packages" / "dspx-core" / "src",
    _REPO_ROOT / "apps" / "forge" / "src",
):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)


def _default_mlflow_tracking_uri() -> str:
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    safe_worker = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_" for char in worker
    )
    db_path = (
        Path(tempfile.gettempdir())
        / f"dspx_mlflow_tests_{safe_worker}_{os.getpid()}.db"
    )
    return f"sqlite:///{db_path}"


@pytest.fixture(autouse=True)
def _default_provider_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    # Avoid accidental MLflow HTTP calls from third-party libraries (e.g., DSPy)
    # when a user has an HTTP tracking URI in a local config.
    monkeypatch.setenv("MLFLOW_TRACKING_URI", _default_mlflow_tracking_uri())
