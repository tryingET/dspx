# AK-800: Add Request Body Size Limits Middleware

**Date**: 2026-04-05
**Task**: AK-800 — security(TG25): add request body size limits middleware to dspx server
**Status**: Complete

## Summary

Added `BodySizeLimitMiddleware` to the DSPx server that rejects requests whose `Content-Length` exceeds a configurable limit before the body is read. This prevents oversized payloads from reaching route handlers and consuming server resources.

## Changes

### Middleware (`packages/dspx-core/src/dspx/server/security.py`)
- Added `BodySizeLimitConfig` dataclass with `from_env()` class method:
  - `DSPX_BODY_SIZE_LIMIT_ENABLED` (default: `1`) — toggle the middleware
  - `DSPX_MAX_BODY_SIZE` (default: `10MB`) — configurable limit with human-friendly suffix parsing (`k`, `kb`, `m`, `mb`, `g`, `gb`)
- Added `_parse_size()` helper for parsing human-friendly size strings
- Added `BodySizeLimitMiddleware(BaseHTTPMiddleware)`:
  - Rejects `Content-Length` > limit with `413 Payload Too Large`
  - Rejects non-numeric `Content-Length` with `400 Bad Request`
  - Standardized JSON error responses matching the existing server error contract
- Extended `_Stats` with `status_413` counter

### Wiring (`packages/dspx-core/src/dspx/server/app.py`)
- Imported `BodySizeLimitConfig`, `BodySizeLimitMiddleware`
- Installed middleware in `create_app()` after the rate limiter

### Docs (`docs/SERVER.md`)
- Documented the body size limit configuration, default, suffixes, and error response

### Tests (`tests/test_server_body_size.py`)
- 21 new tests covering:
  - `_parse_size` unit tests (plain int, suffixes, case insensitivity, errors)
  - `BodySizeLimitConfig.from_env` (defaults, custom, disabled, negative rejection)
  - Middleware integration (small body passes, oversized rejected, invalid Content-Length, zero limit, disabled bypass, exact limit, all endpoints, GET not blocked)

### Fixups (`tests/test_server_metrics.py`)
- Updated snapshot assertions to include the new `status_413` counter

## Validation

- `ruff format` ✅
- `ruff check` ✅
- `ty check` ✅
- All 55 server tests pass ✅
- `./scripts/ci/smoke.sh` ✅ (work-items projection in sync)

## Design Decisions

1. **Content-Length only**: The middleware checks `Content-Length` header, not the actual body stream. This is the standard approach for pre-read rejection in ASGI middleware and avoids buffering the entire body.
2. **Default 10 MiB**: Chosen as a generous default for DSPy template/module generation requests while still bounding memory exposure.
3. **Enabled by default**: Follows the fail-closed security posture established in TG24/TG25 (AK-797, AK-798, AK-799).
4. **Human-friendly size parsing**: Supports `k`/`kb`/`m`/`mb`/`g`/`gb` suffixes for operator convenience.
