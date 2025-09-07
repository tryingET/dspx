from __future__ import annotations

import sys
from pathlib import Path
import os
from typing import List, Optional

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
tools_app = typer.Typer(no_args_is_help=True)
openapi_app = typer.Typer(no_args_is_help=True)
adapters_app = typer.Typer(no_args_is_help=True)
adapters_dataset_app = typer.Typer(no_args_is_help=True)

app.add_typer(sig_app, name="signature", help="Signature operations")
app.add_typer(mermaid_app, name="mermaid", help="Mermaid workflow operations")
app.add_typer(tools_app, name="tools", help="Tools and integrations")
tools_app.add_typer(openapi_app, name="openapi", help="OpenAPI loader/caller")
app.add_typer(adapters_app, name="adapters", help="Adapters (datasets/eval/stores)")
adapters_app.add_typer(adapters_dataset_app, name="dataset", help="Dataset adapters")


def _ensure_env(provider: Optional[str]) -> None:
    if provider:
        import os

        os.environ["DSPX_PROVIDER"] = provider
    load_config_env()
    enable_mlflow_from_env()


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
) -> None:
    _ensure_env(provider)
    if no_cache:
        os.environ["DSPX_CACHE_ENABLE"] = "0"
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
            from dspx.tracing import ensure_run_with_standard_tags
            import mlflow

            ensure_run_with_standard_tags(
                "signature", template_version=template_version
            )
            try:
                mlflow.log_artifact(str(outfile))  # type: ignore[attr-defined]
            except Exception:
                pass
            meta_path = outfile.parent / (outfile.name + ".meta.json")
            if meta_path.exists():
                try:
                    mlflow.log_artifact(str(meta_path))  # type: ignore[attr-defined]
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
) -> None:
    from dspx.services.refine_service import run_refine as _run_refine

    _ensure_env(provider)
    code = _run_refine(
        prompt,
        attempts=attempts,
        non_interactive=non_interactive,
        wrap_script=wrap_script,
        outfile=str(outfile) if outfile else None,
    )
    if not outfile:
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
) -> None:
    _ensure_env(provider)
    if no_cache:
        os.environ["DSPX_CACHE_ENABLE"] = "0"
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
            from dspx.tracing import ensure_run_with_standard_tags
            import mlflow

            ensure_run_with_standard_tags("module", template_version=template_version)
            try:
                mlflow.log_artifact(str(outfile))  # type: ignore[attr-defined]
            except Exception:
                pass
            meta_path = outfile.parent / (outfile.name + ".meta.json")
            if meta_path.exists():
                try:
                    mlflow.log_artifact(str(meta_path))  # type: ignore[attr-defined]
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
) -> None:
    _ensure_env(provider)
    if no_cache:
        os.environ["DSPX_CACHE_ENABLE"] = "0"
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
            from dspx.tracing import ensure_run_with_standard_tags
            import mlflow

            ensure_run_with_standard_tags("codegen", template_version=template_version)
            try:
                mlflow.log_artifact(str(outfile))  # type: ignore[attr-defined]
            except Exception:
                pass
            meta_path = outfile.parent / (outfile.name + ".meta.json")
            if meta_path.exists():
                try:
                    mlflow.log_artifact(str(meta_path))  # type: ignore[attr-defined]
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
) -> None:
    from dspx.tools.openapi import load_spec, extract_operations

    allowed = {allow_host: True} if allow_host else None
    data = load_spec(str(spec), allowed_hosts=allowed)
    ops = extract_operations(data)
    flt = (grep or "").lower()
    mflt = (method or "").strip().upper()
    tagset = None
    if tags:
        tagset = {t.strip().lower() for t in tags.split(",") if t.strip()}
    for k in sorted(ops.keys()):
        if flt:
            path = str(ops[k].get("path", ""))
            if flt not in k.lower() and flt not in path.lower():
                continue
        if mflt and str(ops[k].get("method", "")).upper() != mflt:
            continue
        if tagset:
            op_tags = [str(t).lower() for t in (ops[k].get("tags") or [])]
            if not any(t in op_tags for t in tagset):
                continue
        if paths:
            typer.echo(
                f"{str(ops[k].get('method', '')).upper()} {ops[k].get('path', '')}"
            )
        else:
            typer.echo(k)


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
) -> None:
    import json as _json
    from dspx.tools.openapi import load_spec, extract_operations
    from dspx.dtos import OpenAPICallRequest

    data = load_spec(
        str(spec), allowed_hosts=({allow_host: True} if allow_host else None)
    )
    ops = extract_operations(data)
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

    res = call_operation(req, operation=ops[op], allowed_hosts=allowed)
    # Print raw_text for user-friendly output
    typer.echo(res.raw_text or "")


