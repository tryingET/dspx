from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Issue:
    path: Path
    message: str


def _read_text(root: Path, relpath: str) -> str:
    return (root / relpath).read_text(encoding="utf-8")


def _require_file(root: Path, relpath: str, issues: list[Issue]) -> Path | None:
    path = root / relpath
    if not path.exists():
        issues.append(Issue(Path(relpath), "missing required file"))
        return None
    return path


def _check_required_substrings(
    text: str,
    relpath: str,
    required: list[str],
    issues: list[Issue],
) -> None:
    for needle in required:
        if needle not in text:
            issues.append(Issue(Path(relpath), f"missing required text: {needle!r}"))


def _check_forbidden_substrings(
    text: str,
    relpath: str,
    forbidden: list[str],
    issues: list[Issue],
) -> None:
    for needle in forbidden:
        if needle in text:
            issues.append(
                Issue(Path(relpath), f"contains forbidden stale text: {needle!r}")
            )


def collect_issues(root: Path) -> list[Issue]:
    root = root.resolve()
    issues: list[Issue] = []

    gitignore = _require_file(root, ".gitignore", issues)
    if gitignore is not None:
        gitignore_text = gitignore.read_text(encoding="utf-8")
        _check_required_substrings(
            gitignore_text,
            ".gitignore",
            ["__pycache__/", "*.py[cod]"],
            issues,
        )

    _require_file(root, ".pre-commit-config.yaml", issues)
    _require_file(root, "docs/project/developer_workflow.md", issues)

    file_checks: dict[str, dict[str, list[str]]] = {
        "AGENTS.md": {
            "required": [
                "docs/project/developer_workflow.md",
                "just hooks-install",
                "docs/project/vision.md",
                "docs/project/strategic_goals.md",
                "docs/project/tactical_goals.md",
                "docs/project/operational_goals.md",
            ],
            "forbidden": ["./scripts/install-hooks.sh"],
        },
        "CONTRIBUTING.md": {
            "required": [
                "docs/project/developer_workflow.md",
                "just install",
                "just hooks-install",
                "just verify-full",
            ],
            "forbidden": ["uv pip install -e ."],
        },
        "README.md": {
            "required": [
                "docs/project/developer_workflow.md",
                "just hooks-install",
                "just verify-full",
            ],
            "forbidden": [],
        },
        "docs/tech-stack.local.md": {
            "required": [
                "docs/project/developer_workflow.md",
                "just hooks-install",
                "just verify-full",
            ],
            "forbidden": [],
        },
        "next_session_prompt.md": {
            "required": [
                "Planned active/deferred work map",
                "Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it.",
            ],
            "forbidden": ["Active/deferred work contract"],
        },
        "NEXT_STEPS.md": {
            "required": [
                "Current active strategic goal:",
                "Current active tactical goal:",
                "docs/project/operational_goals.md",
            ],
            "forbidden": [],
        },
        "Justfile": {
            "required": [
                "hooks-install:",
                "uvx pre-commit install --hook-type pre-commit --hook-type pre-push",
                "workflow-contract-check:",
                "direction-contract-check:",
                "governance-check:",
                "uvx pre-commit run --all-files",
                "cue vet governance/work-items.json governance/work-items.cue",
            ],
            "forbidden": [],
        },
        "scripts/ci/smoke.sh": {
            "required": [
                "need_cmd cue",
                "need_cmd python3",
                "need_cmd ak",
                "cue vet governance/work-items.json governance/work-items.cue",
                "python3 scripts/check_workflow_contracts.py",
                "python3 scripts/check_direction_to_execution.py",
            ],
            "forbidden": [],
        },
        "governance/README.md": {
            "required": [
                "Use it to choose the next slice; do not treat it as a scheduler or live execution state.",
                "ak work-items export",
                "ak work-items check",
            ],
            "forbidden": [],
        },
    }

    for relpath, spec in file_checks.items():
        path = _require_file(root, relpath, issues)
        if path is None:
            continue
        text = path.read_text(encoding="utf-8")
        _check_required_substrings(text, relpath, spec["required"], issues)
        _check_forbidden_substrings(text, relpath, spec["forbidden"], issues)

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check DSPx workflow docs and validation contract surfaces"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root (default: current directory)",
    )
    args = parser.parse_args()

    issues = collect_issues(args.root)
    if not issues:
        print("ok: workflow contract checks passed")
        return 0

    for issue in issues:
        print(f"{issue.path}: {issue.message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
