OpenAPI Tooling (Proposed)
==========================

Purpose
-------
Enable safe, typed access to HTTP APIs described by OpenAPI, as first‑class tools integrated into Agent/Service workflows.

Components
----------
- Loader: `openapi.load(spec_url_or_path, name)`
  - Parses OpenAPI v3, normalizes operations, resolves `$ref`s (best‑effort), and registers tools under `ToolRegistry` with IDs `name.opId`.
  - Records base URL(s), security schemes, and spec version for tracing.
- Caller: `openapi.call(name, opId, params, body, auth)`
  - Validates request per schema; applies path/query/header/body; executes via `httpx` with timeouts.
  - Enforces host allowlist and per‑call budgets; redacts secrets in logs.
- DTOs
  - `OpenAPISpecDescriptor(name, base_urls, security, version)`
  - `OpenAPIOperation(id, method, path, in_schema, out_schema)`
  - `OpenAPICallRequest(opId, params, body, auth)` / `OpenAPICallResult(status, headers, body)`

CLI
---
```
# Load a spec
dspx tools openapi load --spec https://api.github.com/openapi.json --name gh

# List operations
dspx tools openapi ops --name gh | head

# Call an operation (read‑only)
dspx tools openapi call --name gh --op repos/listForUser --params '{"username":"octocat"}'
```

Policy & Safety
---------------
- `--allow-host` required for remote specs/requests; reject unknown hosts.
- Budgets and timeouts per call; exponential backoff + retry for idempotent GETs.
- Token handling via env or OS keychain; redact in logs; never persist secrets.
- Opt‑in logging of responses; cap sizes and redact PII.

Integration
-----------
- AgentService: treat OpenAPI operations as tools (by capability: network, read‑only, destructive).
- MermaidWorkflowService: allow node labels like `op:gh.repos/listForUser` to bind to operations.
- CodegenService: scaffold typed client wrappers for frequently used operations.

Testing
-------
- Use recorded fixtures or mock `httpx` for deterministic tests.
- Contract tests to ensure opId → request mapping stays valid across spec updates.

Roadmap
-------
1) Minimal loader/caller with host allowlists + tracing metadata.
2) Generator: Python client wrappers with types (pydantic/dataclasses).
3) OAuth helpers for common flows; token caching; device code flow CLI.
4) Spec caching + pinning; `dspx tools openapi update` with diff preview.
