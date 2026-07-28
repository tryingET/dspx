from __future__ import annotations

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
