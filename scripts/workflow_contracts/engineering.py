from __future__ import annotations

import json
import re
from pathlib import Path

from .common import (
    COMMIT_PATTERN,
    IDENTIFIER_PATTERN,
    LOOP_VALIDATION_COMMANDS,
    Issue,
    _extract_recipe_body,
    _require_file,
)


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
