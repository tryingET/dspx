from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dspx.dtos import OpenAPICallRequest
from dspx.tools.openapi import extract_operations, load_spec
from dspx.tools.openapi.caller import call_operation


def _ok_client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))


def test_body_additional_properties_false_rejects_unknown_keys(tmp_path: Path) -> None:
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
                                    "properties": {"a": {"type": "string"}},
                                    "additionalProperties": False,
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

    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(operation_id="create", body={"a": "x", "b": "y"}),
            operation=ops["create"],
            allowed_hosts={"api.example.com": True},
            client=_ok_client(),
        )


def test_body_additional_properties_schema_validates_unknown_keys(
    tmp_path: Path,
) -> None:
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
                                    "properties": {"a": {"type": "string"}},
                                    "additionalProperties": {"type": "integer"},
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

    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(operation_id="create", body={"a": "x", "extra": "nope"}),
            operation=ops["create"],
            allowed_hosts={"api.example.com": True},
            client=_ok_client(),
        )

    res = call_operation(
        OpenAPICallRequest(operation_id="create", body={"a": "x", "extra": 123}),
        operation=ops["create"],
        allowed_hosts={"api.example.com": True},
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"ok": True})
            )
        ),
    )
    assert res.status_code == 200


def test_body_nullable_accepts_null(tmp_path: Path) -> None:
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
                                    "required": ["note"],
                                    "properties": {
                                        "note": {"type": "string", "nullable": True}
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

    res = call_operation(
        OpenAPICallRequest(operation_id="create", body={"note": None}),
        operation=ops["create"],
        allowed_hosts={"api.example.com": True},
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"ok": True})
            )
        ),
    )
    assert res.status_code == 200 and res.body == {"ok": True}
