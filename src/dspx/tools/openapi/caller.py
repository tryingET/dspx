from __future__ import annotations

import httpx
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urljoin, urlparse

from dspx.dtos import OpenAPICallRequest, OpenAPICallResult
import time as _time
from dspx.tracing import ensure_run_from_env


def _build_url(server: str, path: str, params: Mapping[str, Any]) -> str:
    """Replace path params like {id} and join with server.

    Query params are not appended here; httpx handles them via params=.
    """
    out_path = path
    for k, v in params.items():
        tok = "{" + str(k) + "}"
        if tok in out_path:
            out_path = out_path.replace(tok, str(v))
    if server:
        base = server if server.endswith("/") else (server + "/")
        joined = urljoin(base, out_path.lstrip("/"))
        return joined
    return out_path


def _host_allowed(url: str, allowed_hosts: Optional[Mapping[str, bool]]) -> bool:
    if not allowed_hosts:
        return True
    host = urlparse(url).hostname or ""
    return bool(allowed_hosts.get(host, False))


def call_operation(
    request: OpenAPICallRequest,
    *,
    operation: Mapping[str, Any],
    allowed_hosts: Optional[Mapping[str, bool]] = None,
    client: Optional[httpx.Client] = None,
) -> OpenAPICallResult:
    """Execute an OpenAPI operation safely with host allowlist.

    - Validates host against `allowed_hosts` mapping (host -> True/False) if provided.
    - Uses path parameter interpolation for URL building.
    - Passes remaining params as query params.
    """
    method = (request.method or operation.get("method") or "GET").upper()
    server = request.server or operation.get("server") or ""
    path = request.path or operation.get("path") or request.operation_id
    params = dict(request.params or {})
    body = request.body or None
    headers = request.headers or {}
    # Validate required path/query parameters and request body schema
    # Validate required path parameters when present in operation description
    try:
        param_specs = operation.get("parameters") or []
        for p in param_specs:
            if not isinstance(p, dict):
                continue
            where = str(p.get("in", "")).lower()
            if where == "path" and bool(p.get("required", False)):
                name = str(p.get("name"))
                if not name:
                    continue
                if name not in params:
                    raise ValueError(f"Missing required path parameter: {name}")
            if where == "query" and bool(p.get("required", False)):
                name = str(p.get("name"))
                if not name:
                    continue
                if name not in params:
                    raise ValueError(f"Missing required query parameter: {name}")
            # Basic type checks for query params
            if where == "query" and "schema" in p and p.get("name") in params:
                schema = p.get("schema") or {}
                t = schema.get("type")
                enum = (
                    schema.get("enum") if isinstance(schema.get("enum"), list) else None
                )
                val = params.get(p.get("name"))
                if enum is not None:
                    if str(val) not in {str(x) for x in enum}:
                        raise ValueError(
                            f"Invalid value for query param {p.get('name')}: must be one of {enum}"
                        )
                if t == "integer":
                    try:
                        int(str(val))
                    except Exception:
                        raise ValueError(
                            f"Invalid type for query param {p.get('name')}: expected integer"
                        )
                elif t == "number":
                    try:
                        float(str(val))
                    except Exception:
                        raise ValueError(
                            f"Invalid type for query param {p.get('name')}: expected number"
                        )
                elif t == "boolean":
                    sval = str(val).lower()
                    if sval not in {"true", "false", "1", "0", "yes", "no"}:
                        raise ValueError(
                            f"Invalid type for query param {p.get('name')}: expected boolean"
                        )
                elif t == "array":
                    items = schema.get("items") or {}
                    itype = items.get("type")
                    # Expect list-like in params (programmatic usage)
                    if not isinstance(val, (list, tuple)):
                        raise ValueError(
                            f"Invalid type for query param {p.get('name')}: expected array/list"
                        )
                    if itype == "integer":
                        for el in val:
                            try:
                                int(str(el))
                            except Exception:
                                raise ValueError(
                                    f"Invalid item type in array param {p.get('name')}: expected integer"
                                )
                    elif itype == "number":
                        for el in val:
                            try:
                                float(str(el))
                            except Exception:
                                raise ValueError(
                                    f"Invalid item type in array param {p.get('name')}: expected number"
                                )
                    elif itype == "boolean":
                        for el in val:
                            if str(el).lower() not in {
                                "true",
                                "false",
                                "1",
                                "0",
                                "yes",
                                "no",
                            }:
                                raise ValueError(
                                    f"Invalid item type in array param {p.get('name')}: expected boolean"
                                )
    except ValueError:
        # Surface validation errors
        raise
    except Exception:
        # Be permissive by default; surface only obvious missing path params
        pass

    # Request body schema validation (application/json)
    try:
        rb = operation.get("requestBody")
        if isinstance(rb, dict):
            required_rb = bool(rb.get("required", False))
            schema = rb.get("schema") or {}
            if required_rb and body is None:
                raise ValueError("Missing required request body")
            if body is not None and isinstance(schema, dict):
                # Only handle simple object schemas with required + properties
                if schema.get("type") == "object":
                    required_props = schema.get("required") or []
                    properties = schema.get("properties") or {}
                    # required fields present
                    for prop in required_props:
                        if prop not in body:
                            raise ValueError(f"Missing required body property: {prop}")
                    # basic type checks
                    for name, ps in properties.items():
                        if name not in body:
                            continue
                        ps = ps or {}
                        t = ps.get("type")
                        val = body.get(name)
                        # enum constraint
                        if isinstance(ps.get("enum"), list) and val is not None:
                            if str(val) not in {str(x) for x in ps["enum"]}:
                                raise ValueError(
                                    f"Invalid value for body property {name}: must be one of {ps['enum']}"
                                )
                        if t == "integer":
                            try:
                                int(val)
                            except Exception:
                                raise ValueError(
                                    f"Invalid type for body property {name}: expected integer"
                                )
                        elif t == "number":
                            try:
                                float(val)
                            except Exception:
                                raise ValueError(
                                    f"Invalid type for body property {name}: expected number"
                                )
                        elif t == "boolean":
                            if not isinstance(val, bool):
                                sval = str(val).lower()
                                if sval not in {"true", "false", "1", "0", "yes", "no"}:
                                    raise ValueError(
                                        f"Invalid type for body property {name}: expected boolean"
                                    )
                        elif t == "string":
                            # allow any value; we'll stringify
                            pass
                        elif t == "array":
                            items = ps.get("items") or {}
                            itype = items.get("type")
                            if not isinstance(val, list):
                                raise ValueError(
                                    f"Invalid type for body property {name}: expected array"
                                )
                            if itype == "integer":
                                for el in val:
                                    try:
                                        int(el)
                                    except Exception:
                                        raise ValueError(
                                            f"Invalid item type in body array {name}: expected integer"
                                        )
                            elif itype == "number":
                                for el in val:
                                    try:
                                        float(el)
                                    except Exception:
                                        raise ValueError(
                                            f"Invalid item type in body array {name}: expected number"
                                        )
                            elif itype == "boolean":
                                for el in val:
                                    if not isinstance(el, bool):
                                        sval = str(el).lower()
                                        if sval not in {
                                            "true",
                                            "false",
                                            "1",
                                            "0",
                                            "yes",
                                            "no",
                                        }:
                                            raise ValueError(
                                                f"Invalid item type in body array {name}: expected boolean"
                                            )
                            elif itype == "string":
                                for el in val:
                                    if not isinstance(el, str):
                                        raise ValueError(
                                            f"Invalid item type in body array {name}: expected string"
                                        )
                        elif t == "object":
                            # shallow nested object validation
                            if not isinstance(val, dict):
                                raise ValueError(
                                    f"Invalid type for body property {name}: expected object"
                                )
                            sub_props = ps.get("properties") or {}
                            sub_required = set(ps.get("required") or [])
                            for r in sub_required:
                                if r not in val:
                                    raise ValueError(
                                        f"Missing required nested property {name}.{r}"
                                    )
                            for sub_name, sps in sub_props.items():
                                if sub_name not in val:
                                    continue
                                sps = sps or {}
                                st = sps.get("type")
                                sv = val.get(sub_name)
                                if st == "integer":
                                    try:
                                        int(sv)
                                    except Exception:
                                        raise ValueError(
                                            f"Invalid type for nested property {name}.{sub_name}: expected integer"
                                        )
                                elif st == "number":
                                    try:
                                        float(sv)
                                    except Exception:
                                        raise ValueError(
                                            f"Invalid type for nested property {name}.{sub_name}: expected number"
                                        )
                                elif st == "boolean":
                                    if not isinstance(sv, bool):
                                        raise ValueError(
                                            f"Invalid type for nested property {name}.{sub_name}: expected boolean"
                                        )
                                # strings/arrays/objects deeper are accepted as-is (keep shallow)
    except ValueError:
        raise
    except Exception:
        pass

    url = _build_url(server, path, params)

    if not _host_allowed(url, allowed_hosts):
        raise PermissionError(f"Host not allowed for URL: {url}")

    # Remove path params from query
    query: Dict[str, Any] = {}
    for k, v in params.items():
        tok = "{" + str(k) + "}"
        if tok not in path:
            query[k] = v

    close_client = False
    if client is None:
        client = httpx.Client(timeout=request.timeout)
        close_client = True
    try:
        t0 = _time.time()
        resp = client.request(
            method,
            url,
            params=query,
            json=body,
            headers=headers,
            timeout=request.timeout,
        )
        t1 = _time.time()
        raw_text = resp.text
        content_type = resp.headers.get("content-type", "")
        parsed: Optional[Dict[str, Any]] = None
        if "json" in content_type:
            try:
                parsed = resp.json()
            except Exception:
                parsed = None
        result = OpenAPICallResult(
            status_code=resp.status_code,
            body=parsed,
            headers=dict(resp.headers),
            raw_text=raw_text,
        )
        # Best-effort MLflow logging if enabled via env; avoid starting runs unless requested
        try:
            if ensure_run_from_env(
                tags={"tool": "openapi", "op_id": request.operation_id}
            ):
                import mlflow

                mlflow.log_params(
                    {
                        "openapi.method": method,
                        "openapi.path": path,
                        "openapi.server": server or "",
                        "openapi.url": url,
                    }
                )  # type: ignore[attr-defined]
                mlflow.log_metrics(
                    {
                        "openapi.status_code": float(resp.status_code),
                        "openapi.duration_ms": (t1 - t0) * 1000.0,
                    }
                )  # type: ignore[attr-defined]
        except Exception:
            pass
        return result
    finally:
        if close_client:
            client.close()
