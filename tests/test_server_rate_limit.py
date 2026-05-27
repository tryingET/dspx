from __future__ import annotations

import asyncio
import ipaddress
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

from dspx.server.app import create_app
from dspx.server.security import (
    Rate,
    RateLimitConfig,
    RateLimitMiddleware,
    parse_rate_spec,
)


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch):
    for k in [
        "DSPX_SERVER_TOKEN",
        "DSPX_SERVER_TOKENS",
        "DSPX_SERVER_TOKEN_FILE",
        "DSPX_AUTH_REQUIRED",
        "DSPX_AUTH_SKIP_FOR_DEV",
        "DSPX_RATE_LIMIT_ENABLED",
        "DSPX_RATE_LIMIT_DEFAULT",
        "DSPX_RATE_LIMIT_PATHS",
        "DSPX_RATE_LIMIT_IDENTITY",
        "DSPX_TRUSTED_PROXIES",
    ]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DSPX_AUTH_SKIP_FOR_DEV", "1")


def _client() -> TestClient:
    return TestClient(create_app())


def _rate_limit_only_client(config: RateLimitConfig) -> TestClient:
    app = FastAPI()
    app.add_middleware(cast(Any, RateLimitMiddleware), config=config)

    @app.post("/module")
    def _module() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/signature")
    def _signature() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


def _identity_request(client_host: str, xff: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("utf-8")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/signature",
        "raw_path": b"/signature",
        "query_string": b"",
        "headers": headers,
        "client": (client_host, 50000),
        "server": ("testserver", 80),
    }
    return Request(scope)


def _ip_identity_middleware(*trusted: str) -> RateLimitMiddleware:
    return RateLimitMiddleware(
        FastAPI(),
        config=RateLimitConfig(
            enabled=True,
            default=[Rate(1, 1.0)],
            per_path={},
            identity="ip",
            trusted_proxies=[ipaddress.ip_network(v, strict=False) for v in trusted],
            global_default=[],
            global_per_path={},
        ),
    )


