from __future__ import annotations

import json
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.tools.registry import register_openapi_operations


runner = CliRunner()


def test_tools_list_json_includes_capabilities() -> None:
    res = runner.invoke(app, ["tools", "list", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert isinstance(data, list) and len(data) > 0
    # find web_fetch and check capability
    wf = next((x for x in data if x.get("name") == "web_fetch"), None)
    assert wf is not None
    caps = set(wf.get("capabilities") or [])
    assert "network.read" in caps
    # description present for default tool
    assert isinstance(wf.get("description"), str) and len(wf.get("description")) > 0


def test_tools_list_json_shows_openapi_metadata() -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {"/send": {"post": {"operationId": "send", "responses": {"200": {}}}}},
    }
    register_openapi_operations(
        "tlist", spec, allowed_hosts={"http://api.example.com": True}
    )
    res = runner.invoke(app, ["tools", "list", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    op = next((x for x in data if x.get("name") == "tlist.send"), None)
    assert op is not None
    assert op.get("openapi") is True
    assert op.get("method") == "POST"
    assert op.get("path") == "/send"
    # summary may be absent; but list json should include it as a string or None
    # We don't assert here to keep deterministic
