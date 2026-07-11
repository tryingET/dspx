# summary: "Tests task-scope CLI help, assignment-style arguments, dirty-tree defaults, and explicit snapshot selection."
# read_when:
#   - "You are changing task-scope CLI arguments, Just recipes, scope artifact discovery, or working-tree validation."

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


from task_scope_helpers import _commit_all, _init_repo, _write_snapshot


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
    assert "AK task-scope snapshot" in proc.stdout
    assert "brownfield" in proc.stdout
    assert "legacy scope-file fallback" in proc.stdout
    assert "--scope-artifact" in proc.stdout
    assert "Explicit task-scope artifact path" in proc.stdout
    assert "legacy manifest" not in proc.stdout
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


def test_check_task_scope_cli_accepts_explicit_scope_artifact_path_for_snapshot(
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
    (repo / "scripts" / "allowed.py").write_text("print('dirty')\n", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "check_task_scope.py"
    snapshot_path = repo / "governance" / "task-scopes" / "AK-266.snapshot.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--root",
            str(repo),
            "--scope-artifact",
            str(snapshot_path),
            "--mode",
            "working-tree",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "ok: task-scope-check task=AK-266 mode=working-tree" in proc.stdout


def test_check_task_scope_cli_manifest_alias_accepts_snapshot_path(
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
    (repo / "scripts" / "allowed.py").write_text("print('dirty')\n", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "check_task_scope.py"
    snapshot_path = repo / "governance" / "task-scopes" / "AK-266.snapshot.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--root",
            str(repo),
            "--manifest",
            str(snapshot_path),
            "--mode",
            "working-tree",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "ok: task-scope-check task=AK-266 mode=working-tree" in proc.stdout
