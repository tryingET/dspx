from __future__ import annotations

import json
from pathlib import Path
import httpx
import pytest

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
        return httpx.Response(
            200, text=request.url.path.split("/echo/")[-1], request=request
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = tool(params={"msg": "hi"}, client=client)
    assert (out or "").strip() == "hi"


def test_registered_openapi_tool_rejects_operation_overrides(tmp_path: Path) -> None:
    spec = load_spec(_spec(tmp_path))
    register_openapi_operations(
        "ex_lock", spec, allowed_hosts={"api.example.com": True}
    )
    tool = get_tool("ex_lock.echo")

    with pytest.raises(ValueError, match="operation overrides"):
        tool(method="DELETE", path="/admin", params={"msg": "hi"})


def test_register_openapi_operations_preserves_array_json_body(tmp_path: Path) -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/bulk": {
                "post": {
                    "operationId": "bulkCreate",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"type": "object"},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    p = tmp_path / "bulk.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    names = register_openapi_operations(
        "bulk", load_spec(str(p)), allowed_hosts={"api.example.com": True}
    )
    assert "bulk.bulkCreate" in names
    tool = get_tool("bulk.bulkCreate")

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content.decode("utf-8")) == [{"id": 1}]
        return httpx.Response(200, json=[{"ok": True}], request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = tool(body=[{"id": 1}], client=client)
    assert out == [{"ok": True}]
