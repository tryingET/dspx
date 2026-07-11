# summary: "Shared helpers for constructing local and SQLite-backed MLflow runs and DSPx run receipts."
# read_when:
#   - "Testing run-receipt ingestion, MLflow artifacts, tracking setup, or signature receipts."

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()


def _end_active_mlflow_runs() -> None:
    try:
        import mlflow
    except Exception:
        return

    try:
        active_run = getattr(mlflow, "active_run", None)
        end_run = getattr(mlflow, "end_run", None)
        if not callable(active_run) or not callable(end_run):
            return
        while active_run() is not None:
            end_run()
    except Exception:
        pass


def _write_fake_local_mlflow_run(
    tracking_root: Path,
    *,
    experiment_id: str,
    run_id: str,
    artifacts: dict[str, str],
    tags: dict[str, str],
) -> None:
    run_dir = tracking_root / experiment_id / run_id
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in artifacts.items():
        path = artifacts_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    (run_dir / "meta.yaml").write_text(
        "\n".join(
            [
                f"run_id: {run_id}",
                f"experiment_id: {experiment_id}",
                "status: FINISHED",
                "lifecycle_stage: active",
                "start_time: 1",
                "end_time: 2",
                f"artifact_uri: {artifacts_dir.resolve().as_uri()}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tags_dir = run_dir / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)
    for key, value in tags.items():
        tag_path = tags_dir / key
        tag_path.parent.mkdir(parents=True, exist_ok=True)
        tag_path.write_text(str(value), encoding="utf-8")


def _write_sqlite_mlflow_run(
    tmp_path: Path,
    *,
    run_name: str,
    artifacts: dict[str, str],
    tags: dict[str, str],
) -> str:
    import mlflow

    mlflow_any = cast(Any, mlflow)
    staging_root = tmp_path / "mlflow-artifact-staging" / run_name
    with mlflow_any.start_run(run_name=run_name) as run:
        mlflow_any.set_tags(tags)
        for rel_path, content in artifacts.items():
            source = staging_root / rel_path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(content, encoding="utf-8")
            artifact_parent = Path(rel_path).parent.as_posix()
            mlflow_any.log_artifact(
                str(source),
                artifact_path=None if artifact_parent == "." else artifact_parent,
            )
        return str(run.info.run_id)


def _setup_sqlite_mlflow(
    tmp_path: Path,
    monkeypatch,
    *,
    experiment_name: str,
) -> str:
    import mlflow
    from mlflow import MlflowClient

    tracking_db = tmp_path / "tracking" / "mlflow.db"
    tracking_db.parent.mkdir(parents=True, exist_ok=True)
    tracking_uri = f"sqlite:///{tracking_db}"
    artifact_root = tmp_path / "mlflow_artifacts" / experiment_name
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking_uri)
    monkeypatch.setenv("MLFLOW_EXPERIMENT", experiment_name)
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)
    try:
        client.create_experiment(
            experiment_name,
            artifact_location=artifact_root.resolve().as_uri(),
        )
    except Exception:
        pass
    mlflow.set_experiment(experiment_name)
    return tracking_uri


def _generate_signature_receipt(
    tmp_path: Path, monkeypatch, *, output_name: str
) -> Path:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / output_name
    result = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(out),
        ],
    )
    assert result.exit_code == 0
    return tmp_path / f"{output_name}.meta.json"
