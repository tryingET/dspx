"""Provider utilities commands.

Commands for listing, inspecting, testing, and benchmarking providers.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, List, Optional, cast

import typer

from dspx.cli.utils import (
    ensure_env,
    output_json,
    sanitize_cli_error,
    write_summary_json,
)

app = typer.Typer(no_args_is_help=True)


def _describe_provider_or_exit(name: str, *, json_out: bool) -> dict[str, Any]:
    from dspx.provider_runtime import describe_provider

    try:
        return describe_provider(name)
    except Exception as exc:
        error = sanitize_cli_error(exc)
        safe_name = sanitize_cli_error(name)
        if json_out:
            typer.echo(
                json.dumps(
                    {"ok": False, "provider": safe_name, "error": error},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=2) from exc


@app.command("list")
def providers_list(
    json_out: bool = typer.Option(False, "--json", help="Output JSON list"),
) -> None:
    """List all available providers."""
    from dspx.provider_registry import ensure_default_providers, available

    ensure_env(None, tracing=False)
    ensure_default_providers()
    names = sorted(available().keys())

    if json_out:
        typer.echo(json.dumps(names, ensure_ascii=False, indent=2))
    else:
        for n in names:
            typer.echo(n)


@app.command("capabilities")
def providers_capabilities(
    provider: Optional[str] = typer.Option(None, help="Provider (registry name)"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show capabilities for a specific provider."""
    ensure_env(provider, tracing=False)
    name = provider or os.getenv("DSPX_PROVIDER") or "pi-rpc"
    resolved = _describe_provider_or_exit(name, json_out=json_out)
    caps = resolved.get("capabilities") or {}

    payload = {
        "provider": name,
        "supports_tools": bool(caps.get("supports_tools", False)),
        "code_exec": bool(caps.get("code_exec", False)),
        "json_mode": bool(caps.get("json_mode", False)),
        "multi_turn": bool(caps.get("multi_turn", False)),
        "structured_output_format": str(caps.get("structured_output_format", "none")),
        "supports_vision": bool(caps.get("supports_vision", False)),
        "supports_audio": bool(caps.get("supports_audio", False)),
    }

    output_json(payload, json_out)


