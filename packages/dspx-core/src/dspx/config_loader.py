# summary: "Loads secret-free DSPx TOML configuration into managed environment variables."
# read_when:
#   - "Changing config discovery, TOML sections, secret rejection, or environment precedence."

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from dspx.security import reject_url_userinfo

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
_CONFIG_ENV_KEYS = (
    "MLFLOW_ENABLE",
    "MLFLOW_TRACKING_URI",
    "MLFLOW_EXPERIMENT",
    "MLFLOW_ARTIFACT_ROOT",
    "DSPX_QUALITY_CRITERIA_MODEL",
    "DSPX_QUALITY_CRITERIA_REASONING_EFFORT",
    "DSPX_ORACLE_SEMANTIC_MODEL",
    "DSPX_ORACLE_SEMANTIC_REASONING_EFFORT",
    "DSPX_ORACLE_SEMANTIC_BACKEND",
    "DSPX_ORACLE_SEMANTIC_PROVIDER",
    "DSPX_ORACLE_SEMANTIC_FIXTURE_PATH",
    "DSPX_OPTIMIZE_STUDENT_PROVIDER",
    "DSPX_OPTIMIZE_REFLECTION_PROVIDER",
    "DSPX_PROVIDER",
    "DSPX_OPENAI_COMPAT_MODEL",
    "DSPX_OPENAI_COMPAT_API_BASE",
    "DSPX_OPENAI_COMPAT_TIMEOUT",
)
_RETIRED_PROVIDER_SECTIONS = frozenset(
    {"codex", "openrouter", "pi", "lm_auth", "openai_compatible", "vllm"}
)


def _coerce_bool(val: Any, *, label: str = "boolean config value") -> str:
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, int) and val in {0, 1}:
        return "1" if val else "0"
    if isinstance(val, str):
        s = val.strip().lower()
        if s in {"1", "true", "yes", "on"}:
            return "1"
        if s in {"0", "false", "no", "off", ""}:
            return "0"
    raise ValueError(
        f"{label} must be a boolean or one of true/false, yes/no, on/off, 1/0"
    )


