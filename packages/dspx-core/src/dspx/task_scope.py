from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path


DEFAULT_FORBIDDEN_PATTERNS = [
    "**/__pycache__/**",
    "**/*.pyc",
    "**/*.pyo",
    "**/*.backup",
]


@dataclass(frozen=True)
class ScopeIssue:
    message: str
    path: str | None = None


@dataclass(frozen=True)
class TaskScopeManifest:
    task_id: int
    description: str
    allowed_paths: tuple[str, ...]
    required_paths: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = tuple(DEFAULT_FORBIDDEN_PATTERNS)


@dataclass(frozen=True)
class ScopeCheckResult:
    task_id: int | None
    mode: str
    changed_files: tuple[str, ...]
    issues: tuple[ScopeIssue, ...]
    skipped: bool = False
    skip_reason: str | None = None

    @property
    def ok(self) -> bool:
        return not self.skipped and not self.issues


def _run(
    cmd: list[str],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _git_output(cmd: list[str], *, cwd: Path) -> list[str]:
    proc = _run(["git", *cmd], cwd=cwd)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "git command failed").strip())
    return [line.rstrip() for line in proc.stdout.splitlines() if line.strip()]


def _git_output_nul(cmd: list[str], *, cwd: Path) -> list[str]:
    proc = subprocess.run(
        ["git", *cmd],
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace") if proc.stderr else ""
        stdout = proc.stdout.decode(errors="replace") if proc.stdout else ""
        raise RuntimeError((stderr or stdout or "git command failed").strip())
    return [
        item.decode(errors="replace")
        for item in proc.stdout.split(b"\0")
        if item.strip(b"\0")
    ]


def claimed_task_ids_for_repo(repo_root: Path) -> list[int]:
    proc = _run(["ak", "task", "list", "-s", "claimed", "-F", "json"], cwd=repo_root)
    if proc.returncode != 0:
        raise RuntimeError(
            (proc.stderr or proc.stdout or "ak task list failed").strip()
        )
    payload = json.loads(proc.stdout)
    if not isinstance(payload, list):
        raise RuntimeError("claimed task payload was not a list")

    repo = str(repo_root.resolve())
    out: list[int] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("repo") != repo:
            continue
        task_id = item.get("id")
        if isinstance(task_id, int):
            out.append(task_id)
    return out


def infer_claimed_task_id(repo_root: Path) -> int | None:
    claimed = claimed_task_ids_for_repo(repo_root)
    if not claimed:
        return None
    if len(claimed) > 1:
        raise RuntimeError(
            f"multiple claimed tasks for repo {repo_root}: {', '.join(str(item) for item in claimed)}"
        )
    return claimed[0]


def manifest_path_for_task(repo_root: Path, task_id: int) -> Path:
    return repo_root / "governance" / "task-scopes" / f"AK-{task_id}.json"


def _manifest_relpath_for_task(task_id: int) -> str:
    return f"governance/task-scopes/AK-{task_id}.json"


def _task_id_from_manifest_path(path: str) -> int | None:
    normalized = path.replace("\\", "/")
    prefix = "governance/task-scopes/AK-"
    suffix = ".json"
    if not normalized.startswith(prefix) or not normalized.endswith(suffix):
        return None
    raw = normalized[len(prefix) : -len(suffix)]
    if not raw.isdigit():
        return None
    return int(raw)


def infer_task_id_from_changed_files(changed_files: list[str]) -> int | None:
    task_ids = {
        task_id
        for path in changed_files
        if (task_id := _task_id_from_manifest_path(path)) is not None
    }
    if not task_ids:
        return None
    if len(task_ids) > 1:
        raise RuntimeError(
            "multiple task scope manifests detected in changed files: "
            + ", ".join(f"AK-{item}" for item in sorted(task_ids))
        )
    return next(iter(task_ids))


def infer_task_id_from_head(
    repo_root: Path, rev_range: str = "HEAD^..HEAD"
) -> int | None:
    return infer_task_id_from_changed_files(
        changed_files_for_head(repo_root, rev_range=rev_range)
    )


def _extract_task_id_from_next_session_marker(text: str, *, label: str) -> int | None:
    match = re.search(rf"^\s*-\s*{re.escape(label)}\s*`AK-(\d+)`", text, re.MULTILINE)
    if match is None:
        return None
    return int(match.group(1))


def infer_task_id_from_next_session_checkpoint(repo_root: Path) -> int | None:
    path = repo_root / "next_session_prompt.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    return _extract_task_id_from_next_session_marker(text, label="Slice executed:")


def infer_task_id_from_working_tree(repo_root: Path) -> int | None:
    return infer_task_id_from_changed_files(changed_files_for_working_tree(repo_root))


def task_slice_commits(repo_root: Path, task_id: int) -> list[str]:
    manifest_relpath = _manifest_relpath_for_task(task_id)
    manifest_commits = _git_output(
        ["rev-list", "--reverse", "HEAD", "--", manifest_relpath], cwd=repo_root
    )
    if not manifest_commits:
        return []

    first_commit = manifest_commits[0]
    remainder = _git_output(
        ["rev-list", "--reverse", "--ancestry-path", f"{first_commit}..HEAD"],
        cwd=repo_root,
    )
    return [first_commit, *remainder]


def changed_files_for_task_slice(repo_root: Path, task_id: int) -> list[str]:
    commits = task_slice_commits(repo_root, task_id)
    changed: set[str] = set()
    for commit in commits:
        changed.update(
            _git_output(
                [
                    "diff-tree",
                    "--root",
                    "--no-commit-id",
                    "--name-only",
                    "--diff-filter=ACMRD",
                    "-r",
                    commit,
                ],
                cwd=repo_root,
            )
        )
    return sorted(changed)


def load_manifest(path: Path) -> TaskScopeManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"task scope manifest must be a JSON object: {path}")

    task_id = data.get("task_id")
    description = data.get("description")
    allowed_paths = data.get("allowed_paths")
    required_paths = data.get("required_paths") or []
    forbidden_paths = data.get("forbidden_paths") or DEFAULT_FORBIDDEN_PATTERNS

    if not isinstance(task_id, int):
        raise ValueError(f"task scope manifest missing integer task_id: {path}")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"task scope manifest missing description: {path}")
    if (
        not isinstance(allowed_paths, list)
        or not allowed_paths
        or not all(isinstance(item, str) and item for item in allowed_paths)
    ):
        raise ValueError(f"task scope manifest missing allowed_paths: {path}")
    if not isinstance(required_paths, list) or not all(
        isinstance(item, str) and item for item in required_paths
    ):
        raise ValueError(f"task scope manifest has invalid required_paths: {path}")
    if not isinstance(forbidden_paths, list) or not all(
        isinstance(item, str) and item for item in forbidden_paths
    ):
        raise ValueError(f"task scope manifest has invalid forbidden_paths: {path}")

    return TaskScopeManifest(
        task_id=task_id,
        description=description.strip(),
        allowed_paths=tuple(allowed_paths),
        required_paths=tuple(required_paths),
        forbidden_paths=tuple(forbidden_paths),
    )


