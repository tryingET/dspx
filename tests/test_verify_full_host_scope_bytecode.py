"""Feature: the host scope gate never mutates the repository it inspects."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import verify_full_authority as authority  # noqa: E402
from test_verify_full_isolation import commit_tiny, gate  # noqa: E402
from verify_full_processes import Processes  # noqa: E402


def test_host_scope_never_writes_bytecode_into_the_inspected_repo(
    tmp_path, monkeypatch
):
    """Scenario: the scope gate is loaded by an interpreter without ``-B``.

    Given an interpreter that writes bytecode on import
    When host_scope loads the repository's own scope module to inspect it
    Then no ``__pycache__`` appears in the inspected repository
    And the scope check is not failed by the checker's own side effect
    And the interpreter's bytecode setting is restored afterwards
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    run = Processes(tmp_path / "logs").run
    run("init", ["/usr/bin/git", "init"], cwd=repo, env=gate.GIT_ENV)
    (repo / "README").write_text("baseline")
    commit_tiny(repo, Processes(tmp_path / "commit-logs"))
    target = repo / "packages/dspx-core/src/dspx/task_scope.py"
    target.parent.mkdir(parents=True)
    shutil.copy2(ROOT / target.relative_to(repo), target)
    manifest = repo / "governance/task-scopes/AK-266.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"task_id": 266, "description": "UNIT", "allowed_paths": ["**"]})
    )
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    monkeypatch.setattr(authority, "canonical_claim", lambda *args: 266)

    assert authority.host_scope(run, repo, "unit", 266)["task_id"] == 266
    assert not list(repo.rglob("__pycache__"))
    assert sys.dont_write_bytecode is False
