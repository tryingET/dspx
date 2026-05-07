from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable
from urllib.parse import urlsplit

ONEPASSWORD_REF_SCHEME = "op"

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key_material",
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", re.IGNORECASE),
    ),
    (
        "bearer_token",
        re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    ),
    (
        "secret_assignment",
        re.compile(
            r"\b(password|passwd|pwd|api[_-]?key|secret|token|access[_-]?key)\s*[:=]\s*\S{8,}",
            re.IGNORECASE,
        ),
    ),
    ("openai_style_token", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b")),
)
_SECRET_URL_SCHEMES = {
    "postgres",
    "postgresql",
    "mysql",
    "mariadb",
    "mongodb",
    "redis",
    "rediss",
    "amqp",
    "amqps",
}


class ProgramOracleSecretPolicyError(ValueError):
    """Raised when publication custody text or secret refs violate policy."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redact_onepassword_ref(ref: str) -> str:
    parts = urlsplit(ref)
    segments = [segment for segment in parts.path.split("/") if segment]
    field = segments[-1] if segments else "field"
    return f"op://<redacted>/<redacted>/{field}"


def normalize_onepassword_ref(value: str) -> str:
    """Validate a URI-safe 1Password secret reference without resolving it."""

    ref = str(value or "").strip()
    if not ref:
        raise ProgramOracleSecretPolicyError("publisher_secret_ref must not be empty")
    if any(char.isspace() for char in ref):
        raise ProgramOracleSecretPolicyError(
            "publisher_secret_ref must not contain whitespace"
        )
    parsed = urlsplit(ref)
    if parsed.scheme != ONEPASSWORD_REF_SCHEME:
        raise ProgramOracleSecretPolicyError(
            "publisher_secret_ref must use a 1Password op:// reference"
        )
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not parsed.netloc or len(segments) < 2:
        raise ProgramOracleSecretPolicyError(
            "publisher_secret_ref must have op://vault/item/field shape"
        )
    return ref


def build_onepassword_ref_descriptors(
    refs: Iterable[str] | None,
) -> list[dict[str, Any]]:
    """Return redacted descriptors for 1Password refs without fetching secrets.

    This is SDK-ready custody metadata: it preserves provider and stable ref hash,
    but intentionally does not resolve or persist secret values.
    """

    descriptors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_ref in refs or []:
        ref = normalize_onepassword_ref(raw_ref)
        if ref in seen:
            continue
        seen.add(ref)
        descriptors.append(
            {
                "provider": "1password",
                "ref_kind": "op_uri",
                "ref_redacted": _redact_onepassword_ref(ref),
                "ref_sha256": _sha256_text(ref),
                "sdk_resolution_attempted": False,
                "secret_value_persisted": False,
            }
        )
    return descriptors


def validate_publisher_assertion_no_secret(value: str) -> None:
    """Reject obvious pasted secrets in free-text publisher assertions."""

    text = str(value or "")
    if "op://" in text:
        raise ProgramOracleSecretPolicyError(
            "publisher_assertion must not contain 1Password refs; use --publisher-secret-ref"
        )
    for scheme in _SECRET_URL_SCHEMES:
        if re.search(
            rf"\b{re.escape(scheme)}://[^\s/@]+:[^\s/@]+@", text, re.IGNORECASE
        ):
            raise ProgramOracleSecretPolicyError(
                "publisher_assertion must not contain secret-bearing URLs"
            )
    for name, pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            raise ProgramOracleSecretPolicyError(
                f"publisher_assertion appears to contain {name}; use a 1Password ref"
            )
