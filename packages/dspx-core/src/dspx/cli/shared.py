# summary: "Provides shared CLI configuration loading and MLflow tracing initialization."
# read_when:
#   - "Changing common command startup, config-file error handling, or tracing enablement."

from __future__ import annotations

import typer

from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env


def ensure_env_and_tracing(config_path: str | None = None) -> None:
    try:
        load_config_env(config_path)
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    enable_mlflow_from_env()
