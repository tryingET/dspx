from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dspx.task_scope import (
    TaskScopeManifest,
    changed_files_for_head,
    changed_files_for_working_tree,
    check_task_scope,
    collect_scope_issues,
    infer_task_id_from_next_session_checkpoint,
    load_manifest,
    load_snapshot,
)


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


def test_collect_scope_issues_rejects_root_level_forbidden_artifacts() -> None:
    manifest = TaskScopeManifest(
        task_id=266,
        description="test",
        allowed_paths=("**",),
    )

    issues = collect_scope_issues(manifest, ["foo.pyc", "bar.backup"])

    assert any(issue.path == "foo.pyc" for issue in issues)
    assert any(issue.path == "bar.backup" for issue in issues)
    assert all(issue.message == "matches forbidden path pattern" for issue in issues)


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


def test_load_snapshot_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "AK-266.snapshot.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "exported_at": "2026-03-31T00:00:00Z",
                "task_id": 266,
                "entity_version": 2,
                "commit_sha": None,
                "scope": {
                    "allowed_paths": ["scripts/*.py", "tests/*.py"],
                    "required_paths": ["scripts/*.py"],
                    "forbidden_paths": ["**/*.pyc"],
                },
                "default_applies": False,
                "export_tool": "ak task scope export",
                "export_tool_version": "snapshot-v1",
            }
        ),
        encoding="utf-8",
    )

    snapshot = load_snapshot(path)
    assert snapshot.task_id == 266
    assert snapshot.allowed_paths == ("scripts/*.py", "tests/*.py")
    assert snapshot.required_paths == ("scripts/*.py",)
    assert snapshot.forbidden_paths == ("**/*.pyc",)
    assert snapshot.source_kind == "ak_snapshot"
    assert snapshot.default_applies is False


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


def test_infer_task_id_from_next_session_checkpoint(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "next_session_prompt.md").write_text(
        "## SESSION CHECKPOINT (UPDATE BEFORE /commit)\n"
        "- Slice executed: `AK-266` — something\n",
        encoding="utf-8",
    )

    assert infer_task_id_from_next_session_checkpoint(repo) == 266


