"""UNIT authority parsing/dispatch; fake results never invoke native G."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
import verify_full_authority as authority


def claim(repo):
    return {
        "id": 5511,
        "repo": str(repo),
        "status": "claimed",
        "claimed_by": "unit-claimant",
        "lease_expires_at": "2030-01-01T00:00:00Z",
    }


def test_unit_exact_canonical_commands(tmp_path):
    calls = []

    def run(label, argv, **kwargs):
        calls.append(argv)
        assert kwargs["env"] == authority.HOST_ENV
        return (
            json.dumps([claim(tmp_path)])
            if label == "claim"
            else '{"ok":true,"payload":{"task":{"id":5061}}}'
        )

    assert authority.canonical_claim(run, tmp_path, "unit-claimant", 5511) == 5511
    assert authority.native_task5061(run, tmp_path)["kind"] == "native-integration"
    assert calls == [
        [authority.G, "--", "task", "list", "-s", "claimed", "-F", "json", "--verbose"],
        [authority.G, "--", "task", "show", "5061", "--machine"],
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "other-repo",
        "claimant",
        "expired",
        "timezone",
        "lease-missing",
        "bool-id",
        "wrong-id",
        "status",
        "malformed",
    ],
)
def test_unit_claim_rejects(tmp_path, mutation):
    row = claim(tmp_path)
    rows = [row]
    if mutation == "missing":
        rows = []
    elif mutation == "duplicate":
        rows *= 2
    elif mutation == "other-repo":
        row["repo"] = "/other"
    elif mutation == "claimant":
        row["claimed_by"] = "other"
    elif mutation == "expired":
        row["lease_expires_at"] = "2000-01-01T00:00:00Z"
    elif mutation == "timezone":
        row["lease_expires_at"] = "2030-01-01T00:00:00"
    elif mutation == "lease-missing":
        del row["lease_expires_at"]
    elif mutation == "bool-id":
        row["id"] = True
    elif mutation == "wrong-id":
        row["id"] = 5512
    elif mutation == "status":
        row["status"] = "completed"
    else:
        rows = ["not a task"]
    with pytest.raises(ValueError):
        authority.claimed_id(
            rows,
            tmp_path,
            "unit-claimant",
            5511,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize(
    "output",
    [
        "{}",
        "null",
        "not json",
        '{"ok":false}',
        '{"ok":true,"payload":{"task":{"id":1}}}',
        '{"ok":true,"ok":true}',
    ],
)
def test_unit_task5061_never_skips_or_accepts_malformed(tmp_path, output):
    with pytest.raises((ValueError, AttributeError)):
        authority.native_task5061(lambda *a, **k: output, tmp_path)


def test_unit_gate_error_propagates(tmp_path):
    def denied(*a, **k):
        raise RuntimeError("G owner denied")

    with pytest.raises(RuntimeError, match="owner denied"):
        authority.canonical_claim(denied, tmp_path, "unit-claimant", 5511)


def test_unit_host_scope_injects_native_resolver_without_task_shortcut(
    tmp_path, monkeypatch
):
    source = tmp_path / "packages/dspx-core/src/dspx/task_scope.py"
    source.parent.mkdir(parents=True)
    source.write_text("""from types import SimpleNamespace

def check_task_scope(repo, *, mode, claimed_task_resolver):
    return SimpleNamespace(ok=True, task_id=claimed_task_resolver(repo), mode=mode, changed_files=['unit'])
""")
    assert (
        authority.host_scope(
            lambda *a, **k: json.dumps([claim(tmp_path)]),
            tmp_path,
            "unit-claimant",
            5511,
        )["task_id"]
        == 5511
    )


def test_unit_scope_git_is_managed_and_nonzero_is_not_authority_fallback(tmp_path):
    import subprocess
    from verify_full_git import GIT_ENV

    subprocess.run(
        ["/usr/bin/git", "init", str(tmp_path)],
        env=GIT_ENV,
        check=True,
        capture_output=True,
    )
    source = tmp_path / "packages/dspx-core/src/dspx/task_scope.py"
    source.parent.mkdir(parents=True)
    source.write_text("""from types import SimpleNamespace

def check_task_scope(repo, *, mode, claimed_task_resolver):
    result = _run(['git', 'notes', 'show', 'HEAD'], cwd=repo)
    assert result.returncode == 1
    assert _git_output_nul(['diff', '-z'], cwd=repo) == ['a space.py', 'b.py']
    return SimpleNamespace(ok=True, task_id=claimed_task_resolver(repo), mode=mode, changed_files=[])
""")
    calls = []

    def run(label, argv, **kwargs):
        calls.append(argv)
        if label.endswith("-gitlinks"):
            return ""
        if label == "scope-git":
            assert argv[0] == "/usr/bin/git" and kwargs["check"] is False
            assert kwargs["env"]["GIT_CONFIG_GLOBAL"] == "/dev/null"
            kwargs["status"].append(1 if "notes" in argv else 0)
            return "missing note" if "notes" in argv else "a space.py\0b.py\0"
        return json.dumps([claim(tmp_path)])

    assert authority.host_scope(run, tmp_path, "unit-claimant", 5511)["task_id"] == 5511
    assert calls[-1][0] == authority.G


@pytest.mark.parametrize(
    "lease",
    [
        "2030-01-01T00:00:00+00:99",
        "2030-01-01T00:00:00-24:00",
        "2030-01-01T00:00:00-00:60",
        "2030-02-29T00:00:00Z",
        "2030-09-31T00:00:00Z",
        "2030-01-01T24:00:00Z",
    ],
)
@pytest.mark.parametrize("other_repo", [False, True])
def test_unit_literal_rfc3339_invalid_even_in_other_repo(tmp_path, lease, other_repo):
    row = claim(tmp_path / "other" if other_repo else tmp_path)
    row["lease_expires_at"] = lease
    row["id"] = 5512 if other_repo else 5511
    rows = [claim(tmp_path), row] if other_repo else [row]
    with pytest.raises(ValueError):
        authority.claimed_id(rows, tmp_path, "unit-claimant", 5511)


@pytest.mark.parametrize(
    "lease",
    [
        "2030-01-01T00:00:00Z",
        "2030-01-01T00:00:00+00:00",
        "2030-01-01T00:00:00.123456789+05:30",
    ],
)
def test_unit_rfc3339_valid_fractional_and_offset(tmp_path, lease):
    row = claim(tmp_path)
    row["lease_expires_at"] = lease
    assert authority.claimed_id([row], tmp_path, "unit-claimant", 5511) == 5511
