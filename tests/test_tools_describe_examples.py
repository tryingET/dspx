from __future__ import annotations

import json
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.tools.registry import register_openapi_operations


runner = CliRunner()


def test_tools_describe_builtin_examples_json() -> None:
    res = runner.invoke(app, ["tools", "describe", "web_fetch", "--json", "--examples"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    ex = data.get("examples") or []
    assert any("tools web fetch" in e for e in ex)


def test_tools_describe_openapi_examples_json() -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {"/x": {"get": {"operationId": "getX", "responses": {"200": {}}}}},
    }
    register_openapi_operations(
        "tdesc2", spec, allowed_hosts={"http://api.example.com": True}
    )
    res = runner.invoke(
        app, ["tools", "describe", "tdesc2.getX", "--json", "--examples"]
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    ex = data.get("examples") or []
    assert any("tools openapi call" in e for e in ex)
