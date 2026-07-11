# summary: "Tests that enabled MLflow still requires an explicit tracking URI."
# read_when:
#   - "Changing MLflow defaults, run creation, or local-store safeguards."

from __future__ import annotations

from pathlib import Path


def test_mlflow_enabled_without_tracking_uri_does_not_create_local_store(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.setenv("MLFLOW_EXPERIMENT", "DSPxTest")
    monkeypatch.delenv("MLFLOW_RUN_NAME", raising=False)

    from dspx.tracing import (
        default_tracking_uri_from_env,
        enable_mlflow_from_env,
        ensure_run_with_standard_tags,
        get_mlflow,
    )

    assert default_tracking_uri_from_env() == ""
    assert get_mlflow() is None
    assert enable_mlflow_from_env() is False
    assert ensure_run_with_standard_tags("test", run_name="test-local-run") is False
    assert not (tmp_path / "mlflow.db").exists()
    assert not (tmp_path / "mlruns").exists()
