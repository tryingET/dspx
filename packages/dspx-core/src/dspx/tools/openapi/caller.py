from __future__ import annotations

import json
import os

import httpx
from typing import Any, Dict, Mapping, Optional, cast
import math as _math
import re as _re
from urllib.parse import quote, urljoin

from dspx.dtos import OpenAPICallRequest, OpenAPICallResult
from dspx.http_guard import host_allowed, send_with_host_allowlist
from dspx.security import read_response_text_bounded
from dspx.policy import (
    bypass as _policy_bypass,
    allow_network_mutate as _policy_allow_mutate,
    allowed_http_methods as _policy_allowed_methods,
    disallowed_http_methods as _policy_disallowed_methods,
    enforce_network_mutate as _policy_enforce_mutate,
)
import time as _time

_safe_regex: Any = None
try:
    import regex as _regex_module
except Exception:  # pragma: no cover - stdlib fallback is intentionally conservative
    pass
else:
    _safe_regex = _regex_module

try:
    from dspx.redaction import redact_url as _redact_url
except Exception:  # pragma: no cover

    def _redact_url(u: str) -> str:
        return u


_DEFAULT_OPERATION_RESPONSE_MAX_BYTES = 2_000_000
_DEFAULT_OPERATION_TIMEOUT_SECONDS = 20.0
_DEFAULT_SCHEMA_REGEX_TIMEOUT_SECONDS = 0.05
_FALLBACK_REGEX_INPUT_MAX_CHARS = 4096
_BLOCKED_REQUEST_HEADERS = {
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _operation_response_max_bytes() -> int:
    raw = os.getenv("DSPX_OPENAPI_RESPONSE_MAX_BYTES") or os.getenv(
        "DSPX_OPENAPI_MAX_BYTES",
        str(_DEFAULT_OPERATION_RESPONSE_MAX_BYTES),
    )
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            "DSPX_OPENAPI_RESPONSE_MAX_BYTES must be an integer byte count"
        ) from exc
    if value < 1:
        raise ValueError("DSPX_OPENAPI_RESPONSE_MAX_BYTES must be positive")
    return value


def _operation_timeout_seconds() -> float:
    raw = os.getenv(
        "DSPX_OPENAPI_OPERATION_TIMEOUT", str(_DEFAULT_OPERATION_TIMEOUT_SECONDS)
    )
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            "DSPX_OPENAPI_OPERATION_TIMEOUT must be a positive number"
        ) from exc
    if not _math.isfinite(value) or value <= 0:
        raise ValueError(
            "DSPX_OPENAPI_OPERATION_TIMEOUT must be a positive finite number"
        )
    return value


def _schema_regex_timeout_seconds() -> float:
    raw = os.getenv(
        "DSPX_OPENAPI_SCHEMA_REGEX_TIMEOUT",
        str(_DEFAULT_SCHEMA_REGEX_TIMEOUT_SECONDS),
    )
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            "DSPX_OPENAPI_SCHEMA_REGEX_TIMEOUT must be a positive number"
        ) from exc
    if not _math.isfinite(value) or value <= 0:
        raise ValueError(
            "DSPX_OPENAPI_SCHEMA_REGEX_TIMEOUT must be a positive finite number"
        )
    return value


def _operation_identity(
    request: OpenAPICallRequest, operation: Mapping[str, Any]
) -> tuple[str, str, str]:
    """Resolve and enforce the fixed OpenAPI operation identity.

    OpenAPICallRequest retains method/server/path fields for compatibility with
    older programmatic callers, but operation identity must not be changed after
    an operation descriptor has been selected. Supplying the same value is
    tolerated; supplying a different value is rejected before validation/call.
    """

    method = str(operation.get("method") or "GET").upper()
    server = str(operation.get("server") or "")
    path = str(operation.get("path") or request.operation_id)
    attempted: list[str] = []
    if request.method is not None and str(request.method).upper() != method:
        attempted.append("method")
    if request.server is not None and str(request.server) != server:
        attempted.append("server")
    if request.path is not None and str(request.path) != path:
        attempted.append("path")
    if attempted:
        raise ValueError(
            "OpenAPI operation identity is fixed by the selected descriptor; "
            "overrides rejected: " + ", ".join(sorted(attempted))
        )
    return method, server, path


