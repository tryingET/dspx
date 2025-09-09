from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dspx.server.app import create_app


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
    # Trigger some requests
    c.post("/signature", json={"prompt": "p"})
    r = c.get("/metrics")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert "requests_total" in data
