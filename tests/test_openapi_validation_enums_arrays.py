from __future__ import annotations

import json
from pathlib import Path
import pytest

from dspx.tools.openapi import load_spec, extract_operations
from dspx.tools.openapi.caller import call_operation
from dspx.dtos import OpenAPICallRequest
import httpx


def test_query_param_enum_and_array_validation(tmp_path: Path) -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/search": {
                "get": {
                    "operationId": "search",
                    "parameters": [
                        {
                            "in": "query",
                            "name": "mode",
                            "required": True,
                            "schema": {"type": "string", "enum": ["all", "any"]},
                        },
                        {
                            "in": "query",
                            "name": "ids",
                            "schema": {"type": "array", "items": {"type": "integer"}},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    ops = extract_operations(load_spec(str(p)))

    # invalid enum
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(operation_id="search", params={"mode": "invalid"}),
            operation=ops["search"],
            allowed_hosts={"api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )
    # invalid ids (not a list)
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(
                operation_id="search", params={"mode": "all", "ids": "1,2"}
            ),
            operation=ops["search"],
            allowed_hosts={"api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )
    # invalid ids element type
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(
                operation_id="search", params={"mode": "all", "ids": ["a"]}
            ),
            operation=ops["search"],
            allowed_hosts={"api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )
    # valid
    res = call_operation(
        OpenAPICallRequest(
            operation_id="search", params={"mode": "any", "ids": [1, 2]}
        ),
        operation=ops["search"],
        allowed_hosts={"api.example.com": True},
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"ok": True})
            )
        ),
    )
    assert res.status_code == 200 and res.body == {"ok": True}


def test_body_arrays_and_nested_objects(tmp_path: Path) -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/create": {
                "post": {
                    "operationId": "create",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["tags", "meta"],
                                    "properties": {
                                        "tags": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "scores": {
                                            "type": "array",
                                            "items": {"type": "number"},
                                        },
                                        "meta": {
                                            "type": "object",
                                            "required": ["flag"],
                                            "properties": {"flag": {"type": "boolean"}},
                                        },
                                        "status": {
                                            "type": "string",
                                            "enum": ["new", "old"],
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    p = tmp_path / "spec2.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    ops = extract_operations(load_spec(str(p)))

    # Missing required
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(operation_id="create", body={"scores": [0.1]}),
            operation=ops["create"],
            allowed_hosts={"api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )
    # Invalid array type
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(
                operation_id="create",
                body={"tags": [1], "scores": [0.1], "meta": {"flag": True}},
            ),
            operation=ops["create"],
            allowed_hosts={"api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )
    # Invalid nested type
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(
                operation_id="create",
                body={"tags": ["a"], "scores": [0.1], "meta": {"flag": "yes"}},
            ),
            operation=ops["create"],
            allowed_hosts={"api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )
    # Invalid enum
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(
                operation_id="create",
                body={
                    "tags": ["a"],
                    "scores": [0.1],
                    "meta": {"flag": True},
                    "status": "bad",
                },
            ),
            operation=ops["create"],
            allowed_hosts={"api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )
    # Valid
    res = call_operation(
        OpenAPICallRequest(
            operation_id="create",
            body={
                "tags": ["a"],
                "scores": [0.1],
                "meta": {"flag": True},
                "status": "new",
            },
        ),
        operation=ops["create"],
        allowed_hosts={"api.example.com": True},
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"ok": True})
            )
        ),
    )
    assert res.status_code == 200 and res.body == {"ok": True}
