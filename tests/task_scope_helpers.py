# summary: "Git-backed helper routines for creating task-scope test repositories, commits, and snapshot fixtures."
# read_when:
#   - "Testing task-scope validation, snapshot handling, or synthetic repository history."

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "git", "init")
    _git(repo, "git", "config", "user.email", "pi@example.com")
    _git(repo, "git", "config", "user.name", "Pi")


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "git", "add", ".")
    _git(repo, "git", "commit", "-m", message)


def _write_snapshot(repo: Path, task_id: int, payload: dict[str, object]) -> None:
    path = repo / "governance" / "task-scopes" / f"AK-{task_id}.snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
