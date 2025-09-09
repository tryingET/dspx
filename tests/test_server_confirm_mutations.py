from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dspx.server.app import create_app


def test_server_mermaid_requires_confirmation_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_CONFIRM_MUTATIONS", "1")
    app = create_app()
    c = TestClient(app)
    mermaid = "\n".join(["graph TD", "  A[Start] --> B{Done}"])
    r = c.post(
        "/mermaid", json={"mermaid": mermaid, "name": "x", "variants": ["predict"]}
    )
    assert r.status_code == 403
    assert r.json().get("error") == "confirmation_required"
    # With header, it should pass
    r2 = c.post(
        "/mermaid",
        headers={"X-DSPX-Confirm": "1"},
        json={"mermaid": mermaid, "name": "x2", "variants": ["predict"]},
    )
    assert r2.status_code == 200


def test_server_signature_not_affected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_CONFIRM_MUTATIONS", "1")
    app = create_app()
    c = TestClient(app)
    r = c.post("/signature", json={"prompt": "p"})
    assert r.status_code == 200
