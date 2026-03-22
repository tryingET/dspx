"""Code generation command.

Command for generating code from specifications.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer

from dspx.cli.utils import ensure_env, require_template_adapter

app = typer.Typer(no_args_is_help=True)


@app.command("codegen")
def codegen(
    spec: str = typer.Argument(..., help="Codegen task description"),
    language: Optional[str] = typer.Option(
        None, "--language", "-l", help="Target language"
    ),
    template_version: str = typer.Option(
        "simple-v1", help="Template version (use 'simple-*' for deterministic output)"
    ),
    provider: Optional[str] = typer.Option(None, help="Provider (registry name)"),
    outfile: Optional[Path] = typer.Option(None, help="Write code to file"),
    no_cache: bool = typer.Option(False, help="Bypass on-disk cache for this run"),
    cache_info: bool = typer.Option(False, help="Print cache key and path info"),
    budget_ms: Optional[int] = typer.Option(
        None, help="Time budget in ms (logs to MLflow; may clamp provider timeout)"
    ),
    template_config: Optional[Path] = typer.Option(
        None,
        "--template-config",
        help="YAML config file for TemplateAdapter (requires dspy-template-adapter)",
    ),
) -> None:
    """Generate code from a specification."""
    from dspx.dtos import CodegenRequest
    from dspx.services.codegen_service import run_dto as codegen_run_dto

    # Fast-fail if template-config requested but file doesn't exist or adapter not installed
    if template_config is not None:
        if not template_config.exists():
            typer.echo(
                f"Error: Template config file not found: {template_config}",
                err=True,
            )
            raise typer.Exit(code=2)
        require_template_adapter("template-config")

    ensure_env(provider)
    if no_cache:
        os.environ["DSPX_CACHE_ENABLE"] = "0"
    if budget_ms is not None:
        os.environ["DSPX_BUDGET_CODEGEN_MS"] = str(int(budget_ms))

    req = CodegenRequest(
        spec=spec, language=language, template_version=template_version
    )
    res = codegen_run_dto(req)

    if outfile:
        _write_codegen_output(
            outfile=outfile,
            code=res.code,
            spec=spec,
            language=language,
            template_version=template_version,
        )
        typer.echo(str(outfile))
    else:
        sys.stdout.write(res.code)
        if cache_info:
            _print_codegen_cache_info(spec, language, template_version)


def _write_codegen_output(
    outfile: Path,
    code: str,
    spec: str,
    language: Optional[str],
    template_version: str,
) -> None:
    """Write codegen output with receipt and MLflow logging."""
    outfile.parent.mkdir(parents=True, exist_ok=True)
    outfile.write_text(code, encoding="utf-8")

    # Write a versioned run receipt for replay/explain
    try:
        from dspx.cache import cache_dir, make_key, sha256_text
        from dspx.run_receipts import (
            build_mlflow_hints,
            build_run_receipt,
            current_receipt_lineage,
            write_run_receipt,
        )

        cache_key = make_key(
            {
                "kind": "codegen",
                "spec": spec,
                "language": (language or "python"),
                "template_version": template_version,
                "options": {},
            }
        )
        cfile = cache_dir() / "codegen" / f"{cache_key}.json"
        lang = language or "python"
        cache_enabled = os.getenv("DSPX_CACHE_ENABLE", "1") not in {
            "0",
            "false",
            "False",
            "",
        }
        output_hash = sha256_text(code)
        meta = build_run_receipt(
            run_kind="codegen",
            output_path=outfile,
            output_hash=output_hash,
            template_version=template_version,
            cache_key=cache_key,
            cache_file=str(cfile),
            cache_enabled=cache_enabled,
            replay_inputs={
                "spec": spec,
                "language": lang,
                "template_version": template_version,
                "options": {},
            },
            extra={
                "language": lang,
                "spec_len": len(spec),
                "mlflow_hints": build_mlflow_hints(
                    run_kind="codegen",
                    template_version=template_version,
                    output_path=outfile,
                    output_hash=output_hash,
                    cache_key=cache_key,
                ),
            },
            **current_receipt_lineage(),
        )
        write_run_receipt(outfile, meta)
    except Exception:
        pass

    # MLflow logging of artifacts
    try:
        from dspx.cache import make_key, sha256_text
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        cache_key_for_tags = make_key(
            {
                "kind": "codegen",
                "spec": spec,
                "language": (language or "python"),
                "template_version": template_version,
                "options": {},
            }
        )
        output_hash_for_tags = sha256_text(code)

        mlflow = get_mlflow()
        if mlflow is not None:
            ensure_run_with_standard_tags(
                "codegen",
                template_version=template_version,
                run_name=f"codegen-{language or 'python'}",
                run_kind="codegen",
                output_basename=outfile.name,
                cache_key=cache_key_for_tags,
                output_hash=output_hash_for_tags,
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


def _print_codegen_cache_info(
    spec: str, language: Optional[str], template_version: str
) -> None:
    """Print cache key and file info for codegen."""
    try:
        from dspx.cache import make_key, cache_dir

        cache_key = make_key(
            {
                "kind": "codegen",
                "spec": spec,
                "language": (language or "python"),
                "template_version": template_version,
                "options": {},
            }
        )
        cfile = cache_dir() / "codegen" / f"{cache_key}.json"
        typer.echo(
            f"cache_key={cache_key} cache_file={cfile} exists={cfile.exists()}",
            err=True,
        )
    except Exception:
        pass
