from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()


def test_adapters_list_outputs_items() -> None:
    out = runner.invoke(app, ["adapters", "list"]).stdout
    assert "dataset.csv" in out and "eval.accuracy" in out


def test_adapters_dataset_describe_csv(tmp_path: Path) -> None:
    p = tmp_path / "d.csv"
    p.write_text("id,name\n1,Alice\n", encoding="utf-8")
    res = runner.invoke(
        app,
        [
            "adapters",
            "dataset",
            "describe",
            "-t",
            "csv",
            "-p",
            str(p),
            "--json",
        ],
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["type"] == "csv" and data["columns"] == ["id", "name"]
