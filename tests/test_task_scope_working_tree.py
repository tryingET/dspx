from __future__ import annotations

import json
from pathlib import Path

import pytest

import dspx.task_scope as task_scope_module
from dspx.task_scope import (
    changed_files_for_working_tree,
    check_task_scope,
)
from task_scope_helpers import _commit_all, _git, _init_repo, _write_snapshot


def test_changed_files_for_working_tree_reports_modified_tracked_file(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "allowed.py").write_text("print('ok')\n", encoding="utf-8")
    _commit_all(repo, "init")

    (repo / "scripts" / "allowed.py").write_text("print('changed')\n", encoding="utf-8")

    changed = changed_files_for_working_tree(repo)

    assert changed == ["scripts/allowed.py"]


def test_changed_files_for_working_tree_preserves_spaces_in_tracked_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "scripts").mkdir(parents=True)
    tracked = repo / "scripts" / "my file.py"
    tracked.write_text("print('ok')\n", encoding="utf-8")
    _commit_all(repo, "init")

    tracked.write_text("print('changed')\n", encoding="utf-8")

    changed = changed_files_for_working_tree(repo)

    assert changed == ["scripts/my file.py"]


def test_changed_files_for_working_tree_reports_untracked_nested_files(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")

    (repo / "scripts").mkdir(parents=True)
    nested = repo / "scripts" / "my file.py"
    nested.write_text("print('new')\n", encoding="utf-8")

    changed = changed_files_for_working_tree(repo)

    assert changed == ["scripts/my file.py"]


def test_changed_files_for_working_tree_does_not_misparse_arrow_in_filename(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")

    arrow_file = repo / "a -> b.py"
    arrow_file.write_text("print('new')\n", encoding="utf-8")

    changed = changed_files_for_working_tree(repo)

    assert changed == ["a -> b.py"]


def test_check_task_scope_working_tree_resolves_uncommitted_manifest_before_head(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")
    (repo / "README.md").write_text("hello again\n", encoding="utf-8")
    _commit_all(repo, "second")

    (repo / "scripts").mkdir(parents=True)
    (repo / "governance" / "task-scopes").mkdir(parents=True)
    (repo / "governance" / "task-scopes" / "AK-266.json").write_text(
        json.dumps(
            {
                "task_id": 266,
                "description": "Scope attestation",
                "allowed_paths": ["scripts/*.py", "governance/task-scopes/*.json"],
                "required_paths": ["scripts/*.py", "governance/task-scopes/*.json"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "allowed.py").write_text("print('changed')\n", encoding="utf-8")

    result = check_task_scope(repo, mode="working-tree")

    assert result.ok is True
    assert result.task_id == 266
    assert sorted(result.changed_files) == [
        "governance/task-scopes/AK-266.json",
        "scripts/allowed.py",
    ]


def test_check_task_scope_working_tree_resolves_uncommitted_snapshot_before_head(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")
    (repo / "README.md").write_text("hello again\n", encoding="utf-8")
    _commit_all(repo, "second")

    (repo / "scripts").mkdir(parents=True)
    _write_snapshot(
        repo,
        266,
        {
            "schema_version": 1,
            "exported_at": "2026-03-31T00:00:00Z",
            "task_id": 266,
            "entity_version": 2,
            "commit_sha": None,
            "scope": {
                "allowed_paths": [
                    "scripts/*.py",
                    "governance/task-scopes/*.snapshot.json",
                ],
                "required_paths": [
                    "scripts/*.py",
                    "governance/task-scopes/*.snapshot.json",
                ],
                "forbidden_paths": ["**/*.pyc"],
            },
            "default_applies": False,
            "export_tool": "ak task scope export",
            "export_tool_version": "snapshot-v1",
        },
    )
    (repo / "scripts" / "allowed.py").write_text("print('changed')\n", encoding="utf-8")

    result = check_task_scope(repo, mode="working-tree")

    assert result.ok is True
    assert result.task_id == 266
    assert sorted(result.changed_files) == [
        "governance/task-scopes/AK-266.snapshot.json",
        "scripts/allowed.py",
    ]


def test_check_task_scope_auto_uses_working_tree_for_uncommitted_slice(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")

    (repo / "scripts").mkdir(parents=True)
    (repo / "governance" / "task-scopes").mkdir(parents=True)
    (repo / "governance" / "task-scopes" / "AK-266.json").write_text(
        json.dumps(
            {
                "task_id": 266,
                "description": "Scope attestation",
                "allowed_paths": ["scripts/*.py", "governance/task-scopes/*.json"],
                "required_paths": [
                    "scripts/*.py",
                    "governance/task-scopes/*.json",
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "allowed.py").write_text("print('changed')\n", encoding="utf-8")

    result = check_task_scope(repo, mode="auto")

    assert result.ok is True
    assert result.mode == "working-tree"
    assert result.task_id == 266
    assert sorted(result.changed_files) == [
        "governance/task-scopes/AK-266.json",
        "scripts/allowed.py",
    ]


def test_check_task_scope_auto_uses_working_tree_to_catch_dirty_out_of_scope_files(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "scripts").mkdir(parents=True)
    (repo / "governance" / "task-scopes").mkdir(parents=True)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")

    (repo / "governance" / "task-scopes" / "AK-266.json").write_text(
        json.dumps(
            {
                "task_id": 266,
                "description": "Scope attestation",
                "allowed_paths": ["scripts/*.py", "governance/task-scopes/*.json"],
                "required_paths": [
                    "scripts/*.py",
                    "governance/task-scopes/*.json",
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "allowed.py").write_text("print('changed')\n", encoding="utf-8")
    _commit_all(repo, "task slice")

    (repo / "rogue.md").write_text("oops\n", encoding="utf-8")

    result = check_task_scope(repo, mode="auto")

    assert result.ok is False
    assert result.mode == "working-tree"
    assert result.task_id == 266
    assert "rogue.md" in result.changed_files
    assert any(issue.path == "rogue.md" for issue in result.issues)


def test_check_task_scope_working_tree_uses_claimed_task_binding_without_scope_artifact_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "scripts").mkdir(parents=True)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")

    _write_snapshot(
        repo,
        266,
        {
            "schema_version": 1,
            "exported_at": "2026-03-31T00:00:00Z",
            "task_id": 266,
            "entity_version": 1,
            "commit_sha": None,
            "scope": {
                "allowed_paths": ["scripts/*.py"],
                "required_paths": ["scripts/*.py"],
                "forbidden_paths": ["**/*.pyc"],
            },
            "default_applies": False,
            "export_tool": "ak task scope export",
            "export_tool_version": "snapshot-v1",
        },
    )
    _commit_all(repo, "snapshot")

    (repo / "scripts" / "seed.py").write_text("print('seed')\n", encoding="utf-8")
    _commit_all(repo, "seed")

    (repo / "scripts" / "allowed.py").write_text("print('dirty')\n", encoding="utf-8")

    monkeypatch.setattr(task_scope_module, "infer_claimed_task_id", lambda _: 266)

    result = check_task_scope(repo, mode="working-tree")

    assert result.ok is True
    assert result.task_id == 266
    assert result.changed_files == ("scripts/allowed.py",)


def test_check_task_scope_working_tree_accepts_required_paths_from_recent_commit_group_provenance(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "scripts").mkdir(parents=True)
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")

    (repo / "scripts" / "first.py").write_text("print('first')\n", encoding="utf-8")
    _commit_all(repo, "first commit group")
    _git(
        repo,
        "git",
        "notes",
        "--ref=refs/notes/ai-society/provenance",
        "add",
        "-m",
        "kind: ai-society/commit-provenance/v1\nlinks:\n  task_ids:\n    - 266\n",
        "HEAD",
    )

    _write_snapshot(
        repo,
        266,
        {
            "schema_version": 1,
            "exported_at": "2026-03-31T00:00:00Z",
            "task_id": 266,
            "entity_version": 2,
            "commit_sha": None,
            "scope": {
                "allowed_paths": [
                    "scripts/*.py",
                    "docs/*.md",
                    "governance/task-scopes/*.snapshot.json",
                ],
                "required_paths": [
                    "scripts/first.py",
                    "docs/second.md",
                    "governance/task-scopes/*.snapshot.json",
                ],
                "forbidden_paths": ["**/*.pyc"],
            },
            "default_applies": False,
            "export_tool": "ak task scope export",
            "export_tool_version": "snapshot-v1",
        },
    )
    (repo / "docs" / "second.md").write_text("second\n", encoding="utf-8")

    result = check_task_scope(repo, task_id=266, mode="working-tree")

    assert result.ok is True
    assert result.task_id == 266
    assert sorted(result.changed_files) == [
        "docs/second.md",
        "governance/task-scopes/AK-266.snapshot.json",
        "scripts/first.py",
    ]
