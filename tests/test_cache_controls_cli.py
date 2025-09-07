from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner

from dspx.cli.dspx import app


def test_signature_codegen_module_meta_has_cache_key(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    r = CliRunner().invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(tmp_path / "sig.py"),
        ],
    )
    assert r.exit_code == 0
    meta = json.loads((tmp_path / "sig.py.meta.json").read_text(encoding="utf-8"))
    assert "cache_key" in meta and "cache_file" in meta

    r2 = CliRunner().invoke(
        app,
        [
            "codegen",
            "A CLI that prints hi",
            "-l",
            "python",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(tmp_path / "gen.py"),
            "--no-cache",
        ],
    )
    assert r2.exit_code == 0
    meta2 = json.loads((tmp_path / "gen.py.meta.json").read_text(encoding="utf-8"))
    assert meta2.get("cache_enabled") in (True, False)
    assert "cache_key" in meta2

    r3 = CliRunner().invoke(
        app,
        [
            "module-gen",
            "-n",
            "Summarizer",
            "-d",
            "Summarizes text",
            "-i",
            "text",
            "-o",
            "summary",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(tmp_path / "mod.py"),
        ],
    )
    assert r3.exit_code == 0
    meta3 = json.loads((tmp_path / "mod.py.meta.json").read_text(encoding="utf-8"))
    assert "cache_key" in meta3 and isinstance(meta3["cache_key"], str)
