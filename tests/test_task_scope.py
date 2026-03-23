from __future__ import annotations

import json
import subprocess
from pathlib import Path

from dspx.task_scope import (
    TaskScopeManifest,
    changed_files_for_head,
    check_task_scope,
    collect_scope_issues,
    load_manifest,
)


def test_collect_scope_issues_rejects_files_outside_manifest() -> None:
    manifest = TaskScopeManifest(
        task_id=266,
        description="test",
        allowed_paths=("scripts/*.py", "tests/*.py"),
        required_paths=("scripts/*.py",),
    )

    issues = collect_scope_issues(
        manifest,
        ["scripts/check_task_scope.py", "packages/dspx-core/src/dspx/task_scope.py"],
    )

    assert any(
        issue.path == "packages/dspx-core/src/dspx/task_scope.py" for issue in issues
    )
    assert any(issue.message == "falls outside attested task scope" for issue in issues)


def test_load_manifest_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "AK-266.json"
    path.write_text(
        json.dumps(
            {
                "task_id": 266,
                "description": "Scope attestation",
                "allowed_paths": ["scripts/*.py", "tests/*.py"],
                "required_paths": ["scripts/*.py"],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_manifest(path)
    assert manifest.task_id == 266
    assert manifest.allowed_paths == ("scripts/*.py", "tests/*.py")
    assert manifest.required_paths == ("scripts/*.py",)


def test_check_task_scope_head_passes_for_attested_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "pi@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Pi"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    (repo / "governance" / "task-scopes").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "tests").mkdir()

    (repo / "scripts" / "allowed.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    (repo / "governance" / "task-scopes" / "AK-266.json").write_text(
        json.dumps(
            {
                "task_id": 266,
                "description": "Scope attestation",
                "allowed_paths": [
                    "scripts/*.py",
                    "tests/*.py",
                    "governance/task-scopes/*.json",
                ],
                "required_paths": ["scripts/*.py", "governance/task-scopes/*.json"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "allowed.py").write_text("print('changed')\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "task slice"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    changed = changed_files_for_head(repo)
    assert sorted(changed) == [
        "governance/task-scopes/AK-266.json",
        "scripts/allowed.py",
    ]

    result = check_task_scope(repo, task_id=266, mode="head")
    assert result.ok is True
    assert result.changed_files == tuple(changed)


def test_check_task_scope_fails_without_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "pi@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Pi"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("hello again\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "change"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    result = check_task_scope(repo, task_id=266, mode="head")
    assert result.ok is False
    assert result.issues
    assert "missing task scope manifest" in result.issues[0].message
