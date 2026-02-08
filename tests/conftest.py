from __future__ import annotations

import sys
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


@pytest.fixture(autouse=True)
def _default_provider_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    # Avoid accidental MLflow HTTP calls from third-party libraries (e.g., DSPy)
    # when a user has an HTTP tracking URI in a local config.
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "sqlite:////tmp/dspx_mlflow_tests.db")
