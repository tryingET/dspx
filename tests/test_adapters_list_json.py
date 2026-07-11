# summary: "Verifies the adapters list JSON mode returns the registered adapter-name array."
# read_when:
#   - "Changing adapter registry names or JSON list output."

from __future__ import annotations

import json
from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()


def test_adapters_list_json_outputs_array() -> None:
    res = runner.invoke(app, ["adapters", "list", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert isinstance(data, list) and "dataset.csv" in data
