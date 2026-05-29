from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SanitizeResult:
    sanitized: str
    detected: bool
    notes: list[str]


_SECRET_KEY = (
    r"(?:api[-_]?key|access[-_]?token|token|key|secret|password|authorization)"
)

_secret_patterns: list[tuple[str, re.Pattern[str]]] = [
    ("op_ref", re.compile(r"op://[A-Za-z0-9_./ -]+", re.IGNORECASE)),
    ("bearer", re.compile(r"(?i)authorization\s*:\s*bearer\s+[^\s]+")),
    ("openai_sk_proj", re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}")),
    ("openai_sk", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9_]{20,}")),
    ("gitlab_pat", re.compile(r"glpat-[A-Za-z0-9\-]{10,}")),
    (
        "env_key",
        re.compile(rf"(?im)^(\s*\w*{_SECRET_KEY}\w*\s*=\s*).+$"),
    ),
    (
        "yaml_key",
        re.compile(
            rf"(?im)^(\s*[A-Za-z0-9_.-]*{_SECRET_KEY}[A-Za-z0-9_.-]*\s*:\s*).+$"
        ),
    ),
    (
        "json_key",
        re.compile(
            rf'(?i)("[A-Za-z0-9_.-]*{_SECRET_KEY}[A-Za-z0-9_.-]*"\s*:\s*")[^"]+(")'
        ),
    ),
]


def sanitize_text(raw: str) -> SanitizeResult:
    text = raw or ""
    notes: list[str] = []
    detected = False
    for name, pat in _secret_patterns:
        if pat.search(text):
            detected = True
            notes.append(f"redacted:{name}")
            if name in {"env_key", "yaml_key"}:
                text = pat.sub(r"\1[REDACTED]", text)
            elif name == "json_key":
                text = pat.sub(r"\1[REDACTED]\2", text)
            else:
                text = pat.sub("[REDACTED]", text)
    return SanitizeResult(sanitized=text, detected=detected, notes=notes)
