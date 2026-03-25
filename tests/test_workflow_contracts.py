from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "check_workflow_contracts.py"
    spec = importlib.util.spec_from_file_location("workflow_contracts", script_path)
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


def test_collect_issues_accepts_aligned_contract(tmp_path: Path) -> None:
    _write(tmp_path, ".gitignore", "__pycache__/\n*.py[cod]\n")
    _write(tmp_path, ".pre-commit-config.yaml", "repos: []\n")
    _write(tmp_path, "docs/project/developer_workflow.md", "workflow\n")
    _write(
        tmp_path,
        "AGENTS.md",
        "See docs/project/developer_workflow.md and run just hooks-install.\n"
        "Canonical reads: docs/project/vision.md docs/project/strategic_goals.md docs/project/tactical_goals.md docs/project/operational_goals.md\n",
    )
    _write(
        tmp_path,
        "CONTRIBUTING.md",
        "docs/project/developer_workflow.md\njust install\njust hooks-install\njust verify-full\n",
    )
    _write(
        tmp_path,
        "README.md",
        "docs/project/developer_workflow.md\njust hooks-install\njust verify-full\n",
    )
    _write(
        tmp_path,
        "docs/tech-stack.local.md",
        "docs/project/developer_workflow.md\njust hooks-install\njust verify-full\n",
    )
    _write(
        tmp_path,
        "next_session_prompt.md",
        "Planned active/deferred work map\n"
        "Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it.\n",
    )
    _write(
        tmp_path,
        "Justfile",
        "hooks-install:\n"
        "  uvx pre-commit install --hook-type pre-commit --hook-type pre-push\n"
        "workflow-contract-check:\n"
        "  python3 scripts/check_workflow_contracts.py\n"
        "direction-contract-check:\n"
        "  python3 scripts/check_direction_to_execution.py\n"
        "governance-check:\n"
        "  cue vet governance/work-items.json governance/work-items.cue\n"
        "task-scope-check:\n"
        "  uv run -q python scripts/check_task_scope.py --mode head --range auto\n"
        "verify-full:\n"
        "  uvx pre-commit run --all-files\n"
        "  cue vet governance/work-items.json governance/work-items.cue\n",
    )
    _write(
        tmp_path,
        "scripts/ci/smoke.sh",
        "need_cmd cue\nneed_cmd python3\nneed_cmd ak\ncue vet governance/work-items.json governance/work-items.cue\npython3 scripts/check_workflow_contracts.py\npython3 scripts/check_direction_to_execution.py\n",
    )
    _write(
        tmp_path,
        "governance/README.md",
        "Use it to choose the next slice; do not treat it as a scheduler or live execution state.\n"
        "Refresh with ak work-items export and verify with ak work-items check.\n",
    )

    issues = MODULE.collect_issues(tmp_path)
    assert issues == []


def test_collect_issues_flags_stale_contracts(tmp_path: Path) -> None:
    _write(tmp_path, ".gitignore", "")
    _write(tmp_path, "AGENTS.md", "Run ./scripts/install-hooks.sh after cloning.\n")
    _write(tmp_path, "CONTRIBUTING.md", "uv pip install -e .\n")
    _write(tmp_path, "README.md", "")
    _write(tmp_path, "docs/tech-stack.local.md", "")
    _write(tmp_path, "next_session_prompt.md", "Active/deferred work contract\n")
    _write(
        tmp_path,
        "Justfile",
        "pre-commit install --hook-type pre-commit --hook-type pre-push\n",
    )
    _write(tmp_path, "scripts/ci/smoke.sh", "")
    _write(tmp_path, "governance/README.md", "")

    issues = MODULE.collect_issues(tmp_path)
    messages = {f"{issue.path}: {issue.message}" for issue in issues}

    assert ".pre-commit-config.yaml: missing required file" in messages
    assert "docs/project/developer_workflow.md: missing required file" in messages
    assert (
        "AGENTS.md: contains forbidden stale text: './scripts/install-hooks.sh'"
        in messages
    )
    assert (
        "CONTRIBUTING.md: contains forbidden stale text: 'uv pip install -e .'"
        in messages
    )
    assert (
        "next_session_prompt.md: contains forbidden stale text: 'Active/deferred work contract'"
        in messages
    )
