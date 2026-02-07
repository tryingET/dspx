from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_monorepo_boundaries.py"


def _run_check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), "--root", str(root)],
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )


def test_monorepo_boundary_check_passes_on_repo() -> None:
    res = _run_check(REPO_ROOT)
    assert res.returncode == 0, res.stdout + res.stderr


def test_monorepo_boundary_check_detects_core_importing_forge(tmp_path: Path) -> None:
    bad_file = tmp_path / "src" / "dspx" / "services" / "bad.py"
    bad_file.parent.mkdir(parents=True, exist_ok=True)
    bad_file.write_text(
        "from dspx.forge.workorder import build_workorder\n", encoding="utf-8"
    )

    res = _run_check(tmp_path)
    assert res.returncode == 1
    out = (res.stdout + res.stderr).lower()
    assert "core module imports forge app module" in out


def test_monorepo_boundary_check_detects_core_importing_app_surface(
    tmp_path: Path,
) -> None:
    bad_file = tmp_path / "src" / "dspx" / "services" / "bad.py"
    bad_file.parent.mkdir(parents=True, exist_ok=True)
    bad_file.write_text(
        "from dspx.apps.forge_compat import build_workorder\n", encoding="utf-8"
    )

    res = _run_check(tmp_path)
    assert res.returncode == 1
    out = (res.stdout + res.stderr).lower()
    assert "core module imports app surface module" in out
