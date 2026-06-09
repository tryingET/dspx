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


@pytest.fixture(autouse=True)
def _allow_openapi_mutation_for_schema_combinator_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")


def _ops_from_spec(tmp_path: Path, spec: dict) -> dict[str, dict]:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    return extract_operations(load_spec(str(spec_path)))


def test_request_body_oneof_resolves_refs_and_fails_closed_when_no_branch_matches(
    tmp_path: Path, mock_client: httpx.Client
) -> None:
    ops = _ops_from_spec(
        tmp_path,
        {
            "openapi": "3.1.0",
            "servers": [{"url": "http://api.example.com"}],
            "components": {
                "schemas": {
                    "Alpha": {
                        "type": "object",
                        "required": ["alpha"],
                        "properties": {"alpha": {"type": "integer"}},
                        "additionalProperties": False,
                    },
                    "Beta": {
                        "type": "object",
                        "required": ["beta"],
                        "properties": {"beta": {"type": "integer"}},
                        "additionalProperties": False,
                    },
                }
            },
            "paths": {
                "/items": {
                    "post": {
                        "operationId": "createOneOfRefItem",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "oneOf": [
                                            {"$ref": "#/components/schemas/Alpha"},
                                            {"$ref": "#/components/schemas/Beta"},
                                        ]
                                    }
                                }
                            },
                        },
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        },
    )

    with pytest.raises(ValueError, match="none matched"):
        call_operation(
            OpenAPICallRequest(operation_id="createOneOfRefItem", body={}),
            operation=ops["createOneOfRefItem"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )

    with pytest.raises(ValueError, match="none matched"):
        call_operation(
            OpenAPICallRequest(operation_id="createOneOfRefItem", body={"gamma": 3}),
            operation=ops["createOneOfRefItem"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )

    result = call_operation(
        OpenAPICallRequest(operation_id="createOneOfRefItem", body={"alpha": 1}),
        operation=ops["createOneOfRefItem"],
        allowed_hosts={"api.example.com": True},
        client=mock_client,
    )
    assert result.status_code == 200


def test_request_body_oneof_requires_exactly_one_matching_branch(
    tmp_path: Path, mock_client: httpx.Client
) -> None:
    ops = _ops_from_spec(
        tmp_path,
        {
            "openapi": "3.1.0",
            "servers": [{"url": "http://api.example.com"}],
            "paths": {
                "/items": {
                    "post": {
                        "operationId": "createExclusiveItem",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "oneOf": [
                                            {
                                                "type": "object",
                                                "required": ["alpha"],
                                                "properties": {
                                                    "alpha": {"type": "integer"}
                                                },
                                            },
                                            {
                                                "type": "object",
                                                "required": ["beta"],
                                                "properties": {
                                                    "beta": {"type": "integer"}
                                                },
                                            },
                                        ]
                                    }
                                }
                            },
                        },
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        },
    )

    with pytest.raises(ValueError, match="matched multiple oneOf branches"):
        call_operation(
            OpenAPICallRequest(
                operation_id="createExclusiveItem",
                body={"alpha": 1, "beta": 2},
            ),
            operation=ops["createExclusiveItem"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )


def test_request_body_anyof_resolves_refs_and_requires_one_passing_branch(
    tmp_path: Path, mock_client: httpx.Client
) -> None:
    ops = _ops_from_spec(
        tmp_path,
        {
            "openapi": "3.1.0",
            "servers": [{"url": "http://api.example.com"}],
            "components": {
                "schemas": {
                    "Alpha": {
                        "type": "object",
                        "required": ["alpha"],
                        "properties": {"alpha": {"type": "integer"}},
                        "additionalProperties": False,
                    },
                    "Beta": {
                        "type": "object",
                        "required": ["beta"],
                        "properties": {"beta": {"type": "integer"}},
                        "additionalProperties": False,
                    },
                }
            },
            "paths": {
                "/items": {
                    "post": {
                        "operationId": "createAnyOfRefItem",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "anyOf": [
                                            {"$ref": "#/components/schemas/Alpha"},
                                            {"$ref": "#/components/schemas/Beta"},
                                        ]
                                    }
                                }
                            },
                        },
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        },
    )

    with pytest.raises(ValueError, match="none matched"):
        call_operation(
            OpenAPICallRequest(operation_id="createAnyOfRefItem", body={}),
            operation=ops["createAnyOfRefItem"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )

    result = call_operation(
        OpenAPICallRequest(operation_id="createAnyOfRefItem", body={"beta": 2}),
        operation=ops["createAnyOfRefItem"],
        allowed_hosts={"api.example.com": True},
        client=mock_client,
    )
    assert result.status_code == 200


def test_request_body_repeated_ref_branches_do_not_collapse_to_unconstrained_schema(
    tmp_path: Path, mock_client: httpx.Client
) -> None:
    ops = _ops_from_spec(
        tmp_path,
        {
            "openapi": "3.1.0",
            "servers": [{"url": "http://api.example.com"}],
            "components": {
                "schemas": {
                    "Shared": {
                        "type": "object",
                        "required": ["x"],
                        "properties": {"x": {"type": "integer"}},
                        "additionalProperties": False,
                    }
                }
            },
            "paths": {
                "/items": {
                    "post": {
                        "operationId": "createRepeatedRefOneOfItem",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "oneOf": [
                                            {"$ref": "#/components/schemas/Shared"},
                                            {"$ref": "#/components/schemas/Shared"},
                                        ]
                                    }
                                }
                            },
                        },
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        },
    )

    with pytest.raises(ValueError, match="none matched"):
        call_operation(
            OpenAPICallRequest(operation_id="createRepeatedRefOneOfItem", body={}),
            operation=ops["createRepeatedRefOneOfItem"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )

    with pytest.raises(ValueError, match="none matched"):
        call_operation(
            OpenAPICallRequest(
                operation_id="createRepeatedRefOneOfItem",
                body={"y": 1},
            ),
            operation=ops["createRepeatedRefOneOfItem"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )

    with pytest.raises(ValueError, match="matched multiple oneOf branches"):
        call_operation(
            OpenAPICallRequest(
                operation_id="createRepeatedRefOneOfItem",
                body={"x": 1},
            ),
            operation=ops["createRepeatedRefOneOfItem"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )


def test_request_body_reused_property_refs_validate_each_sibling_independently(
    tmp_path: Path, mock_client: httpx.Client
) -> None:
    ops = _ops_from_spec(
        tmp_path,
        {
            "openapi": "3.1.0",
            "servers": [{"url": "http://api.example.com"}],
            "components": {
                "schemas": {
                    "Shared": {
                        "type": "object",
                        "required": ["x"],
                        "properties": {"x": {"type": "integer"}},
                        "additionalProperties": False,
                    }
                }
            },
            "paths": {
                "/items": {
                    "post": {
                        "operationId": "createRepeatedPropertyRefItem",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["a", "b"],
                                        "properties": {
                                            "a": {
                                                "$ref": "#/components/schemas/Shared"
                                            },
                                            "b": {
                                                "$ref": "#/components/schemas/Shared"
                                            },
                                        },
                                        "additionalProperties": False,
                                    }
                                }
                            },
                        },
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        },
    )

    with pytest.raises(ValueError, match="body.b: missing required property 'x'"):
        call_operation(
            OpenAPICallRequest(
                operation_id="createRepeatedPropertyRefItem",
                body={"a": {"x": 1}, "b": {}},
            ),
            operation=ops["createRepeatedPropertyRefItem"],
            allowed_hosts={"api.example.com": True},
            client=mock_client,
        )

    result = call_operation(
        OpenAPICallRequest(
            operation_id="createRepeatedPropertyRefItem",
            body={"a": {"x": 1}, "b": {"x": 2}},
        ),
        operation=ops["createRepeatedPropertyRefItem"],
        allowed_hosts={"api.example.com": True},
        client=mock_client,
    )
    assert result.status_code == 200
