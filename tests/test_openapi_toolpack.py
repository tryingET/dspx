from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.tools.openapi import load_spec, extract_operations
from dspx.tools.openapi.caller import (
    _validate_json_value_against_schema,
    call_operation,
)
from dspx.dtos import OpenAPICallRequest


runner = CliRunner()


def _make_spec(tmp_path: Path) -> str:
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/ping": {
                "get": {
                    "operationId": "ping",
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/echo/{msg}": {
                "get": {
                    "operationId": "echo",
                    "parameters": [
                        {
                            "name": "msg",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    return str(p)


def test_openapi_loader_and_ops(tmp_path: Path) -> None:
    spec_path = _make_spec(tmp_path)
    data = load_spec(spec_path)
    ops = extract_operations(data)
    assert "ping" in ops and "echo" in ops
    assert ops["ping"]["path"] == "/ping"
    assert ops["ping"]["method"] == "GET"


def test_openapi_loader_extracts_json_suffix_request_body_schema() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/items": {
                "post": {
                    "operationId": "createItem",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/vnd.api+json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["name"],
                                    "properties": {"name": {"type": "string"}},
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

    ops = extract_operations(spec)

    assert ops["createItem"]["requestBody"]["schema"]["required"] == ["name"]


def test_openapi_loader_rejects_duplicate_operation_id() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/safe": {
                "get": {
                    "operationId": "same",
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/danger": {
                "delete": {
                    "operationId": "same",
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }

    with pytest.raises(ValueError, match="duplicate OpenAPI operationId: same"):
        extract_operations(spec)


def test_openapi_call_with_mock_transport(tmp_path: Path) -> None:
    spec_path = _make_spec(tmp_path)
    data = load_spec(spec_path)
    ops = extract_operations(data)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != "api.example.com":
            return httpx.Response(403, text="forbidden")
        if request.url.path == "/ping":
            return httpx.Response(200, json={"ok": True})
        if request.url.path.startswith("/echo/"):
            return httpx.Response(200, text=request.url.path.split("/echo/")[-1])
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    # ping
    req = OpenAPICallRequest(operation_id="ping")
    res = call_operation(
        req,
        operation=ops["ping"],
        allowed_hosts={"api.example.com": True},
        client=client,
    )
    assert res.status_code == 200 and res.body == {"ok": True}

    # echo with path param
    req2 = OpenAPICallRequest(operation_id="echo", params={"msg": "hello"})
    res2 = call_operation(
        req2,
        operation=ops["echo"],
        allowed_hosts={"api.example.com": True},
        client=client,
    )
    assert res2.status_code == 200 and (res2.raw_text or "").strip() == "hello"


def test_openapi_call_parses_json_content_type_case_insensitively(
    tmp_path: Path,
) -> None:
    spec_path = _make_spec(tmp_path)
    ops = extract_operations(load_spec(spec_path))
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"Content-Type": "Application/JSON"},
                text='{"ok": true}',
                request=request,
            )
        )
    )

    res = call_operation(
        OpenAPICallRequest(operation_id="ping"),
        operation=ops["ping"],
        allowed_hosts={"api.example.com": True},
        client=client,
    )

    assert res.body == {"ok": True}


def test_openapi_load_preserves_remote_spec_url(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "tools",
            "openapi",
            "load",
            "--prefix",
            "remote",
            "--spec",
            "https://api.example.com/openapi.json",
            "--allow-host",
            "api.example.com",
            "--outdir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads((tmp_path / "remote.json").read_text(encoding="utf-8"))
    assert payload["spec"] == "https://api.example.com/openapi.json"


def test_openapi_call_enforces_response_byte_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec_path = _make_spec(tmp_path)
    data = load_spec(spec_path)
    ops = extract_operations(data)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="x" * 32, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setenv("DSPX_OPENAPI_RESPONSE_MAX_BYTES", "8")

    with pytest.raises(
        ValueError, match="OpenAPI operation response exceeded byte limit"
    ):
        call_operation(
            OpenAPICallRequest(operation_id="ping"),
            operation=ops["ping"],
            allowed_hosts={"api.example.com": True},
            client=client,
        )


def test_openapi_call_rejects_operation_identity_overrides(tmp_path: Path) -> None:
    spec_path = _make_spec(tmp_path)
    data = load_spec(spec_path)
    ops = extract_operations(data)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))

    with pytest.raises(ValueError, match="operation identity"):
        call_operation(
            OpenAPICallRequest(operation_id="ping", method="DELETE", path="/admin"),
            operation=ops["ping"],
            allowed_hosts={"api.example.com": True},
            client=client,
        )


def test_openapi_call_requires_explicit_allowed_hosts(tmp_path: Path) -> None:
    spec_path = _make_spec(tmp_path)
    data = load_spec(spec_path)
    ops = extract_operations(data)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))

    with pytest.raises(PermissionError, match="Host not allowed"):
        call_operation(
            OpenAPICallRequest(operation_id="ping"),
            operation=ops["ping"],
            client=client,
        )


