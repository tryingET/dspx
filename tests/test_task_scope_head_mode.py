from __future__ import annotations

import json
from pathlib import Path

import pytest

import dspx.task_scope as task_scope_module
from dspx.task_scope import (
    changed_files_for_head,
    check_task_scope,
)
from task_scope_helpers import _commit_all, _git, _init_repo, _write_snapshot


def test_check_task_scope_head_passes_for_attested_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "governance" / "task-scopes").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "tests").mkdir()

    (repo / "scripts" / "allowed.py").write_text("print('ok')\n", encoding="utf-8")
    _commit_all(repo, "init")

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
    _commit_all(repo, "task slice")

    changed = changed_files_for_head(repo)
    assert sorted(changed) == [
        "governance/task-scopes/AK-266.json",
        "scripts/allowed.py",
    ]

    result = check_task_scope(repo, task_id=266, mode="head")
    assert result.ok is True
    assert result.task_id == 266
    assert result.changed_files == tuple(changed)


def test_check_task_scope_skips_when_no_scope_artifact_exists(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")
    (repo / "README.md").write_text("hello again\n", encoding="utf-8")
    _commit_all(repo, "change")

    result = check_task_scope(repo, task_id=266, mode="head")
    assert result.ok is False
    assert result.skipped is True
    assert result.issues == ()
    assert "repo-default scope applies" in (result.skip_reason or "")


def test_check_task_scope_resolves_head_manifest_when_no_claim(tmp_path: Path) -> None:
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
                "required_paths": ["scripts/*.py", "governance/task-scopes/*.json"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "allowed.py").write_text("print('changed')\n", encoding="utf-8")
    _commit_all(repo, "task slice")

    result = check_task_scope(repo, mode="head")
    assert result.ok is True
    assert result.skipped is False
    assert result.task_id == 266
    assert sorted(result.changed_files) == [
        "governance/task-scopes/AK-266.json",
        "scripts/allowed.py",
    ]


def test_check_task_scope_head_passes_for_snapshot_commit(tmp_path: Path) -> None:
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
    _commit_all(repo, "snapshot task slice")

    result = check_task_scope(repo, task_id=266, mode="head")
    assert result.ok is True
    assert result.task_id == 266
    assert sorted(result.changed_files) == [
        "governance/task-scopes/AK-266.snapshot.json",
        "scripts/allowed.py",
    ]


def test_check_task_scope_skips_when_snapshot_default_applies(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

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
            "scope": None,
            "default_applies": True,
            "export_tool": "ak task scope export",
            "export_tool_version": "snapshot-v1",
        },
    )

    result = check_task_scope(repo, task_id=266, mode="head")
    assert result.ok is False
    assert result.skipped is True
    assert result.task_id == 266
    assert "repo-default scope applies" in (result.skip_reason or "")


