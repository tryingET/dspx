from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Mapping
from pathlib import Path
import os
import sqlite3

import httpx
from bs4 import BeautifulSoup
import pandas as pd
from duckduckgo_search import DDGS
from urllib.parse import urlparse
from dspx.tools.descriptors import ToolDescriptor
from dspx.tools.openapi.models import OpenAPIOperationInfo


_TOOLS: Dict[str, Callable[..., Any]] = {}
_TOOL_DESCRIPTORS: Dict[str, ToolDescriptor] = {}


def register_tool(
    name: str, func: Callable[..., Any], descriptor: Optional[ToolDescriptor] = None
) -> None:
    # Wrap with policy enforcement
    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        # Import policy lazily; if unavailable, skip enforcement
        try:
            from dspx.policy import (
                check_tool_allowed,
                apply_timeout_policy,
                check_capability as _check_cap,
            )
        except Exception:
            return func(*args, **kwargs)
        check_tool_allowed(name)
        # Enforce declared capability tags if present on the original function
        caps = getattr(func, "_dspx_capabilities", None)
        try:
            to_check = list(caps) if caps else []  # type: ignore[arg-type]
        except Exception:
            to_check = []
        for cap in to_check:
            _check_cap(str(cap))
        if kwargs:
            kwargs = apply_timeout_policy(kwargs)
        return func(*args, **kwargs)

    # Propagate DSPX metadata from the original function to the wrapper so
    # CLI layers can inspect tool properties (e.g., OpenAPI method/path) safely.
    try:
        for k, v in getattr(func, "__dict__", {}).items():
            if str(k).startswith("_dspx_"):
                setattr(_wrapped, k, v)
    except Exception:
        # Best-effort metadata propagation; ignore failures.
        pass

    _TOOLS[name] = _wrapped
    # Store descriptor
    if descriptor is None:
        try:
            caps = list(getattr(func, "_dspx_capabilities", []) or [])
        except Exception:
            caps = []
        try:
            desc = str(getattr(func, "_dspx_description", "") or "")
            if not desc:
                desc = None
        except Exception:
            desc = None
        kind = "builtin"
        openapi_info = None
        try:
            if bool(getattr(func, "_dspx_is_openapi_tool", False)):
                kind = "openapi"
                info = getattr(func, "_dspx_openapi_info", None)
                if isinstance(info, dict):
                    oi = dict(info)
                    op_id = getattr(func, "_dspx_openapi_operation_id", name)
                    oi["operation_id"] = op_id
                    openapi_info = OpenAPIOperationInfo(**oi)
        except Exception:
            pass
        descriptor = ToolDescriptor(
            name=name,
            capabilities=caps,
            description=desc,
            kind=kind,
            openapi=openapi_info,
        )
    _TOOL_DESCRIPTORS[name] = descriptor


def get_tool(name: str) -> Callable[..., Any]:
    return _TOOLS[name]


def available() -> List[str]:
    return sorted(_TOOLS.keys())


def available_descriptors() -> List[ToolDescriptor]:
    return [
        _TOOL_DESCRIPTORS[name]
        for name in sorted(_TOOL_DESCRIPTORS.keys())
        if name in _TOOLS
    ]


def get_descriptor(name: str) -> ToolDescriptor:
    return _TOOL_DESCRIPTORS[name]


