from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()


def _make_spec(tmp_path: Path) -> str:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/items/{id}": {
                "get": {
                    "operationId": "getItem",
                    "parameters": [{"in": "path", "name": "id", "required": True}],
                    "summary": "Fetch item",
                }
            }
        },
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    return str(p)


def test_openapi_ops_json_outputs_array(tmp_path: Path) -> None:
    spec = _make_spec(tmp_path)
    res = runner.invoke(
        app,
        ["tools", "openapi", "ops", spec, "--allow-host", "api.example.com", "--json"],
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert isinstance(data, list) and len(data) == 1
    op = data[0]
    assert op.get("operationId") == "getItem"
    assert op.get("method") == "GET"
    assert op.get("path") == "/items/{id}"
    assert op.get("summary") == "Fetch item"
