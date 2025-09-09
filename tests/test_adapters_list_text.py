from __future__ import annotations

from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()


def test_adapters_list_text_shows_descriptions() -> None:
    res = runner.invoke(app, ["adapters", "list"])
    assert res.exit_code == 0
    s = res.stdout
    assert "dataset.csv - " in s
    assert "eval.f1_binary - " in s
