# ---
# summary: "Validate DSPx workflow documentation, commands, and engineering-lane contract surfaces."
# read_when:
#   - "Changing workflow docs, Just recipes, CI entrypoints, or loop-validation policy."
# ---
from __future__ import annotations

import argparse
import json
import re
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


def _extract_recipe_body(text: str, header: str) -> str | None:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.rstrip() != header:
            continue
        body: list[str] = []
        for candidate in lines[idx + 1 :]:
            if candidate.startswith(("  ", "\t")) or candidate == "":
                body.append(candidate)
                continue
            break
        return "\n".join(body)
    return None


def _check_recipe_body_contains(
    text: str,
    relpath: str,
    header: str,
    required: list[str],
    issues: list[Issue],
) -> None:
    body = _extract_recipe_body(text, header)
    if body is None:
        issues.append(Issue(Path(relpath), f"missing recipe: {header}"))
        return
    for needle in required:
        if needle not in body:
            issues.append(
                Issue(
                    Path(relpath),
                    f"recipe {header!r} missing required text in body: {needle!r}",
                )
            )


LOOP_VALIDATION_COMMANDS = [
    "loop-doctor",
    "loop-verify-fast",
    "loop-impact-plan",
    "loop-impact-run",
    "loop-impact-wide",
    "loop-landing-check",
]

STALE_PROMPT_SOURCE_SUBSTRINGS = [
    "~/steve/prompts",
    "prompts/triggers",
    "prompt-snippets.md",
]

COMMIT_PATTERN = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z")
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _check_engineering_guidance_policy(root: Path, issues: list[Issue]) -> None:
    relpath = "policy/engineering-lane.json"
    path = _require_file(root, relpath, issues)
    if path is None:
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(Issue(Path(relpath), f"invalid JSON: {exc}"))
        return
    engineering_core = (
        payload.get("engineering_core") if isinstance(payload, dict) else None
    )
    if not isinstance(engineering_core, dict):
        issues.append(Issue(Path(relpath), "missing engineering_core object"))
        return
    release_pin = engineering_core.get("release_pin")
    if not isinstance(release_pin, dict):
        issues.append(
            Issue(Path(relpath), "missing engineering_core.release_pin object")
        )
        return
    source = release_pin.get("source")
    resolved_commit = release_pin.get("resolved_commit")
    if not isinstance(source, str) or not source.strip():
        issues.append(
            Issue(Path(relpath), "release_pin.source must be a non-empty string")
        )
    if not isinstance(resolved_commit, str) or not resolved_commit.strip():
        issues.append(
            Issue(
                Path(relpath),
                "release_pin.resolved_commit must be a non-empty string",
            )
        )
    elif not COMMIT_PATTERN.fullmatch(resolved_commit):
        issues.append(
            Issue(
                Path(relpath),
                "release_pin.resolved_commit must be a full 40- or 64-character hexadecimal commit",
            )
        )
    if isinstance(source, str) and isinstance(resolved_commit, str):
        if not source.startswith("git+") or not source.endswith(f"@{resolved_commit}"):
            issues.append(
                Issue(
                    Path(relpath),
                    "release_pin.source must be an immutable git source ending in resolved_commit",
                )
            )
        if "--prefer-repo" in source:
            issues.append(
                Issue(Path(relpath), "release_pin.source must not use --prefer-repo")
            )
    lane = engineering_core.get("lane")
    if not isinstance(lane, str) or not lane.strip():
        issues.append(Issue(Path(relpath), "engineering_core.lane must be non-empty"))
    elif not IDENTIFIER_PATTERN.fullmatch(lane.strip()):
        issues.append(
            Issue(
                Path(relpath),
                "engineering_core.lane must be a non-option identifier",
            )
        )
    disciplines = engineering_core.get("disciplines")
    normalized_disciplines: list[str] = []
    if (
        not isinstance(disciplines, list)
        or not disciplines
        or any(not isinstance(item, str) or not item.strip() for item in disciplines)
    ):
        issues.append(
            Issue(
                Path(relpath),
                "engineering_core.disciplines must be a non-empty string list",
            )
        )
    else:
        normalized_disciplines = [item.strip() for item in disciplines]
        if any(
            not IDENTIFIER_PATTERN.fullmatch(item) for item in normalized_disciplines
        ):
            issues.append(
                Issue(
                    Path(relpath),
                    "engineering_core.disciplines must contain non-option identifiers",
                )
            )
        if len(set(normalized_disciplines)) != len(normalized_disciplines):
            issues.append(
                Issue(Path(relpath), "engineering_core.disciplines contains duplicates")
            )

    guidance_doc = root / "docs/engineering.local.md"
    if guidance_doc.exists() and normalized_disciplines:
        guidance_text = guidance_doc.read_text(encoding="utf-8")
        examples = re.findall(
            r"scripts/engineering_guidance\.py discipline ([^\s]+) (?:headings|range)",
            guidance_text,
        )
        for example in examples:
            if example not in normalized_disciplines:
                issues.append(
                    Issue(
                        Path("docs/engineering.local.md"),
                        f"discipline example {example!r} is not selected by policy",
                    )
                )


def _check_loop_validation_policy(
    root: Path, justfile_text: str, issues: list[Issue]
) -> None:
    relpath = "policy/engineering-lane.json"
    path = _require_file(root, relpath, issues)
    if path is None:
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(Issue(Path(relpath), f"invalid JSON: {exc}"))
        return
    if not isinstance(payload, dict):
        issues.append(Issue(Path(relpath), "expected top-level JSON object"))
        return
    engineering_core = payload.get("engineering_core")
    if not isinstance(engineering_core, dict):
        issues.append(Issue(Path(relpath), "missing engineering_core object"))
        return
    loop_validation = engineering_core.get("loop_validation")
    if not isinstance(loop_validation, dict):
        issues.append(
            Issue(Path(relpath), "missing engineering_core.loop_validation object")
        )
        return
    if loop_validation.get("version") != "repo-loop-validation-v1":
        issues.append(
            Issue(
                Path(relpath),
                "engineering_core.loop_validation.version must be repo-loop-validation-v1",
            )
        )
    if (
        loop_validation.get("contract_doc")
        != "docs/engineering.local.md#repo-loop-validation"
    ):
        issues.append(
            Issue(
                Path(relpath),
                "engineering_core.loop_validation.contract_doc must point at docs/engineering.local.md#repo-loop-validation",
            )
        )
    commands = loop_validation.get("commands")
    if not isinstance(commands, dict):
        issues.append(Issue(Path(relpath), "missing loop_validation.commands object"))
        return
    for phase in LOOP_VALIDATION_COMMANDS:
        raw_command = commands.get(phase)
        if not isinstance(raw_command, str) or not raw_command.strip():
            issues.append(Issue(Path(relpath), f"missing loop command: {phase}"))
            continue
        command = raw_command.strip()
        if not command.startswith("just "):
            issues.append(
                Issue(Path(relpath), f"loop command {phase!r} must use a just recipe")
            )
            continue
        recipe = command.split()[1]
        if _extract_recipe_body(justfile_text, f"{recipe}:") is None:
            issues.append(
                Issue(
                    Path(relpath),
                    f"loop command {phase!r} targets missing Just recipe: {recipe}",
                )
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
