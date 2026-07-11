# summary: "Tests the AK-native direction-to-execution repository contract."
# read_when:
#   - "Changing direction-file retirement checks or AGENTS direction requirements."

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "check_direction_to_execution.py"
    spec = importlib.util.spec_from_file_location("direction_to_execution", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def _write(root: Path, relpath: str, content: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _agents_text() -> str:
    return (
        "docs/project/vision.md\n"
        "docs/project/product-posture.md\n"
        "Active direction lives in AK direction runtime.\n"
    )


def test_collect_issues_reports_missing_required_files(tmp_path: Path) -> None:
    issues = MODULE.collect_issues(tmp_path)
    messages = {f"{issue.path}: {issue.message}" for issue in issues}

    assert "AGENTS.md: missing required file" in messages
    assert not any(
        "next_session_prompt.md: missing required file" in item for item in messages
    )
    assert not any("_goals.md: missing required file" in item for item in messages)


def test_collect_issues_accepts_ak_native_direction_posture(tmp_path: Path) -> None:
    _write(tmp_path, "AGENTS.md", _agents_text())

    issues = MODULE.collect_issues(tmp_path)

    assert issues == []


def test_collect_issues_rejects_retired_direction_files(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "AGENTS.md",
        _agents_text() + "docs/project/legacy_goals.md\n" + "next_session_prompt.md\n",
    )
    _write(tmp_path, "next_session_prompt.md", "legacy handoff\n")
    _write(tmp_path, "docs/project/legacy_goals.md", "legacy direction ladder\n")

    issues = MODULE.collect_issues(tmp_path)
    messages = {f"{issue.path}: {issue.message}" for issue in issues}

    assert (
        "next_session_prompt.md: retired file still exists; use AK direction runtime"
        in messages
    )
    assert (
        "docs/project/legacy_goals.md: retired file still exists; use AK direction runtime"
        in messages
    )
    assert (
        "AGENTS.md: retired read-order reference remains: docs/project/legacy_goals.md"
        in messages
    )
    assert (
        "AGENTS.md: retired read-order reference remains: next_session_prompt.md"
        in messages
    )


def test_collect_issues_requires_product_posture_read_order(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "AGENTS.md",
        "docs/project/vision.md\nActive direction lives in AK direction runtime.\n",
    )

    issues = MODULE.collect_issues(tmp_path)

    assert any(
        issue.path == Path("AGENTS.md")
        and "missing read-order reference: docs/project/product-posture.md"
        in issue.message
        for issue in issues
    )


def test_collect_issues_requires_ak_direction_authority_reminder(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "AGENTS.md",
        "docs/project/vision.md\ndocs/project/product-posture.md\n",
    )

    issues = MODULE.collect_issues(tmp_path)

    assert any(
        issue.path == Path("AGENTS.md")
        and issue.message == "missing AK direction authority reminder"
        for issue in issues
    )
