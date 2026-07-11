# summary: "Configures opt-in MLflow tracing, normalized tags, and explicit run lifecycles."
# read_when:
#   - "Changing MLflow enablement, tracking backend policy, tags, or nested runs."

"""
MLflow tracing helper for DSPx + DSPy.

Environment knobs:
- MLFLOW_ENABLE=1 (default: enabled)
- MLFLOW_TRACKING_URI=<uri> (required for MLflow side effects; no local fallback)
- MLFLOW_EXPERIMENT=DSPy
- MLFLOW_ARTIFACT_ROOT=<file URI or path> (optional; used when creating a new experiment)

DSPy autologging knobs (MLflow 3.x):
- DSPX_MLFLOW_DSPY_AUTOLOG=1 (default)
- DSPX_MLFLOW_DSPY_LOG_TRACES=0 (default; avoids noisy span warnings in GEPA)
- DSPX_MLFLOW_DSPY_SILENT=1 (default)
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import inspect
import os
from urllib.parse import urlparse

__all__ = [
    "enable_mlflow_from_env",
    "ensure_run_from_env",
    "mlflow_enabled",
    "get_mlflow",
    "default_tracking_uri_from_env",
    "filesystem_tracking_uri_unsupported",
    "standard_tags",
    "ensure_run_with_standard_tags",
    "nested_run_with_tags",
]


def _truthy(val: str | None) -> bool:
    """Return True if the given string-like value is truthy.

    Treat None as True (default-enabled behavior). Handles common falsy
    variants like 0, false, no (case-insensitive, with surrounding whitespace
    ignored).
    """
    if val is None:
        return True  # default enabled
    s = val.strip().lower()
    return s not in {"", "0", "false", "no"}


def mlflow_enabled() -> bool:
    """Return True if MLflow is enabled by env."""
    return _truthy(os.getenv("MLFLOW_ENABLE", "1"))


def get_mlflow():
    """Return mlflow module if enabled+explicitly configured; otherwise None.

    Centralizes the "MLFLOW_ENABLE=0 means no MLflow side effects" rule and
    the alpha policy that DSPx does not invent a local MLflow backend when
    `MLFLOW_TRACKING_URI` is unset.
    """
    if not mlflow_enabled():
        return None
    if tracking_uri_missing() or filesystem_tracking_uri_unsupported():
        return None
    try:
        import mlflow

        return mlflow
    except Exception:
        return None


def default_tracking_uri_from_env() -> str:
    """Return the explicitly configured tracking URI, or an empty string.

    DSPx alpha policy does not keep a local sqlite fallback. Callers that want
    MLflow side effects must set `MLFLOW_TRACKING_URI` explicitly, normally to
    the shared DS1621 server (`http://ds1621:50000`).
    """
    uri = os.getenv("MLFLOW_TRACKING_URI")
    if uri and uri.strip():
        return uri.strip()
    return ""


def tracking_uri_missing() -> bool:
    """Return True when MLflow is enabled but no tracking URI is configured."""

    return not default_tracking_uri_from_env()


def filesystem_tracking_uri_unsupported(uri: str | None = None) -> bool:
    """Return True when a URI selects MLflow's deprecated filesystem backend."""

    value = os.getenv("MLFLOW_TRACKING_URI") if uri is None else uri
    raw = str(value or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    if parsed.scheme in {"", "file"}:
        return True
    return False


def _autolog_enabled() -> bool:
    return _truthy(os.getenv("DSPX_MLFLOW_DSPY_AUTOLOG", "1"))


def _bool_env(name: str, default: str) -> bool:
    return _truthy(os.getenv(name, default))


def _enable_dspy_autolog(mlflow) -> None:
    """Enable DSPy autolog with MLflow-version-aware arguments.

    MLflow 3.x removed `create_run` and added trace/eval/compile flags.
    We default to trace-disabled mode to avoid noisy GEPA span warnings.
    """
    if not _autolog_enabled():
        return
    try:
        dspy_mod = getattr(mlflow, "dspy", None)
        autolog_fn = getattr(dspy_mod, "autolog", None)
        if autolog_fn is None:
            # Fallback for very old integrations.
            if hasattr(mlflow, "autolog"):
                try:
                    mlflow.autolog(disable=False)
                except Exception:
                    pass
            return

        try:
            params = inspect.signature(autolog_fn).parameters
        except Exception:
            params = {}

        # Older API (MLflow <=2.x style)
        if "create_run" in params:
            autolog_fn(create_run=False)
            return

        # MLflow 3.x API.
        kwargs = {}
        if "log_traces" in params:
            kwargs["log_traces"] = _bool_env("DSPX_MLFLOW_DSPY_LOG_TRACES", "0")
        if "log_traces_from_compile" in params:
            kwargs["log_traces_from_compile"] = _bool_env(
                "DSPX_MLFLOW_DSPY_LOG_TRACES_FROM_COMPILE", "0"
            )
        if "log_traces_from_eval" in params:
            kwargs["log_traces_from_eval"] = _bool_env(
                "DSPX_MLFLOW_DSPY_LOG_TRACES_FROM_EVAL", "0"
            )
        if "log_compiles" in params:
            kwargs["log_compiles"] = _bool_env("DSPX_MLFLOW_DSPY_LOG_COMPILES", "0")
        if "log_evals" in params:
            kwargs["log_evals"] = _bool_env("DSPX_MLFLOW_DSPY_LOG_EVALS", "0")
        if "silent" in params:
            kwargs["silent"] = _bool_env("DSPX_MLFLOW_DSPY_SILENT", "1")
        if "disable" in params:
            kwargs["disable"] = False

        autolog_fn(**kwargs)
    except Exception:
        # Never fail core DSPx flow on autolog setup.
        pass


def enable_mlflow_from_env() -> bool:
    """Enable MLflow using environment variables.

    Returns True if setup succeeded, False otherwise.
    """
    if not mlflow_enabled():
        return False
    if tracking_uri_missing() or filesystem_tracking_uri_unsupported():
        return False

    mlflow = get_mlflow()
    if mlflow is None:
        return False

    uri = default_tracking_uri_from_env()
    exp = os.getenv("MLFLOW_EXPERIMENT", "DSPy")

    artifact_root = os.getenv("MLFLOW_ARTIFACT_ROOT") or None

    try:
        mlflow.set_tracking_uri(uri)
        if artifact_root:
            try:
                mlflow.create_experiment(exp, artifact_location=artifact_root)
            except Exception:
                # Experiment may already exist or the backend may not support explicit
                # artifact roots. Continue with set_experiment so MLflow availability
                # is not lost solely because the creation race failed.
                pass
        mlflow.set_experiment(exp)
        _enable_dspy_autolog(mlflow)
        # No implicit run creation here. Runs are started explicitly via ensure_run_*.
        return True
    except Exception:
        # Fallback to no-op if backend is unreachable or integration unavailable.
        return False


def ensure_run_from_env(
    run_name: str | None = None, tags: dict[str, str] | None = None
) -> bool:
    """Ensure an MLflow run is active using explicit run-start semantics.

    - If a run is already active, set provided tags (if any) and return False.
    - If no run is active, start one only when a run name is explicitly provided
      (`run_name` or `$MLFLOW_RUN_NAME`) and return True.
    - Honors `MLFLOW_ENABLE` toggle; returns False if disabled or mlflow missing.
    """
    if not mlflow_enabled():
        return False
    if tracking_uri_missing() or filesystem_tracking_uri_unsupported():
        return False
    mlflow = get_mlflow()
    if mlflow is None:
        return False
    try:
        if mlflow.active_run() is not None:
            if tags:
                for k, v in tags.items():
                    try:
                        mlflow.set_tag(k, v)
                    except Exception:
                        pass
            return False

        rn = run_name or os.getenv("MLFLOW_RUN_NAME")
        if not rn:
            return False

        mlflow.start_run(run_name=rn)
        if tags:
            for k, v in tags.items():
                try:
                    mlflow.set_tag(k, v)
                except Exception:
                    pass
        return True
    except Exception:
        return False


def _normalize_slug(
    value: str | None,
    *,
    default: str = "unknown",
    max_len: int = 32,
) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return default

    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
    cleaned = "".join(ch if ch in allowed else "-" for ch in raw)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-._")
    if not cleaned:
        return default
    if len(cleaned) <= max_len:
        return cleaned

    digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:8]
    keep = max(1, max_len - 9)
    return f"{cleaned[:keep]}-{digest}"