def _build_url(server: str, path: str, params: Mapping[str, Any]) -> str:
    """Replace path params like {id} and join with server.

    Query params are not appended here; httpx handles them via params=.
    Path parameters are URL-encoded so reserved characters stay inside the
    parameter value instead of mutating route structure.
    """
    out_path = path
    for k, v in params.items():
        tok = "{" + str(k) + "}"
        if tok in out_path:
            out_path = out_path.replace(tok, quote(str(v), safe=""))
    if server:
        base = server if server.endswith("/") else (server + "/")
        joined = urljoin(base, out_path.lstrip("/"))
        return joined
    return out_path


_INTEGER_PATTERN = _re.compile(r"^[+-]?\d+$")


def _coerce_integer_value(
    value: Any,
    *,
    label: str,
    allow_strings: bool,
) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label}: expected integer")
    if isinstance(value, int):
        return value
    if allow_strings and isinstance(value, str):
        text = value.strip()
        if _INTEGER_PATTERN.fullmatch(text):
            return int(text)
    raise ValueError(f"{label}: expected integer")


def _coerce_number_value(
    value: Any,
    *,
    label: str,
    allow_strings: bool,
) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label}: expected number")
    if isinstance(value, (int, float)):
        number = float(value)
        if _math.isfinite(number):
            return number
        raise ValueError(f"{label}: expected finite number")
    if allow_strings and isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{label}: expected number")
        try:
            number = float(text)
        except Exception:
            raise ValueError(f"{label}: expected number")
        if _math.isfinite(number):
            return number
        raise ValueError(f"{label}: expected finite number")
    raise ValueError(f"{label}: expected number")


def _coerce_numeric_param(value: Any, *, integer: bool, label: str) -> float | int:
    if integer:
        return _coerce_integer_value(value, label=label, allow_strings=True)
    return _coerce_number_value(value, label=label, allow_strings=True)


def _schema_numeric_value(raw: Any, *, label: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"{label}: expected finite number")
    number = float(raw)
    if not _math.isfinite(number):
        raise ValueError(f"{label}: expected finite number")
    return number


def _exclusive_threshold(
    schema: Mapping[str, Any], *, key: str, fallback_key: str
) -> float | None:
    raw = schema.get(key)
    if isinstance(raw, bool):
        if not raw:
            return None
        if fallback_key not in schema:
            raise ValueError(f"{key}: missing {fallback_key}")
        return _schema_numeric_value(
            schema.get(fallback_key),
            label=f"{key}/{fallback_key}",
        )
    if raw is None:
        return None
    return _schema_numeric_value(raw, label=key)


def _validate_numeric_bounds(
    value: float | int, schema: Mapping[str, Any], *, label: str
) -> None:
    if "minimum" in schema:
        minimum = _schema_numeric_value(schema["minimum"], label="minimum")
        if value < minimum:
            raise ValueError(f"{label}: below minimum")
    if "maximum" in schema:
        maximum = _schema_numeric_value(schema["maximum"], label="maximum")
        if value > maximum:
            raise ValueError(f"{label}: above maximum")

    exclusive_minimum = _exclusive_threshold(
        schema,
        key="exclusiveMinimum",
        fallback_key="minimum",
    )
    if exclusive_minimum is not None and value <= exclusive_minimum:
        raise ValueError(f"{label}: <= exclusiveMinimum")

    exclusive_maximum = _exclusive_threshold(
        schema,
        key="exclusiveMaximum",
        fallback_key="maximum",
    )
    if exclusive_maximum is not None and value >= exclusive_maximum:
        raise ValueError(f"{label}: >= exclusiveMaximum")


