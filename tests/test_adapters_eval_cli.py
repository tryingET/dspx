from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()


def test_adapters_eval_run_accuracy_and_f1(tmp_path: Path) -> None:
    p = tmp_path / "labels.csv"
    p.write_text("y,yhat\n1,1\n0,1\n1,0\n0,0\n", encoding="utf-8")
    # accuracy = 0.5
    out = runner.invoke(
        app,
        [
            "adapters",
            "eval",
            "run",
            "--csv",
            str(p),
            "--truth-col",
            "y",
            "--pred-col",
            "yhat",
            "--metric",
            "accuracy",
        ],
    ).stdout
    data = json.loads(out)
    assert data["metric"] == "accuracy" and abs(data["value"] - 0.5) < 1e-6

    # f1 (positive=1): tp=1, fp=1, fn=1 => f1=0.5
    out2 = runner.invoke(
        app,
        [
            "adapters",
            "eval",
            "run",
            "--csv",
            str(p),
            "--truth-col",
            "y",
            "--pred-col",
            "yhat",
            "--metric",
            "f1",
        ],
    ).stdout
    data2 = json.loads(out2)
    assert data2["metric"] == "f1" and abs(data2["value"] - 0.5) < 1e-6
