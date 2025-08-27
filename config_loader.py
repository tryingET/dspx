from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional


def _coerce_bool(val: Any) -> str:
    if isinstance(val, bool):
        return "1" if val else "0"
    s = str(val).strip().lower()
    return "0" if s in {"0", "false", "no", "off", ""} else "1"


def _set_if_missing(key: str, value: Optional[str]) -> None:
    if value is None:
        return
    if os.getenv(key) is None:
        os.environ[key] = value


def _load_toml(path: Path) -> Dict[str, Any]:
    try:
        import tomllib  # Python 3.11+
    except Exception:
        # Optional fallback if someone pins older Python (not expected here)
        try:
            import tomli as tomllib  # type: ignore
        except Exception:
            return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        return data  # type: ignore[return-value]
    except Exception:
        return {}


def load_config_env(path: Optional[str] = None) -> Dict[str, Any]:
    """Load config from a TOML file and export to environment variables.

    Order:
    - If `path` is provided and exists, load it.
    - Else, load `config.toml` from the current working directory if present.

    Returns the parsed config dict (possibly empty).
    """
    cfg_path = Path(path) if path else Path.cwd() / "config.toml"
    data: Dict[str, Any] = {}
    if cfg_path.exists():
        data = _load_toml(cfg_path)

    # Sections: [mlflow], [codex]
    mlflow = data.get("mlflow", {}) if isinstance(data, dict) else {}
    codex = data.get("codex", {}) if isinstance(data, dict) else {}

    # MLflow envs
    _set_if_missing("MLFLOW_ENABLE", _coerce_bool(mlflow.get("enable", True)))
    _set_if_missing("MLFLOW_TRACKING_URI", mlflow.get("tracking_uri"))
    _set_if_missing("MLFLOW_EXPERIMENT", mlflow.get("experiment", "DSPy"))

    # Codex Exec envs
    _set_if_missing("CODEX_MODEL", codex.get("model"))
    _set_if_missing("CODEX_REASONING", codex.get("reasoning_effort"))
    _set_if_missing("CODEX_BYPASS", _coerce_bool(codex.get("bypass", True)))

    return data

