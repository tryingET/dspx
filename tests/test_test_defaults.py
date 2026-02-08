from __future__ import annotations


def test_suite_defaults_are_offline_and_deterministic() -> None:
    # Enforced by tests/conftest.py (autouse fixture).
    import os

    assert os.environ.get("DSPX_PROVIDER") == "stub"
    assert os.environ.get("MLFLOW_ENABLE") == "0"
    assert (
        os.environ.get("MLFLOW_TRACKING_URI") == "sqlite:////tmp/dspx_mlflow_tests.db"
    )
