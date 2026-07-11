# summary: "Tests JSON descriptions for built-in and registered OpenAPI tools."
# read_when:
#   - "Changing the tools describe CLI, capability descriptions, or OpenAPI operation metadata."

from __future__ import annotations

import json
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.tools.registry import register_openapi_operations


runner = CliRunner()


def test_tools_describe_builtin_json() -> None:
    res = runner.invoke(app, ["tools", "describe", "web_fetch", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data.get("name") == "web_fetch"
    assert "network.read" in set(data.get("capabilities") or [])
    assert isinstance(data.get("description"), str) and len(data.get("description")) > 0


def test_tools_describe_openapi_json() -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/x": {
                "post": {
                    "operationId": "create",
                    "summary": "Create x",
                    "responses": {"200": {}},
                }
            }
        },
    }
    register_openapi_operations(
        "tdesc", spec, allowed_hosts={"http://api.example.com": True}
    )
    res = runner.invoke(app, ["tools", "describe", "tdesc.create", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data.get("openapi") is True
    assert data.get("method") == "POST"
    assert data.get("path") == "/x"
    assert data.get("summary") == "Create x"
    assert isinstance(data.get("responses"), dict)