def test_openapi_call_rejects_hostless_url_before_http_client() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))

    with pytest.raises(PermissionError, match="Host not allowed"):
        call_operation(
            OpenAPICallRequest(operation_id="ping"),
            operation={"method": "GET", "server": "", "path": "/ping"},
            allowed_hosts={},
            client=client,
        )


def test_openapi_call_url_encodes_reserved_path_chars(tmp_path: Path) -> None:
    spec_path = _make_spec(tmp_path)
    data = load_spec(spec_path)
    ops = extract_operations(data)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    res = call_operation(
        OpenAPICallRequest(operation_id="echo", params={"msg": "a/b"}),
        operation=ops["echo"],
        allowed_hosts={"api.example.com": True},
        client=client,
    )

    assert res.status_code == 200
    assert seen == ["http://api.example.com/echo/a%2Fb"]


def test_openapi_call_strips_hop_by_hop_headers(tmp_path: Path) -> None:
    spec_path = _make_spec(tmp_path)
    data = load_spec(spec_path)
    ops = extract_operations(data)
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.headers))
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    res = call_operation(
        OpenAPICallRequest(
            operation_id="ping",
            headers={
                "Connection": "keep-alive, X-Test",
                "Transfer-Encoding": "chunked",
                "X-Test": "ok",
            },
        ),
        operation=ops["ping"],
        allowed_hosts={"api.example.com": True},
        client=client,
    )

    assert res.status_code == 200
    assert "x-test" not in seen
    assert seen.get("connection") != "keep-alive, X-Test"
    assert "transfer-encoding" not in seen


def test_openapi_schema_pattern_timeout_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsafe regex pattern timed out"):
        _validate_json_value_against_schema(
            "a" * 30_000 + "!",
            {"type": "string", "pattern": "^(a+)+$"},
            path="$.name",
        )


def test_openapi_call_with_body_and_headers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/send": {
                "post": {
                    "operationId": "send",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    p = tmp_path / "spec2.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    data = load_spec(str(p))
    ops = extract_operations(data)
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")

    def handler(request: httpx.Request) -> httpx.Response:
        # echo back header and json body
        if request.url.path == "/send" and request.method.upper() == "POST":
            payload = request.content.decode("utf-8")
            return httpx.Response(
                200, text=f"H={request.headers.get('X-Test', '')};B={payload}"
            )
        return httpx.Response(404, text="not found")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    req = OpenAPICallRequest(
        operation_id="send", headers={"X-Test": "ok"}, body={"k": 1}
    )
    res = call_operation(
        req,
        operation=ops["send"],
        allowed_hosts={"api.example.com": True},
        client=client,
    )
    raw = res.raw_text or ""
    assert (
        res.status_code == 200 and "H=ok" in raw and ('"k":1' in raw or '"k": 1' in raw)
    )


def test_openapi_call_rejects_redirect_to_unallowed_host(tmp_path: Path) -> None:
    spec_path = _make_spec(tmp_path)
    data = load_spec(spec_path)
    ops = extract_operations(data)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "api.example.com":
            return httpx.Response(
                302,
                headers={"location": "http://evil.example/leak"},
                request=request,
            )
        if request.url.host == "evil.example":
            return httpx.Response(200, text="evil", request=request)
        return httpx.Response(404, text="not found", request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    try:
        call_operation(
            OpenAPICallRequest(operation_id="ping"),
            operation=ops["ping"],
            allowed_hosts={"api.example.com": True},
            client=client,
        )
    except PermissionError as exc:
        assert "Redirect target host not allowed" in str(exc)
    else:  # pragma: no cover - fail closed assertion
        raise AssertionError("expected PermissionError for redirected OpenAPI call")

    assert seen == ["http://api.example.com/ping"]


def test_openapi_call_accepts_array_json_body_and_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
                                    "items": {
                                        "type": "object",
                                        "required": ["id"],
                                        "properties": {"id": {"type": "integer"}},
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
    p = tmp_path / "bulk.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    ops = extract_operations(load_spec(str(p)))
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert json.loads(request.content.decode("utf-8")) == [{"id": 1}, {"id": 2}]
        return httpx.Response(200, json=[{"ok": True}], request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    res = call_operation(
        OpenAPICallRequest(operation_id="bulkCreate", body=[{"id": 1}, {"id": 2}]),
        operation=ops["bulkCreate"],
        allowed_hosts={"api.example.com": True},
        client=client,
    )
    assert res.status_code == 200
    assert res.body == [{"ok": True}]


def test_openapi_call_preserves_falsey_json_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    p = tmp_path / "bulk-empty.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    ops = extract_operations(load_spec(str(p)))
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.content.decode("utf-8") == "[]"
        return httpx.Response(200, json=[], request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    res = call_operation(
        OpenAPICallRequest(operation_id="bulkCreate", body=[]),
        operation=ops["bulkCreate"],
        allowed_hosts={"api.example.com": True},
        client=client,
    )
    assert res.status_code == 200
    assert res.body == []
