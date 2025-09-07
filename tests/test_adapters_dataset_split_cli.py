from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()


def test_dataset_split_test_size(tmp_path: Path) -> None:
    p = tmp_path / "data.csv"
    df = pd.DataFrame({"id": list(range(10)), "y": [i % 2 for i in range(10)]})
    df.to_csv(p, index=False)
    outdir = tmp_path / "splits"
    out = runner.invoke(
        app,
        [
            "adapters",
            "dataset",
            "split",
            "--csv",
            str(p),
            "--outdir",
            str(outdir),
            "--test-size",
            "0.3",
        ],
    ).stdout
    data = json.loads(out)
    assert Path(data["train"]).exists() and Path(data["test"]).exists()
    tr = pd.read_csv(data["train"])  # type: ignore[arg-type]
    te = pd.read_csv(data["test"])  # type: ignore[arg-type]
    assert len(tr) + len(te) == 10 and len(te) in (3, 4)
    assert set(tr["id"]).isdisjoint(set(te["id"]))


def test_dataset_split_ratios(tmp_path: Path) -> None:
    p = tmp_path / "data.csv"
    df = pd.DataFrame({"id": list(range(10))})
    df.to_csv(p, index=False)
    outdir = tmp_path / "splits2"
    out = runner.invoke(
        app,
        [
            "adapters",
            "dataset",
            "split",
            "--csv",
            str(p),
            "--outdir",
            str(outdir),
            "--ratios",
            "0.6,0.2,0.2",
        ],
    ).stdout
    data = json.loads(out)
    assert (
        Path(data["train"]).exists()
        and Path(data["val"]).exists()
        and Path(data["test"]).exists()
    )
    tr = pd.read_csv(data["train"])  # type: ignore[arg-type]
    va = pd.read_csv(data["val"])  # type: ignore[arg-type]
    te = pd.read_csv(data["test"])  # type: ignore[arg-type]
    assert len(tr) + len(va) + len(te) == 10
    ids = set(tr["id"]).union(set(va["id"]))
    assert ids.isdisjoint(set(te["id"]))