def _normalize_run_kind(value: str | None) -> str:
    allowed = {
        "signature-gen",
        "signature-refine",
        "module-gen",
        "program-gen",
        "program-runtime",
        "program-eval",
        "codegen",
        "other",
    }
    v = (value or "").strip().lower()
    return v if v in allowed else "other"


def _run_kind_from_service(service: str) -> str:
    mapped = {
        "signature": "signature-gen",
        "module": "module-gen",
        "program": "program-gen",
        "codegen": "codegen",
    }.get((service or "").strip().lower(), "other")
    return _normalize_run_kind(mapped)


def _normalize_output_basename(value: str | None) -> str:
    base = os.path.basename((value or "").strip())
    if not base:
        return "unknown"
    return _normalize_slug(base, default="unknown", max_len=64)


def _normalize_cache_key(value: str | None) -> str | None:
    raw = (value or "").strip().lower()
    if not raw:
        return None
    if all(ch in "0123456789abcdef" for ch in raw) and len(raw) >= 12:
        return raw
    return None


def _normalize_hash_prefix(value: str | None, *, width: int = 12) -> str | None:
    raw = (value or "").strip().lower()
    if not raw:
        return None
    filtered = "".join(ch for ch in raw if ch in "0123456789abcdef")
    if len(filtered) < width:
        return None
    return filtered[:width]


