from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dspx.dtos import OpenAPICallRequest
from dspx.tools.openapi import extract_operations, load_spec
from dspx.tools.openapi.caller import call_operation


@pytest.fixture
def mock_client() -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"ok": True, "url": str(request.url)}
            )
        )
    )


def test_query_numeric_bounds_fail_closed(
    tmp_path: Path, mock_client: httpx.Client
) -> None:
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
                            "name": "limit",
                            "required": True,
                            "schema": {"type": "integer", "minimum": 5, "maximum": 10},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    ops = extract_operations(load_spec(str(spec_path)))

    with pytest.raises(ValueError, match="below minimum"):
        call_operation(
            OpenAPICallRequest(operation_id="search", params={"limit": 1}),
            operation=ops["search"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )

    with pytest.raises(ValueError, match="above maximum"):
        call_operation(
            OpenAPICallRequest(operation_id="search", params={"limit": 11}),
            operation=ops["search"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )


def test_path_exclusive_numeric_bounds_enforced(
    tmp_path: Path, mock_client: httpx.Client
) -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/items/{id}": {
                "get": {
                    "operationId": "getItem",
                    "parameters": [
                        {
                            "in": "path",
                            "name": "id",
                            "required": True,
                            "schema": {
                                "type": "integer",
                                "minimum": 5,
                                "exclusiveMinimum": True,
                            },
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    ops = extract_operations(load_spec(str(spec_path)))

    with pytest.raises(ValueError, match="exclusiveMinimum"):
        call_operation(
            OpenAPICallRequest(operation_id="getItem", params={"id": 5}),
            operation=ops["getItem"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )

    result = call_operation(
        OpenAPICallRequest(operation_id="getItem", params={"id": 6}),
        operation=ops["getItem"],
        allowed_hosts={"api.example.com": True},
        client=mock_client,
    )
    assert result.status_code == 200
    assert result.body == {"ok": True, "url": "http://api.example.com/items/6"}


def test_numeric_exclusive_bounds_support_openapi_31_form(
    tmp_path: Path, mock_client: httpx.Client
) -> None:
    spec = {
        "openapi": "3.1.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/search": {
                "get": {
                    "operationId": "search31",
                    "parameters": [
                        {
                            "in": "query",
                            "name": "limit",
                            "required": True,
                            "schema": {
                                "type": "number",
                                "exclusiveMinimum": 5,
                                "exclusiveMaximum": 10,
                            },
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    spec_path = tmp_path / "spec31.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    ops = extract_operations(load_spec(str(spec_path)))

    with pytest.raises(ValueError, match="exclusiveMinimum"):
        call_operation(
            OpenAPICallRequest(operation_id="search31", params={"limit": 5}),
            operation=ops["search31"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )

    with pytest.raises(ValueError, match="exclusiveMaximum"):
        call_operation(
            OpenAPICallRequest(operation_id="search31", params={"limit": 10}),
            operation=ops["search31"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )

    result = call_operation(
        OpenAPICallRequest(operation_id="search31", params={"limit": 7.5}),
        operation=ops["search31"],
        allowed_hosts={"api.example.com": True},
        client=mock_client,
    )
    assert result.status_code == 200
