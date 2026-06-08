from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional
from .models import OpenAPIOperationInfo
import os
from pathlib import Path
from urllib.parse import unquote, urlparse
import httpx

from dspx.http_guard import host_allowed, send_with_host_allowlist
from dspx.redaction import redact_url
from dspx.security import read_file_text_bounded, read_response_text_bounded

_DEFAULT_REMOTE_SPEC_MAX_BYTES = 2_000_000


def _is_url(s: str) -> bool:
    try:
        return urlparse(s).scheme in {"http", "https"}
    except Exception:
        return False


def _cache_enabled() -> bool:
    return os.getenv("DSPX_OPENAPI_CACHE", "1") not in {"", "0", "false", "False"}


def _cache_dir() -> str:
    return os.getenv("DSPX_OPENAPI_CACHE_DIR") or os.path.join(
        os.getcwd(), "generated", "openapi", "cache"
    )


def _cache_key(url: str) -> str:
    import hashlib

    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _remote_spec_max_bytes() -> int:
    raw = os.getenv("DSPX_OPENAPI_MAX_BYTES", str(_DEFAULT_REMOTE_SPEC_MAX_BYTES))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            "DSPX_OPENAPI_MAX_BYTES must be an integer byte count"
        ) from exc
    if value < 1:
        raise ValueError("DSPX_OPENAPI_MAX_BYTES must be positive")
    return value


def _cache_path(url: str) -> str:
    d = _cache_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return os.path.join(d, _cache_key(url) + ".json")


def _load_text(text: str, path_hint: str) -> Dict[str, Any]:
    # Try JSON first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # If YAML, parse via PyYAML if available
    try:
        import yaml

        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("YAML did not parse into a dictionary")
        return data
    except ModuleNotFoundError:
        raise ValueError(
            "Failed to parse spec as JSON; install PyYAML to load YAML (pip install pyyaml)."
        )
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Failed to parse spec at {path_hint}: {e}")


