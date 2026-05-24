"""OpenAPI tool commands.

Commands for loading, inspecting, and calling OpenAPI operations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

import typer

from dspx.cli.utils import ensure_env

app = typer.Typer(no_args_is_help=True)


def _coerce_cli_bool(value: Any) -> bool:
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"expected boolean, got {value!r}")


def _coerce_cli_value(value: Any, schema: Mapping[str, Any] | None) -> Any:
    if not isinstance(schema, Mapping):
        return value
    schema_type = schema.get("type")
    if schema_type == "array":
        items_schema = (
            schema.get("items") if isinstance(schema.get("items"), Mapping) else None
        )
        if isinstance(value, list):
            raw_items = value
        else:
            raw_items = [item.strip() for item in str(value).split(",") if item.strip()]
        return [_coerce_cli_value(item, items_schema) for item in raw_items]
    if schema_type == "integer":
        return int(str(value).strip())
    if schema_type == "number":
        return float(str(value).strip())
    if schema_type == "boolean":
        return _coerce_cli_bool(value)
    return value


def _parse_cli_param_pairs(raw: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    current_key: str | None = None
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            current_key = key.strip()
            if current_key:
                parsed[current_key] = value.strip()
            continue
        if current_key is not None:
            parsed[current_key] = f"{parsed[current_key]},{token}"
    return parsed


def _coerce_cli_params(
    raw: Optional[str],
    operation: Any,
) -> dict[str, Any]:
    if not raw:
        return {}

    text = raw.strip()
    if not text:
        return {}

    if text.startswith("{"):
        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise typer.BadParameter("--params JSON must decode to an object")
        base_params: dict[str, Any] = dict(loaded)
    else:
        base_params = _parse_cli_param_pairs(text)

    schemas: dict[str, Mapping[str, Any]] = {}
    parameters = getattr(operation, "parameters", None) or []
    for param in parameters:
        if not isinstance(param, dict):
            continue
        name = str(param.get("name") or "").strip()
        schema = param.get("schema")
        if name and isinstance(schema, Mapping):
            schemas[name] = schema

    coerced: dict[str, Any] = {}
    for key, value in base_params.items():
        try:
            coerced[key] = _coerce_cli_value(value, schemas.get(key))
        except (TypeError, ValueError) as exc:
            raise typer.BadParameter(
                f"invalid --params value for {key}: {exc}"
            ) from exc
    return coerced


@app.command("ops")
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
    """List operations from an OpenAPI spec."""
    from dspx.tools.openapi import load_spec
    from dspx.tools.openapi.loader import extract_operation_infos

    ensure_env(None, tracing=False)
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
        typer.echo(json.dumps(items, ensure_ascii=False, indent=2))


@app.command("call")
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
    """Call an OpenAPI operation."""
    from dspx.tools.openapi import load_spec
    from dspx.tools.openapi.loader import extract_operation_infos
    from dspx.dtos import OpenAPICallRequest
    from dspx.tools.descriptors import ToolDescriptor
    from dspx.ui.confirmations import build_preview, needs_confirmation
    from dspx.tools.openapi.caller import call_operation

    ensure_env(None)
    data = load_spec(
        str(spec), allowed_hosts=({allow_host: True} if allow_host else None)
    )
    ops = extract_operation_infos(data)
    if op not in ops:
        raise typer.Exit(code=2)

    pmap = _coerce_cli_params(params, ops[op])

    body_data = None
    if body:
        body_data = json.loads(body.read_text(encoding="utf-8"))

    req = OpenAPICallRequest(
        operation_id=op, params=pmap, body=body_data, timeout=timeout
    )
    allowed = {allow_host: True} if allow_host else {}

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

    # Start an MLflow run for traceability when enabled
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
    typer.echo(res.raw_text or "")


@app.command("describe")
def openapi_describe(
    spec: str = typer.Option(..., "--spec", help="OpenAPI spec path or URL"),
    op: str = typer.Option(..., "--op", help="operationId to describe"),
    allow_host: Optional[str] = typer.Option(None, help="Allowlisted host for URL"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Describe an OpenAPI operation in detail."""
    from dspx.tools.openapi import load_spec
    from dspx.tools.openapi.loader import extract_operation_infos

    ensure_env(None, tracing=False)
    data = load_spec(spec, allowed_hosts=({allow_host: True} if allow_host else None))
    ops = extract_operation_infos(data)
    if op not in ops:
        raise typer.Exit(code=2)

    info = ops[op]

    if json_out:
        from dspx.tools.descriptors import ToolDescriptor
        from dspx.ui.renderers import tool_descriptor_to_json, schema_example

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
        # Best-effort response examples
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
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
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


@app.command("load")
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
    """Persist a mapping file for an OpenAPI spec.

    Writes a JSON file with {"prefix", "spec", "allow_host"} under
    generated/openapi/<prefix>.json by default.
    """
    ensure_env(None, tracing=False)
    base = outdir or Path("generated/openapi")
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{prefix}.json"
    payload = {"prefix": prefix, "spec": str(spec), "allow_host": allow_host}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(str(path))


@app.command("env")
def openapi_env(
    prefix: str = typer.Option(
        ..., "--prefix", "-p", help="Registration prefix (e.g., gh)"
    ),
    map_file: Optional[Path] = typer.Option(
        None, "--map", help="Path to <prefix>.json mapping"
    ),
) -> None:
    """Print shell exports for DSPX_OPENAPI_SPEC_<P> and DSPX_OPENAPI_HOST_<P>."""
    ensure_env(None, tracing=False)
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

    data = json.loads(path.read_text(encoding="utf-8"))
    spec = data.get("spec")
    host = data.get("allow_host")
    u = prefix.upper()
    if spec:
        typer.echo(f"export DSPX_OPENAPI_SPEC_{u}='{spec}'")
    if host:
        typer.echo(f"export DSPX_OPENAPI_HOST_{u}='{host}'")
