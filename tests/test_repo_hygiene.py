from __future__ import annotations

import re
import subprocess
from pathlib import Path


def test_no_tracked_python_cache_or_backup_artifacts() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    tracked = subprocess.check_output(["git", "ls-files"], cwd=repo_root, text=True)
    bad = [
        line
        for line in tracked.splitlines()
        if re.search(r"(__pycache__/|\.pyc$|\.backup$)", line)
    ]
    assert bad == [], f"tracked generated artifacts must be removed: {bad}"
