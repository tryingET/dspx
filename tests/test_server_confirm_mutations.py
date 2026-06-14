from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dspx.server.app import create_app


@pytest.fixture(autouse=True)
def _skip_server_auth_for_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_AUTH_SKIP_FOR_DEV", "1")
    monkeypatch.setenv("DSPX_SERVER_HOST", "localhost")


def _configure_server_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DSPX_CONFIRM_MUTATIONS", "1")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_SERVER_OUTPUT_DIR", str(tmp_path / "server-output"))
    monkeypatch.setenv("DSPX_SYNTHESIS_DIR", str(tmp_path / "synthesis"))
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_RECEIPTS_PATH",
        str(tmp_path / "receipts"),
    )
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_ORACLE_INDEX_PATH",
        str(tmp_path / "oracle" / "coordinates.db"),
    )


def test_server_mutating_endpoints_require_confirmation_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_server_env(monkeypatch, tmp_path)
    app = create_app()
    c = TestClient(app)
    mermaid = "\n".join(["graph TD", "  A[Start] --> B{Done}"])

    signature = c.post("/signature", json={"prompt": "p"})
    assert signature.status_code == 403
    assert signature.json().get("error") == "confirmation_required"

    module = c.post(
        "/module",
        json={
            "name": "Summarizer",
            "description": "Summarizes text",
            "inputs": ["text"],
            "outputs": ["summary"],
        },
    )
    assert module.status_code == 403
    assert module.json().get("error") == "confirmation_required"

    mermaid_res = c.post(
        "/mermaid", json={"mermaid": mermaid, "name": "x", "variants": ["predict"]}
    )
    assert mermaid_res.status_code == 403
    assert mermaid_res.json().get("error") == "confirmation_required"


def test_server_mutating_endpoints_accept_confirmation_header(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_server_env(monkeypatch, tmp_path)
    app = create_app()
    c = TestClient(app)
    headers = {"X-DSPX-Confirm": "1"}
    mermaid = "\n".join(["graph TD", "  A[Start] --> B{Done}"])

    signature = c.post("/signature", headers=headers, json={"prompt": "p"})
    assert signature.status_code == 200

    module = c.post(
        "/module",
        headers=headers,
        json={
            "name": "Summarizer",
            "description": "Summarizes text",
            "inputs": ["text"],
            "outputs": ["summary"],
        },
    )
    assert module.status_code == 200

    mermaid_res = c.post(
        "/mermaid",
        headers=headers,
        json={"mermaid": mermaid, "name": "x2", "variants": ["predict"]},
    )
    assert mermaid_res.status_code == 200
