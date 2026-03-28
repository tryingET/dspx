from __future__ import annotations

import httpx
import pytest

from dspx.tools.registry import ensure_default_tools, get_tool


def _mock_ok(body: str = "ok") -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_web_fetch_denies_unallowed_host() -> None:
    ensure_default_tools()
    fn = get_tool("web_fetch")
    client = _mock_ok("hello")
    # not in allowlist
    with pytest.raises(PermissionError):
        _ = fn(
            "http://blocked.example/path",
            allowed_hosts={"allowed.example": True},
            client=client,
        )


def test_web_fetch_allows_allowed_host() -> None:
    ensure_default_tools()
    fn = get_tool("web_fetch")
    client = _mock_ok("world")
    out = fn(
        "http://allowed.example/hi",
        allowed_hosts={"allowed.example": True},
        client=client,
    )
    assert out["status_code"] == 200
    assert "world" in out.get("text", "")


def test_web_scrape_respects_allowlist() -> None:
    ensure_default_tools()
    fn = get_tool("web_scrape")

    html = "<html><body><h1>Title</h1><p>Para</p></body></html>"
    client = _mock_ok(html)

    # blocked host
    with pytest.raises(PermissionError):
        _ = fn(
            "http://blocked.example/page",
            allowed_hosts={"allowed.example": True},
            client=client,
        )

    # allowed host
    out = fn(
        "http://allowed.example/page",
        selector="h1",
        allowed_hosts={"allowed.example": True},
        client=client,
    )
    assert out["status_code"] == 200
    assert "Title" in out.get("text", "")


def test_web_fetch_rejects_redirect_to_unallowed_host() -> None:
    ensure_default_tools()
    fn = get_tool("web_fetch")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "allowed.example":
            return httpx.Response(
                302,
                headers={"location": "http://evil.example/secret"},
            )
        if request.url.host == "evil.example":
            return httpx.Response(200, text="evil")
        return httpx.Response(404)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    with pytest.raises(PermissionError):
        fn(
            "http://allowed.example/start",
            allowed_hosts={"allowed.example": True},
            client=client,
        )
