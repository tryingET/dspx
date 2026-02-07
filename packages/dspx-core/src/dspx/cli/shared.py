from __future__ import annotations

from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env


def ensure_env_and_tracing(config_path: str | None = None) -> None:
    load_config_env(config_path)
    enable_mlflow_from_env()
