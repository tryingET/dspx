# summary: "Tests that nested MLflow runs restore rather than end their parent run."
# read_when:
#   - "Changing nested tracing contexts or MLflow run lifecycle handling."

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
    start_run = getattr(mlflow, "start_run", None)
    active_run = getattr(mlflow, "active_run", None)
    end_run = getattr(mlflow, "end_run", None)
    assert callable(start_run)
    assert callable(active_run)
    assert callable(end_run)

    # Start parent explicitly.
    start_run(run_name="parent")
    try:
        parent = active_run()
        assert parent is not None
        parent_id = parent.info.run_id
        with nested_run_with_tags(run_name="child", tags={"k": "v"}):
            current = active_run()
            assert current is not None
            child_id = current.info.run_id
            assert child_id != parent_id
        current = active_run()
        assert current is not None
        assert current.info.run_id == parent_id
    finally:
        try:
            end_run()
        except Exception:
            pass
