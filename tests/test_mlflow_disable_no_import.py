# summary: "Tests that disabled MLflow stays unimported and creates no local store."
# read_when:
#   - "Changing disabled tracing startup or MLflow import behavior."

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_mlflow_disabled_does_not_import_mlflow() -> None:
    env = dict(os.environ)
    repo = Path(__file__).resolve().parents[1]
    extra = (
        f"{repo / 'packages' / 'dspx-core' / 'src'}:{repo / 'apps' / 'forge' / 'src'}"
    )
    env["PYTHONPATH"] = extra + (
        ":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env["MLFLOW_ENABLE"] = "0"
    env["MLFLOW_TRACKING_URI"] = "http://127.0.0.1:1"
    code = (
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "import dspx.tracing as t\n"
        "Path('sandbox').mkdir(exist_ok=True)\n"
        "os.chdir('sandbox')\n"
        "print(t.get_mlflow())\n"
        "print(t.enable_mlflow_from_env())\n"
        "print(t.ensure_run_from_env(run_name='should-not-start'))\n"
        "print('mlflow' in sys.modules)\n"
        "print(Path('mlflow.db').exists())\n"
        "print(Path('mlruns').exists())\n"
    )
    p = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert p.returncode == 0
    out = (p.stdout or "").strip().splitlines()
    assert out and out[0].strip() == "None"
    assert len(out) >= 2 and out[1].strip() == "False"
    assert len(out) >= 3 and out[2].strip() == "False"
    assert len(out) >= 4 and out[3].strip() == "False"
    assert len(out) >= 5 and out[4].strip() == "False"
    assert len(out) >= 6 and out[5].strip() == "False"
