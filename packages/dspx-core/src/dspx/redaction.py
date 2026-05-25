from __future__ import annotations

import re
from typing import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SENSITIVE_KEYS = {
    "token",
    "access_token",
    "auth",
    "authorization",
    "apikey",
    "api_key",
    "key",
    "secret",
    "password",
}
_MAX_PREVIEW_CHARS = 320
_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)([^\s,;]+)")
_AUTH_HEADER_RE = re.compile(r"(?i)\b(authorization\s*:\s*bearer\s+)([^\s,;]+)")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b((?:api[-_]?key|access[-_]?token|token|secret|password)\s*[=:]\s*)([^\s,;]+)"
)
_JSON_SECRET_RE = re.compile(
    r'(?i)("(?:api[-_]?key|access[-_]?token|token|secret|password|authorization)"\s*:\s*")([^"]+)(")'
)


def _truncate_text(text: str, *, limit: int = _MAX_PREVIEW_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…[truncated]"


def redact_url(url: str) -> str:
    """Redact common sensitive values in a URL.

    - Masks query parameters for keys in _SENSITIVE_KEYS.
    - Redacts user:pass in the authority portion if present.
    - Preserves ordering and brackets.
    """
    try:
        sp = urlsplit(url)
        # Redact userinfo in netloc if any
        netloc = sp.netloc
        if "@" in netloc:
            hostpart = netloc.split("@", 1)[1]
            netloc = f"[REDACTED]@{hostpart}"
        # Redact sensitive query params
        if sp.query:
            pairs = parse_qsl(sp.query, keep_blank_values=True)
            redacted = []
            for k, v in pairs:
                if k.lower() in _SENSITIVE_KEYS:
                    redacted.append((k, "[REDACTED]"))
                else:
                    redacted.append((k, v))
            q = urlencode(redacted)
            # Keep the marker human-readable (avoid URL-encoding the brackets).
            q = q.replace("%5BREDACTED%5D", "[REDACTED]").replace(
                "%5bREDACTED%5d", "[REDACTED]"
            )
        else:
            q = sp.query
        return urlunsplit((sp.scheme, netloc, sp.path, q, sp.fragment))
    except Exception:
        return url


def sanitize_diagnostic_text(text: str, *, limit: int = _MAX_PREVIEW_CHARS) -> str:
    """Redact common secrets from diagnostic text and cap preview length."""

    sanitized = str(text or "")
    sanitized = _URL_RE.sub(lambda match: redact_url(match.group(0)), sanitized)
    sanitized = _AUTH_HEADER_RE.sub(r"\1[REDACTED]", sanitized)
    sanitized = _JSON_SECRET_RE.sub(r"\1[REDACTED]\3", sanitized)
    sanitized = _SECRET_ASSIGNMENT_RE.sub(r"\1[REDACTED]", sanitized)
    sanitized = _BEARER_RE.sub(r"\1[REDACTED]", sanitized)
    return _truncate_text(sanitized, limit=limit)


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Redact Authorization-like and cookie headers."""
    out: dict[str, str] = {}
    for k, v in headers.items():
        kl = k.lower()
        if kl in {"authorization", "proxy-authorization", "cookie", "set-cookie"}:
            out[k] = "[REDACTED]"
        elif any(x in kl for x in ("token", "secret", "key", "password")):
            out[k] = "[REDACTED]"
        else:
            out[k] = v
    return out
