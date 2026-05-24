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


def test_extract_active_operational_task_uses_active_section_only() -> None:
    issues: list[object] = []
    text = """
# Operational Goals

Historical note: `AK-111`

## Active operating slices

1. `AK-200` — active
2. `AK-201` — follow-up

## Recently completed

- `AK-150` — done
"""

    active = MODULE._extract_active_operational_task(
        text,
        "docs/project/operational_goals.md",
        issues,
    )

    assert active == "AK-200"
    assert issues == []


def test_collect_issues_reports_missing_required_files(tmp_path: Path) -> None:
    issues = MODULE.collect_issues(tmp_path)
    messages = {f"{issue.path}: {issue.message}" for issue in issues}

    assert "AGENTS.md: missing required file" in messages
    assert "next_session_prompt.md: missing required file" in messages
    assert "docs/project/strategic_goals.md: missing required file" in messages
    assert "docs/project/tactical_goals.md: missing required file" in messages
    assert "docs/project/operational_goals.md: missing required file" in messages


def test_collect_issues_ignores_historical_ak_mentions_before_active_slice(
    tmp_path: Path,
) -> None:
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
        "next_session_prompt.md",
        "Objective (one sentence): Claim `AK-200`\n",
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
    _write(
        tmp_path,
        "docs/project/operational_goals.md",
        "Active tactical goal: `TG10`\n"
        "\n"
        "Historical note: `AK-111`\n"
        "\n"
        "## Active operating slices\n"
        "\n"
        "1. `AK-200` — active\n"
        "\n"
        "## Recently completed\n"
        "\n"
        "- `AK-111` — older slice\n",
    )

    MODULE._run_json = lambda *args, **kwargs: [
        {"id": 200, "repo": str(tmp_path.resolve())}
    ]
    MODULE._run_check = lambda *args, **kwargs: None

    issues = MODULE.collect_issues(tmp_path)
    messages = [issue.message for issue in issues]

    assert messages == []
