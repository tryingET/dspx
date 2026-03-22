"""Signature generation and refinement commands.

Commands for generating, refining, and analyzing DSPy signatures.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import typer

from dspx.cli.utils import (
    check_template_adapter_available,
    ensure_env,
    require_template_adapter,
)

app = typer.Typer(no_args_is_help=True)


def _preview_template_messages(
    prompt: str,
    template_config: Path,
    provider: Optional[str],
) -> None:
    """Preview rendered template messages without calling LM.

    Validates the template config and renders messages with sample inputs
    to show what would be sent to the LM.
    """
    from dspx.schema_validation import (
        validate_template_adapter_config,
        SchemaValidationError,
    )

    # Validate the config against schema
    try:
        config = validate_template_adapter_config(template_config)
        typer.echo(f"✓ Config validation passed: {template_config}", err=True)
    except SchemaValidationError as e:
        typer.echo("✗ Config validation failed:", err=True)
        typer.echo(str(e), err=True)
        raise typer.Exit(code=2)

    # Get provider capabilities if available
    caps_dict = None
    if provider:
        ensure_env(provider, tracing=False)
        from dspx.provider_registry import capabilities as _caps

        caps = _caps(provider)
        caps_dict = {
            "json_mode": getattr(caps, "json_mode", False),
            "structured_output_format": getattr(
                caps, "structured_output_format", "none"
            ),
            "provider_type": provider.split("-")[0] if "-" in provider else provider,
        }

    # Try to render with dspy-template-adapter if available
    if check_template_adapter_available():
        try:
            from dspy_template_adapter import TemplateAdapter  # type: ignore[import-untyped]

            # Build a mock signature for preview
            import dspy

            class PreviewSignature(dspy.Signature):
                """Generate a DSPy signature from task description."""

                task: str = dspy.InputField()
                spec_json: str = dspy.OutputField()

            # Prepare messages
            messages = config.get("messages", [])
            adapter_messages = []
            for msg in messages:
                adapter_messages.append(
                    {
                        "role": msg.get("role"),
                        "content": msg.get("content", ""),
                    }
                )

            # Resolve parse_mode
            parse_mode = config.get("parse_mode", "auto")
            if parse_mode == "auto":
                if caps_dict and caps_dict.get("json_mode"):
                    parse_mode = "json"
                elif caps_dict and caps_dict.get("provider_type") == "claude":
                    parse_mode = "xml"
                else:
                    parse_mode = "json"

            # Create adapter and preview
            adapter = TemplateAdapter(messages=adapter_messages, parse_mode=parse_mode)

            # Preview with sample inputs
            sample_inputs = {"task": prompt}

            typer.echo("\n--- Rendered Messages Preview ---", err=True)
            rendered = adapter.format(PreviewSignature, [], **sample_inputs)
            for i, msg in enumerate(rendered):
                typer.echo(
                    f"\n[Message {i + 1}] role={msg.get('role', 'unknown')}", err=True
                )
                typer.echo("-" * 40, err=True)
                content = msg.get("content", "")
                # Truncate long content for display
                if len(content) > 500:
                    content = content[:500] + "\n... (truncated)"
                typer.echo(content, err=True)

            typer.echo("\n--- Adapter Configuration ---", err=True)
            typer.echo(f"parse_mode: {parse_mode}", err=True)
            typer.echo(f"provider: {provider or 'default'}", err=True)
            if caps_dict:
                typer.echo(f"capabilities: {json.dumps(caps_dict)}", err=True)

            typer.echo("\n✓ Dry-run complete. No LM call was made.", err=True)

        except Exception as e:
            typer.echo(f"Error rendering template: {e}", err=True)
            raise typer.Exit(code=1)
    else:
        # Adapter not available - show config summary only
        typer.echo("\n--- Template Config Summary ---", err=True)
        typer.echo(f"parse_mode: {config.get('parse_mode', 'auto')}", err=True)
        typer.echo(f"messages: {len(config.get('messages', []))} message(s)", err=True)
        for i, msg in enumerate(config.get("messages", [])):
            typer.echo(f"  [{i + 1}] role={msg.get('role')}", err=True)
            content = msg.get("content", "")
            if content and len(content) > 60:
                content = content[:60] + "..."
            typer.echo(f"      content: {content}", err=True)

        typer.echo(
            "\n⚠ dspy-template-adapter not installed. Cannot render full preview.",
            err=True,
        )
        typer.echo("  Install with: pip install dspx-core[templates]", err=True)


@app.command("gen")
def signature_gen(
    prompt: str = typer.Argument(..., help="Natural language description"),
    template_version: str = typer.Option(
        "simple-v1", help="Template version (use 'simple-*' for deterministic output)"
    ),
    class_name: Optional[str] = typer.Option(None, help="Optional class name override"),
    provider: Optional[str] = typer.Option(None, help="Provider (registry name)"),
    outfile: Optional[Path] = typer.Option(None, help="Write code to file"),
    no_cache: bool = typer.Option(False, help="Bypass on-disk cache for this run"),
    cache_info: bool = typer.Option(False, help="Print cache key and path info"),
    budget_ms: Optional[int] = typer.Option(
        None, help="Time budget in ms (logs to MLflow; may clamp provider timeout)"
    ),
    summary: bool = typer.Option(False, help="Print run summary to stderr"),
    summary_json_out: Optional[Path] = typer.Option(
        None, help="Write machine-readable run summary JSON"
    ),
    template_config: Optional[Path] = typer.Option(
        None,
        "--template-config",
        help="YAML config file for TemplateAdapter (requires dspy-template-adapter)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview rendered template messages without calling LM (requires --template-config)",
    ),
) -> None:
    """Generate a DSPy signature from a natural language description."""
    from dspx.dtos import SignatureGenRequest
    from dspx.services.signatures_service import run_generate_dto

    # Fast-fail if template-config requested but file doesn't exist
    if template_config is not None:
        if not template_config.exists():
            typer.echo(
                f"Error: Template config file not found: {template_config}",
                err=True,
            )
            raise typer.Exit(code=2)

    # dry-run requires template-config
    if dry_run and template_config is None:
        typer.echo(
            "Error: --dry-run requires --template-config",
            err=True,
        )
        raise typer.Exit(code=2)

    # Handle dry-run: preview rendered messages without calling LM
    if dry_run and template_config is not None:
        _preview_template_messages(prompt, template_config, provider)
        return

    # For non-dry-run with template-config, require the adapter
    if template_config is not None:
        require_template_adapter("template-config")

    ensure_env(provider)
    if no_cache:
        os.environ["DSPX_CACHE_ENABLE"] = "0"
    if budget_ms is not None:
        os.environ["DSPX_BUDGET_SIGNATURE_MS"] = str(int(budget_ms))

    req = SignatureGenRequest(
        prompt=prompt,
        template_version=template_version,
        options={"class_name": class_name} if class_name else {},
    )
    res = run_generate_dto(req)
    summary_payload = dict(res.metadata or {})

    if summary_json_out is not None:
        summary_json_out.parent.mkdir(parents=True, exist_ok=True)
        summary_json_out.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if summary and summary_payload:
        typer.echo(
            "signature summary "
            f"provider={summary_payload.get('provider', '-')} "
            f"attempts={summary_payload.get('attempts_used', 0)}/{summary_payload.get('max_attempts', 0)} "
            f"fallback={summary_payload.get('fallback_used', False)} "
            f"validation={float(summary_payload.get('validation_pass_rate') or 0.0):.2f} "
            f"smoke={float(summary_payload.get('smoke_pass_rate') or 0.0):.2f}",
            err=True,
        )

    if outfile:
        _write_signature_output(
            outfile=outfile,
            code=res.code,
            prompt=prompt,
            template_version=template_version,
            class_name=class_name,
            signature_name=res.signature_name,
            summary_payload=summary_payload,
        )
        typer.echo(str(outfile))
    else:
        sys.stdout.write(res.code)
        if cache_info:
            _print_cache_info(prompt, template_version, class_name)


def _write_signature_output(
    outfile: Path,
    code: str,
    prompt: str,
    template_version: str,
    class_name: Optional[str],
    signature_name: Optional[str],
    summary_payload: dict[str, Any],
) -> None:
    """Write signature output with receipt and MLflow logging."""
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

        cls = str(class_name or "GeneratedSignature")
        cache_key = make_key(
            {
                "kind": "signature",
                "prompt": prompt,
                "template_version": template_version,
                "class_name": cls,
                "options": {"class_name": class_name} if class_name else {},
            }
        )
        cfile = cache_dir() / "signature" / f"{cache_key}.json"
        cache_enabled = os.getenv("DSPX_CACHE_ENABLE", "1") not in {
            "0",
            "false",
            "False",
            "",
        }
        output_hash = sha256_text(code)
        meta = build_run_receipt(
            run_kind="signature-gen",
            output_path=outfile,
            output_hash=output_hash,
            template_version=template_version,
            cache_key=cache_key,
            cache_file=str(cfile),
            cache_enabled=cache_enabled,
            replay_inputs={
                "prompt": prompt,
                "template_version": template_version,
                "class_name": class_name,
                "options": {"class_name": class_name} if class_name else {},
            },
            run_summary=summary_payload,
            extra={
                "class_name": class_name or signature_name or "",
                "mlflow_hints": build_mlflow_hints(
                    run_kind="signature-gen",
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

    # Log artifacts to MLflow when enabled
    try:
        from dspx.cache import make_key, sha256_text
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        cls = str(class_name or "GeneratedSignature")
        cache_key_for_tags = make_key(
            {
                "kind": "signature",
                "prompt": prompt,
                "template_version": template_version,
                "class_name": cls,
                "options": {"class_name": class_name} if class_name else {},
            }
        )
        output_hash_for_tags = sha256_text(code)

        mlflow = get_mlflow()
        if mlflow is not None:
            ensure_run_with_standard_tags(
                "signature",
                template_version=template_version,
                run_name=f"signature-{class_name or signature_name or ''}",
                run_kind="signature-gen",
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


def _print_cache_info(
    prompt: str, template_version: str, class_name: Optional[str]
) -> None:
    """Print cache key and file info for signature."""
    try:
        from dspx.cache import make_key, cache_dir

        cls = str(class_name or "GeneratedSignature")
        cache_key = make_key(
            {
                "kind": "signature",
                "prompt": prompt,
                "template_version": template_version,
                "class_name": cls,
                "options": {"class_name": class_name} if class_name else {},
            }
        )
        cfile = cache_dir() / "signature" / f"{cache_key}.json"
        typer.echo(
            f"cache_key={cache_key} cache_file={cfile} exists={cfile.exists()}",
            err=True,
        )
    except Exception:
        pass


@app.command("refine")
def signature_refine(
    prompt: str = typer.Argument(..., help="Signature prompt to refine"),
    attempts: int = typer.Option(3, help="Number of attempts"),
    non_interactive: bool = typer.Option(True, help="Run without interactive reward"),
    wrap_script: bool = typer.Option(False, help="Wrap output as runnable DSPy script"),
    provider: Optional[str] = typer.Option(None, help="Provider (registry name)"),
    outfile: Optional[Path] = typer.Option(None, help="Write code to file"),
    budget_ms: Optional[int] = typer.Option(
        None, help="Time budget in ms (logs to MLflow)"
    ),
    summary: bool = typer.Option(False, help="Print run summary to stderr"),
    summary_json_out: Optional[Path] = typer.Option(
        None, help="Write machine-readable run summary JSON"
    ),
    template_config: Optional[Path] = typer.Option(
        None,
        "--template-config",
        help="YAML config file for TemplateAdapter (requires dspy-template-adapter)",
    ),
) -> None:
    """Refine a DSPy signature through iterative improvement."""
    from dspx.services.refine_service import run_refine as _run_refine

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
    if budget_ms is not None:
        os.environ["DSPX_BUDGET_SIGNATURE_MS"] = str(int(budget_ms))

    code = _run_refine(
        prompt,
        attempts=attempts,
        non_interactive=non_interactive,
        wrap_script=wrap_script,
        outfile=str(outfile) if outfile else None,
    )

    summary_payload: dict[str, Any] = {
        "run_kind": "signature-refine",
        "provider": provider or os.getenv("DSPX_PROVIDER") or "pi-rpc",
        "attempts_requested": int(attempts),
        "non_interactive": bool(non_interactive),
        "wrap_script": bool(wrap_script),
        "prompt_len": len(prompt or ""),
    }

    if outfile:
        meta_path = outfile.parent / (outfile.name + ".meta.json")
        try:
            from dspx.run_receipts import load_run_receipt

            loaded = load_run_receipt(meta_path)
            if isinstance(loaded, dict):
                summary_payload.update(loaded)
        except Exception:
            pass

    if summary_json_out is not None:
        summary_json_out.parent.mkdir(parents=True, exist_ok=True)
        summary_json_out.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if summary:
        typer.echo(
            "refine summary "
            f"provider={summary_payload.get('provider', '-')} "
            f"attempts={summary_payload.get('attempts', summary_payload.get('attempts_requested', 0))} "
            f"rounds={summary_payload.get('rounds', 0)} "
            f"feedback={summary_payload.get('feedback_count', 0)}",
            err=True,
        )

    if outfile:
        typer.echo(str(outfile))
    else:
        sys.stdout.write(code)


@app.command("quality-summary")
def signature_quality_summary(
    log_path: Optional[Path] = typer.Option(
        None,
        help="Path to signature quality JSONL (default: generated/cache/signature/quality_runs.jsonl)",
    ),
    provider: Optional[str] = typer.Option(None, help="Filter by provider"),
    run_kind: Optional[str] = typer.Option(
        None, help="Filter by run kind (signature-gen/signature-refine)"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON summary"),
    fail_on_gate: bool = typer.Option(
        False, "--fail-on-gate", help="Exit with code 2 when any gate fails"
    ),
    max_fallback_rate: float = typer.Option(0.25, help="Gate: maximum fallback rate"),
    max_attempts_p95: float = typer.Option(3.0, help="Gate: maximum attempts-used p95"),
    min_validation_pass_rate: float = typer.Option(
        0.90, help="Gate: minimum validation pass rate"
    ),
    min_smoke_pass_rate: float = typer.Option(
        0.90, help="Gate: minimum smoke pass rate"
    ),
) -> None:
    """Summarize signature generation quality metrics."""
    from dspx.services.signature_quality import (
        SignatureQualityGate,
        evaluate_quality_gates,
        format_quality_summary,
        read_quality_events,
        summarize_quality_events,
    )

    events = read_quality_events(log_path)
    summary = summarize_quality_events(events, provider=provider, run_kind=run_kind)
    gate_eval = evaluate_quality_gates(
        summary,
        gate=SignatureQualityGate(
            max_fallback_rate=float(max_fallback_rate),
            max_attempts_p95=float(max_attempts_p95),
            min_validation_pass_rate=float(min_validation_pass_rate),
            min_smoke_pass_rate=float(min_smoke_pass_rate),
        ),
    )

    payload = {"summary": summary, "gates": gate_eval}
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(format_quality_summary(summary, gate_eval))

    if fail_on_gate and not bool(gate_eval.get("overall_pass")):
        raise typer.Exit(code=2)
