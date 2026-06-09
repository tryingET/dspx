from __future__ import annotations

import json
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.tools.registry import register_openapi_operations


runner = CliRunner()


def test_tools_search_by_name_text() -> None:
    res = runner.invoke(app, ["tools", "search", "web"])  # search substring
    assert res.exit_code == 0
    s = res.stdout
    assert "web_fetch" in s and "web_scrape" in s


def test_tools_search_by_tags_json() -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/users": {
                "post": {
                    "operationId": "createUser",
                    "tags": ["users"],
                    "responses": {"200": {}},
                }
            }
        },
    }
    register_openapi_operations(
        "tsearch", spec, allowed_hosts={"http://api.example.com": True}
    )
    res = runner.invoke(app, ["tools", "search", "", "--tags", "users", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    names = [x.get("name") for x in data]
    assert "tsearch.createUser" in names
