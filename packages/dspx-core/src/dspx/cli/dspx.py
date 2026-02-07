from __future__ import annotations

import sys
from pathlib import Path
import os
from typing import Any, List, Optional, cast

import typer

from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env
from dspx.dtos import (
    SignatureGenRequest,
    CodegenRequest,
    ModuleSpec,
)
from dspx.services.signatures_service import run_generate_dto
from dspx.services.codegen_service import run_dto as codegen_run_dto
from dspx.services.module_service import run_generate as module_run_generate
from dspx.services.mermaid_workflow_service import generate_programs
from dspx.adapters import datasets as _datasets


app = typer.Typer(no_args_is_help=True, add_completion=False)
sig_app = typer.Typer(no_args_is_help=True)
mermaid_app = typer.Typer(no_args_is_help=True)
providers_app = typer.Typer(no_args_is_help=True)
tools_app = typer.Typer(no_args_is_help=True)
openapi_app = typer.Typer(no_args_is_help=True)
web_app = typer.Typer(no_args_is_help=True)
adapters_app = typer.Typer(no_args_is_help=True)
adapters_dataset_app = typer.Typer(no_args_is_help=True)
adapters_eval_app = typer.Typer(no_args_is_help=True)
cache_app = typer.Typer(no_args_is_help=True)
optimize_app = typer.Typer(no_args_is_help=True)

app.add_typer(sig_app, name="signature", help="Signature operations")
app.add_typer(mermaid_app, name="mermaid", help="Mermaid workflow operations")
app.add_typer(providers_app, name="providers", help="Provider utilities")
app.add_typer(tools_app, name="tools", help="Tools and integrations")
tools_app.add_typer(openapi_app, name="openapi", help="OpenAPI loader/caller")
tools_app.add_typer(web_app, name="web", help="Web tools (fetch/scrape)")
app.add_typer(adapters_app, name="adapters", help="Adapters (datasets/eval/stores)")
adapters_app.add_typer(adapters_dataset_app, name="dataset", help="Dataset adapters")
adapters_app.add_typer(adapters_eval_app, name="eval", help="Evaluation helpers")
app.add_typer(cache_app, name="cache", help="Inspect and manage the on-disk cache")
app.add_typer(optimize_app, name="optimize", help="Program optimization (GEPA, etc.)")


def _ensure_env(provider: Optional[str], *, tracing: bool = True) -> None:
    if provider:
        import os

        os.environ["DSPX_PROVIDER"] = provider
    load_config_env()
    if tracing:
        enable_mlflow_from_env()


@providers_app.command("list")
def providers_list(
    json_out: bool = typer.Option(False, "--json", help="Output JSON list"),
) -> None:
    from dspx.provider_registry import ensure_default_providers, available

    _ensure_env(None, tracing=False)
    ensure_default_providers()
    names = sorted(available().keys())
    if json_out:
        import json as _json

        typer.echo(_json.dumps(names, ensure_ascii=False, indent=2))
    else:
        for n in names:
            typer.echo(n)


