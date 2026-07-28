from __future__ import annotations

import re
from pathlib import Path

from .common import (
    STALE_PROMPT_SOURCE_SUBSTRINGS,
    Issue,
    _check_forbidden_substrings,
    _check_recipe_body_contains,
    _check_required_substrings,
    _require_file,
)
from .engineering import (
    _check_engineering_guidance_policy,
    _check_loop_validation_policy,
)


def collect_issues(root: Path) -> list[Issue]:
    root = root.resolve()
    issues: list[Issue] = []
    for pattern in ("next_session_prompt.md", "docs/project/*_goals.md"):
        for retired_path in root.glob(pattern):
            if retired_path.exists():
                issues.append(
                    Issue(
                        retired_path.relative_to(root),
                        "retired AK-native workflow file still exists",
                    )
                )

    for markdown_path in root.rglob("*.md"):
        parts = set(markdown_path.relative_to(root).parts)
        if parts & {".git", ".venv", "__pycache__"}:
            continue
        try:
            markdown_text = markdown_path.read_text(encoding="utf-8")
        except OSError:
            continue
        _check_forbidden_substrings(
            markdown_text,
            markdown_path.relative_to(root).as_posix(),
            STALE_PROMPT_SOURCE_SUBSTRINGS,
            issues,
        )

    core_reference_relpath = "docs/_core/README.md"
    core_reference = root / core_reference_relpath
    if core_reference.exists():
        core_reference_lines = {
            line.strip()
            for line in core_reference.read_text(encoding="utf-8").splitlines()
        }
        headings_command = "python3 scripts/engineering_guidance.py lane headings"
        if headings_command not in core_reference_lines:
            issues.append(
                Issue(
                    Path(core_reference_relpath),
                    f"missing required command: {headings_command!r}",
                )
            )
        range_pattern = re.compile(
            r"python3 scripts/engineering_guidance\.py lane range (\d+) (\d+)"
        )
        valid_range = False
        for line in core_reference_lines:
            match = range_pattern.fullmatch(line)
            if match is None:
                continue
            start, end = (int(value) for value in match.groups())
            if 1 <= start <= end and end - start + 1 <= 40:
                valid_range = True
                break
        if not valid_range:
            issues.append(
                Issue(
                    Path(core_reference_relpath),
                    "missing required bounded lane range command with at most 40 lines",
                )
            )
        stale_command = (
            "uv tool run --from ~/ai-society/core/engineering-core "
            "engineering-core show py --prefer-repo"
        )
        if stale_command in core_reference_lines:
            issues.append(
                Issue(
                    Path(core_reference_relpath),
                    f"contains forbidden stale command: {stale_command!r}",
                )
            )

    gitignore = _require_file(root, ".gitignore", issues)
    if gitignore is not None:
        gitignore_text = gitignore.read_text(encoding="utf-8")
        _check_required_substrings(
            gitignore_text,
            ".gitignore",
            ["__pycache__/", "*.py[cod]"],
            issues,
        )

    pre_commit = _require_file(root, ".pre-commit-config.yaml", issues)
    if pre_commit is not None:
        pre_commit_text = pre_commit.read_text(encoding="utf-8")
        _check_required_substrings(
            pre_commit_text,
            ".pre-commit-config.yaml",
            [
                "rev: v0.15.4",
                "id: verify-pre-push",
                "entry: just verify-pre-push",
                "stages: [pre-push]",
            ],
            issues,
        )
    _require_file(root, "docs/project/developer_workflow.md", issues)
    _require_file(root, "scripts/ci/verify-full.sh", issues)
    _require_file(root, "scripts/engineering_guidance.py", issues)

    file_checks: dict[str, dict[str, list[str]]] = {
        "AGENTS.md": {
            "required": [
                "docs/project/developer_workflow.md",
                "just hooks-install",
                "docs/project/vision.md",
                "docs/project/product-posture.md",
                "AK direction",
            ],
            "forbidden": ["./scripts/install-hooks.sh", "--prefer-repo"],
        },
        "CONTRIBUTING.md": {
            "required": [
                "docs/project/developer_workflow.md",
                "just install",
                "just hooks-install",
                "just help",
                "just doctor",
                "just run",
                "just task-scope-check task_id=<AK-ID> mode=working-tree",
                "just verify-pre-push",
                "just verify-full",
            ],
            "forbidden": ["uv pip install -e ."],
        },
        "README.md": {
            "required": [
                "docs/project/developer_workflow.md",
                "just help",
                "just check",
                "just ci",
                "just doctor",
                "just run",
                "just hooks-install",
                "just task-scope-check task_id=<AK-ID> mode=working-tree",
                "just verify-pre-push",
                "just verify-full",
                "uv run --no-sync",
            ],
            "forbidden": ["changed manifest path, or next_session checkpoint"],
        },
        "docs/project/developer_workflow.md": {
            "required": [
                "just help",
                "just check",
                "just ci",
                "just doctor",
                "just run",
                "just task-scope-check task_id=<AK-ID> mode=working-tree",
                "just verify-impact-plan",
                "just verify-impact",
                'just hooks-run files="path/one.py path/two.py"',
                "just verify-impact-receipt",
                "an active AK claim, or changed task-scope snapshot/legacy-scope-file paths",
                "brownfield legacy scope file",
                "AK task ready/list/show is the live execution source of truth",
                "uv run --no-sync",
            ],
            "forbidden": [
                "changed task-scope snapshot/legacy-manifest paths, or the committed `next_session_prompt.md` checkpoint",
                "transitional legacy manifest",
            ],
        },
        "docs/engineering.local.md": {
            "required": [
                "docs/project/developer_workflow.md",
                "just hooks-install",
                "just task-scope-check task_id=<AK-ID> mode=working-tree",
                "just verify-pre-push",
                "just verify-full",
                "just help",
                "just check",
                "just ci",
                "just doctor",
                "just run ...",
                "No `just dev` target",
                "fails closed",
                "parallel",
                "python3 scripts/engineering_guidance.py lane headings",
                "python3 scripts/engineering_guidance.py lane range",
                "python3 scripts/engineering_guidance.py discipline",
                "headings",
                "range",
                "fail closed",
            ],
            "forbidden": ["uv tool", "--prefer-repo"],
        },
        "Justfile": {
            "required": [
                "standardized-justfile-contract.md",
                "help:",
                "hooks-install:",
                "workflow-contract-check:",
                "direction-contract-check:",
                "governance-check:",
                "check:",
                "test:",
                'test-parallel jobs="auto":',
                'test-slow-parallel jobs="auto":',
                "test-residual-serial:",
                "build:",
                "lint:",
                "fmt:",
                "ci:",
                "doctor:",
                "run *args:",
                "uvx prek install --hook-type pre-commit --hook-type pre-push",
                'hooks-run files="":',
                "uvx prek run --files $paths",
                'task-scope-check task_id="" mode="auto" rev_range="auto":',
                "working tree when the repo is dirty",
                "active AK claim or changed task-scope artifact paths",
                "verify-fast:",
                "verify-runtime-replay:",
                "verify-runtime-monorepo:",
                "verify-runtime-module-synthesis:",
                "verify-runtime-boundary:",
                "verify-runtime:",
                'verify-impact-plan base="auto":',
                'verify-impact base="auto":',
                'verify-impact-receipt base="auto" out="generated/ci/verify-impact-result.json":',
                "typecheck-tests:",
                "verify-tests:",
                "verify-pre-push:",
                "bash scripts/ci/verify-full.sh",
                "uvx prek run --all-files",
                "AK DB is canonical; work-items projection is compatibility-only",
            ],
            "forbidden": [
                "next_session_prompt checkpoint before failing closed",
                "legacy manifest fallback",
            ],
        },
        "scripts/ci/smoke.sh": {
            "required": [
                "need_cmd python3",
                "need_cmd ak",
                "python3 scripts/check_workflow_contracts.py",
                "python3 scripts/check_direction_to_execution.py",
            ],
            "forbidden": [
                "cue vet governance/work-items.json governance/work-items.cue"
            ],
        },
        "governance/README.md": {
            "required": [
                "AK DB is canonical for live task/work-item truth.",
                "legacy compatibility projection",
                "not a landing gate",
            ],
            "forbidden": [
                "Use it to choose the next slice",
                "ak work-items export",
                "ak work-items check",
                "cue vet governance/work-items.json governance/work-items.cue",
            ],
        },
    }

    justfile_text = ""
    for relpath, spec in file_checks.items():
        path = _require_file(root, relpath, issues)
        if path is None:
            continue
        text = path.read_text(encoding="utf-8")
        if relpath == "Justfile":
            justfile_text = text
        _check_required_substrings(text, relpath, spec["required"], issues)
        _check_forbidden_substrings(text, relpath, spec["forbidden"], issues)
        if relpath == "Justfile":
            _check_recipe_body_contains(
                text,
                relpath,
                "help:",
                ["just --list"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "check:",
                ["just verify-fast"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "ci:",
                ["just verify-full"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "doctor:",
                [
                    "uv run --no-sync --package dspx-core -q python -m dspx.cli.dspx --help >/dev/null",
                    "uv run --no-sync --package dspx-forge -q python -m dspx_forge.cli --help >/dev/null",
                ],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "test:",
                ["uv run --no-sync -m pytest -q tests"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                'test-parallel jobs="auto":',
                [
                    "uv run --no-sync -m pytest -q tests -n",
                    "not slow and not live and not network and not model and not gpu and not postgres",
                ],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                'test-slow-parallel jobs="auto":',
                [
                    "uv run --no-sync -m pytest -q tests -n",
                    "slow and not live and not network and not model and not gpu and not postgres",
                ],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "test-residual-serial:",
                [
                    "uv run --no-sync -m pytest -q tests -m",
                    "live or network or model or gpu or postgres",
                ],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "typecheck-tests:",
                ["uvx ty check tests"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "verify-tests:",
                [
                    "just typecheck",
                    "just typecheck-tests",
                    "just test-parallel",
                    "just test-slow-parallel",
                    "just test-residual-serial",
                ],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "replay-provenance-check:",
                ["uv run --no-sync -q python scripts/check_replay_provenance.py"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "module-synthesis-quality-check:",
                [
                    "uv run --no-sync -q python scripts/build_module_synthesis_quality_log.py"
                ],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "verify-runtime-replay:",
                ["just replay-provenance-check"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "verify-runtime-monorepo:",
                ["just monorepo-check"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "verify-runtime-module-synthesis:",
                ["just module-synthesis-quality-check"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "verify-runtime-boundary:",
                ["just boundary-contract-check"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "verify-runtime:",
                [
                    "just verify-runtime-replay",
                    "just verify-runtime-monorepo",
                    "just verify-runtime-module-synthesis",
                    "just verify-runtime-boundary",
                ],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                'verify-impact-plan base="auto":',
                ["uv run --no-sync python scripts/ci/verify_changed.py --base"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                'verify-impact base="auto":',
                ["uv run --no-sync python scripts/ci/verify_changed.py --base"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                'verify-impact-receipt base="auto" out="generated/ci/verify-impact-result.json":',
                [
                    "uv run --no-sync python scripts/ci/verify_changed.py --base",
                    "--result-out",
                ],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "monorepo-check:",
                ["uv run --no-sync -q python scripts/check_monorepo_boundaries.py"],
                issues,
            )
            _check_recipe_body_contains(
                text,
                relpath,
                "run *args:",
                [
                    'if [ "$#" -eq 0 ]; then set -- --help; fi;',
                    'uv run --no-sync --package dspx-core -q python -m dspx.cli.dspx "$@"',
                ],
                issues,
            )

    _check_loop_validation_policy(root, justfile_text, issues)
    _check_engineering_guidance_policy(root, issues)

    return issues
