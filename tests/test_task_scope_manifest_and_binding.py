# summary: "Tests task-scope manifest and AK snapshot parsing, forbidden-path checks, claimed-task discovery, and artifact preference."
# read_when:
#   - "Changing scope artifact schemas, default forbidden patterns, AK claim binding, or snapshot-versus-legacy resolution."

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import dspx.task_scope as task_scope_module
from dspx.task_scope import (
    TaskScopeManifest,
    claimed_task_ids_for_repo,
    collect_scope_issues,
    infer_claimed_task_id,
    load_manifest,
    load_snapshot,
    scope_artifact_path_for_task,
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


def test_claimed_task_ids_for_repo_filters_to_current_repo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    other_repo = tmp_path / "other"
    other_repo.mkdir()

    def fake_run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        assert cmd == ["ak", "task", "list", "-s", "claimed", "-F", "json"]
        assert cwd == repo
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=json.dumps(
                [
                    {"id": 266, "repo": str(repo.resolve())},
                    {"id": "bad", "repo": str(repo.resolve())},
                    {"id": 267, "repo": str(other_repo.resolve())},
                    "not-a-dict",
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr(task_scope_module, "_run", fake_run)

    assert claimed_task_ids_for_repo(repo) == [266]


def test_infer_claimed_task_id_rejects_multiple_repo_claims(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        task_scope_module,
        "claimed_task_ids_for_repo",
        lambda repo_root: [266, 267],
    )

    with pytest.raises(RuntimeError, match="multiple claimed tasks"):
        infer_claimed_task_id(repo)


def test_scope_artifact_path_for_task_prefers_snapshot_over_legacy_manifest(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    snapshot = repo / "governance" / "task-scopes" / "AK-266.snapshot.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("{}\n", encoding="utf-8")
    legacy_manifest = repo / "governance" / "task-scopes" / "AK-266.json"
    legacy_manifest.write_text("{}\n", encoding="utf-8")

    assert scope_artifact_path_for_task(repo, 266) == snapshot
