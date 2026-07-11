# summary: "Tests server metrics enablement, authentication, response counters, and rate-limit accounting."
# read_when:
#   - "You are changing server metrics endpoints, request counters, auth protection, or rate-limit instrumentation."

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dspx.server.app import create_app


@pytest.fixture(autouse=True)
def _skip_server_auth_for_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_AUTH_SKIP_FOR_DEV", "1")
    monkeypatch.setenv("DSPX_SERVER_HOST", "localhost")


def test_metrics_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DSPX_METRICS_ENABLED", raising=False)
    app = create_app()
    c = TestClient(app)
    r = c.get("/metrics")
    assert r.status_code in {404, 405}


def test_metrics_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_METRICS_ENABLED", "1")
    app = create_app()
    c = TestClient(app)
    c.post("/signature", json={"prompt": "p"})
    r = c.get("/metrics")
    assert r.status_code == 200
    data = r.json()
    assert data == {
        "status": "ok",
        "requests_total": 2,
        "status_401": 0,
        "status_429": 0,
        "status_413": 0,
    }


def test_metrics_requires_auth_when_auth_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DSPX_AUTH_SKIP_FOR_DEV", raising=False)
    monkeypatch.setenv("DSPX_AUTH_REQUIRED", "1")
    monkeypatch.setenv("DSPX_SERVER_TOKEN", "secret")
    monkeypatch.setenv("DSPX_METRICS_ENABLED", "1")
    app = create_app()
    c = TestClient(app)

    assert c.get("/metrics").status_code == 401
    assert c.get("/metrics-prom").status_code == 401
    assert (
        c.get("/metrics", headers={"Authorization": "Bearer secret"}).status_code == 200
    )


def test_metrics_count_rate_limited_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_METRICS_ENABLED", "1")
    monkeypatch.setenv("DSPX_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("DSPX_RATE_LIMIT_DEFAULT", "1/sec")
    monkeypatch.setenv("DSPX_RATE_LIMIT_PATHS", '{"GET /metrics": "100/sec"}')
    app = create_app()
    c = TestClient(app)

    assert c.post("/signature", json={"prompt": "p"}).status_code == 200
    assert c.post("/signature", json={"prompt": "p"}).status_code == 429

    data = c.get("/metrics").json()
    assert data == {
        "status": "ok",
        "requests_total": 3,
        "status_401": 0,
        "status_429": 1,
        "status_413": 0,
    }
