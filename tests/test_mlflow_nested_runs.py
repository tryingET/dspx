from __future__ import annotations

from pathlib import Path


def test_nested_run_does_not_end_parent(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    monkeypatch.setenv("MLFLOW_EXPERIMENT", "DSPxNestedTest")
    monkeypatch.setenv("DSPX_MLFLOW_NESTED_RUNS", "1")

    from dspx.tracing import enable_mlflow_from_env, get_mlflow, nested_run_with_tags

    enable_mlflow_from_env()
    mlflow = get_mlflow()
    assert mlflow is not None

    # Start parent explicitly.
    mlflow.start_run(run_name="parent")  # type: ignore[attr-defined]
    try:
        parent_id = mlflow.active_run().info.run_id  # type: ignore[attr-defined]
        with nested_run_with_tags(run_name="child", tags={"k": "v"}):
            assert mlflow.active_run() is not None  # type: ignore[attr-defined]
            child_id = mlflow.active_run().info.run_id  # type: ignore[attr-defined]
            assert child_id != parent_id
        assert mlflow.active_run() is not None  # type: ignore[attr-defined]
        assert mlflow.active_run().info.run_id == parent_id  # type: ignore[attr-defined]
    finally:
        try:
            mlflow.end_run()  # type: ignore[attr-defined]
        except Exception:
            pass
