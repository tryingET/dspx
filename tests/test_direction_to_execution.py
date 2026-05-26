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


def test_collect_issues_reports_missing_required_files(tmp_path: Path) -> None:
    issues = MODULE.collect_issues(tmp_path)
    messages = {f"{issue.path}: {issue.message}" for issue in issues}

    assert "AGENTS.md: missing required file" in messages
    assert "docs/project/strategic_goals.md: missing required file" in messages
    assert "docs/project/tactical_goals.md: missing required file" in messages
    assert "next_session_prompt.md: missing required file" not in messages
    assert "docs/project/operational_goals.md: missing required file" not in messages


def test_collect_issues_accepts_ak_native_direction_docs(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "AGENTS.md",
        "docs/project/vision.md\n"
        "docs/project/strategic_goals.md\n"
        "docs/project/tactical_goals.md\n",
    )
    _write(
        tmp_path,
        "docs/project/strategic_goals.md",
        "Active strategic goal: `SG2`\n",
    )
    _write(
        tmp_path,
        "docs/project/tactical_goals.md",
        "Active strategic goal: `SG2`\nActive tactical goal: `TG10`\n",
    )

    issues = MODULE.collect_issues(tmp_path)

    assert issues == []


def test_collect_issues_rejects_retired_direction_files(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "AGENTS.md",
        "docs/project/vision.md\n"
        "docs/project/strategic_goals.md\n"
        "docs/project/tactical_goals.md\n"
        "docs/project/operational_goals.md\n",
    )
    _write(
        tmp_path,
        "docs/project/strategic_goals.md",
        "Active strategic goal: `SG2`\n",
    )
    _write(
        tmp_path,
        "docs/project/tactical_goals.md",
        "Active strategic goal: `SG2`\nActive tactical goal: `TG10`\n",
    )
    _write(tmp_path, "next_session_prompt.md", "legacy handoff\n")
    _write(tmp_path, "docs/project/operational_goals.md", "legacy active slice\n")

    issues = MODULE.collect_issues(tmp_path)
    messages = {f"{issue.path}: {issue.message}" for issue in issues}

    assert (
        "next_session_prompt.md: retired AK-native direction file still exists"
        in messages
    )
    assert (
        "docs/project/operational_goals.md: retired AK-native direction file still exists"
        in messages
    )
    assert (
        "AGENTS.md: retired read-order reference remains: docs/project/operational_goals.md"
        in messages
    )


def test_collect_issues_rejects_tactical_strategic_mismatch(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "AGENTS.md",
        "docs/project/vision.md\n"
        "docs/project/strategic_goals.md\n"
        "docs/project/tactical_goals.md\n",
    )
    _write(
        tmp_path,
        "docs/project/strategic_goals.md",
        "Active strategic goal: `SG2`\n",
    )
    _write(
        tmp_path,
        "docs/project/tactical_goals.md",
        "Active strategic goal: `SG3`\nActive tactical goal: `TG10`\n",
    )

    issues = MODULE.collect_issues(tmp_path)

    assert any("active strategic goal mismatch" in issue.message for issue in issues)
