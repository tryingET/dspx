from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dspx.tools.openapi import extract_operations, load_spec


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
    monkeypatch.setenv("DSPX_OPENAPI_CACHE_FALLBACK", "1")
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


def test_load_spec_cache_fallback_is_opt_in(tmp_path: Path, monkeypatch) -> None:
    good_spec = '{"openapi":"3.0.0","paths":{"/ping":{"get":{"operationId":"ping","responses":{"200":{"description":"ok"}}}}}}'
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(200, text=good_spec)
        return httpx.Response(503, text="unavailable")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setenv("DSPX_OPENAPI_CACHE", "1")
    monkeypatch.delenv("DSPX_OPENAPI_CACHE_FALLBACK", raising=False)
    monkeypatch.setenv("DSPX_OPENAPI_CACHE_DIR", str(tmp_path / "cache"))
    url = "http://api.example.com/spec.json"

    assert "ping" in extract_operations(
        load_spec(url, allowed_hosts={"api.example.com": True}, client=client)
    )
    with pytest.raises(httpx.HTTPStatusError):
        load_spec(url, allowed_hosts={"api.example.com": True}, client=client)


def test_load_spec_url_rejects_unallowed_host(tmp_path: Path) -> None:
    url = "http://api.example.com/spec.json"
    try:
        load_spec(url, allowed_hosts={"other.example": True})
        assert False, "expected PermissionError"
    except PermissionError:
        pass


def test_load_spec_url_rejects_empty_allowlist(tmp_path: Path) -> None:
    url = "http://api.example.com/spec.json"
    with pytest.raises(PermissionError):
        load_spec(url, allowed_hosts={})


def test_load_spec_url_rejects_redirect_to_unallowed_host(tmp_path: Path) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "api.example.com":
            return httpx.Response(
                302,
                headers={"location": "http://evil.example/spec.json"},
                request=request,
            )
        if request.url.host == "evil.example":
            return httpx.Response(
                200, text='{"openapi":"3.0.0","paths":{}}', request=request
            )
        return httpx.Response(404, request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    with pytest.raises(PermissionError):
        load_spec(
            "http://api.example.com/spec.json",
            allowed_hosts={"api.example.com": True},
            client=client,
        )

    assert seen == ["http://api.example.com/spec.json"]


def test_load_spec_keeps_last_good_cache_on_malformed_success(
    tmp_path: Path, monkeypatch
) -> None:
    good_spec = '{"openapi":"3.0.0","paths":{"/ping":{"get":{"operationId":"ping","responses":{"200":{"description":"ok"}}}}}}'
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(200, text=good_spec)
        return httpx.Response(200, text="not-json-not-yaml: [")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setenv("DSPX_OPENAPI_CACHE", "1")
    monkeypatch.setenv("DSPX_OPENAPI_CACHE_FALLBACK", "1")
    monkeypatch.setenv("DSPX_OPENAPI_CACHE_DIR", str(tmp_path / "cache"))

    url = "http://api.example.com/spec.json"
    first = load_spec(url, allowed_hosts={"api.example.com": True}, client=client)
    assert "ping" in extract_operations(first)

    second = load_spec(url, allowed_hosts={"api.example.com": True}, client=client)
    assert "ping" in extract_operations(second)
