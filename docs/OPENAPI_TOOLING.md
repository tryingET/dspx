OpenAPI Tooling (MVP)
=====================

Purpose
-------
Enable safe access to HTTP APIs described by OpenAPI as first‑class tools integrated into DSPx workflows and the unified CLI.

What’s implemented
------------------
- Loader: `dspx.tools.openapi.load_spec(path)`
  - Loads a local JSON or YAML (via PyYAML) OpenAPI v3 spec.
- Operation extraction: `extract_operations(spec)`
  - Returns a dict of `{operationId: {method, path, server, parameters}}`.
- Caller: `call_operation(request, operation, allowed_hosts, client=None)`
  - Builds URL with path params, passes remaining as query, sends with `httpx`.
  - Enforces host allowlist and validates required path params.
  - Returns `OpenAPICallResult(status_code, body, headers, raw_text)`.
- Registry integration: `register_openapi_operations(prefix, spec, allowed_hosts=None)`
  - Registers tools named `<prefix>.<operationId>` in `ToolRegistry`.
  - Each tool accepts kwargs: `params`, `body`, `headers`, `timeout`, `method`, `server`, `path`.

CLI
---
- List operations in a spec
  - `dspx tools openapi ops SPEC.json|yaml`
- Call an operation directly (one‑shot)
  - `dspx tools openapi call --spec SPEC --op OPID --allow-host api.example.com --params k=v,...`
- Persist a mapping file for a prefix (for workflows/env setup)
  - `dspx tools openapi load -p gh --spec /abs/github.json --allow-host api.github.com`
  - Writes `generated/openapi/gh.json` with `{prefix,spec,allow_host}`.
- Print shell exports from mapping (optional convenience)
  - `dspx tools openapi env -p gh`

Mermaid integration
-------------------
- Label a process node to call an operation: `openapi:<prefix>.<operationId>`
- The generated runtime auto‑registers toolpacks for prefixes used in the graph:
  - It reads env vars if available: `DSPX_OPENAPI_SPEC_<PREFIX>`, `DSPX_OPENAPI_HOST_<PREFIX>`.
  - Otherwise it falls back to mapping files: `generated/openapi/<prefix>.json` or `openapi/<prefix>.json`.
  - Optional env overrides for mapping discovery:
    - `DSPX_OPENAPI_MAP_<PREFIX>` for a specific file.
    - `DSPX_OPENAPI_MAP_DIR` for a directory of mapping files.
- Node input format (from upstream context):
  - JSON envelope: `{ "params": {...}, "body": {...}, "headers": {...}, "timeout": 10 }`
  - Or space/newline separated `key=value` tokens (for simple GETs).

Policy & Safety
---------------
- Host allowlists enforced at call time.
- Sizes and timeouts are bounded by `httpx` configuration; extend as needed.
- Secrets should be injected via env/CI secrets; logs should avoid printing sensitive headers.

Testing
-------
- Use `httpx.MockTransport` for deterministic unit tests.
- Validate that required path params are supplied; we raise ValueError if missing.

Roadmap
-------
1) Request validation vs. schema (query/body) with clearer errors.
2) Optional URL loading for specs (with allowlists and caching).
3) MLflow logging and redaction for OpenAPI calls.
4) Typed client generation and richer CLI ergonomics.
