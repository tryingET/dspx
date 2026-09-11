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

    # Contract correction: filter only VALID other-repo rows; malformed rows deny.
    # Unit command-result fixture, not native authority evidence.
    def fake_run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        assert cmd == ["ak", "task", "list", "-s", "claimed", "-F", "json"]
        assert cwd == repo
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=json.dumps(
                [
                    {"id": 266, "repo": str(repo.resolve()), "status": "claimed"},
                    {"id": 267, "repo": str(other_repo.resolve()), "status": "claimed"},
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


def test_native_claim_lookup_really_missing_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Real OS lookup: no fake response, wrapper, or native AK execution.
    monkeypatch.setenv("PATH", "")
    assert not (tmp_path / "scripts/ak.sh").exists()
    assert claimed_task_ids_for_repo(tmp_path) == []
    assert infer_claimed_task_id(tmp_path) is None


@pytest.mark.parametrize(
    "message", ["denied", "registered repo scope", "could not compile `ak-cli`"]
)
def test_native_nonzero_never_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    monkeypatch.setattr(
        task_scope_module,
        "_run",
        lambda *a, **k: subprocess.CompletedProcess([], 1, "", message),
    )
    with pytest.raises(RuntimeError, match=message.replace("`", "[`]")):
        task_scope_module.check_task_scope(tmp_path)


@pytest.mark.parametrize(
    "output",
    [
        "invalid JSON",
        "{}",
        '[{"id": 2, "repo": "REPO", "status": "claimed"}, {"id": 2, "repo": "REPO", "status": "claimed"}]',
    ],
)
def test_native_malformed_or_duplicate_never_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    output = output.replace("REPO", str(tmp_path))
    monkeypatch.setattr(
        task_scope_module,
        "_run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, output, ""),
    )
    with pytest.raises((RuntimeError, ValueError)):
        task_scope_module.check_task_scope(tmp_path)


def test_native_permission_denial_is_not_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrapper = tmp_path / "scripts/ak.sh"
    wrapper.parent.mkdir()
    wrapper.write_text("not executable")
    wrapper.chmod(0o600)
    with pytest.raises(PermissionError):
        task_scope_module.check_task_scope(tmp_path)


def test_resolver_runtime_error_does_not_select_artifact(tmp_path: Path) -> None:
    def denied(_: Path) -> int | None:
        raise RuntimeError("unrelated runtime error")

    with pytest.raises(RuntimeError, match="unrelated runtime error"):
        task_scope_module.check_task_scope(tmp_path, claimed_task_resolver=denied)


@pytest.mark.parametrize(
    "case",
    [
        "wrapper-interpreter",
        "wrapper-link",
        "bare-interpreter",
        "bare-link",
        "missing-cwd",
    ],
)
def test_real_broken_configured_executable_is_not_claim_absence(tmp_path, case):
    # Child loads ONLY the actual stdlib scope module, no pytest audit hook or AK.
    # No executable fixture here can run: every interpreter/target is nonexistent.
    import sys

    repo = tmp_path / "repo"
    repo.mkdir()
    env = {"PATH": ""}
    if case.startswith("wrapper"):
        executable = repo / "scripts/ak.sh"
        executable.parent.mkdir()
    else:
        executable = repo / "ak"
    if case.endswith("link"):
        executable.symlink_to(repo / "missing-target")
    elif case != "missing-cwd":
        executable.write_text("#!/nonexistent-fixture-interpreter\n")
        executable.chmod(0o755)
    if case.startswith("bare"):
        env["PATH"] = str(repo)
    if case == "missing-cwd":
        repo = repo / "absent"
    code = """import importlib.util,sys; from pathlib import Path
spec=importlib.util.spec_from_file_location('scope', sys.argv[1])
module=importlib.util.module_from_spec(spec); sys.modules['scope']=module; spec.loader.exec_module(module)
try:
    module.claimed_task_ids_for_repo(Path(sys.argv[2]))
except RuntimeError as error:
    assert 'configured AK executable could not be launched' in str(error)
else:
    raise AssertionError('broken executable became no claim')
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            code,
            task_scope_module.__file__,
            str(repo),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "row",
    [
        None,
        "row",
        {"id": True},
        {"id": 1.0},
        {"id": "bad"},
        {"id": -1},
        {"repo": None},
        {"repo": 1},
        {"repo": "relative"},
        {"status": True},
        {"status": "queued"},
    ],
)
@pytest.mark.parametrize("other_repo", [False, True])
def test_unit_malformed_claim_rows_any_repo_deny_before_artifact_fallback(
    tmp_path, monkeypatch, row, other_repo
):
    valid = {
        "id": 266,
        "repo": str(tmp_path / "other") if other_repo else str(tmp_path),
        "status": "claimed",
    }
    item = valid | row if isinstance(row, dict) else row
    monkeypatch.setattr(
        task_scope_module,
        "_run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, json.dumps([item]), ""),
    )
    with pytest.raises(RuntimeError, match="malformed claimed task row"):
        task_scope_module.check_task_scope(tmp_path)


@pytest.mark.parametrize(
    "output",
    [
        '[{"id":266,"id":267,"repo":"/repo","status":"claimed"}]',
        '[{"id":266,"repo":"/repo","status":"claimed","extra":NaN}]',
    ],
)
def test_unit_duplicate_keys_and_non_json_constants_deny(tmp_path, monkeypatch, output):
    monkeypatch.setattr(
        task_scope_module,
        "_run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, output, ""),
    )
    with pytest.raises(ValueError):
        claimed_task_ids_for_repo(tmp_path)