@openapi_app.command("describe")
def openapi_describe(
    spec: str = typer.Option(..., "--spec", help="OpenAPI spec path or URL"),
    op: str = typer.Option(..., "--op", help="operationId to describe"),
    allow_host: Optional[str] = typer.Option(None, help="Allowlisted host for URL"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    from dspx.tools.openapi import load_spec, extract_operations

    data = load_spec(spec, allowed_hosts=({allow_host: True} if allow_host else None))
    ops = extract_operations(data)
    if op not in ops:
        raise typer.Exit(code=2)
    info = ops[op]
    if json_out:
        import json as _json

        out = {
            "operationId": op,
            "method": str(info.get("method", "")).upper(),
            "path": info.get("path", ""),
            "server": info.get("server") or None,
            "parameters": [],
            "requestBody": None,
            "responses": info.get("responses") or {},
            "tags": info.get("tags") or [],
        }
        params = info.get("parameters") or []
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
        rb = info.get("requestBody")
        if isinstance(rb, dict):
            out["requestBody"] = {
                "required": bool(rb.get("required", False)),
                "schema": rb.get("schema") or None,
            }
        typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))
        return
    # Text output
    typer.echo(f"operationId: {op}")
    typer.echo(f"method: {info.get('method', '').upper()}")
    typer.echo(f"path: {info.get('path', '')}")
    if info.get("server"):
        typer.echo(f"server: {info.get('server')}")
    if info.get("tags"):
        typer.echo("tags:")
        for t in info.get("tags"):
            typer.echo(f"  - {t}")
    params = info.get("parameters") or []
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
    rb = info.get("requestBody")
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
    resps = info.get("responses") or {}
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


@tools_app.command("list")
def tools_list() -> None:
    from dspx.tools.registry import ensure_default_tools, available

    ensure_default_tools()
    for n in available():
        typer.echo(n)


@tools_app.command("run")
def tools_run(
    name: str = typer.Argument(..., help="Tool name"),
    params: Optional[str] = typer.Option(
        None, help="Comma-separated k=v pairs for 'params'"
    ),
    body_json: Optional[Path] = typer.Option(None, help="JSON file for 'body'"),
) -> None:
    import json as _json
    from dspx.tools.registry import ensure_default_tools, get_tool

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
    out = fn(params=pmap or None, body=body)
    # Try to dump nicely if dict-like
    try:
        typer.echo(_json.dumps(out, ensure_ascii=False, indent=2))
    except Exception:
        typer.echo(str(out))


# --- Adapters CLI ---


@adapters_app.command("list")
def adapters_list() -> None:
    # Keep this list in sync with adapters package
    for line in [
        "dataset.csv",
        "dataset.parquet",
        "dataset.mlflow",
        "eval.accuracy",
        "eval.f1_binary",
        "store.local_object",
    ]:
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
            typer.echo("columns: " + ", ".join(out.get("columns") or []))
            typer.echo("rows:")
            for r in out.get("rows", [])[:nrows]:
                typer.echo(str(r))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