def _validate_numeric_multiple_of(
    value: float | int, schema: Mapping[str, Any], *, label: str
) -> None:
    multiple_of = schema.get("multipleOf")
    if not isinstance(multiple_of, (int, float)) or isinstance(multiple_of, bool):
        return

    step = _schema_numeric_value(multiple_of, label="multipleOf")
    if step == 0.0:
        return
    quotient = float(value) / step
    if abs(quotient - round(quotient)) > 1e-9:
        raise ValueError(f"{label}: not a multipleOf {step}")


def _validate_numeric_schema(
    value: float | int, schema: Mapping[str, Any], *, label: str
) -> None:
    _validate_numeric_bounds(value, schema, label=label)
    _validate_numeric_multiple_of(value, schema, label=label)


def _json_enum_equal(left: Any, right: Any) -> bool:
    """Return JSON-schema enum equality without type-erasing string coercion."""

    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if isinstance(left, bool) or isinstance(right, bool):
            return False
        return float(left) == float(right)
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_enum_equal(l_item, r_item)
            for l_item, r_item in zip(left, right, strict=True)
        )
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(left) != set(right):
            return False
        return all(_json_enum_equal(left[key], right[key]) for key in left)
    return type(left) is type(right) and left == right


def _coerce_enum_candidate_for_parameter(value: Any, schema: Mapping[str, Any]) -> Any:
    schema_type = schema.get("type")
    if schema_type == "integer":
        return _coerce_numeric_param(value, integer=True, label="enum parameter")
    if schema_type == "number":
        return _coerce_numeric_param(value, integer=False, label="enum parameter")
    if schema_type == "boolean" and isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    return value


def _enum_contains(value: Any, enum: list[Any]) -> bool:
    return any(_json_enum_equal(value, item) for item in enum)


def _connection_header_tokens(headers: Mapping[str, str]) -> set[str]:
    tokens: set[str] = set()
    for name, value in headers.items():
        if str(name).strip().lower() != "connection":
            continue
        tokens.update(
            token.strip().lower() for token in str(value).split(",") if token.strip()
        )
    return tokens


def _request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    blocked = _BLOCKED_REQUEST_HEADERS | {"host"} | _connection_header_tokens(headers)
    return {
        str(name): value
        for name, value in headers.items()
        if str(name).strip().lower() not in blocked
    }


