from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dspx.server.app import create_app


@pytest.fixture(autouse=True)
def _server_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DSPX_METRICS_ENABLED", "1")
    monkeypatch.setenv("DSPX_AUTH_SKIP_FOR_DEV", "1")


def test_metrics_json_default() -> None:
    app = create_app()
    c = TestClient(app)
    r = c.get("/metrics")
    assert r.status_code == 200 and r.headers.get("content-type", "").startswith(
        "application/json"
    )
    assert r.json().get("status") == "ok"


def test_metrics_prom_by_accept() -> None:
    app = create_app()
    c = TestClient(app)
    r = c.get("/metrics", headers={"accept": "text/plain"})
    assert r.status_code == 200 and r.headers.get("content-type", "").startswith(
        "text/plain"
    )
    assert "dspx_requests_total" in r.text


def test_metrics_prom_by_query() -> None:
    app = create_app()
    c = TestClient(app)
    r = c.get("/metrics?format=prom")
    assert r.status_code == 200 and r.headers.get("content-type", "").startswith(
        "text/plain"
    )
    assert "dspx_status_401_total" in r.text


def test_metrics_prom_includes_body_size_rejections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_MAX_BODY_SIZE", "10")
    app = create_app()
    c = TestClient(app)

    rejected = c.post(
        "/signature",
        content=b'{"prompt":"oversized"}',
        headers={"content-type": "application/json", "content-length": "999"},
    )
    assert rejected.status_code == 413

    r = c.get("/metrics?format=prom")
    assert r.status_code == 200
    assert "dspx_status_413_total 1" in r.text