def ensure_default_tools() -> None:
    if "web_search" not in _TOOLS:
        try:
            setattr(_web_search, "_dspx_capabilities", ["network.read"])
            setattr(
                _web_search,
                "_dspx_description",
                "DuckDuckGo text search (network.read)",
            )
        except Exception:
            pass
        register_tool("web_search", _web_search)
    if "web_fetch" not in _TOOLS:
        try:
            setattr(_web_fetch, "_dspx_capabilities", ["network.read"])
            setattr(
                _web_fetch,
                "_dspx_description",
                "HTTP GET a URL and return status/headers/text (network.read)",
            )
        except Exception:
            pass
        register_tool("web_fetch", _web_fetch)
    if "web_scrape" not in _TOOLS:
        try:
            setattr(_web_scrape, "_dspx_capabilities", ["network.read"])
            setattr(
                _web_scrape,
                "_dspx_description",
                "Fetch a page and extract text or by CSS selector (network.read)",
            )
        except Exception:
            pass
        register_tool("web_scrape", _web_scrape)
    if "data_preview" not in _TOOLS:
        try:
            setattr(_data_preview, "_dspx_capabilities", ["filesystem.read"])
            setattr(
                _data_preview,
                "_dspx_description",
                "Preview CSV/JSON/Parquet schema and head (filesystem.read)",
            )
        except Exception:
            pass
        register_tool("data_preview", _data_preview)
    if "repo_summary" not in _TOOLS:
        try:
            setattr(_repo_summary, "_dspx_capabilities", ["filesystem.read"])
            setattr(
                _repo_summary,
                "_dspx_description",
                "Lightweight repository summary from local files (filesystem.read)",
            )
        except Exception:
            pass
        register_tool("repo_summary", _repo_summary)
    if "db_schema" not in _TOOLS:
        try:
            setattr(_db_schema, "_dspx_capabilities", ["filesystem.read"])
            setattr(
                _db_schema,
                "_dspx_description",
                "SQLite schema and tiny samples (filesystem.read)",
            )
        except Exception:
            pass
        register_tool("db_schema", _db_schema)
    if "kb_summary" not in _TOOLS:
        try:
            setattr(_kb_summary, "_dspx_capabilities", ["filesystem.read"])
            setattr(
                _kb_summary,
                "_dspx_description",
                "Summarize docs under a path (filesystem.read)",
            )
        except Exception:
            pass
        register_tool("kb_summary", _kb_summary)
    if "ontology_summary" not in _TOOLS:
        try:
            setattr(_ontology_summary, "_dspx_capabilities", ["filesystem.read"])
            setattr(
                _ontology_summary,
                "_dspx_description",
                "Synthesize domain model from code/docs (filesystem.read)",
            )
        except Exception:
            pass
        register_tool("ontology_summary", _ontology_summary)
    # OpenAPI dynamic registration helpers are available via register_openapi_operations


def register_openapi_operations(
    prefix: str,
    spec: Mapping[str, Any],
    *,
    allowed_hosts: Optional[Mapping[str, bool]] = None,
) -> List[str]:
    """Register OpenAPI operations as tools with a name prefix.

    Returns the list of registered tool names. Tools accept keyword args:
    - params: dict for path/query params
    - body: dict
    - headers: dict[str, str]
    - timeout: float
    - method/server/path: override defaults
    - client: optional httpx.Client (for testing)
    """
    from dspx.tools.openapi.loader import extract_operation_infos  # lazy import
    from dspx.tools.openapi.caller import call_operation
    from dspx.dtos import OpenAPICallRequest

    ops = extract_operation_infos(dict(spec))
    names: List[str] = []
    for op_id, op in ops.items():
        tool_name = f"{prefix}.{op_id}"

        def _make_tool(op_id: str, op_desc: OpenAPIOperationInfo):
            def _tool(
                *,
                params: Optional[Mapping[str, Any]] = None,
                body: Optional[Mapping[str, Any]] = None,
                headers: Optional[Mapping[str, str]] = None,
                timeout: Optional[float] = None,
                method: Optional[str] = None,
                server: Optional[str] = None,
                path: Optional[str] = None,
                client: Optional[httpx.Client] = None,
            ) -> Any:
                req = OpenAPICallRequest(
                    operation_id=op_id,
                    method=method,
                    server=server,
                    path=path,
                    params=dict(params or {}),
                    body=dict(body) if body is not None else None,
                    headers=dict(headers or {}),
                    timeout=timeout,
                )
                res = call_operation(
                    req,
                    operation=op_desc.model_dump(),
                    allowed_hosts=allowed_hosts,
                    client=client,
                )
                return res.body if res.body is not None else res.raw_text

            # Attach minimal metadata for safe CLI inspection (used for
            # destructive-op confirmations). These attributes are propagated
            # through register_tool to the stored wrapper.
            try:
                _tool._dspx_is_openapi_tool = True  # type: ignore[attr-defined]
                _tool._dspx_openapi_operation_id = op_id  # type: ignore[attr-defined]
                _tool._dspx_openapi_method = str(op_desc.method).upper()  # type: ignore[attr-defined]
                _tool._dspx_openapi_path = str(op_desc.path)  # type: ignore[attr-defined]
                _tool._dspx_openapi_server = str(op_desc.server or "")  # type: ignore[attr-defined]
                # Preserve a compact copy of operation info for describe
                _tool._dspx_openapi_info = op_desc.model_dump()  # type: ignore[attr-defined]
                if op_desc.summary:
                    _tool._dspx_description = str(op_desc.summary)  # type: ignore[attr-defined]
                # Capability tags used by the wrapper for policy gating
                if _tool._dspx_openapi_method in {"POST", "PUT", "PATCH", "DELETE"}:  # type: ignore[attr-defined]
                    _tool._dspx_capabilities = ["network.mutate"]  # type: ignore[attr-defined]
                else:
                    _tool._dspx_capabilities = ["network.read"]  # type: ignore[attr-defined]
            except Exception:
                pass

            return _tool

        # Create descriptor for registration
        desc = ToolDescriptor(
            name=tool_name,
            capabilities=["network.mutate"]
            if str(op.method).upper() in {"POST", "PUT", "PATCH", "DELETE"}
            else ["network.read"],
            description=op.summary or None,
            kind="openapi",
            openapi=op,
        )
        register_tool(tool_name, _make_tool(op_id, op), descriptor=desc)
        names.append(tool_name)
    return names


