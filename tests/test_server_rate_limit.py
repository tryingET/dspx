from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from dspx.server.app import create_app


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


def test_trusted_proxies_identity_by_xff(monkeypatch: pytest.MonkeyPatch) -> None:
    # Trust local test client (127.0.0.1) and use XFF to distinguish clients
    monkeypatch.setenv("DSPX_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("DSPX_RATE_LIMIT_DEFAULT", "1/sec")
    monkeypatch.setenv("DSPX_RATE_LIMIT_IDENTITY", "ip")
    monkeypatch.setenv("DSPX_TRUSTED_PROXIES", "127.0.0.0/8")
    c = _client()
    h1 = {"x-forwarded-for": "1.2.3.4, 127.0.0.1"}
    h2 = {"x-forwarded-for": "5.6.7.8, 127.0.0.1"}
    # Both should pass if XFF is used (distinct identities)
    r1 = c.post("/signature", json={"prompt": "p"}, headers=h1)
    r2 = c.post("/signature", json={"prompt": "p"}, headers=h2)
    assert r1.status_code == 200 and r2.status_code == 200
    # A second hit from the first identity should be limited under 1/sec
    r3 = c.post("/signature", json={"prompt": "p"}, headers=h1)
    assert r3.status_code == 429


def test_rate_limit_per_path_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_SERVER_TOKEN", "tok")
    monkeypatch.setenv("DSPX_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("DSPX_RATE_LIMIT_DEFAULT", "10/sec")
    monkeypatch.setenv("DSPX_RATE_LIMIT_IDENTITY", "token")
    monkeypatch.setenv(
        "DSPX_RATE_LIMIT_PATHS",
        json.dumps({"POST /module": "1/sec"}),
    )
    c = _client()
    h = {"Authorization": "Bearer tok"}
    r1 = c.post(
        "/module",
        json={"name": "m", "description": "", "inputs": [], "outputs": []},
        headers=h,
    )
    r2 = c.post(
        "/module",
        json={"name": "m", "description": "", "inputs": [], "outputs": []},
        headers=h,
    )
    assert r1.status_code == 200 and r2.status_code == 429
    # Signature should still be under default limit
    ok = c.post("/signature", json={"prompt": "p"}, headers=h)
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