def test_check_task_scope_fails_closed_when_task_id_cannot_be_resolved(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")
    (repo / "README.md").write_text("hello again\n", encoding="utf-8")
    _commit_all(repo, "change")

    result = check_task_scope(repo, mode="head")
    assert result.ok is False
    assert result.skipped is False
    assert result.task_id is None
    assert result.issues
    assert "could not resolve a task id" in result.issues[0].message


def test_check_task_scope_head_fails_closed_when_latest_commit_only_updates_handoff(
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
            "entity_version": 2,
            "commit_sha": None,
            "scope": {
                "allowed_paths": [
                    "scripts/*.py",
                    "governance/task-scopes/*.snapshot.json",
                    "next_session_prompt.md",
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
    _commit_all(repo, "snapshot and allowed file")

    (repo / "next_session_prompt.md").write_text(
        "## SESSION CHECKPOINT (UPDATE BEFORE /commit)\n"
        "- Slice executed: `AK-266` — completed slice\n",
        encoding="utf-8",
    )
    _commit_all(repo, "handoff only")

    result = check_task_scope(repo, mode="head")
    assert result.ok is False
    assert result.task_id is None
    assert result.issues
    assert "HEAD task-scope artifact changes" in result.issues[0].message
    assert "next_session_prompt checkpoint" not in result.issues[0].message


def test_check_task_scope_head_passes_for_explicit_task_id_when_latest_commit_only_updates_handoff(
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
            "entity_version": 2,
            "commit_sha": None,
            "scope": {
                "allowed_paths": [
                    "scripts/*.py",
                    "governance/task-scopes/*.snapshot.json",
                    "next_session_prompt.md",
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
    _commit_all(repo, "snapshot and allowed file")

    (repo / "next_session_prompt.md").write_text(
        "## SESSION CHECKPOINT (UPDATE BEFORE /commit)\n"
        "- Slice executed: `AK-266` — completed slice\n",
        encoding="utf-8",
    )
    _commit_all(repo, "handoff only")

    result = check_task_scope(repo, task_id=266, mode="head")
    assert result.ok is True
    assert result.task_id == 266
    assert "governance/task-scopes/AK-266.snapshot.json" in result.changed_files
    assert "scripts/allowed.py" in result.changed_files
    assert "next_session_prompt.md" in result.changed_files


def test_check_task_scope_head_fails_closed_when_latest_commit_touches_multiple_scope_artifacts_without_explicit_binding(
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
    _commit_all(repo, "task 266 slice")

    _write_snapshot(
        repo,
        267,
        {
            "schema_version": 1,
            "exported_at": "2026-03-31T00:00:00Z",
            "task_id": 267,
            "entity_version": 1,
            "commit_sha": None,
            "scope": {
                "allowed_paths": ["governance/task-scopes/*.snapshot.json"],
                "required_paths": ["governance/task-scopes/*.snapshot.json"],
                "forbidden_paths": ["**/*.pyc"],
            },
            "default_applies": False,
            "export_tool": "ak task scope export",
            "export_tool_version": "snapshot-v1",
        },
    )
    _write_snapshot(
        repo,
        266,
        {
            "schema_version": 1,
            "exported_at": "2026-03-31T00:00:00Z",
            "task_id": 266,
            "entity_version": 3,
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
    _commit_all(repo, "two scope artifacts")

    result = check_task_scope(repo, mode="head")
    assert result.ok is False
    assert result.task_id is None
    assert result.issues
    assert (
        "multiple task-scope artifacts detected in changed files"
        in result.issues[0].message
    )


def test_check_task_scope_auto_range_covers_full_multi_commit_slice(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "scripts").mkdir(parents=True)
    (repo / "docs").mkdir(parents=True)
    (repo / "governance" / "task-scopes").mkdir(parents=True)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")

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
    (repo / "scripts" / "allowed.py").write_text("print('ok')\n", encoding="utf-8")
    _commit_all(repo, "manifest and allowed file")

    (repo / "docs" / "outside.md").write_text("oops\n", encoding="utf-8")
    _commit_all(repo, "out of scope")

    (repo / "scripts" / "allowed.py").write_text(
        "print('still ok')\n", encoding="utf-8"
    )
    _commit_all(repo, "in scope follow-up")

    result = check_task_scope(repo, task_id=266, mode="head")
    assert result.ok is False
    assert "docs/outside.md" in result.changed_files
    assert any(issue.path == "docs/outside.md" for issue in result.issues)

    latest_only = check_task_scope(
        repo, task_id=266, mode="head", rev_range="HEAD^..HEAD"
    )
    assert latest_only.ok is False
    assert latest_only.changed_files == ("scripts/allowed.py",)
    assert all(issue.path != "docs/outside.md" for issue in latest_only.issues)
    assert any(
        "governance/task-scopes/*.json" in issue.message
        for issue in latest_only.issues
        if issue.path is None
    )


def test_changed_files_for_head_handles_root_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")

    changed = changed_files_for_head(repo)

    assert changed == ["README.md"]


def test_check_task_scope_head_uses_claimed_task_binding_for_full_slice(
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
    _commit_all(repo, "snapshot")

    (repo / "scripts" / "allowed.py").write_text("print('changed')\n", encoding="utf-8")
    _commit_all(repo, "allowed change")

    monkeypatch.setattr(task_scope_module, "infer_claimed_task_id", lambda _: 266)

    result = check_task_scope(repo, mode="head")

    assert result.ok is True
    assert result.task_id == 266
    assert result.changed_files == (
        "governance/task-scopes/AK-266.snapshot.json",
        "scripts/allowed.py",
    )


def test_check_task_scope_head_accepts_required_paths_from_recent_commit_group_provenance(
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
    _commit_all(repo, "second commit group")
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

    result = check_task_scope(repo, task_id=266, mode="head")

    assert result.ok is True
    assert result.task_id == 266
    assert sorted(result.changed_files) == [
        "docs/second.md",
        "governance/task-scopes/AK-266.snapshot.json",
        "scripts/first.py",
    ]
