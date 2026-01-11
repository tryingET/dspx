from __future__ import annotations

import httpx
from typing import Any, Dict, Mapping, Optional
import re as _re
from urllib.parse import urljoin, urlparse

from dspx.dtos import OpenAPICallRequest, OpenAPICallResult
from dspx.policy import (
    bypass as _policy_bypass,
    allow_network_mutate as _policy_allow_mutate,
    allowed_http_methods as _policy_allowed_methods,
    disallowed_http_methods as _policy_disallowed_methods,
    enforce_network_mutate as _policy_enforce_mutate,
)
import time as _time

try:
    from dspx.redaction import redact_url as _redact_url
except Exception:  # pragma: no cover

    def _redact_url(u: str) -> str:  # type: ignore
        return u


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
        components = operation.get("components") or {}
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
            if (
                (where in {"query", "path"})
                and "schema" in p
                and p.get("name") in params
            ):
                schema = p.get("schema") or {}
                # Resolve $ref in parameter schema if present
                if isinstance(schema, dict) and "$ref" in schema:
                    schema = _resolve_schema(schema, components)
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
                        iv = int(str(val))
                    except Exception:
                        raise ValueError(
                            f"Invalid type for query param {p.get('name')}: expected integer"
                        )
                    # path-specific integer bounds
                    if where == "path":
                        try:
                            if "minimum" in schema and iv < int(schema["minimum"]):  # type: ignore[index]
                                raise ValueError(
                                    f"Invalid value for param {p.get('name')}: below minimum"
                                )
                            if "maximum" in schema and iv > int(schema["maximum"]):  # type: ignore[index]
                                raise ValueError(
                                    f"Invalid value for param {p.get('name')}: above maximum"
                                )
                            if schema.get("exclusiveMinimum") and iv <= int(
                                schema.get("minimum", iv)
                            ):  # type: ignore[index]
                                raise ValueError(
                                    f"Invalid value for param {p.get('name')}: <= exclusiveMinimum"
                                )
                            if schema.get("exclusiveMaximum") and iv >= int(
                                schema.get("maximum", iv)
                            ):  # type: ignore[index]
                                raise ValueError(
                                    f"Invalid value for param {p.get('name')}: >= exclusiveMaximum"
                                )
                        except Exception:
                            pass
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
                    # Items enum constraint (strings or numbers)
                    items_enum = (
                        items.get("enum")
                        if isinstance(items.get("enum"), list)
                        else None
                    )
                    if items_enum is not None:
                        allowed = {str(x) for x in items_enum}
                        for el in val:
                            if str(el) not in allowed:
                                raise ValueError(
                                    f"Invalid item value in array param {p.get('name')}: must be one of {items_enum}"
                                )
                # Numeric min/max for integer/number
                if t in {"integer", "number"}:
                    try:
                        v = float(str(val))
                        if "minimum" in schema and v < float(schema["minimum"]):  # type: ignore[index]
                            raise ValueError(
                                f"Invalid value for param {p.get('name')}: below minimum"
                            )
                        if "maximum" in schema and v > float(schema["maximum"]):  # type: ignore[index]
                            raise ValueError(
                                f"Invalid value for param {p.get('name')}: above maximum"
                            )
                        if schema.get("exclusiveMinimum") and v <= float(
                            schema.get("minimum", v)
                        ):
                            raise ValueError(
                                f"Invalid value for param {p.get('name')}: <= exclusiveMinimum"
                            )
                        if schema.get("exclusiveMaximum") and v >= float(
                            schema.get("maximum", v)
                        ):
                            raise ValueError(
                                f"Invalid value for param {p.get('name')}: >= exclusiveMaximum"
                            )
                    except Exception:
                        pass
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
            components = operation.get("components") or {}
            if isinstance(schema, dict):
                schema = _resolve_schema(schema, components)
            if required_rb and body is None:
                raise ValueError("Missing required request body")
            if body is not None and isinstance(schema, dict):
                _validate_json_value_against_schema(body, schema, path="body")
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

    # Final path param numeric bounds enforcement (defensive)
    try:
        param_specs2 = operation.get("parameters") or []
        components2 = operation.get("components") or {}
        for p in param_specs2:
            if not isinstance(p, dict):
                continue
            if str(p.get("in", "")).lower() != "path":
                continue
            name = str(p.get("name") or "")
            if not name or name not in params:
                continue
            schema = p.get("schema") or {}
            if isinstance(schema, dict) and "$ref" in schema:
                schema = _resolve_schema(schema, components2)
            t = schema.get("type")
            val = params.get(name)
            if t == "integer":
                try:
                    iv = int(str(val))
                except Exception:
                    raise ValueError(
                        f"Invalid type for path param {name}: expected integer"
                    )
                if "minimum" in schema and iv < int(schema["minimum"]):  # type: ignore[index]
                    raise ValueError(
                        f"Invalid value for path param {name}: below minimum"
                    )
                if "maximum" in schema and iv > int(schema["maximum"]):  # type: ignore[index]
                    raise ValueError(
                        f"Invalid value for path param {name}: above maximum"
                    )
            elif t == "number":
                try:
                    fv = float(str(val))
                except Exception:
                    raise ValueError(
                        f"Invalid type for path param {name}: expected number"
                    )
                if "minimum" in schema and fv < float(schema["minimum"]):  # type: ignore[index]
                    raise ValueError(
                        f"Invalid value for path param {name}: below minimum"
                    )
                if "maximum" in schema and fv > float(schema["maximum"]):  # type: ignore[index]
                    raise ValueError(
                        f"Invalid value for path param {name}: above maximum"
                    )
    except ValueError:
        raise
    except Exception:
        pass

    # Method policy enforcement (mutations)
    if not _policy_bypass():
        allow_set = _policy_allowed_methods()
        deny_set = _policy_disallowed_methods()
        if allow_set is not None and method not in allow_set:
            raise PermissionError(f"HTTP method '{method}' not allowed by policy")
        if method in deny_set:
            raise PermissionError(f"HTTP method '{method}' denied by policy")
        # Capability gating: network.read vs network.mutate
    try:
        from dspx.policy import check_capability as _cap
    except Exception:
        _cap = None  # type: ignore
    if _cap is not None:
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            _cap("network.mutate")
        else:
            _cap("network.read")
        if (
            _policy_enforce_mutate()
            and method in {"POST", "PUT", "PATCH", "DELETE"}
            and not _policy_allow_mutate()
        ):
            raise PermissionError(
                f"Mutating HTTP method '{method}' requires DSPX_POLICY_ALLOW_NETWORK_MUTATE=1"
            )

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
            from dspx.tracing import get_mlflow

            mlflow = get_mlflow()
            if mlflow is not None:
                if mlflow.active_run() is not None:  # type: ignore[attr-defined]
                    # Redact URL before logging
                    try:
                        mlflow.set_tag("tool", "openapi")  # type: ignore[attr-defined]
                        mlflow.set_tag(  # type: ignore[attr-defined]
                            "openapi.operation_id", str(request.operation_id)
                        )
                    except Exception:
                        pass
                    try:
                        mlflow.log_params(
                            {
                                "openapi.method": method,
                                "openapi.path": path,
                                "openapi.server": server or "",
                                "openapi.url": _redact_url(url),
                            }
                        )  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    try:
                        mlflow.log_metrics(
                            {
                                "openapi.status_code": float(resp.status_code),
                                "openapi.duration_ms": (t1 - t0) * 1000.0,
                            }
                        )  # type: ignore[attr-defined]
                    except Exception:
                        pass
        except Exception:
            pass
        return result
    finally:
        if close_client:
            client.close()


