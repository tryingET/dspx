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

    # Ensure a clean slate.
    try:
        if mlflow.active_run() is not None:  # type: ignore[attr-defined]
            mlflow.end_run()  # type: ignore[attr-defined]
    except Exception:
        pass

    started = ensure_run_with_standard_tags("test", run_name="test-local-run")
    assert started is True
    try:
        assert mlflow.active_run() is not None  # type: ignore[attr-defined]
    finally:
        try:
            mlflow.end_run()  # type: ignore[attr-defined]
        except Exception:
            pass

    # MLflow local default changed across versions:
    # - older versions: file store under ./mlruns
    # - newer versions: sqlite backend at ./mlflow.db
    tracking_uri = str(mlflow.get_tracking_uri())  # type: ignore[attr-defined]
    if tracking_uri.startswith("sqlite:///"):
        sqlite_path = tracking_uri.replace("sqlite:///", "", 1)
        local_sqlite = Path(sqlite_path)
        if not local_sqlite.is_absolute():
            local_sqlite = tmp_path / local_sqlite
        assert local_sqlite.exists()
    else:
        assert (tmp_path / "mlruns").exists()