def _config_url(value: Any, *, label: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string URL/path value")
    reject_url_userinfo(value, label=label)
    return value


def _provider_name(value: Any, *, label: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a supported provider name")
    normalized = value.strip().lower()
    if normalized not in {"stub", "openai-compatible"}:
        raise ValueError(
            f"{label} selects unsupported provider {normalized!r}; "
            "supported=('stub', 'openai-compatible')"
        )
    return normalized


def _stub_provider_name(value: Any, *, label: str) -> Optional[str]:
    normalized = _provider_name(value, label=label)
    if normalized not in {None, "stub"}:
        raise ValueError(f"{label} supports only the stub provider")
    return normalized


def _provider_config_values(
    provider: Any,
) -> tuple[str | None, str | None, str | None, str | None]:
    if not isinstance(provider, dict):
        raise ValueError("provider config must be a TOML table")
    unknown = sorted(set(provider) - {"name", "model", "base_url", "timeout"})
    if unknown:
        raise ValueError(
            "provider config contains unsupported fields: " + ", ".join(unknown)
        )
    name = _provider_name(provider.get("name"), label="provider.name")
    http_fields = {key for key in ("model", "base_url", "timeout") if key in provider}
    if name in {None, "stub"}:
        if http_fields:
            raise ValueError("stub provider does not accept HTTP configuration")
        return name, None, None, None

    from dspx.openai_compatible_provider import (
        _validated_endpoint,
        _validated_model,
        _validated_timeout,
    )

    if "model" not in provider or "base_url" not in provider:
        raise ValueError("openai-compatible provider requires model and base_url")
    model = _validated_model(provider.get("model"))
    base_url, _ = _validated_endpoint(provider.get("base_url"))
    timeout = _validated_timeout(provider.get("timeout", 30.0))
    return name, model, base_url, str(timeout)


def _restore_config_env(
    env_snapshot: dict[str, str | None], managed_snapshot: dict[str, str]
) -> None:
    for key, previous in env_snapshot.items():
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
    _CONFIG_MANAGED_VALUES.clear()
    _CONFIG_MANAGED_VALUES.update(managed_snapshot)


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

    retired_sections = sorted(set(data) & _RETIRED_PROVIDER_SECTIONS)
    if retired_sections:
        raise ValueError(
            "unsupported provider config sections after the typed hard cutover: "
            + ", ".join(retired_sections)
        )

    # Supported sections: [mlflow], [provider], [model_roles], and [optimize].
    mlflow = data.get("mlflow", {}) if isinstance(data, dict) else {}
    provider = data.get("provider", {}) if isinstance(data, dict) else {}
    model_roles = data.get("model_roles", {}) if isinstance(data, dict) else {}
    quality_criteria_role = (
        model_roles.get("quality_criteria", {}) if isinstance(model_roles, dict) else {}
    )
    oracle_semantic_role = (
        model_roles.get("oracle_semantic", {}) if isinstance(model_roles, dict) else {}
    )
    optimize = data.get("optimize", {}) if isinstance(data, dict) else {}
    provider_name, provider_model, provider_base_url, provider_timeout = (
        _provider_config_values(provider)
    )

    seen_keys: set[str] = set()
    env_snapshot = {key: os.environ.get(key) for key in _CONFIG_ENV_KEYS}
    managed_snapshot = dict(_CONFIG_MANAGED_VALUES)
    try:
        # MLflow envs
        _set_config_value(
            "MLFLOW_ENABLE",
            _coerce_bool(mlflow.get("enable", True), label="mlflow.enable"),
            seen_keys=seen_keys,
        )
        _set_config_value(
            "MLFLOW_TRACKING_URI",
            _config_url(mlflow.get("tracking_uri"), label="mlflow.tracking_uri"),
            seen_keys=seen_keys,
        )
        _set_config_value(
            "MLFLOW_EXPERIMENT",
            mlflow.get("experiment", "DSPy"),
            seen_keys=seen_keys,
        )
        _set_config_value(
            "MLFLOW_ARTIFACT_ROOT",
            _config_url(mlflow.get("artifact_root"), label="mlflow.artifact_root"),
            seen_keys=seen_keys,
        )

        # Autonomous-foundry role declarations and Oracle semantic backend.
        # These settings do not imply that a live model call has succeeded.
        _set_config_value(
            "DSPX_QUALITY_CRITERIA_MODEL",
            quality_criteria_role.get("model"),
            seen_keys=seen_keys,
        )
        _set_config_value(
            "DSPX_QUALITY_CRITERIA_REASONING_EFFORT",
            quality_criteria_role.get("reasoning_effort"),
            seen_keys=seen_keys,
        )
        _set_config_value(
            "DSPX_ORACLE_SEMANTIC_MODEL",
            oracle_semantic_role.get("model"),
            seen_keys=seen_keys,
        )
        _set_config_value(
            "DSPX_ORACLE_SEMANTIC_REASONING_EFFORT",
            oracle_semantic_role.get("reasoning_effort"),
            seen_keys=seen_keys,
        )
        _set_config_value(
            "DSPX_ORACLE_SEMANTIC_BACKEND",
            oracle_semantic_role.get("backend"),
            seen_keys=seen_keys,
        )
        _set_config_value(
            "DSPX_ORACLE_SEMANTIC_PROVIDER",
            _stub_provider_name(
                oracle_semantic_role.get("provider"),
                label="model_roles.oracle_semantic.provider",
            ),
            seen_keys=seen_keys,
        )
        _set_config_value(
            "DSPX_ORACLE_SEMANTIC_FIXTURE_PATH",
            oracle_semantic_role.get("fixture_path"),
            seen_keys=seen_keys,
        )

        # Optimization provider defaults
        _set_config_value(
            "DSPX_OPTIMIZE_STUDENT_PROVIDER",
            _provider_name(
                optimize.get("student_provider"), label="optimize.student_provider"
            ),
            seen_keys=seen_keys,
        )
        _set_config_value(
            "DSPX_OPTIMIZE_REFLECTION_PROVIDER",
            _provider_name(
                optimize.get("reflection_provider"),
                label="optimize.reflection_provider",
            ),
            seen_keys=seen_keys,
        )

        # Canonical provider selection and secret-free loopback HTTP settings.
        _set_config_value("DSPX_PROVIDER", provider_name, seen_keys=seen_keys)
        _set_config_value(
            "DSPX_OPENAI_COMPAT_MODEL", provider_model, seen_keys=seen_keys
        )
        _set_config_value(
            "DSPX_OPENAI_COMPAT_API_BASE", provider_base_url, seen_keys=seen_keys
        )
        _set_config_value(
            "DSPX_OPENAI_COMPAT_TIMEOUT", provider_timeout, seen_keys=seen_keys
        )

        _refresh_removed_config_values(seen_keys)
    except Exception:
        _restore_config_env(env_snapshot, managed_snapshot)
        raise
    return data
