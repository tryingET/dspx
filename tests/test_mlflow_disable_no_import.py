from __future__ import annotations

import os
import subprocess
import sys


def test_mlflow_disabled_does_not_import_mlflow() -> None:
    env = dict(os.environ)
    env["MLFLOW_ENABLE"] = "0"
    env["MLFLOW_TRACKING_URI"] = "http://127.0.0.1:1"
    code = (
        "import sys\n"
        "import dspx.tracing as t\n"
        "x = t.get_mlflow()\n"
        "print(x)\n"
        "print('mlflow' in sys.modules)\n"
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
