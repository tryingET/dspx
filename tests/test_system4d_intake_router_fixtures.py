from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for TypeScript fixture test"
)
def test_system4d_intake_router_fixture_script() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "test_system4d_intake_router_fixtures.ts"

    result = subprocess.run(
        ["node", str(script)],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, (
        "system4d router fixture script failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert '"ok": true' in result.stdout
