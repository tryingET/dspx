from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

_CONFIG_MANAGED_VALUES: dict[str, str] = {}
_SECRET_KEY_NAMES = {
    "access_token",
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
}
_SECRET_KEY_SUFFIXES = (
    "_access_token",
    "_api_key",
    "_password",
    "_secret",
    "_token",
)


def _coerce_bool(val: Any) -> str:
    if isinstance(val, bool):
        return "1" if val else "0"
    s = str(val).strip().lower()
    return "0" if s in {"0", "false", "no", "off", ""} else "1"


def _set_config_value(key: str, value: Optional[str], *, seen_keys: set[str]) -> None:
    seen_keys.add(key)
    previous = _CONFIG_MANAGED_VALUES.get(key)
    current = os.getenv(key)

    if value is None:
        if previous is not None and current == previous:
            os.environ.pop(key, None)
        _CONFIG_MANAGED_VALUES.pop(key, None)
        return

    if current is None or (previous is not None and current == previous):
        os.environ[key] = value
    _CONFIG_MANAGED_VALUES[key] = value


def _refresh_removed_config_values(seen_keys: set[str]) -> None:
    for key, previous in list(_CONFIG_MANAGED_VALUES.items()):
        if key in seen_keys:
            continue
        if os.getenv(key) == previous:
            os.environ.pop(key, None)
        _CONFIG_MANAGED_VALUES.pop(key, None)


def _looks_secret_key(name: str) -> bool:
    lowered = str(name or "").strip().lower()
    return lowered in _SECRET_KEY_NAMES or lowered.endswith(_SECRET_KEY_SUFFIXES)


def _format_secret_path(parts: tuple[str, ...]) -> str:
    rendered = ""
    for part in parts:
        if part.startswith("["):
            rendered += part
        elif rendered:
            rendered += f".{part}"
        else:
            rendered = part
    return rendered


def _iter_secret_paths(value: Any, prefix: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            next_prefix = (*prefix, key)
            if _looks_secret_key(key):
                yield _format_secret_path(next_prefix)
            yield from _iter_secret_paths(raw_value, next_prefix)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_secret_paths(item, (*prefix, f"[{index}]"))


def _reject_embedded_secrets(data: Dict[str, Any], *, path: Path) -> None:
    secret_paths = sorted(set(_iter_secret_paths(data)))
    if not secret_paths:
        return
    joined = ", ".join(secret_paths)
    raise ValueError(
        "DSPx config TOML must not embed secrets; use environment or CI-provided "
        f"secret injection instead ({joined}) at {path}"
    )


def _load_toml(path: Path) -> Dict[str, Any]:
    try:
        import tomllib  # Python 3.11+
    except Exception:
        # Optional fallback if someone pins older Python (not expected here)
        try:
            import tomli as tomllib  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "TOML parser unavailable for DSPx config loading"
            ) from exc
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Failed to parse DSPx config TOML at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"DSPx config TOML must parse to a table at {path}")
    _reject_embedded_secrets(data, path=path)
    return data


def _find_config_path(explicit: Optional[str]) -> Optional[Path]:
    """Return the best config path to use, if any.

    Priority:
    1) `explicit` argument if provided and exists; otherwise fail closed
    2) `DSPX_CONFIG` env var if set and exists; otherwise fail closed
    3) Nearest `config.toml` by walking up from CWD
    4) Fallback: None
    """
    # 1) explicit
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if p.exists():
            return p
        raise FileNotFoundError(f"explicit DSPx config path not found: {p}")
    # 2) env var
    env_p = os.getenv("DSPX_CONFIG")
    if env_p:
        p = Path(env_p).expanduser().resolve()
        if p.exists():
            return p
        raise FileNotFoundError(f"DSPX_CONFIG path not found: {p}")
    # 3) walk up from CWD
    cur = Path.cwd().resolve()
    for parent in [cur] + list(cur.parents):
        cand = parent / "config.toml"
        if cand.exists():
            return cand
    return None


