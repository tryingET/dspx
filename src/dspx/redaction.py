from __future__ import annotations

from typing import Mapping
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote


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
            q = urlencode(
                redacted,
                quote_via=lambda s, safe, encoding, errors: quote(
                    s, safe + "[]", encoding, errors
                ),
            )
        else:
            q = sp.query
        return urlunsplit((sp.scheme, netloc, sp.path, q, sp.fragment))
    except Exception:
        return url


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
