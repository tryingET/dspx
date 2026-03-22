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
        return data
    except Exception:
        return {}


def _find_config_path(explicit: Optional[str]) -> Optional[Path]:
    """Return the best config path to use, if any.

    Priority:
    1) `explicit` argument if provided and exists
    2) `DSPX_CONFIG` env var if set and exists
    3) Nearest `config.toml` by walking up from CWD
    4) Fallback: None
    """
    # 1) explicit
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if p.exists():
            return p
    # 2) env var
    env_p = os.getenv("DSPX_CONFIG")
    if env_p:
        p = Path(env_p).expanduser().resolve()
        if p.exists():
            return p
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

    # MLflow envs
    _set_if_missing("MLFLOW_ENABLE", _coerce_bool(mlflow.get("enable", True)))
    _set_if_missing("MLFLOW_TRACKING_URI", mlflow.get("tracking_uri"))
    _set_if_missing("MLFLOW_EXPERIMENT", mlflow.get("experiment", "DSPy"))

    # Codex Exec envs
    _set_if_missing("CODEX_MODEL", codex.get("model"))
    _set_if_missing("CODEX_REASONING", codex.get("reasoning_effort"))
    _set_if_missing("CODEX_BYPASS", _coerce_bool(codex.get("bypass", True)))
    _set_if_missing("CODEX_SEARCH", _coerce_bool(codex.get("search", False)))

    # OpenRouter envs (avoid secrets in TOML; API key should come from env/CI secrets)
    _set_if_missing("OPENROUTER_BASE_URL", openrouter.get("base_url"))
    _set_if_missing("OPENROUTER_MODEL", openrouter.get("model"))
    _set_if_missing(
        "OPENROUTER_TIMEOUT",
        str(openrouter.get("timeout_s"))
        if openrouter.get("timeout_s") is not None
        else None,
    )
    _set_if_missing("OPENROUTER_HTTP_REFERER", openrouter.get("http_referer"))
    _set_if_missing("OPENROUTER_APP_TITLE", openrouter.get("app_title"))

    # Pi RPC envs
    _set_if_missing("DSPX_PI_PROVIDER", pi.get("provider"))
    _set_if_missing("DSPX_PI_MODEL", pi.get("model"))
    _set_if_missing("DSPX_PI_THINKING", pi.get("thinking"))
    _set_if_missing(
        "DSPX_PI_TIMEOUT",
        str(pi.get("timeout_s")) if pi.get("timeout_s") is not None else None,
    )
    if "no_tools" in pi:
        _set_if_missing("DSPX_PI_NO_TOOLS", _coerce_bool(pi.get("no_tools")))
    if "no_session" in pi:
        _set_if_missing("DSPX_PI_NO_SESSION", _coerce_bool(pi.get("no_session")))
    if "disable_resources" in pi:
        _set_if_missing(
            "DSPX_PI_DISABLE_RESOURCES", _coerce_bool(pi.get("disable_resources"))
        )

    # dspy-lm-auth envs
    _set_if_missing("DSPX_LM_AUTH_MODEL", lm_auth.get("model"))
    _set_if_missing("DSPX_LM_AUTH_PROVIDER", lm_auth.get("auth_provider"))
    _set_if_missing("DSPX_LM_AUTH_STORAGE", lm_auth.get("auth_storage"))
    _set_if_missing(
        "DSPX_LM_AUTH_TIMEOUT",
        str(lm_auth.get("timeout_s")) if lm_auth.get("timeout_s") is not None else None,
    )
    if "strict" in lm_auth:
        _set_if_missing("DSPX_LM_AUTH_STRICT", _coerce_bool(lm_auth.get("strict")))
    if "temperature" in lm_auth:
        _set_if_missing("DSPX_LM_AUTH_TEMPERATURE", str(lm_auth.get("temperature")))
    if "max_tokens" in lm_auth:
        _set_if_missing("DSPX_LM_AUTH_MAX_TOKENS", str(lm_auth.get("max_tokens")))

    # Generic OpenAI-compatible envs (useful for local vLLM)
    _set_if_missing("DSPX_OPENAI_COMPAT_API_BASE", openai_compatible.get("api_base"))
    _set_if_missing("DSPX_OPENAI_COMPAT_MODEL", openai_compatible.get("model"))
    _set_if_missing("DSPX_OPENAI_COMPAT_API_KEY", openai_compatible.get("api_key"))
    _set_if_missing(
        "DSPX_OPENAI_COMPAT_TIMEOUT",
        str(openai_compatible.get("timeout_s"))
        if openai_compatible.get("timeout_s") is not None
        else None,
    )
    if "json_mode" in openai_compatible:
        _set_if_missing(
            "DSPX_OPENAI_COMPAT_JSON_MODE",
            _coerce_bool(openai_compatible.get("json_mode")),
        )

    # Local vLLM convenience envs
    _set_if_missing("DSPX_VLLM_API_BASE", vllm.get("api_base"))
    _set_if_missing("DSPX_VLLM_MODEL", vllm.get("model"))
    _set_if_missing("DSPX_VLLM_API_KEY", vllm.get("api_key"))
    _set_if_missing(
        "DSPX_VLLM_TIMEOUT",
        str(vllm.get("timeout_s")) if vllm.get("timeout_s") is not None else None,
    )
    if "json_mode" in vllm:
        _set_if_missing("DSPX_VLLM_JSON_MODE", _coerce_bool(vllm.get("json_mode")))

    # Optimization provider defaults
    _set_if_missing("DSPX_OPTIMIZE_STUDENT_PROVIDER", optimize.get("student_provider"))
    _set_if_missing(
        "DSPX_OPTIMIZE_REFLECTION_PROVIDER", optimize.get("reflection_provider")
    )

    # Provider selection env
    _set_if_missing("DSPX_PROVIDER", provider.get("name"))

    return data
    # moved to src/
