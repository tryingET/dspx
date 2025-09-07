from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()


def _make_cache(tmp_path: Path, kind: str, key: str, payload: dict) -> Path:
    d = tmp_path / kind
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{key}.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    return f


def test_cache_cli_list_show_clear(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path))
    _make_cache(tmp_path, "signature", "abc", {"x": 1})
    _make_cache(tmp_path, "module", "def", {"y": 2})

    # info
    out_info = runner.invoke(app, ["cache", "info"]).stdout
    assert "dir:" in out_info and "files:" in out_info

    # list all kinds
    out = runner.invoke(app, ["cache", "list"]).stdout
    assert "signature:abc" in out and "module:def" in out

    # list specific kind
    out2 = runner.invoke(app, ["cache", "list", "--kind", "signature"]).stdout
    assert "signature:abc" in out2 and "module:def" not in out2

    # show
    out3 = runner.invoke(
        app, ["cache", "show", "--kind", "signature", "--key", "abc"]
    ).stdout
    data = json.loads(out3)
    assert data["x"] == 1

    # clear by key
    r = runner.invoke(
        app, ["cache", "clear", "--kind", "signature", "--key", "abc"]
    ).stdout
    assert "cleared: signature:abc" in r
    # clear by kind
    r2 = runner.invoke(app, ["cache", "clear", "--kind", "module"]).stdout
    assert "cleared: module" in r2
    # clear all
    _make_cache(tmp_path, "codegen", "ghi", {"z": 3})
    r3 = runner.invoke(app, ["cache", "clear", "--all"]).stdout
    assert "cleared: all" in r3
