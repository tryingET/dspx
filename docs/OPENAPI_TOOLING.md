---
summary: "OpenAPI toolpack behavior, validation coverage, and CLI integration details."
read_when:
  - "You are changing OpenAPI loading, validation, or call execution behavior."
  - "You are extending tools CLI or Mermaid/OpenAPI integration paths."
---

OpenAPI Tooling
===============

Overview
--------
OpenAPI‑described HTTP APIs are exposed as safe, policy‑aware tools that can be listed, described, and invoked via the unified `dspx` CLI and from generated workflows.

Key Features
------------
- Loader: `dspx.tools.openapi.load_spec(path_or_url)`
  - JSON and YAML (via PyYAML). URLs enforce per‑call host allowlists, fail closed on an explicit empty allowlist, and support on‑disk caching (`DSPX_OPENAPI_CACHE[=_1_]`, `DSPX_OPENAPI_CACHE_DIR`).
- Operation extraction: `extract_operation_infos(spec)`
  - Merges path‑level and op‑level params; captures method, path, server, tags, summary, requestBody schema, and response schemas.
- Caller: `call_operation(request, operation, allowed_hosts, client=None)`
  - Builds URL from path params; passes others as query; executes via `httpx`.
  - Validates required path/query params and enforces basic typing and enums.
  - Deep(er) JSON Schema validation for request bodies (see below).
  - Returns `OpenAPICallResult(status_code, body, headers, raw_text)`.
- Registry integration: `register_openapi_operations(prefix, spec, allowed_hosts=None)`
  - Registers `<prefix>.<operationId>` tools with capability tags and policy gates.
  - Works seamlessly with the root `dspx tools` flow and Mermaid.

CLI
---
- List operations: `dspx tools openapi ops SPEC --tags users,issues --json`
- Describe operation: `dspx tools openapi describe --spec SPEC --op OPID --json`
- Call operation: `dspx tools openapi call --spec SPEC --op OPID --allow-host api.example.com [--dry-run]`
- Persist mapping for prefixes: `dspx tools openapi load -p gh --spec /abs/github.json --allow-host api.github.com`
- Print shell exports from mapping: `dspx tools openapi env -p gh`

Mermaid Integration
-------------------
- Node label: `openapi:<prefix>.<operationId>`
- Runtime auto‑registers toolpacks from env or mapping files under `generated/openapi/`.
- Upstream input envelope for nodes: `{ "params": {...}, "body": {...}, "headers": {...}, "timeout": 10 }`.

Policy & Safety
---------------
- Host allowlists at call time; mutating methods (POST/PUT/PATCH/DELETE) require explicit allowance, and an explicit empty allowlist denies all URL-based access.
- Capability gating for `network.read` vs `network.mutate`. Optional dry‑run prints a redacted preview.
- Redaction covers URL userinfo and sensitive headers; MLflow logging integrates with standard tags.

Validation Coverage (Current)
-----------------------------
- Query params: required flags; type checks for `integer|number|boolean|array`; array item types; enum constraints.
- Request bodies (application/json):
  - Object: required properties, per‑property types (`string|integer|number|boolean|array|object`), and enums.
  - Array: item validation for primitives and objects (arrays of objects supported).
  - Nested objects: validates nested required/primitive types recursively.
  - `$ref`: resolves local refs under `#/components/schemas/*` (request bodies, including `allOf|oneOf|anyOf` branches) and `#/components/parameters/*` (path/query params).
  - `allOf`: preserves branch semantics during validation, resolves local refs inside each branch, and keeps branch-local constraints such as `required` and `additionalProperties` instead of flattening them into a shallow object merge.
  - Combinators: `oneOf` enforces exactly one matching branch, while `anyOf` requires at least one matching branch.
  - Bounds: `minLength|maxLength|pattern` for strings; `minimum|maximum|exclusiveMinimum|exclusiveMaximum` for numbers/integers (including OpenAPI 3.1 numeric exclusive thresholds); `minItems|maxItems` for arrays.
  - Objects: `minProperties|maxProperties` and `additionalProperties` (false rejects unknown keys; schema validates extras).
  - Nullable: OpenAPI `nullable: true` and JSON Schema `type: ["...", "null"]` accept `null` values.
  - Numeric: `multipleOf` (best-effort float-safe check).
  - Const: `const` (exact match).

Limitations (Deliberate)
------------------------
- No remote `$ref` resolution (only local `#/components/...`).
- Schema-composition support is still conservative: DSPx validates resolved `allOf|oneOf|anyOf` branches plus enclosing constraints, but it does not attempt full schema normalization or advanced conflict explanation across deeply composed branches.
- No advanced constraints (`format`, `not`, tuple-typed arrays, etc.).
- Arrays with tuple typing (`items: [..]`) are treated as unconstrained.
- Only `application/json` request bodies are validated.

Examples
--------
- Enum query with array:

  dspx tools openapi call --spec spec.yaml --op search \
    --allow-host api.example.com \
    --params '{"mode":"any","ids":[1,2]}'

- Array of objects body:

  dspx tools openapi call --spec spec.yaml --op bulkCreate \
    --allow-host api.example.com \
    --body '{"items":[{"id":1,"meta":{"tag":"new"}}]}'

Roadmap
-------
- More complete `$ref` support (response schemas; additional component locations; optional remote refs).
- Richer schema-composition conflict diagnostics and broader composition coverage.
- Deeper nested arrays/objects with numeric/string bounds.
- Expanded response schema summaries and example generation.