def standard_tags(
    service: str,
    *,
    template_version: str | None = None,
    extra: dict[str, str] | None = None,
    group: str | None = None,
    run_kind: str | None = None,
    output_basename: str | None = None,
    cache_key: str | None = None,
    output_hash: str | None = None,
) -> dict[str, str]:
    """Build a standard tag set for MLflow runs.

    Includes:
    - legacy tags (`service`, `template_version`, `provider`, `run_group`)
    - DSPx correlation tags (`dspx.*`) for explain/linkage hardening
    """
    tags: dict[str, str] = {"service": service}
    if template_version:
        tags["template_version"] = template_version

    prov = os.getenv("DSPX_PROVIDER")
    if prov:
        tags["provider"] = prov

    grp = group or os.getenv("DSPX_RUN_GROUP")
    if grp:
        tags["run_group"] = grp

    tags["dspx.run_kind"] = _normalize_run_kind(
        run_kind or _run_kind_from_service(service)
    )
    if template_version:
        tags["dspx.template_version"] = _normalize_slug(
            template_version,
            default="unknown",
            max_len=32,
        )

    if output_basename:
        tags["dspx.output_basename"] = _normalize_output_basename(output_basename)

    normalized_cache_key = _normalize_cache_key(cache_key)
    if normalized_cache_key:
        tags["dspx.cache_key"] = normalized_cache_key

    output_hash_prefix = _normalize_hash_prefix(output_hash, width=12)
    if output_hash_prefix:
        tags["dspx.output_hash_prefix"] = output_hash_prefix

    if extra:
        tags.update({k: v for k, v in extra.items() if v is not None})

    if "dspx.run_kind" in tags:
        tags["dspx.run_kind"] = _normalize_run_kind(str(tags["dspx.run_kind"]))
    if "dspx.template_version" in tags:
        tags["dspx.template_version"] = _normalize_slug(
            str(tags["dspx.template_version"]),
            default="unknown",
            max_len=32,
        )
    if "dspx.output_basename" in tags:
        tags["dspx.output_basename"] = _normalize_output_basename(
            str(tags["dspx.output_basename"])
        )
    if "dspx.cache_key" in tags:
        ck = _normalize_cache_key(str(tags["dspx.cache_key"]))
        if ck is None:
            tags.pop("dspx.cache_key", None)
        else:
            tags["dspx.cache_key"] = ck
    if "dspx.output_hash_prefix" in tags:
        hp = _normalize_hash_prefix(str(tags["dspx.output_hash_prefix"]), width=12)
        if hp is None:
            tags.pop("dspx.output_hash_prefix", None)
        else:
            tags["dspx.output_hash_prefix"] = hp

    return tags


def ensure_run_with_standard_tags(
    service: str,
    *,
    template_version: str | None = None,
    extra: dict[str, str] | None = None,
    run_name: str | None = None,
    group: str | None = None,
    run_kind: str | None = None,
    output_basename: str | None = None,
    cache_key: str | None = None,
    output_hash: str | None = None,
) -> bool:
    """Ensure a run is active and set standard tags for consistency.

    If no run is active and MLflow is enabled, starts a run only when
    `run_name` (or `$MLFLOW_RUN_NAME`) is provided.
    """
    return ensure_run_from_env(
        run_name=run_name,
        tags=standard_tags(
            service,
            template_version=template_version,
            extra=extra,
            group=group,
            run_kind=run_kind,
            output_basename=output_basename,
            cache_key=cache_key,
            output_hash=output_hash,
        ),
    )


@contextmanager
def nested_run_with_tags(
    *,
    run_name: str,
    tags: dict[str, str] | None = None,
    enabled_env: str = "DSPX_MLFLOW_NESTED_RUNS",
):
    """Best-effort nested MLflow run.

    Behavior:
    - If MLflow is disabled/unavailable, yields False.
    - If no active parent run exists, yields False (no implicit run creation).
    - If nested runs are not enabled via env, yields False.
    - Otherwise starts a nested run and yields True, ending it on exit.
    """
    if filesystem_tracking_uri_unsupported():
        yield False
        return
    mlflow = get_mlflow()
    if mlflow is None:
        yield False
        return
    try:
        parent = mlflow.active_run()
    except Exception:
        parent = None
    if parent is None:
        yield False
        return
    if not _truthy(os.getenv(enabled_env, "0")):
        yield False
        return
    started = False
    try:
        mlflow.start_run(run_name=run_name, nested=True)
        started = True
        if tags:
            for k, v in tags.items():
                try:
                    mlflow.set_tag(k, v)
                except Exception:
                    pass
        yield True
    except Exception:
        yield False
    finally:
        try:
            if started:
                mlflow.end_run()
        except Exception:
            pass
