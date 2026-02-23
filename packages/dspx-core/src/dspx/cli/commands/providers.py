"""Provider utilities commands.

Commands for listing, inspecting, and testing providers.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

import typer

from dspx.cli.utils import ensure_env

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
    }

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for k, v in payload.items():
            typer.echo(f"{k}: {v}")


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
