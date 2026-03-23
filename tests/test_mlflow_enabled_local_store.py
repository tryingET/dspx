from __future__ import annotations

from pathlib import Path


def test_mlflow_enabled_without_tracking_uri_uses_local_store(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.setenv("MLFLOW_EXPERIMENT", "DSPxTest")
    monkeypatch.delenv("MLFLOW_RUN_NAME", raising=False)

    from dspx.tracing import (
        enable_mlflow_from_env,
        ensure_run_with_standard_tags,
        get_mlflow,
    )

    mlflow = get_mlflow()
    assert mlflow is not None
    enable_mlflow_from_env()
    active_run = getattr(mlflow, "active_run", None)
    end_run = getattr(mlflow, "end_run", None)
    get_tracking_uri = getattr(mlflow, "get_tracking_uri", None)
    assert callable(active_run)
    assert callable(end_run)
    assert callable(get_tracking_uri)

    # Ensure a clean slate.
    try:
        if active_run() is not None:
            end_run()
    except Exception:
        pass

    started = ensure_run_with_standard_tags("test", run_name="test-local-run")
    assert started is True
    try:
        assert active_run() is not None
    finally:
        try:
            end_run()
        except Exception:
            pass

    # DSPx policy: local default backend is sqlite for deterministic behavior.
    tracking_uri = str(get_tracking_uri())
    assert tracking_uri == "sqlite:///mlflow.db"
    assert (tmp_path / "mlflow.db").exists()
