from __future__ import annotations

import json
from pathlib import Path

import httpx

from dspx.tools.openapi import load_spec, extract_operations


def test_load_spec_from_url_with_allowlist_and_cache(
    tmp_path: Path, monkeypatch
) -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/ping": {
                "get": {
                    "operationId": "ping",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    content = json.dumps(spec)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != "api.example.com":
            return httpx.Response(403, text="forbidden")
        return httpx.Response(200, text=content)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setenv("DSPX_OPENAPI_CACHE", "1")
    monkeypatch.setenv("DSPX_OPENAPI_CACHE_DIR", str(tmp_path / "cache"))

    url = "http://api.example.com/spec.json"
    data = load_spec(url, allowed_hosts={"api.example.com": True}, client=client)
    ops = extract_operations(data)
    assert "ping" in ops

    # Simulate network failure and ensure cache fallback works
    def handler_fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    client2 = httpx.Client(transport=httpx.MockTransport(handler_fail))
    data2 = load_spec(url, allowed_hosts={"api.example.com": True}, client=client2)
    ops2 = extract_operations(data2)
    assert "ping" in ops2


def test_load_spec_url_rejects_unallowed_host(tmp_path: Path) -> None:
    url = "http://api.example.com/spec.json"
    try:
        load_spec(url, allowed_hosts={"other.example": True})
        assert False, "expected PermissionError"
    except PermissionError:
        pass
