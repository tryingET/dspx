"""
MLflow tracing helper for DSPy + Codex Exec.

Enable by setting env vars before running any CLI/script:
- MLFLOW_ENABLE=1 (default 1)
- MLFLOW_TRACKING_URI=http://127.0.0.1:5000 (or your server)
- MLFLOW_EXPERIMENT=DSPy (experiment name)

Usage:
    from tracing import enable_mlflow_from_env
    enable_mlflow_from_env()
"""
from __future__ import annotations

import os
from typing import Optional


def _truthy(val: Optional[str]) -> bool:
    if val is None:
        return True  # default enabled
    return val not in {"", "0", "false", "False", "no", "No"}


def enable_mlflow_from_env() -> bool:
    """Enable MLflow autolog for DSPy using environment variables.

    Returns True if enabled successfully, False otherwise.
    """
    if not _truthy(os.getenv("MLFLOW_ENABLE", "1")):
        return False
    # moved to src/

    try:
        import mlflow
    except Exception:
        # MLflow not installed; do not fail hard
        return False

    uri = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
    exp = os.getenv("MLFLOW_EXPERIMENT", "DSPy")

    try:
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(exp)
        # Enable DSPy autologging
        # Requires MLflow >= 2.18 (provided via uv dependency)
        mlflow.dspy.autolog()
        return True
    except Exception:
        # Fallback to no-op if server not reachable or integration unavailable
        return False
