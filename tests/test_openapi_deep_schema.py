# summary: "Tests fail-closed OpenAPI request-body validation for deep, cyclic, nested, array, required, type, and enum schemas."
# read_when:
#   - "Changing OpenAPI schema traversal, reference-cycle detection, validation depth, or nested request-body validation."

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dspx.tools.openapi import load_spec, extract_operations
from dspx.tools.openapi.caller import call_operation
from dspx.dtos import OpenAPICallRequest


def _deep_required_schema(depth: int) -> tuple[dict[str, object], dict[str, object]]:
    schema: dict[str, object] = {"type": "object", "properties": {}}
    value: dict[str, object] = {}
    current_schema = schema
    current_value = value
    for index in range(depth):
        key = f"level_{index}"
        child_schema: dict[str, object] = {"type": "object", "properties": {}}
        current_schema["required"] = [key]
        current_schema["properties"] = {key: child_schema}
        child_value: dict[str, object] = {}
        current_value[key] = child_value
        current_schema = child_schema
        current_value = child_value
    current_schema["required"] = ["leaf"]
    current_schema["properties"] = {"leaf": {"type": "string"}}
    return schema, value


def test_deep_request_body_schema_fails_closed_instead_of_skipping_validation() -> None:
    schema, value = _deep_required_schema(depth=8)

    with pytest.raises(ValueError, match="schema validation depth exceeded"):
        call_operation(
            OpenAPICallRequest(operation_id="deep", body=value),
            operation={
                "method": "POST",
                "server": "http://api.example.com",
                "path": "/deep",
                "requestBody": {"required": True, "schema": schema},
                "responses": {"200": {"description": "ok"}},
            },
            allowed_hosts={"http://api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )


def test_cyclic_request_body_schema_ref_fails_closed() -> None:
    with pytest.raises(ValueError, match="schema reference cycle detected"):
        call_operation(
            OpenAPICallRequest(operation_id="cyclic", body={"name": "x"}),
            operation={
                "method": "POST",
                "server": "http://api.example.com",
                "path": "/cyclic",
                "requestBody": {
                    "required": True,
                    "schema": {"$ref": "#/components/schemas/Node"},
                },
                "responses": {"200": {"description": "ok"}},
                "components": {
                    "schemas": {
                        "Node": {
                            "type": "object",
                            "properties": {
                                "child": {"$ref": "#/components/schemas/Node"}
                            },
                        }
                    }
                },
            },
            allowed_hosts={"http://api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )


def test_body_array_of_objects_and_nested_required(tmp_path: Path, monkeypatch) -> None:
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
                                    "type": "object",
                                    "required": ["items"],
                                    "properties": {
                                        "items": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "required": ["id", "meta"],
                                                "properties": {
                                                    "id": {"type": "integer"},
                                                    "meta": {
                                                        "type": "object",
                                                        "required": ["tag"],
                                                        "properties": {
                                                            "tag": {
                                                                "type": "string",
                                                                "enum": ["new", "old"],
                                                            }
                                                        },
                                                    },
                                                },
                                            },
                                        }
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

    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    ops = extract_operations(load_spec(str(p)))
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")

    # Missing nested required field 'id'
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(
                operation_id="bulkCreate",
                body={"items": [{"meta": {"tag": "new"}}]},
            ),
            operation=ops["bulkCreate"],
            allowed_hosts={"http://api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )

    # Wrong type for id
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(
                operation_id="bulkCreate",
                body={"items": [{"id": "x", "meta": {"tag": "new"}}]},
            ),
            operation=ops["bulkCreate"],
            allowed_hosts={"http://api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )

    # Enum violation
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(
                operation_id="bulkCreate",
                body={"items": [{"id": 1, "meta": {"tag": "bad"}}]},
            ),
            operation=ops["bulkCreate"],
            allowed_hosts={"http://api.example.com": True},
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200))
            ),
        )

    # Valid
    res = call_operation(
        OpenAPICallRequest(
            operation_id="bulkCreate",
            body={"items": [{"id": 1, "meta": {"tag": "new"}}]},
        ),
        operation=ops["bulkCreate"],
        allowed_hosts={"http://api.example.com": True},
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"ok": True})
            )
        ),
    )
    assert res.status_code == 200 and res.body == {"ok": True}
