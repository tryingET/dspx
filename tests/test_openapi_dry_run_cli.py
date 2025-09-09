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
                }
            }
        },
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    return str(p)


def test_openapi_call_dry_run_prints_preview(tmp_path: Path) -> None:
    spec = _make_spec(tmp_path)
    res = runner.invoke(
        app,
        [
            "tools",
            "openapi",
            "call",
            "--spec",
            spec,
            "--op",
            "getItem",
            "--allow-host",
            "api.example.com",
            "--params",
            "id=123",
            "--dry-run",
        ],
    )
    assert res.exit_code == 0
    s = res.stdout.strip().lower()
    assert s.startswith("[dry-run] get ") and "items/123" in s
