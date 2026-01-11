from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_provider_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    # Avoid accidental MLflow HTTP calls from third-party libraries (e.g., DSPy)
    # when a user has an HTTP tracking URI in a local config.
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "file:/tmp/dspx_mlruns_tests")
