"""
MLflow tracing helper for DSPy + Codex Exec.

Enable by setting env vars before running any CLI/script:
- MLFLOW_ENABLE=1 (default 1)
- MLFLOW_TRACKING_URI=http://127.0.0.1:5000 (or your server)
- MLFLOW_EXPERIMENT=DSPy (experiment name)

Usage:
    from dspx.tracing import enable_mlflow_from_env
    enable_mlflow_from_env()
"""

from __future__ import annotations

import os
from typing import Optional, Dict


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

    try:
        import mlflow
    except Exception:
        # MLflow not installed; do not fail hard
        return False

    uri = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
    exp = os.getenv("MLFLOW_EXPERIMENT", "DSPy")
    run_name = os.getenv("MLFLOW_RUN_NAME")

    try:
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(exp)
        # Enable DSPy autologging
        # Requires MLflow >= 2.18 (provided via uv dependency)
        mlflow.dspy.autolog()

        # If a run name is provided and no run is active, start one so the
        # name shows up in the UI. Scripts can still override by starting
        # their own run explicitly.
        try:
            if run_name and mlflow.active_run() is None:  # type: ignore[attr-defined]
                mlflow.start_run(run_name=run_name)  # type: ignore[attr-defined]
        except Exception:
            # Do not fail tracing if we cannot start a run here
            pass
        return True
    except Exception:
        # Fallback to no-op if server not reachable or integration unavailable
        return False


def ensure_run_from_env(
    run_name: Optional[str] = None, tags: Optional[Dict[str, str]] = None
) -> bool:
    """Ensure an MLflow run is active, using env/defaults when needed.

    - If a run is already active, set provided tags (if any) and return False.
    - If no run is active, start one with `run_name` or `$MLFLOW_RUN_NAME` and
      return True.
    - Honors `MLFLOW_ENABLE` toggle; returns False if disabled or mlflow missing.
    """
    if not _truthy(os.getenv("MLFLOW_ENABLE", "1")):
        return False
    try:
        import mlflow
    except Exception:
        return False

    try:
        if mlflow.active_run() is not None:  # type: ignore[attr-defined]
            if tags:
                for k, v in tags.items():
                    try:
                        mlflow.set_tag(k, v)  # type: ignore[attr-defined]
                    except Exception:
                        pass
            return False
        rn = run_name or os.getenv("MLFLOW_RUN_NAME")
        mlflow.start_run(run_name=rn)  # type: ignore[attr-defined]
        if tags:
            for k, v in tags.items():
                try:
                    mlflow.set_tag(k, v)  # type: ignore[attr-defined]
                except Exception:
                    pass
        return True
    except Exception:
        return False
