from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dspx.tools.openapi import load_spec, extract_operations
from dspx.tools.openapi.caller import call_operation
from dspx.dtos import OpenAPICallRequest


def test_body_array_of_objects_and_nested_required(tmp_path: Path) -> None:
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

    # Missing nested required field 'id'
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(
                operation_id="bulkCreate",
                body={"items": [{"meta": {"tag": "new"}}]},
            ),
            operation=ops["bulkCreate"],
            allowed_hosts={"api.example.com": True},
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
            allowed_hosts={"api.example.com": True},
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
            allowed_hosts={"api.example.com": True},
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
        allowed_hosts={"api.example.com": True},
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"ok": True})
            )
        ),
    )
    assert res.status_code == 200 and res.body == {"ok": True}
