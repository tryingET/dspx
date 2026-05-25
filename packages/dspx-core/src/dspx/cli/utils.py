from __future__ import annotations

import json
import os
from functools import wraps
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, ParamSpec, cast

import typer

from dspx.config_loader import load_config_env
from dspx.provider_runtime import _sanitize_text
from dspx.tracing import enable_mlflow_from_env

P = ParamSpec("P")
T = TypeVar("T")

# Template adapter availability check (cached)
_TEMPLATE_ADAPTER_AVAILABLE: bool | None = None


def check_template_adapter_available() -> bool:
    """Check if dspy-template-adapter is installed.

    Cached after first check to avoid repeated import attempts.
    """
    global _TEMPLATE_ADAPTER_AVAILABLE
    if _TEMPLATE_ADAPTER_AVAILABLE is None:
        _TEMPLATE_ADAPTER_AVAILABLE = find_spec("dspy_template_adapter") is not None
    return _TEMPLATE_ADAPTER_AVAILABLE


def require_template_adapter(context: str = "template-config") -> None:
    """Fast-fail if template adapter is not installed.

    Args:
        context: Description of what requires the adapter (for error message)

    Raises:
        typer.Exit: With code 2 and helpful install instructions
    """
    if not check_template_adapter_available():
        typer.echo(
            f"Error: --{context} requires dspy-template-adapter but it is not installed.\n"
            "\n"
            "Install with one of:\n"
            "  pip install dspx-core[templates]\n"
            "  pip install dspy-template-adapter\n",
            err=True,
        )
        raise typer.Exit(code=2)


def ensure_env(provider: Optional[str], *, tracing: bool = True) -> None:
    """Set up environment for a command.

    Sets DSPX_PROVIDER if provider is given, loads config, and optionally
    enables MLflow tracing.
    """
    if provider:
        os.environ["DSPX_PROVIDER"] = provider
    try:
        load_config_env()
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        typer.echo(f"Error: {sanitize_cli_error(exc)}", err=True)
        raise typer.Exit(code=2) from exc
    if tracing:
        enable_mlflow_from_env()


def with_env(tracing: bool = True) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator that ensures environment is set up before command execution.

    Usage:
        @with_env()
        def my_command(provider: Optional[str] = None, ...):

        @with_env(tracing=False)
        def my_readonly_command(provider: Optional[str] = None, ...):
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Extract provider from kwargs if present
            provider = cast(Optional[str], kwargs.get("provider"))
            ensure_env(provider, tracing=tracing)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_template_config(
    template_config: Optional[Path], context: str = "template-config"
) -> Optional[Path]:
    """Validate template config file exists and adapter is available.

    Args:
        template_config: Path to template config file
        context: Context for error messages

    Returns:
        The validated path, or None if no config provided

    Raises:
        typer.Exit: If config doesn't exist or adapter not installed
    """
    if template_config is None:
        return None

    if not template_config.exists():
        typer.echo(
            f"Error: Template config file not found: {template_config}",
            err=True,
        )
        raise typer.Exit(code=2)

    require_template_adapter(context)
    return template_config