def changed_files_for_head(
    repo_root: Path, rev_range: str = "HEAD^..HEAD"
) -> list[str]:
    if rev_range == "HEAD^..HEAD":
        parent_check = _run(["git", "rev-parse", "--verify", "HEAD^"], cwd=repo_root)
        if parent_check.returncode != 0:
            return _git_output(
                [
                    "diff-tree",
                    "--root",
                    "--no-commit-id",
                    "--name-only",
                    "--diff-filter=ACMRD",
                    "-r",
                    "HEAD",
                ],
                cwd=repo_root,
            )
    return _git_output(
        ["diff", "--name-only", "--diff-filter=ACMRD", rev_range], cwd=repo_root
    )


def changed_files_for_working_tree(repo_root: Path) -> list[str]:
    tracked = set(_git_output_nul(["diff", "--name-only", "-z", "HEAD"], cwd=repo_root))
    untracked = set(
        _git_output_nul(
            ["ls-files", "--others", "--exclude-standard", "-z"],
            cwd=repo_root,
        )
    )
    return sorted(tracked | untracked)


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    path = path.replace("\\", "/")
    for pattern in patterns:
        candidates = [pattern]
        if pattern.startswith("**/"):
            candidates.append(pattern[3:])
        if any(fnmatchcase(path, candidate) for candidate in candidates):
            return True
    return False


