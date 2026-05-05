"""Main dspx CLI entrypoint.

This is a thin orchestrator that wires up command groups from
dspx.cli.commands modules. Command implementations live in their
respective modules for maintainability.

Note: codegen and module-gen are kept inline as single commands.
"""

from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional

import typer

from dspx.cli.utils import (
    ensure_env,
    require_template_adapter,
    check_template_adapter_available,
    _TEMPLATE_ADAPTER_AVAILABLE,
)
from dspx.tracing import enable_mlflow_from_env

# Re-exports for backward compatibility with tests
__all__ = [
    "app",
    "enable_mlflow_from_env",
    "check_template_adapter_available",
    "_TEMPLATE_ADAPTER_AVAILABLE",
]

# Import extracted command apps
from dspx.cli.commands import (
    cache_app,
    run_app,
    optimize_app,
    providers_app,
    program_promote_app,
    program_refine_app,
    oracle_app,
    signature_app,
    mermaid_app,
    openapi_app,
    web_app,
    tools_app,
    adapters_app,
    adapters_dataset_app,
    adapters_eval_app,
)

# Main app
app = typer.Typer(no_args_is_help=True, add_completion=False)

# Register command groups (imported from extracted modules)
app.add_typer(signature_app, name="signature", help="Signature operations")
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
app.add_typer(run_app, name="run", help="Replay/explain operations")
app.add_typer(
    program_refine_app,
    name="program-refine",
    help="Bounded program refinement proposals",
)
app.add_typer(
    program_promote_app,
    name="program-promote",
    help="Local program promotion-review evidence packets",
)
app.add_typer(
    oracle_app, name="oracle", help="Behavioral oracle (semantic coordinates)"
)


# =============================================================================
# Inline Commands (single commands kept inline for simplicity)
# =============================================================================


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
    template_config: Optional[Path] = typer.Option(
        None,
        "--template-config",
        help="YAML config file for TemplateAdapter (requires dspy-template-adapter)",
    ),
) -> None:
    """Generate a DSPy module scaffold from a specification."""
    from dspx.dtos import ModuleSpec
    from dspx.services.module_service import run_generate as module_run_generate
    from dspx.cli.commands.module import (
        _write_module_output,
        _print_module_cache_info,
        validate_module_fields_or_exit,
    )

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
        os.environ["DSPX_BUDGET_MODULE_MS"] = str(int(budget_ms))

    validate_module_fields_or_exit(input, output, name)

    spec = ModuleSpec(
        name=name,
        description=description,
        inputs=input,
        outputs=output,
        options={"template_version": template_version},
    )
    art = module_run_generate(
        spec,
        use_signature=use_signature,
        promotion_target=outfile,
    )

    if outfile:
        _write_module_output(
            outfile=outfile,
            code=art.code,
            name=name,
            description=description,
            inputs=input,
            outputs=output,
            use_signature=use_signature,
            template_version=template_version,
            artifact_metadata=art.metadata,
        )
        typer.echo(str(outfile))
    else:
        sys.stdout.write(art.code)
        if cache_info:
            _print_module_cache_info(
                name, description, input, output, use_signature, template_version
            )


def _as_root_relative_file(root: Path, value: object) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    candidate = path if path.is_absolute() else root / path
    try:
        resolved = candidate.resolve()
        root_resolved = root.resolve()
        if not resolved.is_relative_to(root_resolved):
            return None
        if not resolved.is_file():
            return None
        return resolved.relative_to(root_resolved)
    except Exception:
        return None