def test_rate_limit_by_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_SERVER_TOKEN", "tok")
    monkeypatch.setenv("DSPX_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("DSPX_RATE_LIMIT_DEFAULT", "2/sec")
    c = _client()
    h = {"Authorization": "Bearer tok"}
    r1 = c.post("/signature", json={"prompt": "p"}, headers=h)
    r2 = c.post("/signature", json={"prompt": "p"}, headers=h)
    r3 = c.post("/signature", json={"prompt": "p"}, headers=h)
    assert r1.status_code == 200 and r2.status_code == 200 and r3.status_code == 429
    assert r3.json().get("error") == "rate_limited"


def test_rate_limit_by_token_accepts_lowercase_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_SERVER_TOKEN", "tok")
    monkeypatch.setenv("DSPX_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("DSPX_RATE_LIMIT_DEFAULT", "1/sec")
    c = _client()
    h = {"Authorization": "bearer tok"}
    r1 = c.post("/signature", json={"prompt": "p"}, headers=h)
    r2 = c.post("/signature", json={"prompt": "p"}, headers=h)
    assert r1.status_code == 200 and r2.status_code == 429


def test_rate_limit_by_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("DSPX_RATE_LIMIT_DEFAULT", "2/sec")
    monkeypatch.setenv("DSPX_RATE_LIMIT_IDENTITY", "ip")
    c = _client()
    r1 = c.post("/signature", json={"prompt": "p"})
    r2 = c.post("/signature", json={"prompt": "p"})
    r3 = c.post("/signature", json={"prompt": "p"})
    assert r1.status_code == 200 and r2.status_code == 200 and r3.status_code == 429
    assert r3.json().get("error") == "rate_limited"


def test_trusted_proxy_uses_xff_for_identity() -> None:
    middleware = _ip_identity_middleware("127.0.0.0/8")
    request = _identity_request("127.0.0.1", "1.2.3.4, 127.0.0.1")

    ident, ident_kind = middleware._identity(request)

    assert ident == "ip:1.2.3.4"
    assert ident_kind == "ip"


def test_untrusted_proxy_ignores_xff_for_identity() -> None:
    middleware = _ip_identity_middleware("127.0.0.0/8")
    request = _identity_request("198.51.100.10", "1.2.3.4, 127.0.0.1")

    ident, ident_kind = middleware._identity(request)

    assert ident == "ip:198.51.100.10"
    assert ident_kind == "ip"


def test_rate_limit_per_path_override() -> None:
    c = _rate_limit_only_client(
        RateLimitConfig(
            enabled=True,
            default=[Rate(10, 1.0)],
            per_path={"POST /module": [Rate(1, 1.0)]},
            identity="token",
            trusted_proxies=[],
            global_default=[],
            global_per_path={},
        )
    )
    h = {"Authorization": "Bearer tok"}
    r1 = c.post("/module", headers=h)
    r2 = c.post("/module", headers=h)
    assert r1.status_code == 200 and r2.status_code == 429
    # Signature should still be under default limit
    ok = c.post("/signature", headers=h)
    assert ok.status_code == 200


def test_rate_limit_from_env_fails_closed_on_invalid_path_mapping() -> None:
    with pytest.raises(ValueError):
        RateLimitConfig.from_env(
            {
                "DSPX_RATE_LIMIT_ENABLED": "1",
                "DSPX_RATE_LIMIT_PATHS": '{"POST /module": "bad-spec"}',
            }
        )


def test_global_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # Global limit of 2/sec, identity rules allow high throughput
    monkeypatch.setenv("DSPX_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("DSPX_RATE_LIMIT_GLOBAL", "2/sec")
    monkeypatch.setenv("DSPX_RATE_LIMIT_DEFAULT", "100/sec")
    c = _client()
    r1 = c.post("/signature", json={"prompt": "p"})
    r2 = c.post("/signature", json={"prompt": "p"})
    r3 = c.post("/signature", json={"prompt": "p"})
    assert r1.status_code == 200 and r2.status_code == 200 and r3.status_code == 429


def test_rate_specs_reject_fractional_zero_and_negative_counts() -> None:
    for spec in ("1.5/sec", "0/sec", "-1/sec"):
        with pytest.raises(ValueError, match="positive integer"):
            parse_rate_spec(spec)


def test_valid_token_identity_is_hashed() -> None:
    middleware = RateLimitMiddleware(
        FastAPI(),
        config=RateLimitConfig(
            enabled=True,
            default=[Rate(1, 1.0)],
            per_path={},
            identity="token",
            trusted_proxies=[],
            global_default=[],
            global_per_path={},
            valid_tokens=frozenset({"tok"}),
        ),
    )
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/signature",
        "raw_path": b"/signature",
        "query_string": b"",
        "headers": [(b"authorization", b"Bearer tok")],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    ident, ident_kind = middleware._identity(Request(scope))

    assert ident_kind == "token"
    assert ident.startswith("tok:")
    assert ident != "tok:tok"


def test_invalid_tokens_fall_back_to_ip_identity_without_bucket_spray() -> None:
    middleware = RateLimitMiddleware(
        FastAPI(),
        config=RateLimitConfig(
            enabled=True,
            default=[Rate(10, 60.0)],
            per_path={},
            identity="token",
            trusted_proxies=[],
            global_default=[],
            global_per_path={},
            valid_tokens=frozenset({"expected"}),
        ),
    )

    async def _call_next(request: Request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    async def _exercise() -> None:
        for idx in range(5):
            scope = {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/signature",
                "raw_path": b"/signature",
                "query_string": b"",
                "headers": [(b"authorization", f"Bearer bad-{idx}".encode("utf-8"))],
                "client": ("127.0.0.1", 50000),
                "server": ("testserver", 80),
            }
            await middleware.dispatch(Request(scope), _call_next)

    asyncio.run(_exercise())

    assert len(middleware._buckets) == 1
    assert list(middleware._buckets.keys()) == ["ip:127.0.0.1"]


def test_identity_rejection_does_not_burn_global_rate_bucket() -> None:
    middleware = RateLimitMiddleware(
        FastAPI(),
        config=RateLimitConfig(
            enabled=True,
            default=[Rate(1, 60.0)],
            per_path={},
            identity="ip",
            trusted_proxies=[],
            global_default=[Rate(2, 60.0)],
            global_per_path={},
        ),
    )

    async def _call_next(request: Request):
        return JSONResponse({"status": "ok"}, status_code=200)

    async def _dispatch_once(host: str) -> int:
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/signature",
            "raw_path": b"/signature",
            "query_string": b"",
            "headers": [],
            "client": (host, 50000),
            "server": ("testserver", 80),
        }
        resp = await middleware.dispatch(Request(scope), _call_next)
        return resp.status_code

    assert asyncio.run(_dispatch_once("127.0.0.1")) == 200
    assert asyncio.run(_dispatch_once("127.0.0.1")) == 429
    assert asyncio.run(_dispatch_once("127.0.0.2")) == 200


def test_rejected_request_does_not_burn_other_rate_buckets() -> None:
    middleware = RateLimitMiddleware(
        FastAPI(),
        config=RateLimitConfig(
            enabled=True,
            default=[Rate(60, 60.0), Rate(1, 1.0)],
            per_path={},
            identity="ip",
            trusted_proxies=[],
            global_default=[],
            global_per_path={},
        ),
    )

    async def _call_next(request: Request):
        return JSONResponse({"status": "ok"}, status_code=200)

    async def _dispatch_once() -> int:
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/signature",
            "raw_path": b"/signature",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
        resp = await middleware.dispatch(Request(scope), _call_next)
        return resp.status_code

    assert asyncio.run(_dispatch_once()) == 200
    buckets = middleware._buckets["ip:127.0.0.1"]["GLOBAL"]
    first_bucket_tokens = buckets[0].tokens

    assert asyncio.run(_dispatch_once()) == 429
    assert buckets[0].tokens == first_bucket_tokens
