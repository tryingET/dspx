---
summary: "FastAPI server runtime, auth, rate limit, proxy, and metrics configuration."
read_when:
  - "You are modifying server endpoints, auth, rate limits, or deployment defaults."
  - "You need operational guidance for running dspx-server in dev or prod-like setups."
---

DSPx Server (FastAPI) — Auth, Rate Limits, Proxies
==================================================

Overview
--------
`dspx-server` is a small FastAPI app exposing typed endpoints for DSPx services:

- `POST /signature` — generate a signature via templates
- `POST /module` — generate a module via templates
- `POST /mermaid` — generate DSPy programs from a Mermaid diagram

By default, server-generated artifacts are persisted under `generated/server/` (override with `DSPX_SERVER_OUTPUT_DIR`).
Successful responses now return stable artifact references rooted at that directory:

- `/signature` and `/module` return `output_path`, `receipt_path`, and `output_hash`
- `/mermaid` returns `output_dir`, `manifest_path`, and `produced` artifact refs

Persistence truthfulness rules:
- `/signature` and `/module` degrade cleanly when artifact persistence fails by returning `null` refs but still returning the generated code plus `output_hash`
- `/mermaid` returns `artifact_persistence_failed` (`500`) when the generated directory cannot be persisted, because the response contract is the persisted artifact set itself

Run
---
Use Granian (recommended) or any ASGI server. Defaults can be overridden via `DSPX_SERVER_HOST` and `DSPX_SERVER_PORT`.

Options:

- Granian directly:

    granian --interface asgi --host 127.0.0.1 --port 33213 dspx.server.app:app

For Docker / remote access, bind `--host 0.0.0.0` and put auth + TLS in front (reverse proxy).

- Just recipe (convenient):

    just start
    # or
    just start host=0.0.0.0 port=33213

Auth (Bearer tokens)
--------------------
- Server auth is now **required by default**.
- Configure one of:
  - Single token: `DSPX_SERVER_TOKEN='s3cr3t'`
  - Multiple tokens: `DSPX_SERVER_TOKENS='tok1,tok2'`
  - Token file: `DSPX_SERVER_TOKEN_FILE=/path/tokens.txt` (one per line)
- Optional explicit override: `DSPX_AUTH_REQUIRED=0|1`
- Local-only dev bypass: `DSPX_AUTH_SKIP_FOR_DEV=1`
- Client header: `Authorization: Bearer <token>`

Fail-closed startup rule:
- if auth remains required and no tokens are configured, the server refuses to start
- `DSPX_AUTH_SKIP_FOR_DEV=1` is accepted only when `DSPX_SERVER_HOST` is explicitly set to `localhost` or a loopback address; the `dspx-server` launcher sets its default `localhost` bind into env before app creation
- use `DSPX_AUTH_SKIP_FOR_DEV=1` only for intentional local development bypasses, not for shared or production-like deployments

Mutation confirmation
---------------------
Set `DSPX_CONFIRM_MUTATIONS=1` to require `X-DSPX-Confirm: 1` on all mutating server endpoints:

- `POST /signature`
- `POST /module`
- `POST /mermaid`

When enabled, requests without that header fail closed with:
`{ "error": "confirmation_required", "detail": "Mutation requires confirmation header X-DSPX-Confirm: 1", "status": 403 }`

Rate limiting
-------------
- Enable: `DSPX_RATE_LIMIT_ENABLED=1`
- Default cap (applies to each identity): `DSPX_RATE_LIMIT_DEFAULT='60/min,10/sec'`
- Per-path caps (JSON): `DSPX_RATE_LIMIT_PATHS='{"POST /module":"5/min"}'`
- Identity source: `DSPX_RATE_LIMIT_IDENTITY=token` (default) or `ip`
- Trusted proxies: `DSPX_TRUSTED_PROXIES='10.0.0.0/8,192.168.0.0/16,127.0.0.0/8'`
- Global caps (across identities): `DSPX_RATE_LIMIT_GLOBAL='100/min'`
- Per-path global caps (JSON): `DSPX_RATE_LIMIT_GLOBAL_PATHS='{"/signature":"30/min"}'`

Metrics (optional)
------------------
The server can expose lightweight counters for health/debugging.

- Enable: `DSPX_METRICS_ENABLED=1`
- JSON: `GET /metrics`
- Prometheus text: `GET /metrics?format=prom` (or send `Accept: text/plain`), or `GET /metrics-prom`

Errors (standardized JSON)
-------------------------
- Unauthorized: `{ "error": "unauthorized", "detail": "missing bearer token", "status": 401 }`
- Confirmation required: `{ "error": "confirmation_required", "detail": "Mutation requires confirmation header X-DSPX-Confirm: 1", "status": 403 }`
- Rate limited: `{ "error": "rate_limited", "detail": "limit exceeded", "status": 429 }`
- Artifact persistence failure: `{ "error": "artifact_persistence_failed", "detail": "failed to persist <kind> artifacts: ...", "status": 500 }`

Trusted Proxies & X-Forwarded-For
---------------------------------
When `DSPX_TRUSTED_PROXIES` is set to CIDR ranges, the server derives the client IP from the `X-Forwarded-For` chain by picking the first address not in the trusted ranges; if none, it uses the first in the list. This enables correct identity detection behind reverse proxies.

Docker Compose Example
----------------------
  version: "3.9"
  services:
    dspx:
      image: ghcr.io/your-org/dspx:latest
      command: >
        granian --interface asgi --host 0.0.0.0 --port 33213 dspx.server.app:app
      environment:
        - DSPX_SERVER_TOKENS=tok1,tok2
        - DSPX_RATE_LIMIT_ENABLED=1
        - DSPX_RATE_LIMIT_DEFAULT=60/min,10/sec
        - DSPX_RATE_LIMIT_GLOBAL=200/min
        - DSPX_TRUSTED_PROXIES=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
      ports:
        - "33213:33213"

Notes
-----
- Limits are in-memory per-process. For multi-worker or multi-node deployments, add a distributed backend (e.g., Redis) in a future iteration.
- Logging is structured via the `dspx.server` logger with redacted Authorization.

Request body size limits
------------------------
The server rejects request bodies that exceed a configurable size limit.

- Enabled by default. Disable entirely: `DSPX_BODY_SIZE_LIMIT_ENABLED=0`
- Default cap: 10 MiB (`10485760` bytes)
- Override: `DSPX_MAX_BODY_SIZE=<value>`
  - Plain integer bytes: `DSPX_MAX_BODY_SIZE=5242880`
  - Human-friendly suffix: `DSPX_MAX_BODY_SIZE=5MB`, `DSPX_MAX_BODY_SIZE=1GB`, `DSPX_MAX_BODY_SIZE=512k`
  - Supported suffixes: `b`, `k`/`kb`, `m`/`mb`, `g`/`gb` (case-insensitive)
  - Suffix-based values must use an integer count; fractional values like `0.5k` or `1.5mb` are rejected explicitly

Fail-closed behavior:
- If `Content-Length` exceeds the limit, the server rejects with `413 Payload Too Large` before the request body is read
- Invalid `Content-Length` headers are rejected with `400 Bad Request`
- Duplicate `Content-Length` headers are rejected with `400 Bad Request`, even when duplicate values match
- Requests streamed without `Content-Length` are counted as ASGI body chunks are received and rejected with `413 Payload Too Large` once the configured limit is exceeded

Error response:
```json
{"error": "body_too_large", "detail": "request body of N bytes exceeds the M byte limit", "status": 413}
```
