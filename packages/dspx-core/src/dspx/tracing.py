"""
MLflow tracing helper for DSPx + DSPy.

Environment knobs:
- MLFLOW_ENABLE=1 (default: enabled)
- MLFLOW_TRACKING_URI=<uri> (optional; when unset DSPx forces local sqlite)
- MLFLOW_EXPERIMENT=DSPy

DSPy autologging knobs (MLflow 3.x):
- DSPX_MLFLOW_DSPY_AUTOLOG=1 (default)
- DSPX_MLFLOW_DSPY_LOG_TRACES=0 (default; avoids noisy span warnings in GEPA)
- DSPX_MLFLOW_DSPY_SILENT=1 (default)
"""

from __future__ import annotations

from contextlib import contextmanager
import inspect
import os

__all__ = [
    "enable_mlflow_from_env",
    "ensure_run_from_env",
    "mlflow_enabled",
    "get_mlflow",
    "default_tracking_uri_from_env",
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
    """Return mlflow module if enabled+importable; otherwise None.

    Centralizes the "MLFLOW_ENABLE=0 means no MLflow side effects" rule.
    """
    if not mlflow_enabled():
        return None
    try:
        import mlflow

        return mlflow
    except Exception:
        return None


def default_tracking_uri_from_env() -> str:
    """Resolve tracking URI with DSPx local-default policy.

    Policy:
    - explicit MLFLOW_TRACKING_URI wins
    - otherwise use local sqlite backend (deterministic across MLflow versions)
    """
    uri = os.getenv("MLFLOW_TRACKING_URI")
    if uri and uri.strip():
        return uri.strip()
    return "sqlite:///mlflow.db"


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

    mlflow = get_mlflow()
    if mlflow is None:
        return False

    uri = default_tracking_uri_from_env()
    exp = os.getenv("MLFLOW_EXPERIMENT", "DSPy")

    try:
        # Stabilize local default backend across MLflow versions.
        if not os.getenv("MLFLOW_TRACKING_URI"):
            os.environ["MLFLOW_TRACKING_URI"] = uri
        mlflow.set_tracking_uri(uri)
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


def standard_tags(
    service: str,
    *,
    template_version: str | None = None,
    extra: dict[str, str] | None = None,
    group: str | None = None,
) -> dict[str, str]:
    """Build a standard tag set for MLflow runs.

    Includes:
    - service: one of signature/module/codegen/mermaid/tools/openapi
    - template_version: when provided
    - provider: from $DSPX_PROVIDER when present
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
    if extra:
        tags.update({k: v for k, v in extra.items() if v is not None})
    return tags


def ensure_run_with_standard_tags(
    service: str,
    *,
    template_version: str | None = None,
    extra: dict[str, str] | None = None,
    run_name: str | None = None,
    group: str | None = None,
) -> bool:
    """Ensure a run is active and set standard tags for consistency.

    If no run is active and MLflow is enabled, starts a run only when
    `run_name` (or `$MLFLOW_RUN_NAME`) is provided.
    """
    return ensure_run_from_env(
        run_name=run_name,
        tags=standard_tags(
            service, template_version=template_version, extra=extra, group=group
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