@app.command("resolve")
def providers_resolve(
    provider: Optional[str] = typer.Option(None, help="Provider (registry name)"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Resolve a provider into its runtime metadata."""
    ensure_env(provider, tracing=False)
    name = provider or os.getenv("DSPX_PROVIDER") or "pi-rpc"
    payload = _describe_provider_or_exit(name, json_out=json_out)
    output_json(payload, json_out)


@app.command("health")
def providers_health(
    provider: Optional[str] = typer.Option(None, help="Provider (registry name)"),
    probe: bool = typer.Option(
        False, "--probe", help="Send a lightweight request after config checks"
    ),
    prompt: str = typer.Option(
        "Reply with the single word: hello",
        help="Probe prompt when --probe is enabled",
    ),
    max_tokens: Optional[int] = typer.Option(
        16, help="Max tokens for probe requests (best effort)"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Validate provider configuration and optionally probe the runtime."""
    from dspx.provider_runtime import check_provider_health

    ensure_env(provider, tracing=False)
    name = provider or os.getenv("DSPX_PROVIDER") or "pi-rpc"
    payload = check_provider_health(
        name,
        probe=probe,
        prompt=prompt,
        max_tokens=max_tokens,
    )
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"provider: {payload.get('provider')}")
        typer.echo(f"ok: {payload.get('ok')}")
        if payload.get("model") is not None:
            typer.echo(f"model: {payload.get('model')}")
        if payload.get("error"):
            typer.echo(f"error: {payload.get('error')}")
        if payload.get("probe"):
            probe_payload = payload.get("probe") or {}
            typer.echo(f"probe.ok: {probe_payload.get('ok')}")
            if probe_payload.get("text"):
                typer.echo(str(probe_payload.get("text")))
    if not payload.get("ok", False):
        raise typer.Exit(code=2)


@app.command("smoke")
def providers_smoke(
    prompt: str = typer.Argument(
        "Reply with the single word: hello", help="Short prompt to send"
    ),
    provider: Optional[str] = typer.Option(None, help="Provider (registry name)"),
    timeout_s: Optional[float] = typer.Option(
        None, help="Timeout seconds (best-effort)"
    ),
    max_tokens: Optional[int] = typer.Option(
        16, help="Max tokens (best-effort; provider-dependent)"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Smoke test a provider with a simple prompt."""
    from dspx.provider_registry import ensure_default_providers, create_from_env
    from dspx.provider_runtime import invoke_provider, sanitize_payload, sanitize_text

    ensure_env(provider)
    ensure_default_providers()

    if timeout_s is not None:
        secs = str(float(timeout_s))
        for env_k in (
            "CODEX_TIMEOUT",
            "CLAUDE_TIMEOUT",
            "GEMINI_TIMEOUT",
            "OPENROUTER_TIMEOUT",
            "DSPX_PI_TIMEOUT",
            "DSPX_LM_AUTH_TIMEOUT",
            "DSPX_OPENAI_COMPAT_TIMEOUT",
            "DSPX_VLLM_TIMEOUT",
        ):
            os.environ[env_k] = secs

    name = provider or os.getenv("DSPX_PROVIDER") or "pi-rpc"
    lm: Any | None = None

    t0 = time.time()
    text = ""
    ok = False
    err = None

    try:
        lm = cast(Any, create_from_env(default="pi-rpc"))
        text, _usage = invoke_provider(lm, prompt=prompt, max_tokens=max_tokens)
        ok = True
    except Exception as e:
        err = sanitize_text(str(e))

    t1 = time.time()
    duration_ms: float = (t1 - t0) * 1000.0

    payload = cast(
        dict[str, Any],
        sanitize_payload(
            {
                "ok": ok,
                "provider": name,
                "model": getattr(lm, "model", None) if lm is not None else None,
                "duration_ms": duration_ms,
                "text": text,
                "error": err,
            }
        ),
    )

    # Best-effort MLflow logging (only when a run is active).
    try:
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        mlflow = get_mlflow()
        if mlflow is not None:
            ensure_run_with_standard_tags(
                "providers",
                run_name=f"provider-smoke-{name}",
                extra={"provider.smoke_ok": "1" if ok else "0"},
            )
            if mlflow.active_run() is not None:
                try:
                    mlflow.log_metrics(
                        {"provider.smoke_duration_ms": float(duration_ms)}
                    )
                except Exception:
                    pass
    except Exception:
        pass

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if ok:
            typer.echo(
                f"ok provider={name} model={payload['model']} duration_ms={payload['duration_ms']:.1f}"
            )
            typer.echo(str(payload.get("text") or ""))
        else:
            typer.echo(f"error provider={name}: {payload.get('error')}", err=True)
    if not ok:
        raise typer.Exit(code=2)


@app.command("benchmark")
def providers_benchmark(
    provider: List[str] = typer.Option(
        [],
        "--provider",
        help="Provider to benchmark (repeatable). Defaults to current DSPX_PROVIDER.",
    ),
    prompt: str = typer.Option(
        "Reply with the single word: hello",
        help="Prompt used for benchmarking calls",
    ),
    repeats: int = typer.Option(3, help="Number of measured calls per provider"),
    warmup: int = typer.Option(0, help="Warmup calls per provider before timing"),
    max_tokens: Optional[int] = typer.Option(
        16, help="Max tokens per benchmark call (best effort)"
    ),
    summary_json_out: Optional[Path] = typer.Option(
        None, help="Optional path to write benchmark summary JSON"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Benchmark one or more providers with repeated smoke requests."""
    from dspx.provider_runtime import benchmark_providers

    ensure_env(None, tracing=False)
    providers = provider or [os.getenv("DSPX_PROVIDER") or "pi-rpc"]
    payload = benchmark_providers(
        providers,
        prompt=prompt,
        repeats=max(0, int(repeats)),
        warmup=max(0, int(warmup)),
        max_tokens=max_tokens,
    )
    write_summary_json(summary_json_out, payload)
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"providers: {', '.join(payload['providers'])}")
        typer.echo(f"ranking: {', '.join(payload['ranking'])}")
        for row in payload["results"]:
            typer.echo(
                " - {provider}: success_rate={success_rate:.2f} median_ms={median} model={model}".format(
                    provider=row.get("provider"),
                    success_rate=float(row.get("success_rate") or 0.0),
                    median=row.get("duration_median_ms"),
                    model=row.get("model"),
                )
            )
