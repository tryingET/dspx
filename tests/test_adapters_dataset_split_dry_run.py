# summary: "Verifies dataset split dry runs report paths and counts without writing split files."
# read_when:
#   - "Changing dataset split dry-run semantics or summary output."

from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()


def test_dataset_split_dry_run_does_not_write(tmp_path: Path) -> None:
    p = tmp_path / "data.csv"
    df = pd.DataFrame({"id": list(range(10)), "y": [i % 2 for i in range(10)]})
    df.to_csv(p, index=False)
    outdir = tmp_path / "splits_dry"
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
            "--dry-run",
        ],
    ).stdout
    data = json.loads(out)
    # Paths are present in summary but files do not exist
    assert "train" in data and "test" in data
    assert not Path(data["train"]).exists() and not Path(data["test"]).exists()
    # Counts should be consistent
    c = data.get("counts") or {}
    assert c.get("train", 0) + c.get("test", 0) == 10
