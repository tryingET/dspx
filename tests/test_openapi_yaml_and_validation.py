from __future__ import annotations

from pathlib import Path
import textwrap
import pytest

from dspx.tools.openapi import load_spec, extract_operations
from dspx.tools.openapi.caller import call_operation
from dspx.dtos import OpenAPICallRequest


def test_load_yaml_spec_and_extract_ops(tmp_path: Path) -> None:
    yml = textwrap.dedent(
        """
        openapi: 3.0.0
        servers:
          - url: http://api.example.com
        paths:
          /hello/{name}:
            get:
              operationId: hello
              parameters:
                - in: path
                  name: name
                  required: true
                  schema:
                    type: string
              responses:
                '200':
                  description: ok
        """
    ).strip()
    p = tmp_path / "spec.yaml"
    p.write_text(yml, encoding="utf-8")
    data = load_spec(str(p))
    ops = extract_operations(data)
    assert "hello" in ops


def test_required_path_param_validation(tmp_path: Path) -> None:
    yml = textwrap.dedent(
        """
        openapi: 3.0.0
        servers:
          - url: http://api.example.com
        paths:
          /hello/{name}:
            get:
              operationId: hello
              parameters:
                - in: path
                  name: name
                  required: true
                  schema:
                    type: string
              responses:
                '200':
                  description: ok
        """
    ).strip()
    p = tmp_path / "spec.yaml"
    p.write_text(yml, encoding="utf-8")
    data = load_spec(str(p))
    ops = extract_operations(data)
    # Missing required path param should raise
    req = OpenAPICallRequest(operation_id="hello")
    with pytest.raises(ValueError):
        call_operation(
            req, operation=ops["hello"], allowed_hosts={"api.example.com": True}
        )


def test_required_query_param_validation(tmp_path: Path) -> None:
    yml = textwrap.dedent(
        """
        openapi: 3.0.0
        servers:
          - url: http://api.example.com
        paths:
          /greet:
            get:
              operationId: greet
              parameters:
                - in: query
                  name: lang
                  required: true
                  schema:
                    type: string
              responses:
                '200':
                  description: ok
        """
    ).strip()
    p = tmp_path / "spec2.yaml"
    p.write_text(yml, encoding="utf-8")
    data = load_spec(str(p))
    ops = extract_operations(data)
    # Missing required query param should raise
    req = OpenAPICallRequest(operation_id="greet")
    with pytest.raises(ValueError):
        call_operation(
            req, operation=ops["greet"], allowed_hosts={"api.example.com": True}
        )


def test_request_body_ref_schema_validation(tmp_path: Path) -> None:
    yml = textwrap.dedent(
        """
        openapi: 3.0.0
        servers:
          - url: http://api.example.com
        paths:
          /items:
            post:
              operationId: createItemFromRef
              requestBody:
                $ref: '#/components/requestBodies/CreateItem'
              responses:
                '200':
                  description: ok
        components:
          requestBodies:
            CreateItem:
              required: true
              content:
                application/json:
                  schema:
                    type: object
                    required: [title]
                    properties:
                      title:
                        type: string
        """
    ).strip()
    p = tmp_path / "spec-ref-body.yaml"
    p.write_text(yml, encoding="utf-8")
    ops = extract_operations(load_spec(str(p)))

    assert ops["createItemFromRef"]["requestBody"] == {
        "required": True,
        "schema": {
            "type": "object",
            "required": ["title"],
            "properties": {"title": {"type": "string"}},
        },
    }
    with pytest.raises(ValueError):
        call_operation(
            OpenAPICallRequest(operation_id="createItemFromRef", body={}),
            operation=ops["createItemFromRef"],
            allowed_hosts={"api.example.com": True},
        )


def test_request_body_schema_validation(tmp_path: Path) -> None:
    yml = textwrap.dedent(
        """
        openapi: 3.0.0
        servers:
          - url: http://api.example.com
        paths:
          /items:
            post:
              operationId: createItem
              requestBody:
                required: true
                content:
                  application/json:
                    schema:
                      type: object
                      required: [title, count]
                      properties:
                        title:
                          type: string
                        count:
                          type: integer
              responses:
                '200':
                  description: ok
        """
    ).strip()
    p = tmp_path / "spec3.yaml"
    p.write_text(yml, encoding="utf-8")
    data = load_spec(str(p))
    ops = extract_operations(data)
    # Missing body should raise
    req = OpenAPICallRequest(operation_id="createItem")
    with pytest.raises(ValueError):
        call_operation(
            req, operation=ops["createItem"], allowed_hosts={"api.example.com": True}
        )
    # Missing required property should raise
    req2 = OpenAPICallRequest(operation_id="createItem", body={"title": "t"})
    with pytest.raises(ValueError):
        call_operation(
            req2, operation=ops["createItem"], allowed_hosts={"api.example.com": True}
        )
    # Invalid type should raise
    req3 = OpenAPICallRequest(
        operation_id="createItem", body={"title": "t", "count": "abc"}
    )
    with pytest.raises(ValueError):
        call_operation(
            req3, operation=ops["createItem"], allowed_hosts={"api.example.com": True}
        )
    # Valid body passes and we can mock transport
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    req4 = OpenAPICallRequest(
        operation_id="createItem", body={"title": "t", "count": 2}
    )
    res = call_operation(
        req4,
        operation=ops["createItem"],
        allowed_hosts={"api.example.com": True},
        client=client,
    )
    assert res.status_code == 200 and res.body == {"ok": True}
