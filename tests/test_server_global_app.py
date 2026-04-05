from __future__ import annotations

import importlib
from types import SimpleNamespace

from fastapi.testclient import TestClient

import dspx.server.app as server_app_module


def test_global_app_defers_env_sensitive_config_until_first_use(monkeypatch) -> None:
    for key in [
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
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("DSPX_SERVER_TOKEN", "old-token")
    reloaded = importlib.reload(server_app_module)
    monkeypatch.setattr(
        reloaded,
        "run_generate_dto",
        lambda dto: SimpleNamespace(
            code="class GeneratedSignature: ...\n",
            signature_name="GeneratedSignature",
            task_description=dto.prompt,
            metadata={},
        ),
    )
    monkeypatch.setenv("DSPX_SERVER_TOKEN", "new-token")

    client = TestClient(reloaded.app)

    ok = client.post(
        "/signature",
        headers={"Authorization": "Bearer new-token"},
        json={"prompt": "p"},
    )
    rejected = client.post(
        "/signature",
        headers={"Authorization": "Bearer old-token"},
        json={"prompt": "p"},
    )

    assert ok.status_code == 200
    assert rejected.status_code == 401
