from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()


def test_openapi_describe_cli_local_spec(tmp_path: Path) -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/items": {
                "post": {
                    "operationId": "addItem",
                    "parameters": [
                        {
                            "in": "query",
                            "name": "k",
                            "required": False,
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["title", "count"],
                                    "properties": {
                                        "title": {"type": "string"},
                                        "count": {"type": "integer"},
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
    result = runner.invoke(
        app,
        [
            "tools",
            "openapi",
            "describe",
            "--spec",
            str(p),
            "--op",
            "addItem",
        ],
    )
    assert result.exit_code == 0
    out = result.stdout
    assert "operationId: addItem" in out
    assert "method: POST" in out
    assert "path: /items" in out
    assert "parameters:" in out and "query:k" in out
    assert (
        "requestBody:" in out and "title" in out and "count" in out and "integer" in out
    )


def test_openapi_ops_grep_and_describe_json(tmp_path: Path) -> None:
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users": {
                "get": {
                    "operationId": "listUsers",
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/users/{id}": {
                "get": {
                    "operationId": "getUser",
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    from typer.testing import CliRunner

    r = CliRunner().invoke(app, ["tools", "openapi", "ops", str(p), "--grep", "user"])
    assert r.exit_code == 0
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    assert "listUsers" in lines and "getUser" in lines

    r2 = CliRunner().invoke(
        app,
        [
            "tools",
            "openapi",
            "describe",
            "--spec",
            str(p),
            "--op",
            "getUser",
            "--json",
        ],
    )
    assert r2.exit_code == 0
    data = json.loads(r2.stdout)
    assert data["operationId"] == "getUser"
    assert data["path"] == "/users/{id}"


def test_openapi_ops_method_and_paths_output(tmp_path: Path) -> None:
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/u": {"get": {"operationId": "list"}, "post": {"operationId": "create"}}
        },
    }
    p = tmp_path / "spec2.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    out = CliRunner().invoke(app, ["tools", "openapi", "ops", str(p), "--paths"]).stdout
    assert "GET /u" in out and "POST /u" in out
    out2 = (
        CliRunner()
        .invoke(app, ["tools", "openapi", "ops", str(p), "--paths", "--method", "GET"])
        .stdout
    )
    assert "GET /u" in out2 and "POST /u" not in out2


def test_openapi_ops_tags_filter_and_response_schema(tmp_path: Path) -> None:
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users": {
                "get": {
                    "operationId": "listUsers",
                    "tags": ["users"],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "items": {"type": "array"},
                                            "total": {"type": "integer"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/admin": {
                "get": {
                    "operationId": "adminGet",
                    "tags": ["admin"],
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }
    p = tmp_path / "spec3.json"
    p.write_text(__import__("json").dumps(spec), encoding="utf-8")
    from typer.testing import CliRunner

    # tags filter should return only matching ops
    out = (
        CliRunner()
        .invoke(app, ["tools", "openapi", "ops", str(p), "--tags", "users"])
        .stdout
    )
    assert "listUsers" in out and "adminGet" not in out

    # describe should include responses and schema details
    out2 = (
        CliRunner()
        .invoke(
            app,
            [
                "tools",
                "openapi",
                "describe",
                "--spec",
                str(p),
                "--op",
                "listUsers",
            ],
        )
        .stdout
    )
    assert "responses:" in out2 and "200" in out2 and "properties:" in out2
    # JSON describe includes responses
    js = (
        CliRunner()
        .invoke(
            app,
            [
                "tools",
                "openapi",
                "describe",
                "--spec",
                str(p),
                "--op",
                "listUsers",
                "--json",
            ],
        )
        .stdout
    )
    j = __import__("json").loads(js)
    assert "responses" in j and "200" in j["responses"]


def test_openapi_call_cli_coerces_array_query_params(
    tmp_path: Path, monkeypatch
) -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/search": {
                "get": {
                    "operationId": "searchItems",
                    "parameters": [
                        {
                            "in": "query",
                            "name": "ids",
                            "required": True,
                            "schema": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")

    captured: dict[str, object] = {}

    def _fake_call_operation(req, *, operation, allowed_hosts=None, client=None):
        captured["params"] = dict(req.params)
        from dspx.dtos import OpenAPICallResult

        return OpenAPICallResult(status_code=200, raw_text="ok")

    monkeypatch.setattr(
        "dspx.tools.openapi.caller.call_operation", _fake_call_operation
    )

    result = runner.invoke(
        app,
        [
            "tools",
            "openapi",
            "call",
            "--spec",
            str(p),
            "--op",
            "searchItems",
            "--params",
            "ids=1,2",
            "--allow-host",
            "api.example.com",
        ],
    )

    assert result.exit_code == 0
    assert captured["params"] == {"ids": [1, 2]}
