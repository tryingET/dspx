# summary: "Redacts secrets from URLs, headers, and bounded diagnostic text previews."
# read_when:
#   - "Changing sensitive-key detection, diagnostic sanitization, URL redaction, or preview limits."

from __future__ import annotations

import re
from typing import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SENSITIVE_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "refreshtoken",
    "id_token",
    "idtoken",
    "session_token",
    "sessiontoken",
    "auth",
    "authorization",
    "apikey",
    "api_key",
    "key",
    "secret",
    "client_secret",
    "clientsecret",
    "private_key",
    "privatekey",
    "password",
}
_SENSITIVE_KEY_MARKERS = {"token", "secret", "password", "key", "credential"}
_MAX_PREVIEW_CHARS = 320
_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)([^\s,;]+)")
_AUTH_HEADER_RE = re.compile(r"(?i)\b(authorization\s*:\s*bearer\s+)([^\s,;]+)")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(([A-Za-z0-9_.-]*(?:api[-_]?key|token|secret|password|credential)[A-Za-z0-9_.-]*)\s*[=:]\s*)([^\s,;]+)"
)
_JSON_SECRET_RE = re.compile(
    r'(?i)("[A-Za-z0-9_.-]*(?:api[-_]?key|token|secret|password|credential|authorization)[A-Za-z0-9_.-]*"\s*:\s*")([^"]+)(")'
)


def _truncate_text(text: str, *, limit: int = _MAX_PREVIEW_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…[truncated]"


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    if normalized in _SENSITIVE_KEYS:
        return True
    parts = {part for part in normalized.split("_") if part}
    if parts.intersection(_SENSITIVE_KEY_MARKERS):
        return True
    return any(
        normalized.endswith(marker)
        for marker in _SENSITIVE_KEY_MARKERS
        if marker != "key"
    )


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
                if _is_sensitive_key(k):
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
