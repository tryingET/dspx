from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import scripts.cleanup_artifacts as cleanup_artifacts
from scripts.cleanup_artifacts import cleanup


def test_cleanup_defaults_to_dry_run_then_requires_exact_plan_and_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    old = root / "kind" / "old-run.json"
    old.parent.mkdir()
    old.write_text("{}", encoding="utf-8")
    fresh = root / "fresh-run.json"
    fresh.write_text("{}", encoding="utf-8")
    stale = time.time() - 10 * 86400
    os.utime(old, (stale, stale))

    inspected = cleanup(root, older_than_days=7)
    assert inspected["mode"] == "dry_run"
    assert inspected["candidates"] == [str(old)]
    assert inspected["candidate_bytes"] == 2
    assert old.exists() and fresh.exists()

    with pytest.raises(ValueError, match="plan-id"):
        cleanup(root, older_than_days=7, apply=True, confirmed_root=root)
    with pytest.raises(ValueError, match="confirm-root"):
        cleanup(
            root,
            older_than_days=7,
            apply=True,
            expected_plan_id=inspected["plan_id"],
        )

    applied = cleanup(
        root,
        older_than_days=7,
        apply=True,
        expected_plan_id=inspected["plan_id"],
        confirmed_root=root,
    )
    assert applied["deleted"] == [str(old)]
    assert not old.exists()
    assert old.parent.exists()
    assert fresh.exists()


def test_cleanup_plan_fails_closed_when_candidate_changes(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    old = root / "old-run.json"
    old.write_text("{}", encoding="utf-8")
    stale = time.time() - 10 * 86400
    os.utime(old, (stale, stale))
    inspected = cleanup(root, older_than_days=7)

    old.write_text('{"changed": true}', encoding="utf-8")
    os.utime(old, (stale, stale))

    with pytest.raises(ValueError, match="unchanged plan-id"):
        cleanup(
            root,
            older_than_days=7,
            apply=True,
            expected_plan_id=inspected["plan_id"],
            confirmed_root=root,
        )
    assert old.exists()


def test_cleanup_apply_rejects_parent_replaced_by_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "artifacts"
    parent = root / "nested"
    parent.mkdir(parents=True)
    old = parent / "old.json"
    old.write_text("{}", encoding="utf-8")
    stale = time.time() - 10 * 86400
    os.utime(old, (stale, stale))
    inspected = cleanup(root, older_than_days=7)

    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "old.json"
    outside_file.write_text("do not delete", encoding="utf-8")
    saved_parent = root / "saved-nested"
    real_scan = cleanup_artifacts._scan_files

    def scan_then_swap(
        scan_root: Path, *, older_than_days: float
    ) -> list[tuple[Path, int, int]]:
        candidates = real_scan(scan_root, older_than_days=older_than_days)
        parent.rename(saved_parent)
        parent.symlink_to(outside, target_is_directory=True)
        return candidates

    monkeypatch.setattr(cleanup_artifacts, "_scan_files", scan_then_swap)
    with pytest.raises(OSError):
        cleanup(
            root,
            older_than_days=7,
            apply=True,
            expected_plan_id=inspected["plan_id"],
            confirmed_root=root,
        )

    assert outside_file.read_text(encoding="utf-8") == "do not delete"
    assert (saved_parent / "old.json").exists()


def test_cleanup_never_follows_symlink_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "outside.json"
    outside_file.write_text("{}", encoding="utf-8")
    link = root / "escape"
    link.symlink_to(outside, target_is_directory=True)
    stale = time.time() - 10 * 86400
    os.utime(outside_file, (stale, stale))

    result = cleanup(root, older_than_days=0)
    assert str(outside_file) not in result["candidates"]
    assert link.exists() and outside_file.exists()


def test_cleanup_rejects_unsafe_root_and_age(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-filesystem-root"):
        cleanup(Path("/"), older_than_days=7)
    with pytest.raises(ValueError, match="non-negative"):
        cleanup(tmp_path, older_than_days=-1)
    with pytest.raises(ValueError, match="finite"):
        cleanup(tmp_path, older_than_days=float("inf"))
