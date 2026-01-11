DSPx Server (FastAPI) — Auth, Rate Limits, Proxies
==================================================

Overview
--------
`dspx-server` is a small FastAPI app exposing typed endpoints for DSPx services:

- `POST /signature` — generate a signature via templates
- `POST /module` — generate a module via templates
- `POST /mermaid` — generate DSPy programs from a Mermaid diagram

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
- Single token: `DSPX_SERVER_TOKEN='s3cr3t'`
- Multiple tokens: `DSPX_SERVER_TOKENS='tok1,tok2'`
- Token file: `DSPX_SERVER_TOKEN_FILE=/path/tokens.txt` (one per line)
- Require auth: `DSPX_AUTH_REQUIRED=1` (defaults on when any token present)
- Client header: `Authorization: Bearer <token>`

Rate limiting
-------------
- Enable: `DSPX_RATE_LIMIT_ENABLED=1`
- Default cap (applies to each identity): `DSPX_RATE_LIMIT_DEFAULT='60/min,10/sec'`
- Per-path caps (JSON): `DSPX_RATE_LIMIT_PATHS='{"POST /module":"5/min"}'`
- Identity source: `DSPX_RATE_LIMIT_IDENTITY=token` (default) or `ip`
- Trusted proxies: `DSPX_TRUSTED_PROXIES='10.0.0.0/8,192.168.0.0/16,127.0.0.0/8'`
- Global caps (across identities): `DSPX_RATE_LIMIT_GLOBAL='100/min'`
- Per-path global caps (JSON): `DSPX_RATE_LIMIT_GLOBAL_PATHS='{"/signature":"30/min"}'`

Errors (standardized JSON)
-------------------------
- Unauthorized: `{ "error": "unauthorized", "detail": "missing bearer token", "status": 401 }`
- Rate limited: `{ "error": "rate_limited", "detail": "limit exceeded", "status": 429 }`

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