def _validate_json_value_against_schema(
    value: Any, schema: Mapping[str, Any], *, path: str, _depth: int = 0, _max: int = 6
) -> None:
    """Recursive, conservative validation against a subset of JSON Schema used in OpenAPI.

    Supported: type, enum, required, properties, items, oneOf/anyOf, $ref (local), allOf (object merge),
    and a small set of bounds (min/max length, numeric min/max, min/max items, pattern).
    Raises ValueError with a helpful message on the first failure.
    """
    if _depth > _max:
        return
    if not isinstance(schema, Mapping):
        return

    # OpenAPI 3.0 nullable + JSON Schema null.
    if value is None:
        if bool(schema.get("nullable", False)):
            return
        t0 = schema.get("type")
        if t0 == "null":
            return
        if isinstance(t0, list) and "null" in {str(x) for x in t0}:
            return

    # Const constraint
    if "const" in schema:
        if value != schema.get("const"):
            raise ValueError(f"{path}: value must equal const")

    # Combinators: oneOf/anyOf
    for key in ("oneOf", "anyOf"):
        if isinstance(schema.get(key), list) and schema[key]:  # type: ignore[index]
            errs: list[str] = []
            for idx, branch in enumerate(schema[key]):  # type: ignore[index]
                try:
                    _validate_json_value_against_schema(
                        value, branch or {}, path=path, _depth=_depth + 1, _max=_max
                    )
                    return  # any branch passing is enough
                except ValueError as e:
                    errs.append(f"{key}[{idx}]: {e}")
            raise ValueError(f"{path}: none matched ({'; '.join(errs)})")

    # Enum constraint
    if isinstance(schema.get("enum"), list):
        allowed = {str(x) for x in schema["enum"]}  # type: ignore[index]
        if str(value) not in allowed:
            raise ValueError(f"{path}: value must be one of {sorted(allowed)}")

    t = schema.get("type")

    # Object (t may be omitted in some specs when properties/required are present)
    if t == "object" or (
        t is None and ("properties" in schema or "required" in schema)
    ):
        if not isinstance(value, Mapping):
            raise ValueError(f"{path}: expected object")
        # minProperties/maxProperties
        if isinstance(schema.get("minProperties"), (int, float)) and len(value) < int(
            schema["minProperties"]
        ):  # type: ignore[index]
            raise ValueError(f"{path}: too few properties (< minProperties)")
        if isinstance(schema.get("maxProperties"), (int, float)) and len(value) > int(
            schema["maxProperties"]
        ):  # type: ignore[index]
            raise ValueError(f"{path}: too many properties (> maxProperties)")
        required = list(schema.get("required") or [])
        for r in required:
            if r not in value:
                raise ValueError(f"{path}: missing required property '{r}'")
        props = schema.get("properties") or {}
        if isinstance(props, Mapping):
            for name, ps in props.items():
                if name in value:
                    # quick inline checks for common constraints even if type is missing
                    try:
                        if isinstance(ps, Mapping):
                            v = value[name]
                            if isinstance(
                                ps.get("minLength"), (int, float)
                            ) and isinstance(v, str):
                                if len(v) < int(ps["minLength"]):  # type: ignore[index]
                                    raise ValueError(
                                        f"{path}.{name}: shorter than minLength"
                                    )
                            if isinstance(ps.get("pattern"), str) and isinstance(
                                v, str
                            ):
                                if not _re.compile(str(ps.get("pattern"))).search(v):
                                    raise ValueError(
                                        f"{path}.{name}: does not match pattern"
                                    )
                    except ValueError:
                        raise
                    except Exception:
                        pass
                    _validate_json_value_against_schema(
                        value[name],
                        ps or {},
                        path=f"{path}.{name}",
                        _depth=_depth + 1,
                        _max=_max,
                    )
        # additionalProperties
        addl = schema.get("additionalProperties", True)
        if addl is False:
            allowed = set(props.keys()) if isinstance(props, Mapping) else set()
            extra = [k for k in value.keys() if k not in allowed]
            if extra:
                raise ValueError(f"{path}: unexpected properties {sorted(extra)}")
        elif isinstance(addl, Mapping):
            allowed = set(props.keys()) if isinstance(props, Mapping) else set()
            for k in value.keys():
                if k in allowed:
                    continue
                _validate_json_value_against_schema(
                    value[k],
                    addl,
                    path=f"{path}.{k}",
                    _depth=_depth + 1,
                    _max=_max,
                )
        return

    # Array
    if t == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path}: expected array")
        items = schema.get("items")
        if isinstance(items, Mapping):
            for i, el in enumerate(value):
                _validate_json_value_against_schema(
                    el, items, path=f"{path}[{i}]", _depth=_depth + 1, _max=_max
                )
        # minItems/maxItems
        if isinstance(schema.get("minItems"), (int, float)) and len(value) < int(
            schema["minItems"]
        ):  # type: ignore[index]
            raise ValueError(f"{path}: too few items (< minItems)")
        if isinstance(schema.get("maxItems"), (int, float)) and len(value) > int(
            schema["maxItems"]
        ):  # type: ignore[index]
            raise ValueError(f"{path}: too many items (> maxItems)")
        return

    # Primitive types
    if t == "integer":
        try:
            int(value)
        except Exception:
            raise ValueError(f"{path}: expected integer")
        # numeric bounds
        try:
            v = int(value)
            if "minimum" in schema and v < int(schema["minimum"]):  # type: ignore[index]
                raise ValueError(f"{path}: below minimum")
            if "maximum" in schema and v > int(schema["maximum"]):  # type: ignore[index]
                raise ValueError(f"{path}: above maximum")
            if schema.get("exclusiveMinimum") and v <= int(schema.get("minimum", v)):  # type: ignore[index]
                raise ValueError(f"{path}: <= exclusiveMinimum")
            if schema.get("exclusiveMaximum") and v >= int(schema.get("maximum", v)):  # type: ignore[index]
                raise ValueError(f"{path}: >= exclusiveMaximum")
        except ValueError:
            raise
        except Exception:
            pass
        # multipleOf
        if isinstance(schema.get("multipleOf"), (int, float)):
            try:
                m = float(schema["multipleOf"])  # type: ignore[index]
                if m != 0.0:
                    q = float(v) / m
                    if abs(q - round(q)) > 1e-9:
                        raise ValueError(f"{path}: not a multipleOf {m}")
            except ValueError:
                raise
            except Exception:
                pass
        return
    if t == "number":
        try:
            float(value)
        except Exception:
            raise ValueError(f"{path}: expected number")
        try:
            v = float(value)
            if "minimum" in schema and v < float(schema["minimum"]):  # type: ignore[index]
                raise ValueError(f"{path}: below minimum")
            if "maximum" in schema and v > float(schema["maximum"]):  # type: ignore[index]
                raise ValueError(f"{path}: above maximum")
            if schema.get("exclusiveMinimum") and v <= float(schema.get("minimum", v)):  # type: ignore[index]
                raise ValueError(f"{path}: <= exclusiveMinimum")
            if schema.get("exclusiveMaximum") and v >= float(schema.get("maximum", v)):  # type: ignore[index]
                raise ValueError(f"{path}: >= exclusiveMaximum")
        except ValueError:
            raise
        except Exception:
            pass
        # multipleOf
        if isinstance(schema.get("multipleOf"), (int, float)):
            try:
                v = float(value)
                m = float(schema["multipleOf"])  # type: ignore[index]
                if m != 0.0:
                    q = v / m
                    if abs(q - round(q)) > 1e-9:
                        raise ValueError(f"{path}: not a multipleOf {m}")
            except ValueError:
                raise
            except Exception:
                pass
        return
    if t == "boolean":
        if isinstance(value, bool):
            return
        raise ValueError(f"{path}: expected boolean")
    if t == "string":
        if not isinstance(value, str):
            raise ValueError(f"{path}: expected string")
        # minLength/maxLength, pattern
        try:
            if isinstance(schema.get("minLength"), (int, float)) and len(value) < int(
                schema["minLength"]
            ):  # type: ignore[index]
                raise ValueError(f"{path}: shorter than minLength")
            if isinstance(schema.get("maxLength"), (int, float)) and len(value) > int(
                schema["maxLength"]
            ):  # type: ignore[index]
                raise ValueError(f"{path}: longer than maxLength")
            if isinstance(schema.get("pattern"), str):
                pat = schema["pattern"]  # type: ignore[index]
                if not _re.compile(pat).search(value):
                    raise ValueError(f"{path}: does not match pattern")
        except ValueError:
            raise
        except Exception:
            pass
        return
    # unknown or unspecified: accept
    return


