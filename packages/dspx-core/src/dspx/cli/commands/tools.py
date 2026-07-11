# summary: "Defines CLI commands to list, describe, search, preview, confirm, and execute registered tools."
# read_when:
#   - "Changing tool invocation shapes, parameter parsing, mutation confirmation, previews, or tool discovery."

"""Tool inspection and execution commands.

Commands for listing, describing, searching, and running tools.
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Any, Optional

import typer

app = typer.Typer(no_args_is_help=True)


def _invoke_registered_tool(
    fn: Any, *, pmap: dict[str, Any], body: Any, is_openapi: bool
) -> Any:
    """Invoke a registered tool using the descriptor-appropriate calling shape."""
    if is_openapi:
        return fn(params=pmap or None, body=body)

    try:
        signature = inspect.signature(fn)
        parameters = signature.parameters
    except (TypeError, ValueError):
        parameters = {}

    has_var_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values()
    )
    accepts_payload_shape = "params" in parameters or "body" in parameters
    accepts_native_kwargs = has_var_kwargs or any(key in parameters for key in pmap)

    if accepts_native_kwargs and not accepts_payload_shape:
        if body is not None and not has_var_kwargs and "body" not in parameters:
            raise typer.BadParameter("--body-json is not supported by this tool")
        kwargs = dict(pmap)
        if body is not None and (has_var_kwargs or "body" in parameters):
            kwargs["body"] = body
        return fn(**kwargs)

    if accepts_payload_shape:
        kwargs: dict[str, Any] = {}
        if "params" in parameters or has_var_kwargs:
            kwargs["params"] = pmap or None
        if "body" in parameters or has_var_kwargs:
            kwargs["body"] = body
        return fn(**kwargs)

    return fn(**pmap)


@app.command("list")
def tools_list(
    json_out: bool = typer.Option(False, "--json", help="Output JSON with metadata"),
) -> None:
    """List all available tools."""
    from dspx.tools.registry import ensure_default_tools, available_descriptors
    from dspx.ui.renderers import tool_descriptor_to_json, tool_descriptor_to_list_text

    ensure_default_tools()
    descs = available_descriptors()

    if json_out:
        items = [tool_descriptor_to_json(d) for d in descs]
        typer.echo(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        for d in descs:
            typer.echo(tool_descriptor_to_list_text(d))


@app.command("describe")
def tools_describe(
    name: str = typer.Argument(..., help="Tool name"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON details"),
    examples: bool = typer.Option(
        False, "--examples", help="Include usage examples/hints"
    ),
) -> None:
    """Describe a tool in detail."""
    from dspx.tools.registry import ensure_default_tools, get_descriptor, get_tool
    from dspx.ui.renderers import (
        tool_descriptor_to_json,
        tool_descriptor_describe_text,
    )

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
                from urllib.parse import urlparse

                u = urlparse(str(desc.openapi.server or ""))
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
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(
            tool_descriptor_describe_text(desc, examples=ex if examples else None)
        )


@app.command("run")
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
    """Run a tool with the given parameters."""
    from dspx.tools.registry import ensure_default_tools, get_tool, get_descriptor
    from dspx.ui.confirmations import build_preview, needs_confirmation

    ensure_default_tools()
    fn = get_tool(name)

    pmap = {}
    if params:
        pmap = None
        try:
            is_openapi_for_parse = bool(getattr(fn, "_dspx_is_openapi_tool", False))
        except Exception:
            is_openapi_for_parse = False
        if is_openapi_for_parse:
            try:
                desc_for_parse = get_descriptor(name)
            except Exception:
                desc_for_parse = None
            if desc_for_parse is not None and getattr(desc_for_parse, "openapi", None):
                from dspx.cli.commands.openapi import _coerce_cli_params

                pmap = _coerce_cli_params(params, desc_for_parse.openapi)
        if pmap is None:
            pmap = {}
            for part in params.split(","):
                if not part.strip() or "=" not in part:
                    continue
                k, v = part.split("=", 1)
                pmap[k.strip()] = v.strip()

    body = None
    if body_json:
        body = json.loads(body_json.read_text(encoding="utf-8"))

    # Destructive-op confirmation for OpenAPI tools
    try:
        is_openapi = bool(getattr(fn, "_dspx_is_openapi_tool", False))
    except Exception:
        is_openapi = False
    openapi_method = str(getattr(fn, "_dspx_openapi_method", "") or "").upper()
    openapi_confirmed_mutation = (
        is_openapi and yes and openapi_method in {"POST", "PUT", "PATCH", "DELETE"}
    )

    if is_openapi:
        try:
            desc = get_descriptor(name)
        except Exception:
            desc = None

        if dry_run:
            if desc is None:
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
            need = needs_confirmation(desc)
            opi = getattr(desc, "openapi", None)
            if not need and getattr(desc, "kind", "") == "openapi" and opi is not None:
                try:
                    m = str(getattr(opi, "method", "") or "").upper()
                    openapi_method = m or openapi_method
                    need = m in {"POST", "PUT", "PATCH", "DELETE"}
                except Exception:
                    need = False
            if yes and openapi_method in {"POST", "PUT", "PATCH", "DELETE"}:
                openapi_confirmed_mutation = True
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
                openapi_confirmed_mutation = True
        else:
            # Fallback to method-based prompt
            try:
                method_eff = str(getattr(fn, "_dspx_openapi_method", "GET")).upper()
            except Exception:
                method_eff = "GET"
            openapi_method = method_eff or openapi_method
            from dspx.policy import (
                bypass as _p_bypass,
                allow_network_mutate as _p_allow,
            )

            if yes and method_eff in {"POST", "PUT", "PATCH", "DELETE"}:
                openapi_confirmed_mutation = True
            if (
                method_eff in {"POST", "PUT", "PATCH", "DELETE"}
                and not _p_bypass()
                and not _p_allow()
                and not yes
            ):
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
                openapi_confirmed_mutation = True

    # Generic capability-based confirmation for other tools
    if dry_run and not is_openapi:
        try:
            desc = get_descriptor(name)
        except Exception:
            desc = None

        if desc is not None:
            payload = {
                "tool": desc.name,
                "capabilities": desc.capabilities,
                "params": pmap or {},
                "body": body or None,
            }
        else:
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
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not is_openapi:
        try:
            desc = get_descriptor(name)
        except Exception:
            desc = None
        if desc is not None:
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

    old_allow_mutate = os.environ.get("DSPX_POLICY_ALLOW_NETWORK_MUTATE")
    injected_allow_mutate = False
    if openapi_confirmed_mutation:
        os.environ["DSPX_POLICY_ALLOW_NETWORK_MUTATE"] = "1"
        injected_allow_mutate = True
    try:
        out = _invoke_registered_tool(fn, pmap=pmap, body=body, is_openapi=is_openapi)
    finally:
        if injected_allow_mutate and old_allow_mutate is None:
            os.environ.pop("DSPX_POLICY_ALLOW_NETWORK_MUTATE", None)
        elif old_allow_mutate is not None:
            os.environ["DSPX_POLICY_ALLOW_NETWORK_MUTATE"] = old_allow_mutate
    try:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
    except Exception:
        typer.echo(str(out))


@app.command("search")
def tools_search(
    query: str = typer.Argument(..., help="Query string to match name/description"),
    tags: Optional[str] = typer.Option(
        None, "--tags", help="Comma-separated tag filters"
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON with metadata"),
) -> None:
    """Search for tools by name, description, or tags."""
    from dspx.tools.registry import ensure_default_tools, available_descriptors
    from dspx.ui.renderers import tool_descriptor_to_json, tool_descriptor_to_list_text

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
        typer.echo(json.dumps(items, ensure_ascii=False, indent=2))