def test_check_task_scope_head_resolves_next_session_checkpoint_when_latest_commit_lacks_manifest(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "governance" / "task-scopes").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")

    (repo / "governance" / "task-scopes" / "AK-266.json").write_text(
        json.dumps(
            {
                "task_id": 266,
                "description": "Scope attestation",
                "allowed_paths": [
                    "scripts/*.py",
                    "governance/task-scopes/*.json",
                    "next_session_prompt.md",
                ],
                "required_paths": ["scripts/*.py", "governance/task-scopes/*.json"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "allowed.py").write_text("print('changed')\n", encoding="utf-8")
    _commit_all(repo, "manifest and allowed file")

    (repo / "next_session_prompt.md").write_text(
        "## SESSION CHECKPOINT (UPDATE BEFORE /commit)\n"
        "- Slice executed: `AK-266` — completed slice\n",
        encoding="utf-8",
    )
    _commit_all(repo, "checkpoint only")

    result = check_task_scope(repo, mode="head")
    assert result.ok is True
    assert result.task_id == 266
    assert "governance/task-scopes/AK-266.json" in result.changed_files
    assert "scripts/allowed.py" in result.changed_files
    assert "next_session_prompt.md" in result.changed_files


def test_check_task_scope_head_uses_checkpoint_to_disambiguate_multiple_manifests(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "governance" / "task-scopes").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")

    (repo / "governance" / "task-scopes" / "AK-266.json").write_text(
        json.dumps(
            {
                "task_id": 266,
                "description": "Scope attestation",
                "allowed_paths": [
                    "scripts/*.py",
                    "governance/task-scopes/*.json",
                    "next_session_prompt.md",
                ],
                "required_paths": ["scripts/*.py", "governance/task-scopes/*.json"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "allowed.py").write_text("print('changed')\n", encoding="utf-8")
    _commit_all(repo, "task 266 slice")

    (repo / "governance" / "task-scopes" / "AK-267.json").write_text(
        json.dumps(
            {
                "task_id": 267,
                "description": "Other scope attestation",
                "allowed_paths": ["governance/task-scopes/*.json"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "governance" / "task-scopes" / "AK-266.json").write_text(
        json.dumps(
            {
                "task_id": 266,
                "description": "Scope attestation updated",
                "allowed_paths": [
                    "scripts/*.py",
                    "governance/task-scopes/*.json",
                    "next_session_prompt.md",
                ],
                "required_paths": ["scripts/*.py", "governance/task-scopes/*.json"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "next_session_prompt.md").write_text(
        "## SESSION CHECKPOINT (UPDATE BEFORE /commit)\n"
        "- Slice executed: `AK-266` — completed slice\n",
        encoding="utf-8",
    )
    _commit_all(repo, "checkpoint plus two manifests")

    result = check_task_scope(repo, mode="head")
    assert result.ok is True
    assert result.task_id == 266
    assert "governance/task-scopes/AK-266.json" in result.changed_files
    assert "governance/task-scopes/AK-267.json" in result.changed_files


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


def test_changed_files_for_head_handles_root_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _commit_all(repo, "init")

    changed = changed_files_for_head(repo)

    assert changed == ["README.md"]


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


def test_check_task_scope_cli_help_matches_current_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "check_task_scope.py"
    proc = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "AK task-scope snapshot or transitional" in proc.stdout
    assert "legacy manifest" in proc.stdout
    assert "Check the attested task slice reachable from HEAD" in proc.stdout
    assert "current working tree, or auto-select working-tree when" in proc.stdout
    assert "the repo is dirty and HEAD when it is clean" in proc.stdout
    assert "latest committed slice" not in proc.stdout
    assert "the full task slice from the first task-scope artifact" in proc.stdout
    assert "introduction through HEAD" in proc.stdout


def test_check_task_scope_cli_accepts_documented_assignment_style_values(
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

    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "check_task_scope.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--root",
            str(repo),
            "--task-id",
            "task_id=266",
            "--mode",
            "mode=working-tree",
            "--range",
            "rev_range=auto",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "ok: task-scope-check task=AK-266 mode=working-tree" in proc.stdout


def test_task_scope_check_just_recipe_accepts_documented_assignment_style_values(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    repo_root = Path(__file__).resolve().parents[1]
    (repo / "scripts").mkdir(parents=True)
    (repo / "packages" / "dspx-core" / "src" / "dspx").mkdir(parents=True)
    (repo / "governance" / "task-scopes").mkdir(parents=True)
    shutil.copy2(
        repo_root / "scripts" / "check_task_scope.py",
        repo / "scripts" / "check_task_scope.py",
    )
    shutil.copy2(
        repo_root / "packages" / "dspx-core" / "src" / "dspx" / "task_scope.py",
        repo / "packages" / "dspx-core" / "src" / "dspx" / "task_scope.py",
    )
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

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [
            "just",
            "--justfile",
            str(repo_root / "Justfile"),
            "--working-directory",
            str(repo),
            "task-scope-check",
            "task_id=266",
            "mode=working-tree",
        ],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "ok: task-scope-check task=AK-266 mode=working-tree" in proc.stdout


def test_task_scope_check_just_recipe_defaults_to_auto_and_catches_dirty_working_tree(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    repo_root = Path(__file__).resolve().parents[1]
    (repo / "scripts").mkdir(parents=True)
    (repo / "packages" / "dspx-core" / "src" / "dspx").mkdir(parents=True)
    (repo / "governance" / "task-scopes").mkdir(parents=True)
    shutil.copy2(
        repo_root / "scripts" / "check_task_scope.py",
        repo / "scripts" / "check_task_scope.py",
    )
    shutil.copy2(
        repo_root / "packages" / "dspx-core" / "src" / "dspx" / "task_scope.py",
        repo / "packages" / "dspx-core" / "src" / "dspx" / "task_scope.py",
    )
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

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [
            "just",
            "--justfile",
            str(repo_root / "Justfile"),
            "--working-directory",
            str(repo),
            "task-scope-check",
            "task_id=266",
        ],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert "task-scope-check failed for AK-266 mode=working-tree" in proc.stdout
    assert "rogue.md: falls outside attested task scope" in proc.stdout
