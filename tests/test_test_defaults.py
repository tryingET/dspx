from __future__ import annotations

import os
from pathlib import Path


def test_suite_defaults_are_offline_and_deterministic() -> None:
    # Enforced by tests/conftest.py (autouse fixture).
    assert os.environ.get("DSPX_PROVIDER") == "stub"
    assert os.environ.get("MLFLOW_ENABLE") == "0"

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI") or ""
    assert tracking_uri.startswith("sqlite:///")
    db_path = Path(tracking_uri.removeprefix("sqlite:///"))
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    assert db_path.name.startswith(f"dspx_mlflow_tests_{worker}_")
    assert db_path.suffix == ".db"
