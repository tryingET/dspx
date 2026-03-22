"""Provider utilities commands.

Commands for listing, inspecting, testing, and benchmarking providers.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import List, Optional

import typer

from dspx.cli.utils import ensure_env, output_json, write_summary_json

app = typer.Typer(no_args_is_help=True)


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
    from dspx.provider_registry import ensure_default_providers, capabilities as _caps

    ensure_env(provider, tracing=False)
    ensure_default_providers()
    name = provider or os.getenv("DSPX_PROVIDER") or "pi-rpc"
    caps = _caps(name)

    payload = {
        "provider": name,
        "supports_tools": bool(getattr(caps, "supports_tools", False)),
        "code_exec": bool(getattr(caps, "code_exec", False)),
        "json_mode": bool(getattr(caps, "json_mode", False)),
        "multi_turn": bool(getattr(caps, "multi_turn", False)),
        "structured_output_format": str(
            getattr(caps, "structured_output_format", "none")
        ),
        "supports_vision": bool(getattr(caps, "supports_vision", False)),
        "supports_audio": bool(getattr(caps, "supports_audio", False)),
    }

    output_json(payload, json_out)


@app.command("resolve")
def providers_resolve(
    provider: Optional[str] = typer.Option(None, help="Provider (registry name)"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Resolve a provider into its runtime metadata."""
    from dspx.provider_runtime import describe_provider

    ensure_env(provider, tracing=False)
    name = provider or os.getenv("DSPX_PROVIDER") or "pi-rpc"
    payload = describe_provider(name)
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
    from dspx.dtos import LMRequest
    from dspx.provider_registry import ensure_default_providers, create_from_env

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
    lm = create_from_env(default="pi-rpc")

    t0 = time.time()
    text = ""
    ok = False
    err = None

    try:
        if hasattr(lm, "generate"):
            try:
                res = lm.generate(  # type: ignore[misc]
                    LMRequest(prompt=prompt), max_tokens=max_tokens
                )
            except TypeError:
                res = lm.generate(LMRequest(prompt=prompt))  # type: ignore[misc]
            text = str((getattr(res, "outputs", None) or [""])[0]).strip()
        else:
            try:
                resp = lm.forward(prompt=prompt, max_tokens=max_tokens)  # type: ignore[attr-defined]
            except TypeError:
                resp = lm.forward(prompt=prompt)  # type: ignore[attr-defined]
            try:
                text = str(((resp.get("choices") or [{}])[0]).get("text") or "").strip()
            except Exception:
                text = str(resp).strip()
        ok = True
    except Exception as e:
        err = str(e)

    t1 = time.time()
    duration_ms: float = (t1 - t0) * 1000.0

    payload = {
        "ok": ok,
        "provider": name,
        "model": getattr(lm, "model", None),
        "duration_ms": duration_ms,
        "text": text,
        "error": err,
    }

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
            typer.echo(text)
        else:
            typer.echo(f"error provider={name}: {err}", err=True)
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
