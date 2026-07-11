# summary: "Tests CLI exports for precision-recall and ROC evaluation artifacts."
# read_when:
#   - "Changing evaluation metrics, CSV inputs, or curve export filenames."

from __future__ import annotations

from pathlib import Path
from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()


def test_pr_curve_and_per_class_pr_export(tmp_path: Path) -> None:
    # pr_curve export
    p = tmp_path / "scores.csv"
    p.write_text("y,yhat\n0,0.1\n0,0.4\n1,0.35\n1,0.8\n", encoding="utf-8")
    outdir = tmp_path / "out1"
    res = runner.invoke(
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
            "--out",
            str(outdir),
        ],
    )
    assert res.exit_code == 0
    assert (outdir / "pr_curve.csv").exists()

    # per_class_pr export
    pc = tmp_path / "labels.csv"
    pc.write_text("y,yhat\nA,A\nA,B\nB,B\nB,B\n", encoding="utf-8")
    out2 = tmp_path / "out2"
    res2 = runner.invoke(
        app,
        [
            "adapters",
            "eval",
            "run",
            "--csv",
            str(pc),
            "--truth-col",
            "y",
            "--pred-col",
            "yhat",
            "--metric",
            "per_class_pr",
            "--out",
            str(out2),
        ],
    )
    assert res2.exit_code == 0
    assert (out2 / "per_class_pr.csv").exists()


def test_roc_curve_export(tmp_path: Path) -> None:
    p = tmp_path / "scores.csv"
    p.write_text("y,yhat\n0,0.1\n0,0.4\n1,0.35\n1,0.8\n", encoding="utf-8")
    outdir = tmp_path / "out3"
    res = runner.invoke(
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
            "roc_curve",
            "--out",
            str(outdir),
        ],
    )
    assert res.exit_code == 0
    assert (outdir / "roc_curve.csv").exists()
