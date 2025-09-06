from __future__ import annotations

import json
from pathlib import Path
import httpx

from dspx.tools.openapi import load_spec
from dspx.tools.registry import register_openapi_operations, get_tool


def _spec(tmp_path: Path) -> str:
    data = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/echo/{msg}": {
                "get": {
                    "operationId": "echo",
                    "parameters": [{"name": "msg", "in": "path"}],
                }
            }
        },
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_register_openapi_operations_and_run(tmp_path: Path) -> None:
    spec_path = _spec(tmp_path)
    spec = load_spec(spec_path)
    names = register_openapi_operations(
        "ex", spec, allowed_hosts={"api.example.com": True}
    )
    assert any(n.endswith(".echo") for n in names)
    tool = get_tool("ex.echo")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=request.url.path.split("/echo/")[-1])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = tool(params={"msg": "hi"}, client=client)
    assert (out or "").strip() == "hi"
