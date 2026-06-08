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


def test_adapters_eval_run_f1_string_labels_require_positive_label(
    tmp_path: Path,
) -> None:
    p = tmp_path / "labels.csv"
    p.write_text("y,yhat\ncat,cat\ndog,cat\n", encoding="utf-8")

    result = runner.invoke(
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
    )

    assert result.exit_code == 2
    assert "positive_label must be provided" in result.stderr


def test_adapters_eval_run_roc_auc_and_macro_text(tmp_path: Path) -> None:
    # roc_auc with numeric predictions
    p = tmp_path / "scores.csv"
    p.write_text("y,yhat\n0,0.1\n0,0.4\n1,0.35\n1,0.8\n", encoding="utf-8")
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
            "roc_auc",
        ],
    ).stdout
    data = json.loads(out)
    assert data["metric"] == "roc_auc" and abs(data["value"] - 0.75) < 1e-6

    # macro text metrics via average flag
    p2 = tmp_path / "text.csv"
    p2.write_text("ref,hyp\na,a\n'a b',b\n", encoding="utf-8")
    out2 = runner.invoke(
        app,
        [
            "adapters",
            "eval",
            "run",
            "--csv",
            str(p2),
            "--truth-col",
            "ref",
            "--pred-col",
            "hyp",
            "--metric",
            "rouge1_f1",
            "--average",
            "macro",
        ],
    ).stdout
    d2 = json.loads(out2)
    assert d2["metric"] == "rouge1_f1" and d2["value"] > 0 and d2["value"] <= 1


def test_adapters_eval_run_pr_curve_and_ece(tmp_path: Path) -> None:
    # pr_curve with numeric predictions
    p = tmp_path / "scores2.csv"
    p.write_text("y,yhat\n0,0.1\n0,0.4\n1,0.35\n1,0.8\n", encoding="utf-8")
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
            "pr_curve",
        ],
    ).stdout
    data = json.loads(out)
    assert data["metric"] == "pr_curve" and len(data["thresholds"]) > 0

    # ece
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
            "ece",
        ],
    ).stdout
    d2 = json.loads(out2)
    assert d2["metric"] == "ece" and 0.0 <= d2["value"] <= 1.0
