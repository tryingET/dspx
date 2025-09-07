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


def test_adapters_dataset_split_stratified_group(tmp_path: Path) -> None:
    # Build a small labeled, grouped CSV
    import pandas as pd

    rows = []
    for g, lbl in [("g1", "A"), ("g2", "B"), ("g3", "A"), ("g4", "B")]:
        for j in range(5):
            rows.append({"id": f"{g}-{j}", "label": lbl, "group": g})
    df = pd.DataFrame(rows)
    csv = tmp_path / "data.csv"
    df.to_csv(csv, index=False)
    outdir = tmp_path / "splits"

    res = runner.invoke(
        app,
        [
            "adapters",
            "dataset",
            "split",
            "--csv",
            str(csv),
            "--outdir",
            str(outdir),
            "--test-size",
            "0.5",
            "--stratify-col",
            "label",
            "--group-col",
            "group",
        ],
    )
    assert res.exit_code == 0
    json.loads(res.stdout)
    assert (outdir / "train.csv").exists() and (outdir / "test.csv").exists()
    dtr = pd.read_csv(outdir / "train.csv")
    dte = pd.read_csv(outdir / "test.csv")
    assert set(dtr["group"]).isdisjoint(set(dte["group"]))
    # Sanity: label distribution roughly balanced given groups
    # (two groups per split → 10 rows per split)
    assert len(dtr) + len(dte) == len(df)