def with_template_config(
    context: str = "template-config",
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator that validates template config before command execution.

    The decorated function should have a `template_config: Optional[Path]` parameter.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            template_config = cast(Optional[Path], kwargs.get("template_config"))
            validate_template_config(template_config, context)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def sanitize_cli_error(value: object) -> str:
    """Return a concise CLI-safe diagnostic with secrets redacted."""

    return _sanitize_text(str(value))


def output_json(data: Any, json_out: bool, default_text: Optional[str] = None) -> None:
    """Output data as JSON or text.

    Args:
        data: Data to output
        json_out: If True, output as JSON; otherwise output as text
        default_text: Text to output if json_out is False (uses str(data) if None)
    """
    if json_out:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
    elif default_text is not None:
        typer.echo(default_text)
    else:
        typer.echo(str(data))


def write_summary_json(
    summary_json_out: Optional[Path], payload: dict[str, Any]
) -> None:
    """Write a summary JSON file if path is provided."""
    if summary_json_out is not None:
        summary_json_out.parent.mkdir(parents=True, exist_ok=True)
        summary_json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def write_receipt_for_output(
    outfile: Path,
    code: str,
    run_kind: str,
    template_version: str,
    cache_key: str,
    replay_inputs: dict[str, Any],
    extra: Optional[dict[str, Any]] = None,
    class_name: Optional[str] = None,
    run_summary: Optional[dict[str, Any]] = None,
) -> None:
    """Write a run receipt for generated output.

    Args:
        outfile: Output file path
        code: Generated code content
        run_kind: Kind of run (signature-gen, module-gen, codegen)
        template_version: Template version used
        cache_key: Cache key for the run
        replay_inputs: Inputs needed to replay the run
        extra: Additional metadata
        class_name: Optional class name for signatures
    """
    from dspx.cache import cache_dir, sha256_text
    from dspx.run_receipts import (
        build_mlflow_hints,
        build_run_receipt,
        current_receipt_lineage,
        write_run_receipt,
    )

    cfile = cache_dir() / run_kind.split("-")[0] / f"{cache_key}.json"
    cache_enabled = os.getenv("DSPX_CACHE_ENABLE", "1") not in {
        "0",
        "false",
        "False",
        "",
    }
    output_hash = sha256_text(code)

    meta = build_run_receipt(
        run_kind=run_kind,
        output_path=outfile,
        output_hash=output_hash,
        template_version=template_version,
        cache_key=cache_key,
        cache_file=str(cfile),
        cache_enabled=cache_enabled,
        replay_inputs=replay_inputs,
        run_summary=run_summary,
        extra={
            **(extra or {}),
            "class_name": class_name or "",
            "mlflow_hints": build_mlflow_hints(
                run_kind=run_kind,
                template_version=template_version,
                output_path=outfile,
                output_hash=output_hash,
                cache_key=cache_key,
            ),
        },
        **current_receipt_lineage(),
    )
    write_run_receipt(outfile, meta)


def log_artifacts_to_mlflow(
    outfile: Path,
    run_kind: str,
    template_version: str,
    cache_key: str,
    output_hash: str,
    run_name: Optional[str] = None,
) -> None:
    """Log output artifacts to MLflow if enabled.

    Best-effort; silently ignores errors if MLflow is not available.
    """
    from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

    try:
        mlflow = get_mlflow()
        if mlflow is None:
            return

        ensure_run_with_standard_tags(
            run_kind.split("-")[0],
            template_version=template_version,
            run_name=run_name or f"{run_kind}-{outfile.stem}",
            run_kind=run_kind,
            output_basename=outfile.name,
            cache_key=cache_key,
            output_hash=output_hash,
        )

        if mlflow.active_run() is not None:
            try:
                mlflow.log_artifact(str(outfile))
            except Exception:
                pass

            meta_path = outfile.parent / (outfile.name + ".meta.json")
            if meta_path.exists():
                try:
                    mlflow.log_artifact(str(meta_path))
                except Exception:
                    pass
    except Exception:
        pass


def disable_mlflow_temporarily() -> str:
    """Disable MLflow temporarily; returns previous value for restoration."""
    prev = os.getenv("MLFLOW_ENABLE", "")
    os.environ["MLFLOW_ENABLE"] = "0"
    return prev


def restore_mlflow(prev: str) -> None:
    """Restore MLflow enable state."""
    if prev == "":
        os.environ.pop("MLFLOW_ENABLE", None)
    else:
        os.environ["MLFLOW_ENABLE"] = prev


class MLflowDisabled:
    """Context manager to temporarily disable MLflow."""

    def __enter__(self) -> "MLflowDisabled":
        self._prev = disable_mlflow_temporarily()
        return self

    def __exit__(self, *args: Any) -> None:
        restore_mlflow(self._prev)
