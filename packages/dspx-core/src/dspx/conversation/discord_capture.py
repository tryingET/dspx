# summary: "Extracts a likely intent and acceptance signal from Discord-style transcript text."
# read_when:
#   - "Changing transcript ingestion, intent heuristics, or acceptance-token detection."

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple


ACCEPT_TOKENS = {
    "👍",
    ":thumbs_up:",
    "+1",
    ":+1:",
    "yes",
    "yep",
    "ok",
    "okay",
    "sounds good",
    "sgtm",
    "approved",
    "confirmed",
    "looks good",
}


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def _accepted(s: str) -> bool:
    t = s.strip().lower()
    for tok in ACCEPT_TOKENS:
        if tok in t:
            return True
    return False


def _guess_intent_from_text(transcript: str) -> str:
    # Heuristics: prefer explicit lines starting with 'intent:'; else last non-empty
    lines = [ln.strip() for ln in transcript.splitlines() if ln.strip()]
    for ln in reversed(lines):
        low = ln.lower()
        if low.startswith("intent:") or low.startswith("intent -"):
            return ln.split(":", 1)[-1].strip()
    # Next: prefer last user/assistant statements
    for ln in reversed(lines):
        if ln.lower().startswith(("user:", "assistant:", "system:")):
            return ln.split(":", 1)[-1].strip()
    # Fallback: last non-empty line
    return lines[-1] if lines else ""


def capture_intent(
    *, transcript_path_env: str = "DISCORD_TRANSCRIPT", default_text: str = ""
) -> Tuple[str, bool]:
    """Capture intent and acceptance from a transcript file or text.

    - If `DISCORD_TRANSCRIPT` (or env override) points to a file, read it.
    - Else, use `default_text` as conversation text.
    - Returns (intent_text, accepted)
    """
    path = os.getenv(transcript_path_env)
    text = ""
    if path:
        p = Path(path)
        if p.exists():
            text = _read_text(p)
    if not text:
        text = default_text
    intent = _guess_intent_from_text(text)
    accepted = _accepted(text)
    return intent, accepted