def _resolve_schema(
    schema: Mapping[str, Any],
    components: Mapping[str, Any],
    _seen: Optional[set[str]] = None,
) -> Mapping[str, Any]:
    """Resolve $ref and merge allOf for object schemas (shallow) recursively.

    Only resolves local refs under #/components/schemas. Returns a new dict.
    """
    if _seen is None:
        _seen = set()
    if not isinstance(schema, Mapping):
        return schema
    # $ref resolution
    if "$ref" in schema and isinstance(schema.get("$ref"), str):
        ref = str(schema.get("$ref"))
        if ref in _seen:
            return {}
        _seen.add(ref)
        target: Optional[Mapping[str, Any]] = None
        try:
            if ref.startswith("#/components/schemas/") and isinstance(
                components, Mapping
            ):
                key = ref.split("/schemas/")[-1]
                target = (components.get("schemas") or {}).get(key)  # type: ignore[index]
        except Exception:
            target = None
        if isinstance(target, Mapping):
            return _resolve_schema(target, components, _seen)
        # Unresolvable: return as-is
        return schema
    # allOf merge (object schemas)
    if isinstance(schema.get("allOf"), list):
        merged: Dict[str, Any] = {}
        required: set[str] = set()
        props: Dict[str, Any] = {}
        for part in schema.get("allOf"):  # type: ignore[assignment]
            part = _resolve_schema(part or {}, components, _seen)
            if not isinstance(part, Mapping):
                continue
            if (
                part.get("type") == "object"
                or "properties" in part
                or "required" in part
            ):
                rp = part.get("properties") or {}
                if isinstance(rp, Mapping):
                    props.update(rp)  # later wins
                rr = part.get("required") or []
                try:
                    required.update([str(x) for x in rr])
                except Exception:
                    pass
                # carry other object-level constraints conservatively
        if props or required:
            merged.update({"type": "object", "properties": props})
            if required:
                merged["required"] = sorted(required)
            # Merge back any additional top-level keywords except allOf
            for k, v in schema.items():
                if k not in {"allOf", "properties", "required", "type"}:
                    merged[k] = v
            return merged
    # Recurse into object properties/items
    out = dict(schema)
    if isinstance(schema.get("properties"), Mapping):
        new_props: Dict[str, Any] = {}
        for k, v in schema["properties"].items():  # type: ignore[index]
            new_props[k] = _resolve_schema(v, components, _seen)
        out["properties"] = new_props
    if isinstance(schema.get("items"), Mapping):
        out["items"] = _resolve_schema(schema["items"], components, _seen)  # type: ignore[index]
    if isinstance(schema.get("additionalProperties"), Mapping):
        out["additionalProperties"] = _resolve_schema(
            schema["additionalProperties"],
            components,
            _seen,  # type: ignore[index]
        )
    return out
