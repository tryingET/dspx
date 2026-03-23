from __future__ import annotations

import ipaddress
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from dspx.server.app import create_app
from dspx.server.security import Rate, RateLimitConfig, RateLimitMiddleware


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch):
    for k in [
        "DSPX_SERVER_TOKEN",
        "DSPX_SERVER_TOKENS",
        "DSPX_SERVER_TOKEN_FILE",
        "DSPX_AUTH_REQUIRED",
        "DSPX_RATE_LIMIT_ENABLED",
        "DSPX_RATE_LIMIT_DEFAULT",
        "DSPX_RATE_LIMIT_PATHS",
        "DSPX_RATE_LIMIT_IDENTITY",
        "DSPX_TRUSTED_PROXIES",
    ]:
        monkeypatch.delenv(k, raising=False)


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
