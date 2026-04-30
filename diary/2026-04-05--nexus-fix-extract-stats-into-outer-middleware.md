---
summary: "Diary entry: Nexus Fix: Extract Stats into Outer Middleware."
read_when:
  - "You need the historical implementation context captured in this diary entry."
  - "You are reviewing or extending work related to Nexus Fix: Extract Stats into Outer Middleware."
type: "diary"
---

# Nexus Fix: Extract Stats into Outer Middleware

**Date**: 2026-04-05
**Trigger**: Deep adversarial review of AK-797/798/799/800
**Status**: Complete

## Summary

Extracted request/response statistics tracking into a dedicated `RequestStatsMiddleware` that runs as the outermost middleware, fixing three bugs found in the adversarial review:

1. **`status_413` always zero** — Body-size 413 rejections were invisible in `/metrics` because the body-size middleware runs before the rate limiter (which owned stats tracking) and short-circuits without incrementing any counter.
2. **`requests_total` undercount** — Body-size-rejected requests were never counted because they short-circuited before the rate limiter's `stats.requests_total += 1`.
3. **TOCTOU race on `_global` buckets** — `self._global.get(key_g)` was read outside the lock, then written inside the lock, allowing concurrent threads to both see `None`, create separate bucket lists, and overwrite each other.

## Root Cause

Middleware is added in Starlette in reverse execution order. `BodySizeLimitMiddleware` was added after `RateLimitMiddleware`, making it the outermost wrapper. It short-circuited on 413 before the rate limiter ever ran, so the rate limiter's stats counters never fired. The fix was to extract stats tracking into a new outermost middleware that wraps both.

## Changes

### `packages/dspx-core/src/dspx/server/security.py`
- Added `RequestStatsMiddleware(BaseHTTPMiddleware)` — outermost middleware that increments `requests_total` on every request and tracks response status codes (401, 429, 413) after `call_next`.
- Removed `stats.requests_total += 1` from `RateLimitMiddleware.dispatch()`.
- Removed pre-response `stats.status_429 += 1` from both global and identity rate-limit paths.
- Removed post-response `stats.status_401 += 1` and `stats.status_429 += 1` from `RateLimitMiddleware.dispatch()`.
- Fixed TOCTOU race: moved `self._global.get(key_g)` read inside `self._lock` alongside the write.

### `packages/dspx-core/src/dspx/server/app.py`
- Imported `RequestStatsMiddleware`.
- Added `app.add_middleware(RequestStatsMiddleware)` as the last middleware (outermost in execution).

### `tests/test_server_body_size.py`
- Replaced `os.environ` direct mutation with `monkeypatch`-based factory fixture (`make_client`).
- Added `DSPX_METRICS_ENABLED` to the env-cleanup fixture.
- Added `test_body_size_rejection_counted_in_metrics` — nexus regression test that verifies `status_413` is counted in `/metrics`.

## Validation

- All 56 server tests pass ✅
- `ruff format` ✅
- `ruff check` ✅
- `ty check` ✅
- `./scripts/ci/smoke.sh` ✅

## Remaining Known Limitations

1. **Chunked transfer-encoding bypass**: `BodySizeLimitMiddleware` only checks `Content-Length`; `Transfer-Encoding: chunked` bypasses the limit. Future iteration should add stream-level checking.
2. **`_Stats` integer increments not atomic**: Under extreme concurrency, counts can drift. Acceptable for lightweight counters; fix would require per-counter locks on the hot path.
3. **`security.py` God Module**: Now ~660 lines with 8+ concerns. Future refactoring should split into separate modules (auth, rate-limit, body-size, stats).
