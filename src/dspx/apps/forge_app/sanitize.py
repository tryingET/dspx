from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SanitizeResult:
    sanitized: str
    detected: bool
    notes: list[str]


_secret_patterns: list[tuple[str, re.Pattern[str]]] = [
    ("op_ref", re.compile(r"op://[A-Za-z0-9_./ -]+", re.IGNORECASE)),
    ("bearer", re.compile(r"(?i)authorization\\s*:\\s*bearer\\s+[^\\s]+")),
    ("openai_sk", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("gitlab_pat", re.compile(r"glpat-[A-Za-z0-9\\-]{10,}")),
    ("env_key", re.compile(r"(?m)^(\\w*(TOKEN|KEY|SECRET|PASSWORD)\\w*)\\s*=\\s*.+$")),
]


def sanitize_text(raw: str) -> SanitizeResult:
    text = raw or ""
    notes: list[str] = []
    detected = False
    for name, pat in _secret_patterns:
        if pat.search(text):
            detected = True
            notes.append(f"redacted:{name}")
            if name == "env_key":
                text = pat.sub(r"\\1=[REDACTED]", text)
            else:
                text = pat.sub("[REDACTED]", text)
    return SanitizeResult(sanitized=text, detected=detected, notes=notes)
