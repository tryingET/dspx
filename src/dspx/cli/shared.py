from __future__ import annotations

from pathlib import Path
import sys

from config_loader import load_config_env
from tracing import enable_mlflow_from_env


def ensure_env_and_tracing(config_path: str | None = None) -> None:
    load_config_env(config_path)
    enable_mlflow_from_env()


def ensure_vibe_path() -> None:
    here = Path(__file__).resolve().parents[2]
    vibe_src = here / "submodules" / "vibe-dspy" / "src"
    if vibe_src.is_dir() and str(vibe_src) not in sys.path:
        sys.path.insert(0, str(vibe_src))