def load_config_env(path: Optional[str] = None) -> Dict[str, Any]:
    """Load config from a TOML file and export to environment variables.

    Returns the parsed config dict (possibly empty).
    """
    cfg_path = _find_config_path(path)
    data: Dict[str, Any] = {}
    if cfg_path and cfg_path.exists():
        data = _load_toml(cfg_path)

    # Sections: [mlflow], [codex], [openrouter], [pi], [provider], [lm_auth],
    # [openai_compatible], [vllm], [optimize]
    mlflow = data.get("mlflow", {}) if isinstance(data, dict) else {}
    codex = data.get("codex", {}) if isinstance(data, dict) else {}
    openrouter = data.get("openrouter", {}) if isinstance(data, dict) else {}
    pi = data.get("pi", {}) if isinstance(data, dict) else {}
    provider = data.get("provider", {}) if isinstance(data, dict) else {}
    lm_auth = data.get("lm_auth", {}) if isinstance(data, dict) else {}
    openai_compatible = (
        data.get("openai_compatible", {}) if isinstance(data, dict) else {}
    )
    vllm = data.get("vllm", {}) if isinstance(data, dict) else {}
    optimize = data.get("optimize", {}) if isinstance(data, dict) else {}

    seen_keys: set[str] = set()

    # MLflow envs
    _set_config_value(
        "MLFLOW_ENABLE",
        _coerce_bool(mlflow.get("enable", True)),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "MLFLOW_TRACKING_URI",
        mlflow.get("tracking_uri"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "MLFLOW_EXPERIMENT",
        mlflow.get("experiment", "DSPy"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "MLFLOW_ARTIFACT_ROOT",
        mlflow.get("artifact_root"),
        seen_keys=seen_keys,
    )

    # Codex Exec envs
    _set_config_value("CODEX_MODEL", codex.get("model"), seen_keys=seen_keys)
    _set_config_value(
        "CODEX_REASONING",
        codex.get("reasoning_effort"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "CODEX_BYPASS",
        _coerce_bool(codex.get("bypass", False)),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "CODEX_SEARCH",
        _coerce_bool(codex.get("search", False)),
        seen_keys=seen_keys,
    )

    # OpenRouter envs (avoid secrets in TOML; API key should come from env/CI secrets)
    _set_config_value(
        "OPENROUTER_BASE_URL",
        openrouter.get("base_url"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "OPENROUTER_MODEL",
        openrouter.get("model"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "OPENROUTER_TIMEOUT",
        str(openrouter.get("timeout_s"))
        if openrouter.get("timeout_s") is not None
        else None,
        seen_keys=seen_keys,
    )
    _set_config_value(
        "OPENROUTER_HTTP_REFERER",
        openrouter.get("http_referer"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "OPENROUTER_APP_TITLE",
        openrouter.get("app_title"),
        seen_keys=seen_keys,
    )

    # Pi RPC envs
    _set_config_value(
        "DSPX_PI_PROVIDER",
        pi.get("provider"),
        seen_keys=seen_keys,
    )
    _set_config_value("DSPX_PI_MODEL", pi.get("model"), seen_keys=seen_keys)
    _set_config_value(
        "DSPX_PI_THINKING",
        pi.get("thinking"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_PI_TIMEOUT",
        str(pi.get("timeout_s")) if pi.get("timeout_s") is not None else None,
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_PI_NO_TOOLS",
        _coerce_bool(pi.get("no_tools")) if "no_tools" in pi else None,
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_PI_NO_SESSION",
        _coerce_bool(pi.get("no_session")) if "no_session" in pi else None,
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_PI_DISABLE_RESOURCES",
        _coerce_bool(pi.get("disable_resources"))
        if "disable_resources" in pi
        else None,
        seen_keys=seen_keys,
    )

    # dspy-lm-auth envs
    _set_config_value(
        "DSPX_LM_AUTH_MODEL",
        lm_auth.get("model"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_LM_AUTH_PROVIDER",
        lm_auth.get("auth_provider"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_LM_AUTH_STORAGE",
        lm_auth.get("auth_storage"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_LM_AUTH_TIMEOUT",
        str(lm_auth.get("timeout_s")) if lm_auth.get("timeout_s") is not None else None,
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_LM_AUTH_STRICT",
        _coerce_bool(lm_auth.get("strict")) if "strict" in lm_auth else None,
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_LM_AUTH_TEMPERATURE",
        str(lm_auth.get("temperature")) if "temperature" in lm_auth else None,
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_LM_AUTH_MAX_TOKENS",
        str(lm_auth.get("max_tokens")) if "max_tokens" in lm_auth else None,
        seen_keys=seen_keys,
    )

    # Generic OpenAI-compatible envs (useful for local vLLM)
    _set_config_value(
        "DSPX_OPENAI_COMPAT_API_BASE",
        openai_compatible.get("api_base"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_OPENAI_COMPAT_MODEL",
        openai_compatible.get("model"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_OPENAI_COMPAT_TIMEOUT",
        str(openai_compatible.get("timeout_s"))
        if openai_compatible.get("timeout_s") is not None
        else None,
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_OPENAI_COMPAT_JSON_MODE",
        _coerce_bool(openai_compatible.get("json_mode"))
        if "json_mode" in openai_compatible
        else None,
        seen_keys=seen_keys,
    )

    # Local vLLM convenience envs
    _set_config_value(
        "DSPX_VLLM_API_BASE",
        vllm.get("api_base"),
        seen_keys=seen_keys,
    )
    _set_config_value("DSPX_VLLM_MODEL", vllm.get("model"), seen_keys=seen_keys)
    _set_config_value(
        "DSPX_VLLM_TIMEOUT",
        str(vllm.get("timeout_s")) if vllm.get("timeout_s") is not None else None,
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_VLLM_JSON_MODE",
        _coerce_bool(vllm.get("json_mode")) if "json_mode" in vllm else None,
        seen_keys=seen_keys,
    )

    # Optimization provider defaults
    _set_config_value(
        "DSPX_OPTIMIZE_STUDENT_PROVIDER",
        optimize.get("student_provider"),
        seen_keys=seen_keys,
    )
    _set_config_value(
        "DSPX_OPTIMIZE_REFLECTION_PROVIDER",
        optimize.get("reflection_provider"),
        seen_keys=seen_keys,
    )

    # Provider selection env
    _set_config_value("DSPX_PROVIDER", provider.get("name"), seen_keys=seen_keys)

    _refresh_removed_config_values(seen_keys)
    return data
