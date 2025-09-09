from __future__ import annotations

from pathlib import Path
import httpx
import pytest

from dspx.tools.registry import ensure_default_tools, get_tool
from dspx.tools.openapi import extract_operations
from dspx.tools.openapi.caller import call_operation
from dspx.dtos import OpenAPICallRequest


def test_network_read_capability_allows_get_blocks_post(
    tmp_path: Path, monkeypatch
) -> None:
    # Allow only network.read
    monkeypatch.setenv("DSPX_POLICY_ALLOWED_CAPS", "network.read")
    ensure_default_tools()

    # web_fetch (GET) should work
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    tool = get_tool("web_fetch")
    out = tool(
        url="http://example.com/x", allowed_hosts={"example.com": True}, client=client
    )
    assert out["status_code"] == 200

    # POST via openapi should fail under capability policy
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/x": {"post": {"operationId": "create"}, "get": {"operationId": "read"}}
        },
    }
    ops = extract_operations(spec)
    req = OpenAPICallRequest(operation_id="create")

    def handler2(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"ok": True})

    client2 = httpx.Client(transport=httpx.MockTransport(handler2))
    with pytest.raises(PermissionError):
        _ = call_operation(
            req,
            operation=ops["create"],
            allowed_hosts={"api.example.com": True},
            client=client2,
        )

    # GET should pass
    req2 = OpenAPICallRequest(operation_id="read")
    out2 = call_operation(
        req2,
        operation=ops["read"],
        allowed_hosts={"api.example.com": True},
        client=client2,
    )
    assert out2.status_code in {
        200,
        201,
        404,
    }  # transport returns some status; capability allowed