@providers_app.command("capabilities")
def providers_capabilities(
    provider: Optional[str] = typer.Option(None, help="Provider (registry name)"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    from dspx.provider_registry import ensure_default_providers, capabilities as _caps

    _ensure_env(provider, tracing=False)
    ensure_default_providers()
    name = provider or os.getenv("DSPX_PROVIDER") or "codex-exec"
    caps = _caps(name)
    payload = {
        "provider": name,
        "supports_tools": bool(getattr(caps, "supports_tools", False)),
        "code_exec": bool(getattr(caps, "code_exec", False)),
        "json_mode": bool(getattr(caps, "json_mode", False)),
        "multi_turn": bool(getattr(caps, "multi_turn", False)),
    }
    if json_out:
        import json as _json

        typer.echo(_json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for k, v in payload.items():
            typer.echo(f"{k}: {v}")


@providers_app.command("smoke")
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
    import time as _time

    from dspx.dtos import LMRequest
    from dspx.provider_registry import ensure_default_providers, create_from_env

    _ensure_env(provider)
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

    name = provider or os.getenv("DSPX_PROVIDER") or "codex-exec"
    lm = create_from_env(default="codex-exec")

    t0 = _time.time()
    text = ""
    ok = False
    err = None
    try:
        if hasattr(lm, "generate"):
            try:
                res = lm.generate(  # type: ignore[attr-defined]
                    LMRequest(prompt=prompt), max_tokens=max_tokens
                )
            except TypeError:
                res = lm.generate(LMRequest(prompt=prompt))  # type: ignore[attr-defined]
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
    t1 = _time.time()
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
        import json as _json

        typer.echo(_json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if ok:
            typer.echo(
                f"ok provider={name} model={payload['model']} duration_ms={payload['duration_ms']:.1f}"
            )
            typer.echo(text)
        else:
            typer.echo(f"error provider={name}: {err}", err=True)
            raise typer.Exit(code=2)


@optimize_app.command("gepa")
def optimize_gepa(
    program: Path = typer.Option(
        ...,
        "--program",
        help="Path to a Python file exporting build_student() -> dspy.Module",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    train: Path = typer.Option(
        ...,
        "--train",
        help="Training dataset path (.csv/.parquet) with columns matching module inputs + output",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory to save optimized program (loadable via dspy.load)",
        file_okay=False,
        dir_okay=True,
    ),
    val: Optional[Path] = typer.Option(
        None,
        "--val",
        help="Optional validation dataset path (.csv/.parquet)",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    input_keys: List[str] = typer.Option(
        [],
        "--input",
        help="Input column/key (repeatable). If omitted, inferred from io_spec() or module signature.",
    ),
    output_keys: List[str] = typer.Option(
        [],
        "--output-key",
        help="Output column/key (repeatable). If omitted, inferred from io_spec() or module signature.",
    ),
    metric: str = typer.Option(
        "exact", help="Metric: exact|contains|f1 (per output, averaged)"
    ),
    output_weight: List[str] = typer.Option(
        [],
        "--output-weight",
        help="Per-output weight as key=float (repeatable). Overrides defaults; can also be provided by program output_weights().",
    ),
    student_provider: Optional[str] = typer.Option(
        None,
        "--student-provider",
        help="Provider for student calls (defaults to DSPX_PROVIDER, default: codex-exec).",
    ),
    reflection_provider: Optional[str] = typer.Option(
        None,
        "--reflection-provider",
        help="Provider for GEPA reflections (defaults to student-provider).",
    ),
    auto: Optional[str] = typer.Option(
        None,
        help="GEPA intensity: light|medium|heavy (required unless using --max-metric-calls/--max-full-evals).",
    ),
    max_metric_calls: Optional[int] = typer.Option(
        None,
        help="Limit total metric calls (controls GEPA cost/time). If set, --auto is ignored.",
    ),
    max_full_evals: Optional[int] = typer.Option(
        None,
        help="Limit full evaluations (alternative GEPA budget selector).",
    ),
    seed: int = typer.Option(0, help="Deterministic seed for GEPA search"),
    nrows: Optional[int] = typer.Option(
        None, help="Optional cap on rows loaded from train/val datasets"
    ),
) -> None:
    from dspx.services.optimize_service import run_gepa_optimize

    _ensure_env(student_provider)
    budget_set = sum(
        1 for x in (auto, max_metric_calls, max_full_evals) if x is not None
    )
    if budget_set != 1:
        raise typer.BadParameter(
            "Exactly one of --auto, --max-metric-calls, --max-full-evals must be set."
        )
    weights = None
    if output_weight:
        weights = {}
        for item in output_weight:
            if "=" not in item:
                raise typer.BadParameter(
                    "Invalid --output-weight; expected key=float",
                    param_hint="--output-weight",
                )
            k, v = item.split("=", 1)
            k = k.strip()
            if not k:
                raise typer.BadParameter(
                    "Invalid --output-weight; empty key", param_hint="--output-weight"
                )
            try:
                weights[k] = float(v.strip())
            except Exception as e:
                raise typer.BadParameter(
                    "Invalid --output-weight; value must be float",
                    param_hint="--output-weight",
                ) from e
    res = run_gepa_optimize(
        program_path=program,
        train_path=train,
        val_path=val,
        out_dir=out,
        input_keys=input_keys or None,
        output_keys=output_keys or None,
        student_provider=student_provider,
        reflection_provider=reflection_provider,
        auto=auto,
        max_metric_calls=int(max_metric_calls)
        if max_metric_calls is not None
        else None,
        max_full_evals=int(max_full_evals) if max_full_evals is not None else None,
        metric=metric,
        output_weights=weights,
        seed=int(seed),
        nrows=nrows,
    )
    typer.echo(str(res.out_dir))


@app.callback()
def _policy_callback(
    openrouter_api_key_file: Optional[Path] = typer.Option(
        None,
        "--openrouter-api-key-file",
        help="Read OPENROUTER_API_KEY from a file (recommended vs passing via CLI).",
    ),
    openrouter_api_key_op: Optional[str] = typer.Option(
        None,
        "--openrouter-api-key-op",
        help="Read OPENROUTER_API_KEY via 1Password CLI `op read <ref>` (e.g., op://Vault/Item/field).",
    ),
    openrouter_api_key_stdin: bool = typer.Option(
        False,
        "--openrouter-api-key-stdin",
        help="Read OPENROUTER_API_KEY from stdin (e.g., CI).",
    ),
    openrouter_api_key_prompt: bool = typer.Option(
        False,
        "--openrouter-api-key-prompt",
        help="Prompt for OPENROUTER_API_KEY (hidden input).",
    ),
    bypass_permissions: bool = typer.Option(
        False, "--bypass-permissions", help="Bypass policy checks (unsafe)"
    ),
    allowed_tools: Optional[str] = typer.Option(
        None, "--allowed-tools", help="Comma list of allowed tool names"
    ),
    disallowed_tools: Optional[str] = typer.Option(
        None, "--disallowed-tools", help="Comma list of denied tool names"
    ),
    allowed_providers: Optional[str] = typer.Option(
        None, "--allowed-providers", help="Comma list of allowed provider names"
    ),
    disallowed_providers: Optional[str] = typer.Option(
        None, "--disallowed-providers", help="Comma list of denied provider names"
    ),
    max_timeout: Optional[float] = typer.Option(
        None, "--max-timeout", help="Max timeout (s) to allow for tool calls"
    ),
    allow_network_mutate: bool = typer.Option(
        False,
        "--allow-network-mutate",
        help="Allow HTTP POST/PUT/PATCH/DELETE in tools",
    ),
    allowed_http_methods: Optional[str] = typer.Option(
        None, "--allowed-http-methods", help="Comma list of allowed HTTP methods"
    ),
    disallowed_http_methods: Optional[str] = typer.Option(
        None, "--disallowed-http-methods", help="Comma list of denied HTTP methods"
    ),
) -> None:
    # OpenRouter API key injection (avoid leaking secrets via CLI args).
    # Precedence (only if OPENROUTER_API_KEY not already set):
    # - --openrouter-api-key-file
    # - --openrouter-api-key-op
    # - --openrouter-api-key-stdin
    # - --openrouter-api-key-prompt
    if os.getenv("OPENROUTER_API_KEY") is None:
        try:
            if openrouter_api_key_file is not None:
                os.environ["OPENROUTER_API_KEY"] = openrouter_api_key_file.read_text(
                    encoding="utf-8"
                ).strip()
            elif openrouter_api_key_op:
                import shutil
                import subprocess

                if shutil.which("op") is None:
                    raise typer.Exit(code=2)
                p = subprocess.run(
                    ["op", "read", str(openrouter_api_key_op)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                if p.returncode != 0:
                    msg = (p.stderr or "").strip() or "op read failed"
                    typer.echo(msg, err=True)
                    raise typer.Exit(code=p.returncode)
                os.environ["OPENROUTER_API_KEY"] = (p.stdout or "").strip()
            elif openrouter_api_key_stdin:
                os.environ["OPENROUTER_API_KEY"] = sys.stdin.read().strip()
            elif openrouter_api_key_prompt:
                import getpass

                os.environ["OPENROUTER_API_KEY"] = getpass.getpass(
                    "OPENROUTER_API_KEY: "
                ).strip()
        except Exception:
            # Best-effort; provider will error if key is required and missing.
            pass

    # Export policy envs for downstream modules
    if bypass_permissions:
        os.environ["DSPX_POLICY_BYPASS"] = "1"
    if allowed_tools is not None:
        os.environ["DSPX_POLICY_ALLOWED_TOOLS"] = str(allowed_tools)
    if disallowed_tools is not None:
        os.environ["DSPX_POLICY_DISALLOWED_TOOLS"] = str(disallowed_tools)
    if allowed_providers is not None:
        os.environ["DSPX_POLICY_ALLOWED_PROVIDERS"] = str(allowed_providers)
    if disallowed_providers is not None:
        os.environ["DSPX_POLICY_DISALLOWED_PROVIDERS"] = str(disallowed_providers)
    if max_timeout is not None:
        os.environ["DSPX_POLICY_MAX_TIMEOUT"] = str(max_timeout)
    if allow_network_mutate:
        os.environ["DSPX_POLICY_ALLOW_NETWORK_MUTATE"] = "1"
    if allowed_http_methods is not None:
        os.environ["DSPX_POLICY_ALLOWED_HTTP_METHODS"] = str(allowed_http_methods)
    if disallowed_http_methods is not None:
        os.environ["DSPX_POLICY_DISALLOWED_HTTP_METHODS"] = str(disallowed_http_methods)


@sig_app.command("gen")
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
) -> None:
    _ensure_env(provider)
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
    if outfile:
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text(res.code, encoding="utf-8")
        # Write a small metadata file with content hash
        try:
            from dspx.cache import sha256_text
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

            meta = {
                "hash": sha256_text(res.code),
                "template_version": template_version,
                "class_name": class_name or res.signature_name or "",
                "cache_key": cache_key,
                "cache_file": str(cfile),
                "cache_enabled": os.getenv("DSPX_CACHE_ENABLE", "1")
                not in {"0", "false", "False", ""},
            }
            (outfile.parent / (outfile.name + ".meta.json")).write_text(
                __import__("json").dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
        # Log artifacts to MLflow when enabled
        try:
            from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

            mlflow = get_mlflow()
            if mlflow is not None:
                ensure_run_with_standard_tags(
                    "signature",
                    template_version=template_version,
                    run_name=f"signature-{class_name or res.signature_name or ''}",
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
        typer.echo(str(outfile))
    else:
        sys.stdout.write(res.code)
        if cache_info:
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


@sig_app.command("refine")
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
) -> None:
    from dspx.services.refine_service import run_refine as _run_refine

    _ensure_env(provider)
    if budget_ms is not None:
        os.environ["DSPX_BUDGET_SIGNATURE_MS"] = str(int(budget_ms))
    code = _run_refine(
        prompt,
        attempts=attempts,
        non_interactive=non_interactive,
        wrap_script=wrap_script,
        outfile=str(outfile) if outfile else None,
    )
    if outfile:
        typer.echo(str(outfile))
    else:
        sys.stdout.write(code)


@app.command("module-gen")
def module_gen(
    name: str = typer.Option(..., "--name", "-n", help="Module class name"),
    description: str = typer.Option(
        "", "--description", "-d", help="Description docstring"
    ),
    input: List[str] = typer.Option(
        [], "--input", "-i", help="Input fields (repeatable)"
    ),
    output: List[str] = typer.Option(
        [], "--output", "-o", help="Output fields (repeatable)"
    ),
    template_version: str = typer.Option(
        "simple-v1", help="Template version (use 'simple-*' for deterministic output)"
    ),
    use_signature: bool = typer.Option(
        False, help="Embed a simple Signature and wire Predict"
    ),
    provider: Optional[str] = typer.Option(None, help="Provider (registry name)"),
    outfile: Optional[Path] = typer.Option(None, help="Write code to file"),
    no_cache: bool = typer.Option(False, help="Bypass on-disk cache for this run"),
    cache_info: bool = typer.Option(False, help="Print cache key and path info"),
    budget_ms: Optional[int] = typer.Option(
        None, help="Time budget in ms (logs to MLflow)"
    ),
) -> None:
    _ensure_env(provider)
    if no_cache:
        os.environ["DSPX_CACHE_ENABLE"] = "0"
    if budget_ms is not None:
        os.environ["DSPX_BUDGET_MODULE_MS"] = str(int(budget_ms))
    spec = ModuleSpec(
        name=name,
        description=description,
        inputs=input,
        outputs=output,
        options={"template_version": template_version},
    )
    art = module_run_generate(spec, use_signature=use_signature)
    if outfile:
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text(art.code, encoding="utf-8")
        # Write metadata
        try:
            from dspx.cache import sha256_text
            from dspx.cache import make_key, cache_dir

            cache_key = make_key(
                {
                    "kind": "module",
                    "name": name,
                    "description": description,
                    "inputs": input,
                    "outputs": output,
                    "use_signature": bool(use_signature),
                    "template_version": template_version,
                }
            )
            cfile = cache_dir() / "module" / f"{cache_key}.json"

            (outfile.parent / (outfile.name + ".meta.json")).write_text(
                __import__("json").dumps(
                    {
                        "hash": sha256_text(art.code),
                        "template_version": template_version,
                        "use_signature": bool(use_signature),
                        "name": name,
                        "inputs": input,
                        "outputs": output,
                        "cache_key": cache_key,
                        "cache_file": str(cfile),
                        "cache_enabled": os.getenv("DSPX_CACHE_ENABLE", "1")
                        not in {"0", "false", "False", ""},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        # MLflow logging of artifacts
        try:
            from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

            mlflow = get_mlflow()
            if mlflow is not None:
                ensure_run_with_standard_tags(
                    "module",
                    template_version=template_version,
                    run_name=f"module-{name}",
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
        typer.echo(str(outfile))
    else:
        sys.stdout.write(art.code)
        if cache_info:
            try:
                from dspx.cache import make_key, cache_dir

                cache_key = make_key(
                    {
                        "kind": "module",
                        "name": name,
                        "description": description,
                        "inputs": input,
                        "outputs": output,
                        "use_signature": bool(use_signature),
                        "template_version": template_version,
                    }
                )
                cfile = cache_dir() / "module" / f"{cache_key}.json"
                typer.echo(
                    f"cache_key={cache_key} cache_file={cfile} exists={cfile.exists()}",
                    err=True,
                )
            except Exception:
                pass


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
) -> None:
    _ensure_env(provider)
    if no_cache:
        os.environ["DSPX_CACHE_ENABLE"] = "0"
    if budget_ms is not None:
        os.environ["DSPX_BUDGET_CODEGEN_MS"] = str(int(budget_ms))
    req = CodegenRequest(
        spec=spec, language=language, template_version=template_version
    )
    res = codegen_run_dto(req)
    if outfile:
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text(res.code, encoding="utf-8")
        # Write metadata
        try:
            from dspx.cache import sha256_text
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

            (outfile.parent / (outfile.name + ".meta.json")).write_text(
                __import__("json").dumps(
                    {
                        "hash": sha256_text(res.code),
                        "language": language or "python",
                        "template_version": template_version,
                        "spec_len": len(spec),
                        "cache_key": cache_key,
                        "cache_file": str(cfile),
                        "cache_enabled": os.getenv("DSPX_CACHE_ENABLE", "1")
                        not in {"0", "false", "False", ""},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        # MLflow logging of artifacts
        try:
            from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

            mlflow = get_mlflow()
            if mlflow is not None:
                ensure_run_with_standard_tags(
                    "codegen",
                    template_version=template_version,
                    run_name=f"codegen-{language or 'python'}",
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
        typer.echo(str(outfile))
    else:
        sys.stdout.write(res.code)
        if cache_info:
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


def _read_mermaid(path: Optional[Path]) -> str:
    if path and str(path) != "-":
        return Path(path).read_text(encoding="utf-8")
    data = sys.stdin.read()
    if not data:
        raise typer.Exit(code=2)
    return data


@mermaid_app.command("gen")
def mermaid_gen(
    file: Optional[Path] = typer.Option(
        None, "--file", "-f", help="Mermaid file or - for stdin"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Workflow name (slug)"
    ),
    outdir: Optional[Path] = typer.Option(
        None, "--outdir", "-o", help="Output directory"
    ),
    variants: str = typer.Option(
        "predict,cot,react", "--variants", "-v", help="Comma list"
    ),
) -> None:
    diagram = _read_mermaid(file)
    vs = [v.strip() for v in variants.split(",") if v.strip()]
    produced = generate_programs(
        diagram, name=name, out_dir=str(outdir) if outdir else None, variants=vs
    )
    for p in produced:
        typer.echo(p)


@mermaid_app.command("sig")
def mermaid_sig(
    file: Optional[Path] = typer.Option(
        None, "--file", "-f", help="Mermaid file or - for stdin"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Workflow name (slug)"
    ),
    outdir: Optional[Path] = typer.Option(
        None, "--outdir", "-o", help="Output directory"
    ),
    provider: Optional[str] = typer.Option(None, help="Provider name (registry)"),
    use_cli: bool = typer.Option(False, help="Use vibegen/viberefine CLIs"),
    refine: bool = typer.Option(False, help="Use non-interactive viberefine"),
    refine_attempts: int = typer.Option(3, help="Attempts for refine"),
) -> None:
    # Reuse existing canonical CLI implementation to avoid drift
    from dspx.cli import dspx_mermaid2dspy as legacy

    args: List[str] = []
    if file is not None:
        args.extend(["-f", str(file)])
    if name:
        args.extend(["-n", name])
    if outdir:
        args.extend(["-o", str(outdir)])
    if provider:
        args.extend(["--provider", provider])
    if use_cli:
        args.append("--use-cli")
    if refine:
        args.append("--refine")
        args.extend(["--refine-attempts", str(refine_attempts)])
    rc = legacy.main(args)
    raise typer.Exit(code=rc)


@openapi_app.command("ops")
def openapi_ops(
    spec: str = typer.Argument(..., help="OpenAPI spec path or URL"),
    allow_host: Optional[str] = typer.Option(None, help="Allowlisted host for URL"),
    grep: Optional[str] = typer.Option(
        None, help="Filter ops by substring in id or path"
    ),
    method: Optional[str] = typer.Option(
        None, help="Filter by HTTP method (GET, POST, ...)"
    ),
    tags: Optional[str] = typer.Option(
        None, help="Filter by comma-separated tags (any match)"
    ),
    paths: bool = typer.Option(False, help="Print METHOD PATH instead of operationId"),
    json_out: bool = typer.Option(
        False, "--json", help="Output JSON list of operations"
    ),
) -> None:
    from dspx.tools.openapi import load_spec
    from dspx.tools.openapi.loader import extract_operation_infos

    _ensure_env(None, tracing=False)
    allowed = {allow_host: True} if allow_host else None
    data = load_spec(str(spec), allowed_hosts=allowed)
    ops = extract_operation_infos(data)
    flt = (grep or "").lower()
    mflt = (method or "").strip().upper()
    tagset = None
    if tags:
        tagset = {t.strip().lower() for t in tags.split(",") if t.strip()}
    items = []
    for k in sorted(ops.keys()):
        if flt:
            path = str(ops[k].path or "")
            if flt not in k.lower() and flt not in path.lower():
                continue
        if mflt and str(ops[k].method or "").upper() != mflt:
            continue
        if tagset:
            op_tags = [str(t).lower() for t in (ops[k].tags or [])]
            if not any(t in op_tags for t in tagset):
                continue
        if json_out:
            items.append(
                {
                    "operationId": k,
                    "method": str(ops[k].method or "").upper(),
                    "path": ops[k].path or "",
                    "tags": ops[k].tags or [],
                    "summary": ops[k].summary or None,
                }
            )
        elif paths:
            typer.echo(f"{str(ops[k].method or '').upper()} {ops[k].path or ''}")
        else:
            typer.echo(k)
    if json_out:
        import json as _json

        typer.echo(_json.dumps(items, ensure_ascii=False, indent=2))


@openapi_app.command("call")
def openapi_call(
    spec: str = typer.Option(..., "--spec", help="OpenAPI spec path or URL"),
    op: str = typer.Option(..., "--op", help="operationId to call"),
    params: Optional[str] = typer.Option(None, help="Comma-separated k=v pairs"),
    body: Optional[Path] = typer.Option(None, help="JSON body file"),
    allow_host: Optional[str] = typer.Option(
        None, help="Allowlisted host (e.g., api.github.com)"
    ),
    timeout: Optional[float] = typer.Option(None, help="Timeout seconds"),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation for mutating operations (POST/PUT/PATCH/DELETE)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Do not perform the network call; print a preview of the request",
    ),
) -> None:
    import json as _json
    from dspx.tools.openapi import load_spec
    from dspx.tools.openapi.loader import extract_operation_infos
    from dspx.dtos import OpenAPICallRequest
    from dspx.tools.descriptors import ToolDescriptor
    from dspx.ui.confirmations import build_preview, needs_confirmation

    _ensure_env(None)
    data = load_spec(
        str(spec), allowed_hosts=({allow_host: True} if allow_host else None)
    )
    ops = extract_operation_infos(data)
    if op not in ops:
        raise typer.Exit(code=2)
    pmap = {}
    if params:
        for part in params.split(","):
            if not part.strip():
                continue
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            pmap[k.strip()] = v.strip()
    body_data = None
    if body:
        body_data = _json.loads(body.read_text(encoding="utf-8"))
    req = OpenAPICallRequest(
        operation_id=op, params=pmap, body=body_data, timeout=timeout
    )
    allowed = {allow_host: True} if allow_host else None
    # Lazy import to avoid httpx in CLI startup path
    from dspx.tools.openapi.caller import call_operation

    method = str(ops[op].method or "GET").upper()
    desc = ToolDescriptor(
        name=op,
        capabilities=["network.mutate"]
        if method in {"POST", "PUT", "PATCH", "DELETE"}
        else ["network.read"],
        kind="openapi",
        openapi=ops[op],
    )
    preview = build_preview(desc, pmap)
    if dry_run:
        typer.echo(f"[dry-run] {preview}")
        return
    if needs_confirmation(desc) and not yes:
        if not typer.confirm(
            f"About to perform {preview}. Continue? [y/N]", default=False
        ):
            typer.echo(
                "aborted: confirmation required for mutating operation. "
                "Use --yes or set DSPX_POLICY_ALLOW_NETWORK_MUTATE=1",
                err=True,
            )
            raise typer.Exit(code=2)

    # Start an MLflow run for traceability when enabled (local store is fine).
    try:
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        mlflow = get_mlflow()
        if mlflow is not None:
            ensure_run_with_standard_tags(
                "openapi",
                run_name=f"openapi-{op}",
                extra={
                    "openapi.operation_id": op,
                    "openapi.method": method,
                },
            )
    except Exception:
        pass
    res = call_operation(req, operation=ops[op].model_dump(), allowed_hosts=allowed)
    # Print raw_text for user-friendly output
    typer.echo(res.raw_text or "")


@openapi_app.command("describe")
def openapi_describe(
    spec: str = typer.Option(..., "--spec", help="OpenAPI spec path or URL"),
    op: str = typer.Option(..., "--op", help="operationId to describe"),
    allow_host: Optional[str] = typer.Option(None, help="Allowlisted host for URL"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    from dspx.tools.openapi import load_spec
    from dspx.tools.openapi.loader import extract_operation_infos

    _ensure_env(None, tracing=False)
    data = load_spec(spec, allowed_hosts=({allow_host: True} if allow_host else None))
    ops = extract_operation_infos(data)
    if op not in ops:
        raise typer.Exit(code=2)
    info = ops[op]
    if json_out:
        import json as _json
        from dspx.tools.descriptors import ToolDescriptor
        from dspx.ui.renderers import tool_descriptor_to_json, schema_example

        # Use descriptor-based base JSON for consistency
        desc = ToolDescriptor(name=op, capabilities=[], kind="openapi", openapi=info)
        out = tool_descriptor_to_json(desc)
        out.update(
            {
                "operationId": op,
                "parameters": [],
                "requestBody": None,
                "responses": info.responses or {},
            }
        )
        params = info.parameters or []
        if isinstance(params, list):
            for p in params:
                if not isinstance(p, dict):
                    continue
                out["parameters"].append(
                    {
                        "in": p.get("in"),
                        "name": p.get("name"),
                        "required": bool(p.get("required", False)),
                        "type": (
                            (p.get("schema") or {}).get("type")
                            if isinstance(p.get("schema"), dict)
                            else None
                        ),
                    }
                )
        rb = info.requestBody
        if isinstance(rb, dict):
            out["requestBody"] = {
                "required": bool(rb.get("required", False)),
                "schema": rb.get("schema") or None,
            }
        # Best-effort response examples for application/json schemas
        try:
            resps = out.get("responses") or {}
            if isinstance(resps, dict):
                for code, rd in list(resps.items()):
                    if not isinstance(rd, dict):
                        continue
                    schema = (
                        rd.get("schema") if isinstance(rd.get("schema"), dict) else None
                    )
                    if schema:
                        ex = schema_example(schema)
                        if ex is not None:
                            rd["example"] = ex
        except Exception:
            pass
        typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))
        return
    # Text output
    typer.echo(f"operationId: {op}")
    typer.echo(f"method: {str(info.method or '').upper()}")
    typer.echo(f"path: {info.path or ''}")
    if info.server:
        typer.echo(f"server: {info.server}")
    if info.tags:
        typer.echo("tags:")
        for t in info.tags:
            typer.echo(f"  - {t}")
    params = info.parameters or []
    typer.echo("parameters:")
    if isinstance(params, list) and params:
        for p in params:
            if not isinstance(p, dict):
                continue
            where = str(p.get("in") or "")
            name = str(p.get("name") or "")
            required = bool(p.get("required", False))
            t = (
                (p.get("schema") or {}).get("type")
                if isinstance(p.get("schema"), dict)
                else None
            ) or ""
            typer.echo(f"  - {where}:{name} required={str(required).lower()} type={t}")
    else:
        typer.echo("  - (none)")
    rb = info.requestBody
    typer.echo("requestBody:")
    if isinstance(rb, dict) and (rb.get("required") or rb.get("schema")):
        req = bool(rb.get("required", False))
        schema = rb.get("schema") or {}
        typer.echo(f"  required={str(req).lower()}")
        if isinstance(schema, dict) and schema.get("type") == "object":
            props = schema.get("properties") or {}
            reqs = set(schema.get("required") or [])
            if props:
                typer.echo("  properties:")
                for name, ps in props.items():
                    t = (ps or {}).get("type", "")
                    typer.echo(
                        f"    - {name}: type={t} required={'true' if name in reqs else 'false'}"
                    )
            else:
                typer.echo("  properties: (none)")
        else:
            typer.echo("  schema: (unstructured)")
    else:
        typer.echo("  (none)")
    # Responses summary
    typer.echo("responses:")
    resps = info.responses or {}
    if isinstance(resps, dict) and resps:
        for code, desc in resps.items():
            try:
                schema = (desc or {}).get("schema") if isinstance(desc, dict) else None
                cts = (
                    (desc or {}).get("contentTypes") if isinstance(desc, dict) else None
                )
                typer.echo(f"  - {code} contentTypes={cts or []}")
                if isinstance(schema, dict):
                    t = schema.get("type")
                    if t == "object":
                        props = schema.get("properties") or {}
                        reqs = set(schema.get("required") or [])
                        if props:
                            typer.echo("    properties:")
                            for name, ps in props.items():
                                ty = (ps or {}).get("type", "")
                                typer.echo(
                                    f"      - {name}: type={ty} required={'true' if name in reqs else 'false'}"
                                )
                        else:
                            typer.echo("    properties: (none)")
                    else:
                        typer.echo(f"    schema.type={t}")
            except Exception:
                pass
    else:
        typer.echo("  (none)")


@openapi_app.command("load")
def openapi_load(
    prefix: str = typer.Option(
        ..., "--prefix", "-p", help="Registration prefix (e.g., gh)"
    ),
    spec: Path = typer.Option(..., "--spec", help="OpenAPI JSON spec path"),
    allow_host: Optional[str] = typer.Option(
        None, help="Allowlisted host (e.g., api.github.com)"
    ),
    outdir: Optional[Path] = typer.Option(
        None, help="Persist mapping under this dir (default generated/openapi)"
    ),
) -> None:
    """Persist a small mapping to help configure environments consistently.

    Writes a JSON file with {"prefix", "spec", "allow_host"} under generated/openapi/<prefix>.json by default.
    Note: runtime currently relies on environment vars DSPX_OPENAPI_SPEC_<PREFIX> and DSPX_OPENAPI_HOST_<PREFIX>.
    """
    import json as _json

    _ensure_env(None, tracing=False)
    base = outdir or Path("generated/openapi")
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{prefix}.json"
    payload = {"prefix": prefix, "spec": str(spec), "allow_host": allow_host}
    path.write_text(
        _json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    typer.echo(str(path))


@openapi_app.command("env")
def openapi_env(
    prefix: str = typer.Option(
        ..., "--prefix", "-p", help="Registration prefix (e.g., gh)"
    ),
    map_file: Optional[Path] = typer.Option(
        None, "--map", help="Path to <prefix>.json mapping"
    ),
) -> None:
    """Print shell exports for DSPX_OPENAPI_SPEC_<P> and DSPX_OPENAPI_HOST_<P> from a mapping file."""
    import json as _json

    _ensure_env(None, tracing=False)
    path = None
    if map_file and map_file.exists():
        path = map_file
    else:
        # try defaults
        for d in (Path.cwd() / "generated/openapi", Path.cwd() / "openapi"):
            cand = d / f"{prefix}.json"
            if cand.exists():
                path = cand
                break
    if not path:
        raise typer.Exit(code=2)
    data = _json.loads(path.read_text(encoding="utf-8"))
    spec = data.get("spec")
    host = data.get("allow_host")
    u = prefix.upper()
    if spec:
        typer.echo(f"export DSPX_OPENAPI_SPEC_{u}='{spec}'")
    if host:
        typer.echo(f"export DSPX_OPENAPI_HOST_{u}='{host}'")


# --- Tools: Web ---


@web_app.command("fetch")
def tools_web_fetch(
    url: str = typer.Argument(..., help="URL to fetch"),
    allow_host: Optional[str] = typer.Option(
        None, help="Allowlisted host (e.g., example.com)"
    ),
    timeout: float = typer.Option(15.0, help="Timeout seconds"),
) -> None:
    from dspx.tools.registry import ensure_default_tools, get_tool

    ensure_default_tools()
    fn = get_tool("web_fetch")
    allowed = {allow_host: True} if allow_host else None
    out = fn(url, timeout=timeout, allowed_hosts=allowed)
    # Truncate text for terminal friendliness
    text = str(out.get("text", ""))
    if len(text) > 4000:
        out["text"] = text[:4000] + "\n... [truncated]"
    import json as _json

    typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))


@web_app.command("scrape")
def tools_web_scrape(
    url: str = typer.Argument(..., help="URL to fetch and extract"),
    selector: Optional[str] = typer.Option(None, help="Optional CSS selector"),
    allow_host: Optional[str] = typer.Option(
        None, help="Allowlisted host (e.g., example.com)"
    ),
    timeout: float = typer.Option(15.0, help="Timeout seconds"),
) -> None:
    from dspx.tools.registry import ensure_default_tools, get_tool

    ensure_default_tools()
    fn = get_tool("web_scrape")
    allowed = {allow_host: True} if allow_host else None
    out = fn(url, selector=selector, timeout=timeout, allowed_hosts=allowed)
    # Truncate long text
    text = str(out.get("text", ""))
    if len(text) > 4000:
        out["text"] = text[:4000] + "\n... [truncated]"
    import json as _json

    typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))


@tools_app.command("list")
def tools_list(
    json_out: bool = typer.Option(False, "--json", help="Output JSON with metadata"),
) -> None:
    from dspx.tools.registry import ensure_default_tools, available_descriptors
    from dspx.ui.renderers import tool_descriptor_to_json, tool_descriptor_to_list_text
    import json as _json

    ensure_default_tools()
    descs = available_descriptors()
    if json_out:
        items = [tool_descriptor_to_json(d) for d in descs]
        typer.echo(_json.dumps(items, ensure_ascii=False, indent=2))
    else:
        for d in descs:
            typer.echo(tool_descriptor_to_list_text(d))


@tools_app.command("describe")
def tools_describe(
    name: str = typer.Argument(..., help="Tool name"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON details"),
    examples: bool = typer.Option(
        False, "--examples", help="Include usage examples/hints"
    ),
) -> None:
    from dspx.tools.registry import ensure_default_tools, get_descriptor, get_tool
    from dspx.ui.renderers import tool_descriptor_to_json, tool_descriptor_describe_text
    import json as _json

    ensure_default_tools()
    try:
        desc = get_descriptor(name)
    except Exception:
        # Fallback descriptor from function
        fn = get_tool(name)
        from dspx.tools.descriptors import ToolDescriptor

        try:
            caps = list(getattr(fn, "_dspx_capabilities", []) or [])
        except Exception:
            caps = []
        try:
            descr = getattr(fn, "_dspx_description", None) or None
            descr = str(descr) if descr else None
        except Exception:
            descr = None
        desc = ToolDescriptor(name=name, capabilities=caps, description=descr)

    # Build example hints
    ex: list[str] = []
    if examples:
        if desc.kind == "openapi" and desc.openapi is not None:
            host = None
            try:
                from urllib.parse import urlparse as _urlparse

                u = _urlparse(str(desc.openapi.server or ""))
                host = u.hostname
            except Exception:
                host = None
            ex.append(
                "dspx tools openapi call --spec <SPEC.json> --op "
                + (desc.openapi.operation_id)
                + (f" --allow-host {host}" if host else "")
                + " --params k=v"
            )
            ex.append(f"dspx tools run {name} --params k=v")
        else:
            mapping = {
                "web_fetch": [
                    "dspx tools web fetch --allow-host example.com https://example.com",
                    "dspx tools run web_fetch --params url=https://example.com",
                ],
                "web_scrape": [
                    "dspx tools web scrape --allow-host example.com --selector h1 https://example.com",
                    "dspx tools run web_scrape --params url=https://example.com,selector=h1",
                ],
                "data_preview": [
                    "dspx tools run data_preview --params path=./data.csv"
                ],
                "repo_summary": ["dspx tools run repo_summary --params root=."],
                "db_schema": [
                    "dspx tools run db_schema --params url=sqlite:///generated/sixe.db"
                ],
                "kb_summary": ["dspx tools run kb_summary --params path=./docs"],
                "ontology_summary": [
                    "dspx tools run ontology_summary --params path=./src"
                ],
            }
            ex.extend(mapping.get(name, []))

    if json_out:
        payload = tool_descriptor_to_json(desc)
        # Enrich with full OpenAPI details for describe JSON
        if desc.kind == "openapi" and desc.openapi is not None:
            payload["parameters"] = desc.openapi.parameters or []
            payload["requestBody"] = desc.openapi.requestBody or None
            payload["responses"] = desc.openapi.responses or {}
        if ex:
            payload["examples"] = ex
        typer.echo(_json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(
            tool_descriptor_describe_text(desc, examples=ex if examples else None)
        )


@tools_app.command("run")
def tools_run(
    name: str = typer.Argument(..., help="Tool name"),
    params: Optional[str] = typer.Option(
        None, help="Comma-separated k=v pairs for 'params'"
    ),
    body_json: Optional[Path] = typer.Option(None, help="JSON file for 'body'"),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation for mutating operations (OpenAPI POST/PUT/PATCH/DELETE)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Do not execute the tool; print a preview (OpenAPI: METHOD URL)",
    ),
) -> None:
    import json as _json
    from dspx.tools.registry import ensure_default_tools, get_tool, get_descriptor

    ensure_default_tools()
    fn = get_tool(name)
    pmap = {}
    if params:
        for part in params.split(","):
            if not part.strip() or "=" not in part:
                continue
            k, v = part.split("=", 1)
            pmap[k.strip()] = v.strip()
    body = None
    if body_json:
        body = _json.loads(body_json.read_text(encoding="utf-8"))
    # Destructive-op confirmation for OpenAPI tools (unless bypassed)
    try:
        is_openapi = bool(getattr(fn, "_dspx_is_openapi_tool", False))
    except Exception:
        is_openapi = False
    if is_openapi:
        # Use descriptor-based confirmation/preview
        try:
            desc = get_descriptor(name)
        except Exception:
            desc = None
        from dspx.ui.confirmations import build_preview

        if dry_run:
            if desc is None:
                # Build a minimal descriptor from function attributes
                from dspx.tools.descriptors import ToolDescriptor
                from dspx.tools.openapi.models import OpenAPIOperationInfo

                method = str(getattr(fn, "_dspx_openapi_method", "GET"))
                server = str(getattr(fn, "_dspx_openapi_server", ""))
                path = str(getattr(fn, "_dspx_openapi_path", ""))
                caps = (
                    ["network.mutate"]
                    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
                    else ["network.read"]
                )
                opi = OpenAPIOperationInfo(
                    operation_id=name, method=method, path=path, server=server
                )
                desc = ToolDescriptor(
                    name=name, capabilities=caps, kind="openapi", openapi=opi
                )
            preview = build_preview(desc, pmap)
            typer.echo(f"[dry-run] {preview}")
            return
        if desc is not None:
            from dspx.ui.confirmations import needs_confirmation

            need = needs_confirmation(desc)
            opi = getattr(desc, "openapi", None)
            if not need and getattr(desc, "kind", "") == "openapi" and opi is not None:
                try:
                    m = str(getattr(opi, "method", "") or "").upper()
                    need = m in {"POST", "PUT", "PATCH", "DELETE"}
                except Exception:
                    need = False
            if need and not yes:
                preview = build_preview(desc, pmap)
                if not typer.confirm(
                    f"About to perform {preview}. Continue? [y/N]", default=False
                ):
                    typer.echo(
                        "aborted: confirmation required for mutating operation. "
                        "Use --yes or set DSPX_POLICY_ALLOW_NETWORK_MUTATE=1",
                        err=True,
                    )
                    raise typer.Exit(code=2)
        else:
            # No descriptor found: fallback to method-based prompt
            try:
                method_eff = str(getattr(fn, "_dspx_openapi_method", "GET")).upper()
            except Exception:
                method_eff = "GET"
            from dspx.policy import (
                bypass as _p_bypass,
                allow_network_mutate as _p_allow,
            )

            if (
                method_eff in {"POST", "PUT", "PATCH", "DELETE"}
                and not _p_bypass()
                and not _p_allow()
                and not yes
            ):
                server = str(getattr(fn, "_dspx_openapi_server", ""))
                path = str(getattr(fn, "_dspx_openapi_path", ""))
                preview = f"{method_eff} {path or '(unknown path)'}"
                if not typer.confirm(
                    f"About to perform {preview}. Continue? [y/N]", default=False
                ):
                    typer.echo(
                        "aborted: confirmation required for mutating operation. "
                        "Use --yes or set DSPX_POLICY_ALLOW_NETWORK_MUTATE=1",
                        err=True,
                    )
                    raise typer.Exit(code=2)
    # Generic capability-based confirmation for other tools
    if dry_run and not is_openapi:
        try:
            desc = get_descriptor(name)
        except Exception:
            desc = None
        import json as _json

        if desc is not None:
            payload = {
                "tool": desc.name,
                "capabilities": desc.capabilities,
                "params": pmap or {},
                "body": body or None,
            }
        else:
            # Fallback to function attributes
            try:
                caps = list(getattr(fn, "_dspx_capabilities", []) or [])
            except Exception:
                caps = []
            payload = {
                "tool": name,
                "capabilities": caps,
                "params": pmap or {},
                "body": body or None,
            }
        typer.echo(_json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if not is_openapi:
        try:
            desc = get_descriptor(name)
        except Exception:
            desc = None
        if desc is not None:
            from dspx.ui.confirmations import needs_confirmation

            if needs_confirmation(desc) and not yes:
                cap_list = (
                    ", ".join(sorted(desc.capabilities))
                    if desc.capabilities
                    else "mutating"
                )
                prompt = f"About to run tool '{name}' with capabilities: {cap_list}. Continue? [y/N]"
                if not typer.confirm(prompt, default=False):
                    typer.echo(
                        "aborted: confirmation required for mutating capability. "
                        "Use --yes or set DSPX_POLICY_BYPASS=1",
                        err=True,
                    )
                    raise typer.Exit(code=2)
        else:
            # Fallback to function capability attributes
            try:
                caps = set(getattr(fn, "_dspx_capabilities", []) or [])
            except Exception:
                caps = set()
            mutating_caps = {"network.mutate", "filesystem.write", "code.exec"}
            if caps & mutating_caps and not yes:
                if not typer.confirm(
                    f"About to run tool '{name}' with capabilities: {', '.join(sorted(caps))}. Continue? [y/N]",
                    default=False,
                ):
                    typer.echo(
                        "aborted: confirmation required for mutating capability. "
                        "Use --yes or set DSPX_POLICY_BYPASS=1",
                        err=True,
                    )
                    raise typer.Exit(code=2)
    out = fn(params=pmap or None, body=body)
    # Try to dump nicely if dict-like
    try:
        typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))
    except Exception:
        typer.echo(str(out))


@tools_app.command("search")
def tools_search(
    query: str = typer.Argument(..., help="Query string to match name/description"),
    tags: Optional[str] = typer.Option(
        None, "--tags", help="Comma-separated tag filters"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON with metadata"),
) -> None:
    from dspx.tools.registry import ensure_default_tools, available_descriptors
    from dspx.ui.renderers import tool_descriptor_to_json, tool_descriptor_to_list_text
    import json as _json

    ensure_default_tools()
    q = query.strip().lower()
    tagset = None
    if tags:
        tagset = {t.strip().lower() for t in tags.split(",") if t.strip()}

    items = []
    for d in available_descriptors():
        nm = d.name.lower()
        desc_text = (d.description or "").lower()
        match_q = not q or (q in nm or q in desc_text)
        op_tags = [
            str(t).lower()
            for t in (d.openapi.tags if (d.kind == "openapi" and d.openapi) else [])
        ]
        match_tags = True
        if tagset:
            match_tags = any(t in op_tags for t in tagset)
        if not (match_q and match_tags):
            continue
        if json_out:
            items.append(tool_descriptor_to_json(d))
        else:
            typer.echo(tool_descriptor_to_list_text(d))
    if json_out:
        typer.echo(_json.dumps(items, ensure_ascii=False, indent=2))


# --- Adapters CLI ---


@adapters_app.command("list")
def adapters_list(
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    # Keep this list in sync with adapters package
    items = [
        "dataset.csv",
        "dataset.parquet",
        "dataset.mlflow",
        "eval.accuracy",
        "eval.f1_binary",
        "store.local_object",
    ]
    descs = {
        "dataset.csv": "CSV dataset loader",
        "dataset.parquet": "Parquet dataset loader",
        "dataset.mlflow": "MLflow dataset reference",
        "eval.accuracy": "Accuracy metric",
        "eval.f1_binary": "F1 (binary) metric",
        "store.local_object": "Local object store",
    }
    if json_out:
        import json as _json

        typer.echo(_json.dumps(items, ensure_ascii=False, indent=2))
    else:
        for line in items:
            d = descs.get(line)
            if d:
                typer.echo(f"{line} - {d}")
            else:
                typer.echo(line)


@adapters_dataset_app.command("describe")
def adapters_dataset_describe(
    type: str = typer.Option(..., "--type", "-t", help="csv|parquet|mlflow"),
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="File path"),
    run_id: Optional[str] = typer.Option(None, help="MLflow run_id (mlflow only)"),
    artifact_path: Optional[str] = typer.Option(
        None, help="MLflow artifact path (mlflow only)"
    ),
    nrows: int = typer.Option(5, help="Preview rows for csv/parquet"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    t = type.strip().lower()
    if t in {"csv", "parquet"}:
        if not path:
            raise typer.Exit(code=2)
        if t == "csv":
            ds = _datasets.CSVDataset(str(path), nrows=nrows)
        else:
            ds = _datasets.ParquetDataset(str(path), nrows=nrows)
        try:
            rows = ds.load()
        except Exception as e:
            typer.echo(f"error: {e}")
            raise typer.Exit(code=1)
        cols = list(rows[0].keys()) if rows else []
        out = {"type": t, "path": str(path), "columns": cols, "rows": rows}
    elif t == "mlflow":
        if not run_id or not artifact_path:
            raise typer.Exit(code=2)
        ref = _datasets.MLflowDatasetRef(run_id=run_id, artifact_path=artifact_path)
        out = ref.describe()
    else:
        raise typer.Exit(code=2)
    if json_out:
        import json as _json

        typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if out.get("type") == "mlflow_artifact":
            typer.echo(
                f"mlflow dataset: run_id={out['run_id']} artifact_path={out['artifact_path']}"
            )
        else:
            typer.echo(f"type: {out['type']} path: {out['path']}")
            cols_any = out.get("columns")
            cols_txt = (
                ", ".join(str(c) for c in cols_any)
                if isinstance(cols_any, list)
                else ""
            )
            typer.echo("columns: " + cols_txt)
            typer.echo("rows:")
            for r in out.get("rows", [])[:nrows]:
                typer.echo(str(r))


@adapters_dataset_app.command("split")
def adapters_dataset_split(
    csv: Path = typer.Option(..., "--csv", help="CSV path to split"),
    outdir: Path = typer.Option(..., "--outdir", help="Output directory for splits"),
    test_size: Optional[float] = typer.Option(None, help="Test fraction (0-1)"),
    ratios: Optional[str] = typer.Option(
        None, help="Comma-separated ratios train,val,test that sum to 1"
    ),
    seed: int = typer.Option(42, help="Random seed for shuffling"),
    stratify_col: Optional[str] = typer.Option(
        None, help="Column name for label stratification"
    ),
    group_col: Optional[str] = typer.Option(
        None, help="Optional group column to keep groups intact"
    ),
    group_balance: str = typer.Option(
        "instances",
        help="When using --group-col with stratification, balance per label by 'instances' or 'groups'",
    ),
    min_per_label: Optional[int] = typer.Option(
        None,
        help="Minimum per-label count per partition (applies only to stratified splits)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON summary"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Plan splits without writing files"
    ),
) -> None:
    import json as _json
    import pandas as pd
    from dspx.adapters.datasets import (
        train_test_split as _tts,
        train_val_test_split as _tvts,
        stratified_train_test_split as _stts,
        stratified_train_val_test_split as _stvts,
    )

    df = pd.read_csv(str(csv))
    records = df.to_dict(orient="records")
    if not dry_run:
        outdir.mkdir(parents=True, exist_ok=True)
    summary = {"input": str(csv), "outdir": str(outdir)}
    if ratios:
        try:
            parts = [float(x.strip()) for x in ratios.split(",")]
        except Exception:
            raise typer.Exit(code=2)
        # If stratify requested, ensure columns exist and use stratified split
        if stratify_col:
            if stratify_col not in df.columns:
                typer.echo(f"error: stratify_col '{stratify_col}' not found")
                raise typer.Exit(code=2)
            if group_col and group_col not in df.columns:
                typer.echo(f"error: group_col '{group_col}' not found")
                raise typer.Exit(code=2)
            tr, va, te = _stvts(
                records,
                label_key=str(stratify_col),
                ratios=tuple(parts),
                seed=seed,
                group_key=str(group_col) if group_col else None,
                group_balance=group_balance,
                min_per_label=min_per_label,
            )
        else:
            tr, va, te = _tvts(records, ratios=tuple(parts), seed=seed)
        if not dry_run:
            pd.DataFrame(tr).to_csv(outdir / "train.csv", index=False)
            pd.DataFrame(va).to_csv(outdir / "val.csv", index=False)
            pd.DataFrame(te).to_csv(outdir / "test.csv", index=False)
        summary.update(
            {
                "train": str(outdir / "train.csv"),
                "val": str(outdir / "val.csv"),
                "test": str(outdir / "test.csv"),
                "counts": {"train": len(tr), "val": len(va), "test": len(te)},
            }
        )
    else:
        ts = 0.2 if test_size is None else float(test_size)
        if stratify_col:
            if stratify_col not in df.columns:
                typer.echo(f"error: stratify_col '{stratify_col}' not found")
                raise typer.Exit(code=2)
            if group_col and group_col not in df.columns:
                typer.echo(f"error: group_col '{group_col}' not found")
                raise typer.Exit(code=2)
            tr, te = _stts(
                records,
                label_key=str(stratify_col),
                test_size=ts,
                seed=seed,
                group_key=str(group_col) if group_col else None,
                group_balance=group_balance,
                min_per_label=min_per_label,
            )
        else:
            tr, te = _tts(records, test_size=ts, seed=seed)
        if not dry_run:
            pd.DataFrame(tr).to_csv(outdir / "train.csv", index=False)
            pd.DataFrame(te).to_csv(outdir / "test.csv", index=False)
        summary.update(
            {
                "train": str(outdir / "train.csv"),
                "test": str(outdir / "test.csv"),
                "counts": {"train": len(tr), "test": len(te)},
            }
        )
    # Always emit JSON for deterministic CLI consumption
    typer.echo(_json.dumps(summary, ensure_ascii=False, indent=2))


@adapters_eval_app.command("run")
def adapters_eval_run(
    csv: Path = typer.Option(..., "--csv", help="CSV path containing labels"),
    truth_col: str = typer.Option(..., "--truth-col", help="Column for ground truth"),
    pred_col: str = typer.Option(..., "--pred-col", help="Column for predictions"),
    metric: str = typer.Option(
        ...,
        "--metric",
        help="accuracy|f1|confusion|roc_auc|roc_curve|rouge1_f1|bleu1|bertscore_f1|per_class_pr|pr_curve|ece",
    ),
    positive_label: Optional[str] = typer.Option(
        None, "--positive-label", help="Label considered positive for F1"
    ),
    average: str = typer.Option(
        "micro", "--average", help="Averaging for text metrics (micro|macro)"
    ),
    outdir: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Directory to export CSVs for supported metrics (pr_curve, roc_curve, per_class_pr)",
    ),
    json_out: bool = typer.Option(True, "--json", help="Output JSON"),
) -> None:
    import json as _json
    import pandas as pd
    from dspx.adapters.eval import (
        accuracy,
        f1_binary,
        confusion_matrix_binary,
        rouge1_f1,
        bleu1,
        rouge1_f1_macro,
        bleu1_macro,
        roc_auc_binary,
        roc_curve_binary,
        precision_recall_per_class,
        pr_curve_binary,
        expected_calibration_error_binary,
        bertscore_f1,
        bertscore_f1_macro,
    )

    df = pd.read_csv(str(csv))
    if truth_col not in df.columns or pred_col not in df.columns:
        raise typer.Exit(code=2)
    y_true = df[truth_col].tolist()
    y_pred = df[pred_col].tolist()

    # Normalize booleans from common textual forms
    def _parse_bool(x: object) -> object:
        if isinstance(x, bool):
            return x
        s = str(x).strip().lower()
        if s in {"true", "1", "yes"}:
            return True
        if s in {"false", "0", "no"}:
            return False
        return x

    y_true = [_parse_bool(v) for v in y_true]
    y_pred = [_parse_bool(v) for v in y_pred]
    m = metric.strip().lower()
    if m == "accuracy":
        val = accuracy(y_true, y_pred)
    elif m == "f1":
        val = f1_binary(y_true, y_pred, positive_label=positive_label)
    elif m == "confusion":
        cm = confusion_matrix_binary(y_true, y_pred, positive_label=positive_label)
        out = {"metric": m, **cm}
        if json_out:
            typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"tp={cm['tp']} tn={cm['tn']} fp={cm['fp']} fn={cm['fn']}")
        return
    elif m == "roc_auc":
        try:
            val = roc_auc_binary(y_true, y_pred, positive_label=positive_label)
        except Exception:
            # Try converting predictions to floats
            try:
                scores = [float(cast(Any, v)) for v in y_pred]
            except Exception:
                raise typer.Exit(code=2)
            val = roc_auc_binary(y_true, scores, positive_label=positive_label)
    elif m == "rouge1_f1":
        refs = [str(v) for v in y_true]
        cands = [str(v) for v in y_pred]
        avg = (average or "micro").strip().lower()
        val = rouge1_f1(refs, cands) if avg == "micro" else rouge1_f1_macro(refs, cands)
    elif m == "bleu1":
        refs = [str(v) for v in y_true]
        cands = [str(v) for v in y_pred]
        avg = (average or "micro").strip().lower()
        val = bleu1(refs, cands) if avg == "micro" else bleu1_macro(refs, cands)
    elif m == "per_class_pr":
        per = precision_recall_per_class(y_true, y_pred)
        out = {"metric": m, "classes": per}
        if out and out is not None:
            if out is not None:
                pass
        # Export CSV when requested
        if outdir:
            try:
                outdir.mkdir(parents=True, exist_ok=True)
                import csv

                with open(
                    outdir / "per_class_pr.csv", "w", encoding="utf-8", newline=""
                ) as f:
                    w = csv.writer(f)
                    w.writerow(["class", "precision", "recall", "support"])
                    for k, v in per.items():
                        w.writerow(
                            [
                                k,
                                v.get("precision", 0.0),
                                v.get("recall", 0.0),
                                v.get("support", 0.0),
                            ]
                        )
            except Exception:
                pass
        if json_out:
            typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))
        else:
            for k, v in per.items():
                typer.echo(
                    f"{k}: precision={v['precision']:.4f} recall={v['recall']:.4f}"
                )
        return
    elif m == "bertscore_f1":
        refs = [str(v) for v in y_true]
        cands = [str(v) for v in y_pred]
        avg = (average or "micro").strip().lower()
        # Optional configuration via envs
        model = os.getenv("DSPX_BERTSCORE_MODEL")
        lang = os.getenv("DSPX_BERTSCORE_LANG", "en")
        rescale = os.getenv("DSPX_BERTSCORE_RESCALE", "").lower() in {
            "1",
            "true",
            "yes",
        }
        try:
            val = (
                bertscore_f1(
                    refs, cands, model=model, lang=lang, rescale_with_baseline=rescale
                )
                if avg == "micro"
                else bertscore_f1_macro(
                    refs, cands, model=model, lang=lang, rescale_with_baseline=rescale
                )
            )
        except ImportError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=2)
    elif m == "pr_curve":
        try:
            scores = [float(cast(Any, v)) for v in y_pred]
        except Exception:
            raise typer.Exit(code=2)
        curve = pr_curve_binary(y_true, scores, positive_label=positive_label)
        if outdir:
            try:
                outdir.mkdir(parents=True, exist_ok=True)
                import csv

                with open(
                    outdir / "pr_curve.csv", "w", encoding="utf-8", newline=""
                ) as f:
                    w = csv.writer(f)
                    w.writerow(["threshold", "precision", "recall"])
                    for t, p, r in zip(
                        curve["thresholds"], curve["precision"], curve["recall"]
                    ):
                        w.writerow([t, p, r])
            except Exception:
                pass
        out = {"metric": m, **curve}
        if json_out:
            typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"points={len(curve['thresholds'])}")
        return
    elif m == "roc_curve":
        try:
            scores = [float(cast(Any, v)) for v in y_pred]
        except Exception:
            raise typer.Exit(code=2)
        curve = roc_curve_binary(y_true, scores, positive_label=positive_label)
        if outdir:
            try:
                outdir.mkdir(parents=True, exist_ok=True)
                import csv

                with open(
                    outdir / "roc_curve.csv", "w", encoding="utf-8", newline=""
                ) as f:
                    w = csv.writer(f)
                    w.writerow(["threshold", "tpr", "fpr"])
                    for t, tp, fp in zip(
                        curve["thresholds"], curve["tpr"], curve["fpr"]
                    ):
                        w.writerow([t, tp, fp])
            except Exception:
                pass
        out = {"metric": m, **curve}
        if json_out:
            typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"points={len(curve['thresholds'])}")
        return
    elif m == "ece":
        try:
            scores = [float(cast(Any, v)) for v in y_pred]
        except Exception:
            raise typer.Exit(code=2)
        val = expected_calibration_error_binary(
            y_true, scores, positive_label=positive_label
        )
        out = {"metric": m, "value": float(val)}
        if json_out:
            typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"ece: {val:.6f}")
        return
    else:
        raise typer.Exit(code=2)
    out = {"metric": m, "value": float(val)}
    if json_out:
        typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"{m}: {val:.6f}")


@adapters_eval_app.command("run2")
def adapters_eval_run2(
    csv_true: Path = typer.Option(..., "--csv-true", help="CSV with ground truth"),
    csv_pred: Path = typer.Option(..., "--csv-pred", help="CSV with predictions"),
    id_col: str = typer.Option("id", "--id-col", help="Join key column"),
    truth_col: str = typer.Option("y", "--truth-col", help="Truth column in csv_true"),
    pred_col: str = typer.Option("yhat", "--pred-col", help="Pred column in csv_pred"),
    metric: str = typer.Option(
        ...,
        "--metric",
        help="accuracy|f1|confusion|roc_auc|roc_curve|rouge1_f1|bleu1|bertscore_f1|per_class_pr|pr_curve",
    ),
    positive_label: Optional[str] = typer.Option(
        None, "--positive-label", help="Label considered positive for F1/confusion"
    ),
    average: str = typer.Option(
        "micro", "--average", help="Averaging for text metrics (micro|macro)"
    ),
    outdir: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Directory to export CSVs for supported metrics (pr_curve, roc_curve, per_class_pr)",
    ),
    json_out: bool = typer.Option(True, "--json", help="Output JSON"),
) -> None:
    import json as _json
    import pandas as pd
    from dspx.adapters.eval import (
        accuracy,
        f1_binary,
        confusion_matrix_binary,
        rouge1_f1,
        bleu1,
        rouge1_f1_macro,
        bleu1_macro,
        roc_auc_binary,
        precision_recall_per_class,
        pr_curve_binary,
        roc_curve_binary,
        bertscore_f1,
        bertscore_f1_macro,
    )

    df_t = pd.read_csv(str(csv_true))[[id_col, truth_col]]
    df_p = pd.read_csv(str(csv_pred))[[id_col, pred_col]]
    merged = pd.merge(df_t, df_p, on=id_col, how="inner", suffixes=("_t", "_p"))
    y_true = merged[truth_col].tolist()
    y_pred = merged[pred_col].tolist()
    m = metric.strip().lower()
    if m == "accuracy":
        val = accuracy(y_true, y_pred)
        out = {"metric": m, "value": float(val), "count": int(len(merged))}
    elif m == "f1":
        val = f1_binary(y_true, y_pred, positive_label=positive_label)
        out = {"metric": m, "value": float(val), "count": int(len(merged))}
    elif m == "confusion":
        cm = confusion_matrix_binary(y_true, y_pred, positive_label=positive_label)
        out = {"metric": m, **cm, "count": int(len(merged))}
    elif m == "roc_auc":
        try:
            val = roc_auc_binary(y_true, y_pred, positive_label=positive_label)
        except Exception:
            try:
                scores = [float(v) for v in y_pred]
            except Exception:
                raise typer.Exit(code=2)
            val = roc_auc_binary(y_true, scores, positive_label=positive_label)
        out = {"metric": m, "value": float(val), "count": int(len(merged))}
    elif m == "rouge1_f1":
        refs = [str(v) for v in y_true]
        cands = [str(v) for v in y_pred]
        avg = (average or "micro").strip().lower()
        val = rouge1_f1(refs, cands) if avg == "micro" else rouge1_f1_macro(refs, cands)
        out = {
            "metric": m,
            "value": float(val),
            "count": int(len(merged)),
            "average": avg,
        }
    elif m == "bleu1":
        refs = [str(v) for v in y_true]
        cands = [str(v) for v in y_pred]
        avg = (average or "micro").strip().lower()
        val = bleu1(refs, cands) if avg == "micro" else bleu1_macro(refs, cands)
        out = {
            "metric": m,
            "value": float(val),
            "count": int(len(merged)),
            "average": avg,
        }
    elif m == "bertscore_f1":
        refs = [str(v) for v in y_true]
        cands = [str(v) for v in y_pred]
        avg = (average or "micro").strip().lower()
        model = os.getenv("DSPX_BERTSCORE_MODEL")
        lang = os.getenv("DSPX_BERTSCORE_LANG", "en")
        rescale = os.getenv("DSPX_BERTSCORE_RESCALE", "").lower() in {
            "1",
            "true",
            "yes",
        }
        try:
            val = (
                bertscore_f1(
                    refs, cands, model=model, lang=lang, rescale_with_baseline=rescale
                )
                if avg == "micro"
                else bertscore_f1_macro(
                    refs, cands, model=model, lang=lang, rescale_with_baseline=rescale
                )
            )
        except ImportError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=2)
        out = {
            "metric": m,
            "value": float(val),
            "count": int(len(merged)),
            "average": avg,
        }
    elif m == "per_class_pr":
        per = precision_recall_per_class(y_true, y_pred)
        out = {"metric": m, "classes": per, "count": int(len(merged))}
        if outdir:
            try:
                outdir.mkdir(parents=True, exist_ok=True)
                import csv

                with open(
                    outdir / "per_class_pr.csv", "w", encoding="utf-8", newline=""
                ) as f:
                    w = csv.writer(f)
                    w.writerow(["class", "precision", "recall", "support"])
                    for k, v in per.items():
                        w.writerow(
                            [
                                k,
                                v.get("precision", 0.0),
                                v.get("recall", 0.0),
                                v.get("support", 0.0),
                            ]
                        )
            except Exception:
                pass
    elif m == "pr_curve":
        try:
            scores = [float(v) for v in y_pred]
        except Exception:
            raise typer.Exit(code=2)
        curve = pr_curve_binary(y_true, scores, positive_label=positive_label)
        if outdir:
            try:
                outdir.mkdir(parents=True, exist_ok=True)
                import csv

                with open(
                    outdir / "pr_curve.csv", "w", encoding="utf-8", newline=""
                ) as f:
                    w = csv.writer(f)
                    w.writerow(["threshold", "precision", "recall"])
                    for t, p, r in zip(
                        curve["thresholds"], curve["precision"], curve["recall"]
                    ):
                        w.writerow([t, p, r])
            except Exception:
                pass
        out = {"metric": m, **curve, "count": int(len(merged))}
    elif m == "roc_curve":
        try:
            scores = [float(v) for v in y_pred]
        except Exception:
            raise typer.Exit(code=2)
        curve = roc_curve_binary(y_true, scores, positive_label=positive_label)
        if outdir:
            try:
                outdir.mkdir(parents=True, exist_ok=True)
                import csv

                with open(
                    outdir / "roc_curve.csv", "w", encoding="utf-8", newline=""
                ) as f:
                    w = csv.writer(f)
                    w.writerow(["threshold", "tpr", "fpr"])
                    for t, tp, fp in zip(
                        curve["thresholds"], curve["tpr"], curve["fpr"]
                    ):
                        w.writerow([t, tp, fp])
            except Exception:
                pass
        out = {"metric": m, **curve, "count": int(len(merged))}
    else:
        raise typer.Exit(code=2)
    if json_out:
        typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if "value" in out:
            typer.echo(f"{m}: {out['value']:.6f} (n={out['count']})")
        else:
            typer.echo(
                f"tp={out['tp']} tn={out['tn']} fp={out['fp']} fn={out['fn']} (n={out['count']})"
            )


# --- Cache CLI ---


@cache_app.command("info")
def cache_info_cmd() -> None:
    from dspx.cache import cache_dir, cache_enabled

    p = cache_dir()
    enabled = cache_enabled()
    total = 0
    count = 0
    per_kind: dict[str, dict[str, int]] = {}
    now = __import__("time").time()
    oldest = None
    newest = None
    if p.exists():
        for f in p.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                    count += 1
                    # per-kind (top-level dir)
                    try:
                        kind = f.relative_to(p).parts[0]
                    except Exception:
                        kind = "_root"
                    d = per_kind.setdefault(kind, {"size": 0, "files": 0})
                    d["size"] += f.stat().st_size
                    d["files"] += 1
                    mt = f.stat().st_mtime
                    if oldest is None or mt < oldest:
                        oldest = mt
                    if newest is None or mt > newest:
                        newest = mt
                except Exception:
                    pass
    typer.echo(f"dir: {p}")
    typer.echo(f"enabled: {str(enabled).lower()}")
    typer.echo(f"files: {count}")
    typer.echo(f"size_bytes: {total}")
    if oldest is not None and newest is not None:
        typer.echo(f"age_oldest_seconds: {int(now - oldest)}")
        typer.echo(f"age_newest_seconds: {int(now - newest)}")
    # per-kind breakdown
    for k in sorted(per_kind.keys()):
        d = per_kind[k]
        typer.echo(f"kind.{k}.files: {d['files']}")
        typer.echo(f"kind.{k}.size_bytes: {d['size']}")


@cache_app.command("list")
def cache_list(
    kind: Optional[str] = typer.Option(None, help="Cache kind to filter"),
) -> None:
    from dspx.cache import cache_dir

    base = cache_dir()
    kinds = [kind] if kind else []
    if not kinds:
        # List subdirs under cache dir
        if base.exists():
            for d in sorted([p for p in base.iterdir() if p.is_dir()]):
                kinds.append(d.name)
    for k in kinds:
        d = base / k
        if not d.exists() or not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            key = f.stem
            typer.echo(f"{k}:{key} -> {f}")


@cache_app.command("show")
def cache_show(
    kind: str = typer.Option(
        ..., "--kind", "-k", help="Cache kind (signature/module/...)"
    ),
    key: str = typer.Option(..., "--key", help="Cache key (sha256 hex)"),
) -> None:
    import json as _json
    from dspx.cache import cache_dir

    f = cache_dir() / kind / f"{key}.json"
    if not f.exists():
        raise typer.Exit(code=2)
    try:
        typer.echo(
            _json.dumps(
                _json.loads(f.read_text(encoding="utf-8")), ensure_ascii=False, indent=2
            )
        )
    except Exception:
        typer.echo(f.read_text(encoding="utf-8"))


@cache_app.command("clear")
def cache_clear(
    kind: Optional[str] = typer.Option(
        None, "--kind", "-k", help="Cache kind to clear"
    ),
    key: Optional[str] = typer.Option(
        None, "--key", help="Specific cache key to remove"
    ),
    all_: bool = typer.Option(False, "--all", help="Clear entire cache directory"),
) -> None:
    from dspx.cache import cache_dir

    base = cache_dir()
    if all_:
        # Remove all files under cache dir
        if base.exists():
            for f in base.rglob("*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass
        typer.echo("cleared: all")
        return
    if key and not kind:
        typer.echo("error: --key requires --kind", err=True)
        raise typer.Exit(code=2)
    if kind and key:
        f = base / kind / f"{key}.json"
        if f.exists():
            try:
                f.unlink()
                typer.echo(f"cleared: {kind}:{key}")
                return
            except Exception:
                pass
        raise typer.Exit(code=2)
    if kind and not key:
        d = base / kind
        if d.exists():
            for f in d.glob("*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass
        typer.echo(f"cleared: {kind}")
        return
    raise typer.Exit(code=2)


@cache_app.command("prune")
def cache_prune(
    kind: Optional[str] = typer.Option(None, help="Cache kind to prune"),
    max_size_mb: Optional[float] = typer.Option(
        None, help="Reduce total cache size to at most this many MB"
    ),
    older_than_days: Optional[float] = typer.Option(
        None, help="Delete entries older than this many days"
    ),
    dry_run: bool = typer.Option(False, help="Only print what would be deleted"),
) -> None:
    """Prune cache by age and/or target size (oldest first)."""
    from dspx.cache import cache_dir
    import time

    base = cache_dir()
    targets: list[tuple[float, int, str]] = []  # (mtime, size, path)
    now = time.time()
    if not base.exists():
        typer.echo("no cache")
        return
    root = base if not kind else base / kind
    for f in root.rglob("*.json"):
        try:
            st = f.stat()
            targets.append((st.st_mtime, st.st_size, str(f)))
        except Exception:
            pass
    # Age prune
    removed = 0
    saved = 0
    keep: set[str] = set()
    if older_than_days is not None:
        cutoff = now - older_than_days * 86400.0
        for mt, sz, path in list(targets):
            if mt < cutoff:
                if not dry_run:
                    try:
                        __import__("pathlib").Path(path).unlink()
                        removed += 1
                    except Exception:
                        pass
            else:
                keep.add(path)
                saved += sz
    else:
        for _, sz, path in targets:
            keep.add(path)
            saved += sz
    # Size prune
    if max_size_mb is not None and saved > max_size_mb * 1024 * 1024:
        # delete oldest first among kept
        kept_list = sorted([(mt, sz, path) for mt, sz, path in targets if path in keep])
        for mt, sz, path in kept_list:
            if saved <= max_size_mb * 1024 * 1024:
                break
            if not dry_run:
                try:
                    __import__("pathlib").Path(path).unlink()
                    removed += 1
                except Exception:
                    pass
            saved -= sz
    typer.echo(f"pruned: {removed} files; remaining_bytes: {int(saved)}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
