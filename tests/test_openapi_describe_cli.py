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