def collect_scope_issues(
    manifest: TaskScopeManifest,
    changed_files: list[str],
) -> list[ScopeIssue]:
    issues: list[ScopeIssue] = []
    normalized = [item.replace("\\", "/") for item in changed_files if item.strip()]

    if not normalized:
        issues.append(ScopeIssue("no changed files found for scope check"))
        return issues

    for path in normalized:
        if _matches_any(path, manifest.forbidden_paths):
            issues.append(ScopeIssue("matches forbidden path pattern", path=path))
        if not _matches_any(path, manifest.allowed_paths):
            issues.append(ScopeIssue("falls outside attested task scope", path=path))

    for pattern in manifest.required_paths:
        if not any(_matches_any(path, (pattern,)) for path in normalized):
            issues.append(
                ScopeIssue(
                    f"required scope pattern did not appear in changes: {pattern}"
                )
            )
    return issues


def _resolve_scope_check_mode(repo_root: Path, mode: str) -> str:
    if mode != "auto":
        return mode
    return "working-tree" if changed_files_for_working_tree(repo_root) else "head"


def check_task_scope(
    repo_root: Path,
    *,
    task_id: int | None = None,
    manifest_path: Path | None = None,
    mode: str = "head",
    rev_range: str = "auto",
) -> ScopeCheckResult:
    mode = _resolve_scope_check_mode(repo_root, mode)
    resolved_task_id = task_id
    if resolved_task_id is None and manifest_path is None:
        resolution_issue: str | None = None
        resolved_task_id = infer_claimed_task_id(repo_root)
        if resolved_task_id is None and mode == "working-tree":
            resolved_task_id = infer_task_id_from_working_tree(repo_root)
        if resolved_task_id is None:
            head_rev_range = "HEAD^..HEAD" if rev_range == "auto" else rev_range
            try:
                resolved_task_id = infer_task_id_from_head(
                    repo_root, rev_range=head_rev_range
                )
            except RuntimeError as exc:
                resolution_issue = str(exc)
        if resolved_task_id is None and mode == "head":
            resolved_task_id = infer_task_id_from_next_session_checkpoint(repo_root)
        if resolved_task_id is None:
            message = (
                resolution_issue
                or "task scope check could not resolve a task id from explicit input, AK claims, working-tree manifest changes, HEAD manifest changes, or next_session_prompt checkpoint"
            )
            return ScopeCheckResult(
                task_id=None,
                mode=mode,
                changed_files=(),
                issues=(ScopeIssue(message),),
            )

    if manifest_path is not None:
        resolved_manifest_path = manifest_path
    else:
        if resolved_task_id is None:
            raise RuntimeError("task scope check could not resolve a task id")
        resolved_manifest_path = manifest_path_for_task(repo_root, resolved_task_id)
    if not resolved_manifest_path.exists():
        return ScopeCheckResult(
            task_id=resolved_task_id,
            mode=mode,
            changed_files=(),
            issues=(
                ScopeIssue(
                    f"missing task scope manifest: {resolved_manifest_path.relative_to(repo_root)}"
                ),
            ),
        )

    manifest = load_manifest(resolved_manifest_path)
    if resolved_task_id is not None and manifest.task_id != int(resolved_task_id):
        return ScopeCheckResult(
            task_id=resolved_task_id,
            mode=mode,
            changed_files=(),
            issues=(
                ScopeIssue(
                    f"manifest task_id mismatch: expected {resolved_task_id}, found {manifest.task_id}"
                ),
            ),
        )

    if mode == "head":
        if rev_range == "auto":
            changed = changed_files_for_task_slice(repo_root, manifest.task_id)
        else:
            changed = changed_files_for_head(repo_root, rev_range=rev_range)
    elif mode == "working-tree":
        changed = changed_files_for_working_tree(repo_root)
    else:
        raise ValueError(f"unsupported task scope mode: {mode}")

    issues = collect_scope_issues(manifest, changed)
    return ScopeCheckResult(
        task_id=manifest.task_id,
        mode=mode,
        changed_files=tuple(changed),
        issues=tuple(issues),
    )


def format_scope_result(result: ScopeCheckResult) -> str:
    if result.skipped:
        return f"skip: task-scope-check ({result.skip_reason})"
    if result.ok:
        changed = ", ".join(result.changed_files) if result.changed_files else "-"
        return (
            f"ok: task-scope-check task=AK-{result.task_id} mode={result.mode} "
            f"changed={changed}"
        )

    header = (
        f"task-scope-check failed for AK-{result.task_id} mode={result.mode}"
        if result.task_id is not None
        else f"task-scope-check failed mode={result.mode}"
    )
    lines = [header]
    for issue in result.issues:
        if issue.path:
            lines.append(f"- {issue.path}: {issue.message}")
        else:
            lines.append(f"- {issue.message}")
    return "\n".join(lines)