def _schema_pattern_matches(pattern: str, value: str, *, path: str) -> bool:
    if _safe_regex is not None:
        try:
            return bool(
                _safe_regex.compile(pattern).search(
                    value, timeout=_schema_regex_timeout_seconds()
                )
            )
        except TimeoutError as exc:
            raise ValueError(f"{path}: unsafe regex pattern timed out") from exc
        except Exception as exc:
            raise ValueError(f"{path}: invalid regex pattern") from exc
    if len(value) > _FALLBACK_REGEX_INPUT_MAX_CHARS:
        raise ValueError(
            f"{path}: regex input exceeds fallback safety limit "
            f"({_FALLBACK_REGEX_INPUT_MAX_CHARS} chars)"
        )
    try:
        return bool(_re.compile(pattern).search(value))
    except Exception as exc:
        raise ValueError(f"{path}: invalid regex pattern") from exc


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
    method, server, path = _operation_identity(request, operation)
    params = dict(request.params or {})
    body = request.body if request.body is not None else None
    headers = _request_headers(request.headers or {})
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
                    enum_value = _coerce_enum_candidate_for_parameter(val, schema)
                    if not _enum_contains(enum_value, enum):
                        raise ValueError(
                            f"Invalid value for {where} param {p.get('name')}: must be one of {enum}"
                        )
                numeric_value: float | int | None = None
                param_kind = f"{where} param"
                if t == "integer":
                    numeric_value = _coerce_numeric_param(
                        val,
                        integer=True,
                        label=f"Invalid type for {param_kind} {p.get('name')}",
                    )
                elif t == "number":
                    numeric_value = _coerce_numeric_param(
                        val,
                        integer=False,
                        label=f"Invalid type for {param_kind} {p.get('name')}",
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
                        for idx, el in enumerate(val):
                            coerced = _coerce_integer_value(
                                el,
                                label=f"Invalid item type in array param {p.get('name')}",
                                allow_strings=True,
                            )
                            _validate_numeric_schema(
                                coerced,
                                items,
                                label=(
                                    f"Invalid item value in array param {p.get('name')}[{idx}]"
                                ),
                            )
                    elif itype == "number":
                        for idx, el in enumerate(val):
                            coerced = _coerce_number_value(
                                el,
                                label=f"Invalid item type in array param {p.get('name')}",
                                allow_strings=True,
                            )
                            _validate_numeric_schema(
                                coerced,
                                items,
                                label=(
                                    f"Invalid item value in array param {p.get('name')}[{idx}]"
                                ),
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
                        for el in val:
                            enum_item = _coerce_enum_candidate_for_parameter(el, items)
                            if not _enum_contains(enum_item, items_enum):
                                raise ValueError(
                                    f"Invalid item value in array param {p.get('name')}: must be one of {items_enum}"
                                )
                # Numeric min/max for integer/number
                if numeric_value is not None:
                    _validate_numeric_schema(
                        numeric_value,
                        schema,
                        label=f"Invalid value for {param_kind} {p.get('name')}",
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
            components = operation.get("components") or {}
            if isinstance(schema, dict):
                schema = _resolve_schema(schema, components)
            if required_rb and body is None:
                raise ValueError("Missing required request body")
            if body is not None and isinstance(schema, dict):
                _validate_json_value_against_schema(body, schema, path="body")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            f"request body schema validation failed before completion: {exc}"
        ) from exc

    url = _build_url(server, path, params)

    if not host_allowed(url, allowed_hosts):
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
                iv = _coerce_numeric_param(
                    val,
                    integer=True,
                    label=f"Invalid type for path param {name}",
                )
                _validate_numeric_schema(
                    iv,
                    schema,
                    label=f"Invalid value for path param {name}",
                )
            elif t == "number":
                fv = _coerce_numeric_param(
                    val,
                    integer=False,
                    label=f"Invalid type for path param {name}",
                )
                _validate_numeric_schema(
                    fv,
                    schema,
                    label=f"Invalid value for path param {name}",
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
        client = httpx.Client(
            timeout=request.timeout
            if request.timeout is not None
            else _operation_timeout_seconds()
        )
        close_client = True
    try:
        req = client.build_request(
            method,
            url,
            params=query,
            json=body,
            headers=headers,
        )
        t0 = _time.time()
        resp = send_with_host_allowlist(
            client,
            req,
            allowed_hosts=allowed_hosts,
            stream=True,
        )
        try:
            raw_text = read_response_text_bounded(
                resp,
                max_bytes=_operation_response_max_bytes(),
                label="OpenAPI operation response",
            )
        finally:
            resp.close()
        t1 = _time.time()
        content_type = resp.headers.get("content-type", "")
        parsed: Any = None
        if "json" in content_type:
            try:
                parsed = json.loads(raw_text)
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
                if mlflow.active_run() is not None:
                    # Redact URL before logging
                    try:
                        mlflow.set_tag("tool", "openapi")
                        mlflow.set_tag(
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
                        )
                    except Exception:
                        pass
                    try:
                        mlflow.log_metrics(
                            {
                                "openapi.status_code": float(resp.status_code),
                                "openapi.duration_ms": (t1 - t0) * 1000.0,
                            }
                        )
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

    Supported: type, enum, required, properties, items, oneOf/anyOf, $ref (local), allOf,
    and a small set of bounds (min/max length, numeric min/max, min/max items, pattern).
    Raises ValueError with a helpful message on the first failure.
    """
    if _depth > _max:
        raise ValueError(
            f"{path}: schema validation depth exceeded {_max}; "
            "rejecting unsupported nested schema instead of accepting without validation"
        )
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

    all_of = schema.get("allOf")
    if isinstance(all_of, list) and all_of:
        for idx, branch in enumerate(all_of):
            branch_schema = (
                cast(Mapping[str, Any], branch) if isinstance(branch, Mapping) else {}
            )
            try:
                _validate_json_value_against_schema(
                    value,
                    branch_schema,
                    path=path,
                    _depth=_depth + 1,
                    _max=_max,
                )
            except ValueError as e:
                raise ValueError(f"{path}: allOf[{idx}] failed: {e}") from e
        remainder = {k: v for k, v in schema.items() if k != "allOf"}
        if remainder:
            _validate_json_value_against_schema(
                value,
                remainder,
                path=path,
                _depth=_depth + 1,
                _max=_max,
            )
        return

    # Combinators: oneOf/anyOf
    one_of = schema.get("oneOf")
    if isinstance(one_of, list) and one_of:
        errs: list[str] = []
        matched: list[int] = []
        for idx, branch in enumerate(one_of):
            branch_schema = (
                cast(Mapping[str, Any], branch) if isinstance(branch, Mapping) else {}
            )
            try:
                _validate_json_value_against_schema(
                    value,
                    branch_schema,
                    path=path,
                    _depth=_depth + 1,
                    _max=_max,
                )
                matched.append(idx)
            except ValueError as e:
                errs.append(f"oneOf[{idx}]: {e}")
        if len(matched) != 1:
            if not matched:
                raise ValueError(f"{path}: none matched ({'; '.join(errs)})")
            raise ValueError(f"{path}: matched multiple oneOf branches {matched}")
        remainder = {k: v for k, v in schema.items() if k != "oneOf"}
        if remainder:
            _validate_json_value_against_schema(
                value,
                remainder,
                path=path,
                _depth=_depth + 1,
                _max=_max,
            )
        return

    any_of = schema.get("anyOf")
    if isinstance(any_of, list) and any_of:
        errs: list[str] = []
        for idx, branch in enumerate(any_of):
            branch_schema = (
                cast(Mapping[str, Any], branch) if isinstance(branch, Mapping) else {}
            )
            try:
                _validate_json_value_against_schema(
                    value,
                    branch_schema,
                    path=path,
                    _depth=_depth + 1,
                    _max=_max,
                )
                remainder = {k: v for k, v in schema.items() if k != "anyOf"}
                if remainder:
                    _validate_json_value_against_schema(
                        value,
                        remainder,
                        path=path,
                        _depth=_depth + 1,
                        _max=_max,
                    )
                return
            except ValueError as e:
                errs.append(f"anyOf[{idx}]: {e}")
        raise ValueError(f"{path}: none matched ({'; '.join(errs)})")

    # Enum constraint
    if isinstance(schema.get("enum"), list):
        allowed = list(schema["enum"])
        if not _enum_contains(value, allowed):
            raise ValueError(f"{path}: value must be one of {allowed}")

    t = schema.get("type")
    if isinstance(t, list):
        allowed_types = [str(item) for item in t]
        branch_errors: list[str] = []
        for type_name in allowed_types:
            if type_name == "null":
                continue
            if type_name not in {
                "object",
                "array",
                "integer",
                "number",
                "boolean",
                "string",
            }:
                branch_errors.append(f"{type_name}: unsupported type")
                continue
            branch_schema = dict(schema)
            branch_schema["type"] = type_name
            try:
                _validate_json_value_against_schema(
                    value,
                    branch_schema,
                    path=path,
                    _depth=_depth + 1,
                    _max=_max,
                )
                return
            except ValueError as exc:
                branch_errors.append(f"{type_name}: {exc}")
        raise ValueError(
            f"{path}: value did not match any allowed type {allowed_types}"
            + (f" ({'; '.join(branch_errors)})" if branch_errors else "")
        )

    # Object (t may be omitted in some specs when properties/required are present)
    if t == "object" or (
        t is None and ("properties" in schema or "required" in schema)
    ):
        if not isinstance(value, Mapping):
            raise ValueError(f"{path}: expected object")
        # minProperties/maxProperties
        if isinstance(schema.get("minProperties"), (int, float)) and len(value) < int(
            schema["minProperties"]
        ):
            raise ValueError(f"{path}: too few properties (< minProperties)")
        if isinstance(schema.get("maxProperties"), (int, float)) and len(value) > int(
            schema["maxProperties"]
        ):
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
                                if len(v) < int(ps["minLength"]):
                                    raise ValueError(
                                        f"{path}.{name}: shorter than minLength"
                                    )
                            if isinstance(ps.get("pattern"), str) and isinstance(
                                v, str
                            ):
                                if not _schema_pattern_matches(
                                    str(ps.get("pattern")), v, path=f"{path}.{name}"
                                ):
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
        ):
            raise ValueError(f"{path}: too few items (< minItems)")
        if isinstance(schema.get("maxItems"), (int, float)) and len(value) > int(
            schema["maxItems"]
        ):
            raise ValueError(f"{path}: too many items (> maxItems)")
        return

    # Primitive types
    if t == "integer":
        v = _coerce_integer_value(value, label=path, allow_strings=False)
        _validate_numeric_schema(v, schema, label=path)
        return
    if t == "number":
        v = _coerce_number_value(value, label=path, allow_strings=False)
        _validate_numeric_schema(v, schema, label=path)
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
            ):
                raise ValueError(f"{path}: shorter than minLength")
            if isinstance(schema.get("maxLength"), (int, float)) and len(value) > int(
                schema["maxLength"]
            ):
                raise ValueError(f"{path}: longer than maxLength")
            if isinstance(schema.get("pattern"), str):
                pat = schema["pattern"]
                if not _schema_pattern_matches(pat, value, path=path):
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
    _depth: int = 0,
    _max: int = 32,
) -> Mapping[str, Any]:
    """Resolve $ref recursively while preserving combinator semantics.

    Only resolves local refs under #/components/schemas. Returns a new dict.
    """
    if _seen is None:
        _seen = set()
    if _depth > _max:
        raise ValueError(f"schema resolution depth exceeded {_max}")
    if not isinstance(schema, Mapping):
        return schema
    # $ref resolution
    if "$ref" in schema and isinstance(schema.get("$ref"), str):
        ref = str(schema.get("$ref"))
        if ref in _seen:
            raise ValueError(f"schema reference cycle detected: {ref}")
        next_seen = {*_seen, ref}
        target: Optional[Mapping[str, Any]] = None
        try:
            if ref.startswith("#/components/schemas/") and isinstance(
                components, Mapping
            ):
                key = ref.split("/schemas/")[-1]
                target = (components.get("schemas") or {}).get(key)
        except Exception:
            target = None
        if isinstance(target, Mapping):
            return _resolve_schema(target, components, next_seen, _depth + 1, _max)
        # Unresolvable: return as-is
        return schema
    # Preserve composition semantics; resolve refs within each branch.
    out = dict(schema)
    for key in ("allOf", "oneOf", "anyOf"):
        parts = schema.get(key)
        if isinstance(parts, list):
            out[key] = [
                (
                    _resolve_schema(
                        part or {}, components, set(_seen), _depth + 1, _max
                    )
                    if isinstance(part, Mapping)
                    else part
                )
                for part in parts
            ]
    # Recurse into object properties/items
    if isinstance(schema.get("properties"), Mapping):
        new_props: Dict[str, Any] = {}
        for k, v in schema["properties"].items():
            new_props[k] = _resolve_schema(v, components, set(_seen), _depth + 1, _max)
        out["properties"] = new_props
    if isinstance(schema.get("items"), Mapping):
        out["items"] = _resolve_schema(
            schema["items"], components, set(_seen), _depth + 1, _max
        )
    if isinstance(schema.get("additionalProperties"), Mapping):
        out["additionalProperties"] = _resolve_schema(
            schema["additionalProperties"],
            components,
            set(_seen),
            _depth + 1,
            _max,
        )
    return out
