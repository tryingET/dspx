from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from dspx.server.app import create_app
from dspx.server.security import AuthConfigError


@pytest.fixture(autouse=True)
def clear_auth_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Ensure a clean auth environment by default
    for k in [
        "DSPX_SERVER_TOKEN",
        "DSPX_SERVER_TOKENS",
        "DSPX_SERVER_TOKEN_FILE",
        "DSPX_AUTH_REQUIRED",
    ]:
        monkeypatch.delenv(k, raising=False)
    yield


def _client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_auth_disabled_allows_requests() -> None:
    client = _client()
    r = client.post(
        "/signature",
        json={"prompt": "echo", "template_version": "simple-v1"},
    )
    assert r.status_code == 200


def test_auth_required_missing_and_wrong_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_SERVER_TOKEN", "s3cr3t")
    client = _client()
    r1 = client.post("/signature", json={"prompt": "p"})
    assert r1.status_code == 401
    assert r1.json().get("error") == "unauthorized"
    r2 = client.post(
        "/signature",
        headers={"Authorization": "Bearer wrong"},
        json={"prompt": "p"},
    )
    assert r2.status_code == 401
    assert r2.json().get("error") == "unauthorized"


def test_auth_required_correct_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_SERVER_TOKENS", "a, b , c")
    client = _client()
    r = client.post(
        "/module",
        headers={"Authorization": "Bearer b"},
        json={"name": "M", "description": "d", "inputs": [], "outputs": []},
    )
    assert r.status_code == 200


def test_auth_accepts_case_insensitive_bearer_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_SERVER_TOKEN", "s3cr3t")
    client = _client()
    r = client.post(
        "/signature",
        headers={"Authorization": "bearer s3cr3t"},
        json={"prompt": "p"},
    )
    assert r.status_code == 200


def test_auth_token_file_unreadable_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_SERVER_TOKEN_FILE", "/definitely/missing/tokenfile")
    with pytest.raises(AuthConfigError):
        create_app()


def test_auth_required_without_tokens_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_AUTH_REQUIRED", "1")
    with pytest.raises(AuthConfigError):
        create_app()