def _collect_program_manifest_paths(value: object) -> list[object]:
    paths: list[object] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"path", "entrypoint", "harness", "result"}:
                paths.append(item)
            paths.extend(_collect_program_manifest_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.extend(_collect_program_manifest_paths(item))
    return paths


def _declared_program_artifact_files(
    *,
    root: Path,
    artifact: Any,
    manifest: dict[str, Any],
) -> list[Path]:
    candidates: list[object] = ["manifest.json", "manifest.json.meta.json"]
    candidates.extend(_collect_program_manifest_paths(manifest))
    files = getattr(artifact, "files", {}) or {}
    if isinstance(files, dict):
        candidates.extend(files.keys())
        candidates.extend(files.values())

    out: list[Path] = []
    seen: set[str] = set()
    for value in candidates:
        rel = _as_root_relative_file(root, value)
        if rel is None:
            continue
        key = rel.as_posix()
        if key in seen:
            continue
        seen.add(key)
        out.append(rel)
    return out


def _log_declared_program_artifacts(
    mlflow: Any, *, root: Path, files: list[Path]
) -> None:
    with tempfile.TemporaryDirectory(prefix="dspx-program-mlflow-") as tmp:
        staging = Path(tmp)
        for rel in files:
            source = root / rel
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        mlflow.log_artifacts(str(staging))


def _log_program_artifact_to_mlflow(artifact: Any) -> None:
    """Best-effort MLflow logging for materialized program-gen assemblies."""
    try:
        from dspx.cache import sha256_text
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        mlflow = get_mlflow()
        if mlflow is None:
            return

        root = Path(str(getattr(artifact, "root_path", "") or ""))
        if not root.exists() or not root.is_dir():
            return

        manifest_path = root / "manifest.json"
        manifest: dict[str, Any] = {}
        if manifest_path.exists() and manifest_path.is_file():
            try:
                loaded_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(loaded_manifest, dict):
                    manifest = loaded_manifest
            except Exception:
                manifest = {}
        receipt_path = Path(str(getattr(artifact, "receipt_path", "") or ""))
        receipt: dict[str, Any] = {}
        if receipt_path.exists() and receipt_path.is_file():
            try:
                loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    receipt = loaded
            except Exception:
                receipt = {}

        declared_files = _declared_program_artifact_files(
            root=root,
            artifact=artifact,
            manifest=manifest,
        )
        metadata = dict(getattr(artifact, "metadata", {}) or {})
        template_version = str(
            receipt.get("template_version") or "program-candidate-assembly-v1"
        )
        cache_key = str(
            receipt.get("cache_key") or metadata.get("request_id") or manifest_path
        )
        if receipt.get("output_hash"):
            output_hash = str(receipt["output_hash"])
        elif manifest_path.exists():
            output_hash = sha256_text(manifest_path.read_text(encoding="utf-8"))
        else:
            output_hash = ""

        started_run = ensure_run_with_standard_tags(
            "program",
            template_version=template_version,
            run_name="program-gen",
            run_kind="program-gen",
            output_basename=manifest_path.name,
            cache_key=cache_key,
            output_hash=output_hash,
            extra={
                "program.name": str(getattr(artifact, "name", "") or ""),
                "program.assembly_id": str(metadata.get("assembly_id") or ""),
                "program.episode_id": str(metadata.get("episode_id") or ""),
            },
        )

        try:
            if mlflow.active_run() is not None:
                try:
                    mlflow.log_param(
                        "program.generated_file_count",
                        str(len(declared_files)),
                    )
                except Exception:
                    pass
                try:
                    _log_declared_program_artifacts(
                        mlflow,
                        root=root,
                        files=declared_files,
                    )
                except Exception:
                    pass
        finally:
            if started_run:
                try:
                    mlflow.end_run()
                except Exception:
                    pass
    except Exception:
        return


@app.command("program-gen")
def program_gen(
    intent: Path = typer.Option(
        ...,
        "--intent",
        "-i",
        help="Path to a JSON/YAML one-intent program specification",
    ),
    outdir: Optional[Path] = typer.Option(
        None,
        "--outdir",
        "-o",
        help="Directory where the program candidate assembly is materialized",
    ),
    print_manifest: bool = typer.Option(
        False,
        "--print-manifest",
        help="Print the generated manifest JSON instead of only the output directory",
    ),
) -> None:
    """Generate a program-shaped DSPy candidate assembly from one intent."""
    from dspx.services.program_service import run_generate_from_intent_path

    if not intent.exists():
        typer.echo(f"Error: intent file not found: {intent}", err=True)
        raise typer.Exit(code=2)

    ensure_env(None)

    try:
        artifact = run_generate_from_intent_path(intent, outdir=outdir)
    except Exception as exc:
        typer.echo(f"Error: program intent generation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    _log_program_artifact_to_mlflow(artifact)

    if print_manifest:
        typer.echo(json.dumps(artifact.manifest, indent=2, sort_keys=True))
    else:
        typer.echo(artifact.root_path)


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
    from dspx.cli.commands.codegen import (
        _write_codegen_output,
        _print_codegen_cache_info,
    )

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


# =============================================================================
# Policy Callback (OpenRouter key injection, policy env setup)
# =============================================================================


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
    """Global callback for policy and API key setup."""
    # OpenRouter API key injection (avoid leaking secrets via CLI args).
    if os.getenv("OPENROUTER_API_KEY") is None:
        try:
            if openrouter_api_key_file is not None:
                os.environ["OPENROUTER_API_KEY"] = openrouter_api_key_file.read_text(
                    encoding="utf-8"
                ).strip()
            elif openrouter_api_key_op:
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


def main() -> None:
    """Main entrypoint for dspx CLI."""
    app()


if __name__ == "__main__":
    main()
