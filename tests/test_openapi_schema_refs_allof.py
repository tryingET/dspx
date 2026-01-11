from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dspx.tools.openapi import load_spec, extract_operations
from dspx.tools.openapi.caller import call_operation
from dspx.dtos import OpenAPICallRequest


def test_openapi_ref_and_allof_and_bounds(tmp_path: Path) -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "components": {
            "schemas": {
                "Base": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string", "minLength": 3, "pattern": "^a"},
                        "age": {"type": "integer", "minimum": 0, "maximum": 200},
                    },
                },
                "User": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Base"},
                        {
                            "type": "object",
                            "required": ["active"],
                            "properties": {"active": {"type": "boolean"}},
                        },
                    ]
                },
            },
            "parameters": {
                "IdParam": {
                    "in": "path",
                    "name": "id",
                    "required": True,
                    "schema": {"type": "integer", "minimum": 1},
                }
            },
        },
        "paths": {
            "/users/{id}": {
                "post": {
                    "operationId": "updateUser",
                    "parameters": [{"$ref": "#/components/parameters/IdParam"}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        },
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    ops = extract_operations(load_spec(str(p)))

    # Missing required path param
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(
                operation_id="updateUser", body={"name": "abc", "active": True}
            ),
            operation=ops["updateUser"],
            allowed_hosts={"api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )

    # Bad path param type / below minimum
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(
                operation_id="updateUser",
                params={"id": "0"},
                body={"name": "abc", "active": True},
            ),
            operation=ops["updateUser"],
            allowed_hosts={"api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )

    # Violates pattern/minLength
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(
                operation_id="updateUser",
                params={"id": 1},
                body={"name": "bc", "active": True},
            ),
            operation=ops["updateUser"],
            allowed_hosts={"api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )

    # Valid
    res = call_operation(
        OpenAPICallRequest(
            operation_id="updateUser",
            params={"id": 1},
            body={"name": "abc", "active": False, "age": 10},
        ),
        operation=ops["updateUser"],
        allowed_hosts={"api.example.com": True},
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"ok": True})
            )
        ),
    )
    assert res.status_code == 200 and res.body == {"ok": True}