def _host_allowed(url: str, allowed_hosts: Optional[Mapping[str, bool]]) -> bool:
    if not allowed_hosts:
        return True
    host = urlparse(url).hostname or ""
    return bool(allowed_hosts.get(host, False))


def _web_fetch(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 15.0,
    allowed_hosts: Optional[Mapping[str, bool]] = None,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Fetch a URL and return status, headers subset, and text (truncated).

    - Enforces optional host allowlist via `allowed_hosts` mapping: {host: True}.
    - Accepts optional httpx.Client for testing.
    """
    # Capability: network.read
    try:
        from dspx.policy import check_capability as _cap
    except Exception:
        _cap = None  # type: ignore
    if _cap is not None:
        _cap("network.read")
    if not _host_allowed(url, allowed_hosts):
        raise PermissionError(f"Host not allowed for URL: {url}")

    close_client = False
    if client is None:
        client = httpx.Client(follow_redirects=True, timeout=timeout)
        close_client = True
    try:
        resp = client.get(url, headers=headers, timeout=timeout)
        text = resp.text
        max_len = 100_000
        if len(text) > max_len:
            text = (
                text[:max_len] + f"\n... [truncated {len(resp.text) - max_len} bytes]"
            )
        # Redact sensitive tokens in URL and headers
        try:
            from dspx.redaction import (
                redact_url as _redact_url,
                redact_headers as _redact_headers,
            )
        except Exception:

            def _redact_url(u: str) -> str:  # type: ignore
                return u

            def _redact_headers(h: Mapping[str, str]) -> Dict[str, str]:  # type: ignore
                return dict(h)

        return {
            "status_code": resp.status_code,
            "headers": _redact_headers(dict(resp.headers)),
            "text": text,
            "url": _redact_url(str(resp.url)),
        }
    finally:
        if close_client:
            client.close()


def _web_search(query: str, k: int = 5, safe: str = "moderate") -> List[Dict[str, Any]]:
    """DuckDuckGo text search. Returns list of {title, href, body}."""
    results: List[Dict[str, Any]] = []
    # Capability: network.read
    try:
        from dspx.policy import check_capability as _cap
    except Exception:
        _cap = None  # type: ignore
    if _cap is not None:
        _cap("network.read")
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=k, safesearch=safe):
                results.append(
                    {
                        "title": r.get("title"),
                        "href": r.get("href"),
                        "body": r.get("body"),
                    }
                )
    except Exception:
        # Gracefully degrade to empty results on network/captcha errors.
        results = []
    return results


def _web_scrape(
    url: str,
    *,
    selector: Optional[str] = None,
    timeout: float = 15.0,
    allowed_hosts: Optional[Mapping[str, bool]] = None,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Fetch a URL and extract text; optionally restrict via CSS selector."""
    # Capability: network.read is enforced by _web_fetch
    result = _web_fetch(
        url, timeout=timeout, allowed_hosts=allowed_hosts, client=client
    )
    html = result.get("text", "")
    soup = BeautifulSoup(html, "html.parser")
    if selector:
        elems = soup.select(selector)
        text = "\n\n".join(e.get_text(separator=" ", strip=True) for e in elems)
    else:
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        text = soup.get_text(separator=" ", strip=True)
    if len(text) > 100_000:
        text = text[:100_000] + "\n... [truncated]"
    return {
        "url": result.get("url"),
        "status_code": result.get("status_code"),
        "text": text,
    }


def _data_preview(path: str, *, nrows: int = 5) -> Dict[str, Any]:
    # Capability: filesystem.read
    try:
        from dspx.policy import check_capability as _cap
    except Exception:
        _cap = None  # type: ignore
    if _cap is not None:
        _cap("filesystem.read")
    """Preview a local data file (CSV, JSON, Parquet). Returns schema + head."""
    lower = path.lower()
    out: Dict[str, Any] = {"path": path}
    if lower.endswith(".csv"):
        df = pd.read_csv(path, nrows=nrows)
        out.update(
            {
                "type": "csv",
                "columns": df.columns.tolist(),
                "rows": df.head(nrows).to_dict(orient="records"),
            }
        )
    elif lower.endswith(".json") or lower.endswith(".jsonl"):
        try:
            df = pd.read_json(path, lines=True, nrows=nrows)
        except ValueError:
            df = pd.read_json(path)
        out.update(
            {
                "type": "json",
                "columns": df.columns.tolist(),
                "rows": df.head(nrows).to_dict(orient="records"),
            }
        )
    elif lower.endswith(".parquet"):
        df = pd.read_parquet(path)
        out.update(
            {
                "type": "parquet",
                "columns": df.columns.tolist(),
                "rows": df.head(nrows).to_dict(orient="records"),
            }
        )
    else:
        out.update(
            {
                "type": "unknown",
                "error": "Unsupported file extension",
            }
        )
    return out


def _read_head(path: Path, nbytes: int = 2000) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            return f.read(nbytes)
    except Exception:
        return ""


def _repo_summary(root: str = ".", max_files: int = 20, depth: int = 2) -> str:
    # Capability: filesystem.read
    try:
        from dspx.policy import check_capability as _cap
    except Exception:
        _cap = None  # type: ignore
    if _cap is not None:
        _cap("filesystem.read")
    """Return a lightweight repository summary for context building.

    - Lists top-level dirs/files
    - Reads heads of common metadata files and a few code files
    - Skips heavy dirs (.git, .venv, submodules)
    """
    base = Path(root).resolve()
    skip = {".git", ".venv", "venv", "node_modules", "submodules", "__pycache__"}
    parts: List[str] = []
    parts.append(f"Repo: {base}")
    # Top-level contents
    top = [p.name for p in base.iterdir() if p.is_dir() and p.name not in skip]
    files = [p.name for p in base.iterdir() if p.is_file()]
    parts.append("Top-level dirs: " + ", ".join(sorted(top)[:30]))
    parts.append("Top-level files: " + ", ".join(sorted(files)[:30]))

    candidates: List[Path] = []
    preferred = [
        "README.md",
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "Justfile",
        "config.toml",
    ]
    for name in preferred:
        p = base / name
        if p.exists():
            candidates.append(p)

    # Walk a little to pick a few .py and .md files
    picked = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dp = Path(dirpath)
        # Limit depth
        try:
            rel = dp.relative_to(base)
            depth_len = len(rel.parts)
        except Exception:
            depth_len = 0
        if depth_len > depth:
            continue
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if fn.startswith("."):
                continue
            if fn.endswith(".py") or fn.endswith(".md"):
                p = dp / fn
                if p not in candidates:
                    candidates.append(p)
                    picked += 1
                    if picked >= max_files:
                        break
        if picked >= max_files:
            break

    # Emit heads
    for p in candidates[:max_files]:
        head = _read_head(p)
        if head.strip():
            parts.append(f"\n# {p.relative_to(base)}\n{head.strip()}\n")
    return "\n".join(parts)


def _detect_sqlite_url(url: Optional[str]) -> Optional[Path]:
    if url and url.startswith("sqlite:///"):
        return Path(url[len("sqlite///") :])
    if url and url.startswith("sqlite:"):
        # sqlite:path or sqlite:path?mode=rw — not fully supported; try naive strip
        return Path(url.split(":", 1)[1])
    # Try env or default location
    env = os.getenv("DATABASE_URL") or os.getenv("SIXE_DB_URL")
    if env and env.startswith("sqlite///"):
        return Path(env[len("sqlite///") :])
    if env and env.startswith("sqlite:"):
        return Path(env.split(":", 1)[1])
    default = Path("generated/sixe.db")
    if default.exists():
        return default
    return None


def _db_schema(
    url: Optional[str] = None, *, max_tables: int = 25, sample_rows: int = 3
) -> str:
    # Capability: filesystem.read (for SQLite files)
    try:
        from dspx.policy import check_capability as _cap
    except Exception:
        _cap = None  # type: ignore
    if _cap is not None:
        _cap("filesystem.read")
    """Return a compact DB schema + tiny samples.

    Currently supports SQLite. For other engines, returns a stub unless
    accessed via a future SQLAlchemy-based implementation.
    """
    p = _detect_sqlite_url(url)
    if p is None or not p.exists():
        return (
            "[db_schema] No SQLite database detected. Set DATABASE_URL or SIXE_DB_URL."
        )
    try:
        conn = sqlite3.connect(str(p))
    except Exception as e:
        return f"[db_schema] Failed to open SQLite: {e}"
    parts: List[str] = [f"SQLite DB: {p}"]
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [r[0] for r in cur.fetchall()]
        if not tables:
            parts.append("No user tables found.")
        for t in tables[:max_tables]:
            parts.append(f"\n## table: {t}")
            # columns
            try:
                cur.execute(f"PRAGMA table_info({t})")
                cols = cur.fetchall()
                col_line = ", ".join([f"{c[1]}:{c[2]}" for c in cols])
                parts.append(f"columns: {col_line}")
            except Exception:
                pass
            # sample
            try:
                cur.execute(f"SELECT * FROM {t} LIMIT {int(sample_rows)}")
                rows = cur.fetchall()
                parts.append(f"sample_rows: {rows}")
            except Exception:
                parts.append("sample_rows: <error>")
    finally:
        conn.close()
    return "\n".join(parts)


def _kb_summary(root: str = ".", *, max_files: int = 12) -> str:
    # Capability: filesystem.read
    try:
        from dspx.policy import check_capability as _cap
    except Exception:
        _cap = None  # type: ignore
    if _cap is not None:
        _cap("filesystem.read")
    base = Path(root).resolve()
    dirs = [
        base / "kb",
        base / "knowledge",
        base / "docs",
        base / "doc",
    ]
    exts = {".md", ".txt", ".rst"}
    parts: List[str] = []
    for d in dirs:
        if not d.exists():
            continue
        parts.append(f"Knowledge dir: {d}")
        files = [p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in exts]
        for p in files[:max_files]:
            head = _read_head(p)
            if head.strip():
                parts.append(f"\n# {p.relative_to(base)}\n{head.strip()}\n")
    return "\n".join(parts) if parts else "[kb_summary] No local knowledge files found."


def _ontology_summary(root: str = ".", *, max_files: int = 8) -> str:
    # Capability: filesystem.read
    try:
        from dspx.policy import check_capability as _cap
    except Exception:
        _cap = None  # type: ignore
    if _cap is not None:
        _cap("filesystem.read")
    base = Path(root).resolve()
    dirs = [
        base / "ontology",
        base / "ontologies",
        base / "kb",
    ]
    exts = {".ttl", ".rdf", ".owl"}
    parts: List[str] = []
    for d in dirs:
        if not d.exists():
            continue
        parts.append(f"Ontology dir: {d}")
        files = [p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in exts]
        for p in files[:max_files]:
            head = _read_head(p)
            if head.strip():
                parts.append(f"\n# {p.relative_to(base)}\n{head.strip()}\n")
    return "\n".join(parts) if parts else "[ontology_summary] No ontology files found."