def load_spec(
    path: str,
    *,
    allowed_hosts: Optional[Mapping[str, bool]] = None,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Load an OpenAPI spec from a local file or URL.

    - For URLs, enforce `allowed_hosts` and optionally cache to disk.
    - Supports JSON and YAML (via PyYAML) formats.
    """
    if _is_url(path):
        # Capability: network.read for remote spec fetching
        try:
            from dspx.policy import check_capability as _cap
        except Exception:
            _cap = None  # type: ignore
        if _cap is not None:
            _cap("network.read")
        if not allowed_hosts or not host_allowed(path, allowed_hosts):
            raise PermissionError(f"Host not allowed for spec URL: {redact_url(path)}")
        pth = _cache_path(path)
        close_client = False
        if client is None:
            client = httpx.Client(timeout=20.0)
            close_client = True
        try:
            req = client.build_request("GET", path)
            resp = send_with_host_allowlist(
                client,
                req,
                allowed_hosts=allowed_hosts,
                blocked_error_prefix="Host not allowed for spec URL",
                redirect_error_prefix="Redirect target host not allowed for spec URL",
                stream=True,
            )
            try:
                resp.raise_for_status()
                final_url = str(resp.url)
                text = read_response_text_bounded(
                    resp,
                    max_bytes=_remote_spec_max_bytes(),
                    label="OpenAPI remote spec",
                )
            finally:
                resp.close()
            parsed = _load_text(text, final_url)
            if _cache_enabled():
                try:
                    with open(pth, "w", encoding="utf-8") as wf:
                        wf.write(text)
                except Exception:
                    pass
            return parsed
        except PermissionError:
            raise
        except Exception:
            if (
                _cache_enabled()
                and os.getenv("DSPX_OPENAPI_CACHE_FALLBACK", "0").strip().lower()
                in {"1", "true", "yes"}
                and os.path.exists(pth)
            ):
                try:
                    return _load_text(
                        read_file_text_bounded(
                            Path(pth),
                            max_bytes=_remote_spec_max_bytes(),
                            label="OpenAPI cached spec",
                        ),
                        pth,
                    )
                except Exception:
                    pass
            raise
        finally:
            if close_client:
                client.close()
    # Local file path
    text = read_file_text_bounded(
        Path(path),
        max_bytes=_remote_spec_max_bytes(),
        label="OpenAPI local spec",
    )
    return _load_text(text, path)


def _resolve_local_ref(ref: str, spec: Mapping[str, Any]) -> Any:
    """Resolve a local JSON pointer reference from an OpenAPI document."""
    if not ref.startswith("#/"):
        return None
    current: Any = spec
    for raw_part in ref[2:].split("/"):
        part = unquote(raw_part.replace("~1", "/").replace("~0", "~"))
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _first_server_url(servers: Any) -> str | None:
    if isinstance(servers, list) and servers:
        s0 = servers[0]
        if isinstance(s0, dict) and "url" in s0:
            return str(s0["url"]).rstrip("/")
    return None


def extract_operations(spec: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract operations keyed by operationId with basic metadata.

    Returns mapping opId -> { method, path, server, parameters, requestBody, responses, tags }.
    """
    ops: Dict[str, Dict[str, Any]] = {}
    base_server = _first_server_url(spec.get("servers"))
    paths = spec.get("paths") or {}
    components = spec.get("components") or {}
    comp_params = components.get("parameters") if isinstance(components, dict) else None
    if not isinstance(paths, dict):
        return ops
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        item_server = _first_server_url(item.get("servers")) or base_server
        # Path-level parameters (applies to all methods unless overridden)
        path_params = []
        if isinstance(item.get("parameters"), list):
            path_params = [p for p in item.get("parameters") if isinstance(p, dict)]
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            op_id = op.get("operationId")
            if not op_id:
                # derive naive op id
                op_id = f"{method}_{path.strip('/').replace('/', '_').replace('{', '').replace('}', '')}"
            op_params = op.get("parameters") or []
            # Optional summary/description for metadata
            summary = None
            try:
                summary = op.get("summary") or op.get("description")
            except Exception:
                summary = None
            # Merge path-level and op-level parameters; op-level overrides duplicates by (name,in)
            merged_params: list[dict] = []
            seen: set[tuple[str, str]] = set()
            for pr in path_params + list(op_params):
                if not isinstance(pr, dict):
                    continue
                # Resolve parameter $ref if present
                if "$ref" in pr and isinstance(pr.get("$ref"), str):
                    ref = str(pr.get("$ref"))
                    try:
                        if ref.startswith("#/components/parameters/") and isinstance(
                            comp_params, dict
                        ):
                            cand = _resolve_local_ref(ref, spec)
                            if isinstance(cand, dict):
                                pr = cand
                    except Exception:
                        pass
                nm = str(pr.get("name") or "")
                pin = str(pr.get("in") or "")
                key = (nm, pin)
                if key in seen:
                    # overwrite previous entry with op-level
                    for i, mp in enumerate(merged_params):
                        if (mp.get("name"), mp.get("in")) == key:
                            merged_params[i] = pr
                            break
                else:
                    merged_params.append(pr)
                    seen.add(key)
            # Request body (application/json) schema summary
            req_body = None
            if isinstance(op.get("requestBody"), dict):
                rb = op["requestBody"]
                if "$ref" in rb and isinstance(rb.get("$ref"), str):
                    resolved = _resolve_local_ref(str(rb["$ref"]), spec)
                    if isinstance(resolved, dict):
                        rb = resolved
                schema = None
                try:
                    content = rb.get("content") or {}
                    app_json = content.get("application/json") or {}
                    schema = app_json.get("schema")
                except Exception:
                    schema = None
                req_body = {
                    "required": bool(rb.get("required", False)),
                    "schema": schema,
                }
            # Response schemas summary (per status code)
            responses = {}
            if isinstance(op.get("responses"), dict):
                for status, resp in op["responses"].items():
                    if not isinstance(resp, dict):
                        continue
                    ct = []
                    schema = None
                    try:
                        content = resp.get("content") or {}
                        if isinstance(content, dict) and content:
                            ct = list(content.keys())
                            # Prefer JSON schema when present
                            if "application/json" in content and isinstance(
                                content["application/json"], dict
                            ):
                                schema = content["application/json"].get("schema")
                            else:
                                # Pick first content type with schema
                                for _, desc in content.items():
                                    if isinstance(desc, dict) and "schema" in desc:
                                        schema = desc.get("schema")
                                        break
                    except Exception:
                        pass
                    responses[str(status)] = {
                        "contentTypes": ct,
                        "schema": schema,
                    }
            tags = op.get("tags") if isinstance(op.get("tags"), list) else []
            operation_server = _first_server_url(op.get("servers")) or item_server
            ops[str(op_id)] = {
                "method": method.upper(),
                "path": path,
                "server": operation_server or "",
                "parameters": merged_params,
                "requestBody": req_body,
                "responses": responses,
                "tags": tags,
                "summary": summary,
                # Carry components so caller can resolve $ref & allOf
                "components": components,
            }
    return ops


def extract_operation_infos(spec: Dict[str, Any]) -> Dict[str, OpenAPIOperationInfo]:
    """Typed variant of extract_operations.

    Returns mapping opId -> OpenAPIOperationInfo.
    """
    raw = extract_operations(spec)
    out: Dict[str, OpenAPIOperationInfo] = {}
    for op_id, info in raw.items():
        try:
            out[op_id] = OpenAPIOperationInfo(
                operation_id=op_id,
                method=str(info.get("method", "")).upper(),
                path=str(info.get("path", "")),
                server=str(info.get("server") or "") or None,
                tags=list(info.get("tags") or []),
                summary=info.get("summary") or None,
                parameters=list(info.get("parameters") or []),
                requestBody=(info.get("requestBody") or None),
                responses=dict(info.get("responses") or {}),
                components=(info.get("components") or None),
            )
        except Exception:
            # Best-effort; skip invalid
            continue
    return out
