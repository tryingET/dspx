"""Path-confinement and error-bearing primitives for dspx.

These utilities enforce that user/receipt/config-supplied paths cannot
escape an intended root directory, and provide structured error types
for provider results.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Optional
from urllib.parse import urlparse

if TYPE_CHECKING:
    import httpx


class PathEscapeError(ValueError):
    """Raised when a resolved path escapes its confinement root."""

    def __init__(self, root: Path, resolved: Path, detail: str = "") -> None:
        self.root = root
        self.resolved = resolved
        msg = f"Path escapes confinement root: {resolved} is not under {root}" + (
            f" ({detail})" if detail else ""
        )
        super().__init__(msg)


class UnsafePathComponentError(ValueError):
    """Raised when a path component is not safe for confined joins."""


class ByteLimitExceededError(ValueError):
    """Raised when a bounded read exceeds its byte budget."""


DEFAULT_HTTP_RESPONSE_MAX_BYTES = 1_000_000

IDENTITY_BOUNDARY_KEYS = (
    "receipt_bundle_id",
    "episode_id",
    "assembly_id",
    "candidate_id",
    "request_id",
)


def _normalize_identity_value(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def identity_matches_exact(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    keys: Iterable[str] = IDENTITY_BOUNDARY_KEYS,
    require_all_expected: bool = True,
) -> bool:
    """Return True only when identity fields are conflict-free and sufficiently bound.

    By default every non-empty expected field must be present and equal in *actual*.
    This is intentionally stricter than "any shared field matches" for evidence and
    authority-boundary sidecars, where partial identity is ambiguous rather than useful.
    """
    matched = False
    for key in keys:
        wanted = _normalize_identity_value(expected.get(key))
        got = _normalize_identity_value(actual.get(key))
        if wanted is None:
            continue
        if got is None:
            if require_all_expected:
                return False
            continue
        if got != wanted:
            return False
        matched = True
    return matched


def identity_mismatch_keys(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    keys: Iterable[str] = IDENTITY_BOUNDARY_KEYS,
) -> list[str]:
    """Return expected identity keys missing from or conflicting with *actual*."""
    mismatches: list[str] = []
    for key in keys:
        wanted = _normalize_identity_value(expected.get(key))
        if wanted is None:
            continue
        got = _normalize_identity_value(actual.get(key))
        if got != wanted:
            mismatches.append(key)
    return mismatches


def url_origin_allowed(
    url: str,
    allowed_origins: Mapping[str, bool] | set[str] | None,
    *,
    default_scheme: str = "https",
) -> bool:
    """Check a URL against a host/origin allowlist with scheme and port semantics.

    Legacy host-only entries remain supported for default HTTP/HTTPS ports. To
    constrain scheme or allow non-default ports, use an exact origin entry such
    as ``https://api.example.com`` or ``http://localhost:8080``.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    scheme = (parsed.scheme or "").lower()
    if not host or not scheme or allowed_origins is None:
        return False
    port = parsed.port
    default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
    origin = f"{scheme}://{host}" + (
        f":{port}" if port is not None and port != default_port else ""
    )

    if isinstance(allowed_origins, set):
        origin_allowed = origin in allowed_origins
        host_allowed = host in allowed_origins
    else:
        origin_allowed = bool(allowed_origins.get(origin, False))
        host_allowed = bool(allowed_origins.get(host, False))

    if origin_allowed:
        return True
    if port is not None and port != default_port:
        return False
    return scheme in {"http", default_scheme} and host_allowed


def confine_path(root: Path, user_path: str | Path, *, strict: bool = True) -> Path:
    """Resolve *user_path* and verify it stays under *root*.

    Args:
        root: The allowed root directory (resolved internally).
        user_path: A user/receipt/config-supplied path string or Path.
        strict: If True (default), raise PathEscapeError on escape.
                If False, return root instead of raising.

    Returns:
        The resolved path, guaranteed to be under root.

    Raises:
        PathEscapeError: When the resolved path escapes root and strict=True.
    """
    root_resolved = root.resolve()
    resolved = (root_resolved / user_path).resolve()

    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        if strict:
            raise PathEscapeError(root_resolved, resolved) from None
        return root_resolved

    return resolved


def confine_or_none(root: Path, user_path: str | Path) -> Optional[Path]:
    """Like confine_path but returns None instead of raising."""
    try:
        return confine_path(root, user_path, strict=True)
    except PathEscapeError:
        return None


def confine_relative_path(root: Path, *parts: str | Path) -> Path:
    """Join relative path components under *root* and reject traversal.

    Unlike :func:`confine_path`, this treats absolute paths, empty components,
    ``.`` and ``..`` as invalid input rather than normalizing them away. This is
    intended for user-controlled identifiers that become filesystem paths, such
    as project keys and local artifact IDs.
    """
    if not parts:
        raise UnsafePathComponentError("at least one path component is required")

    safe_parts: list[str] = []
    for raw_part in parts:
        raw_text = str(raw_part)
        if raw_text in {"", "."}:
            raise UnsafePathComponentError(
                f"unsafe path component segment is not allowed: {raw_part}"
            )
        part = Path(raw_part)
        if part.is_absolute():
            raise UnsafePathComponentError(
                f"absolute path component is not allowed: {raw_part}"
            )
        if not part.parts:
            raise UnsafePathComponentError(
                f"unsafe path component segment is not allowed: {raw_part}"
            )
        for segment in part.parts:
            if segment in {"", ".", ".."}:
                raise UnsafePathComponentError(
                    f"unsafe path component segment is not allowed: {raw_part}"
                )
            safe_parts.append(segment)

    return confine_path(root, Path(*safe_parts), strict=True)


def _unsafe_implicit_trusted_root(root: Path) -> bool:
    root = root.resolve()
    temp_roots = {
        Path(tempfile.gettempdir()).resolve(),
        Path("/tmp").resolve(),
        Path("/var/tmp").resolve(),
        Path("/private/tmp").resolve(),
    }
    if root.parent == root or root in temp_roots:
        return True
    try:
        return bool(root.stat().st_mode & stat.S_IWOTH)
    except OSError:
        return True


def trusted_path_roots(
    *, env_var: str, include_cwd: bool = True, extra_roots: Iterable[Path] = ()
) -> list[Path]:
    """Return deduplicated trusted roots without implicit world-writable dirs."""
    roots: list[Path] = []
    if include_cwd:
        cwd = Path.cwd().resolve()
        if not _unsafe_implicit_trusted_root(cwd):
            roots.append(cwd)
    roots.extend(root.expanduser().resolve() for root in extra_roots)
    for raw_root in os.getenv(env_var, "").split(os.pathsep):
        if raw_root.strip():
            roots.append(Path(raw_root).expanduser().resolve())

    deduped: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root not in seen:
            deduped.append(root)
            seen.add(root)
    return deduped


def require_path_under_roots(path: Path, roots: Iterable[Path], *, label: str) -> Path:
    """Resolve *path* and require it to live under one of *roots*."""
    resolved = path.expanduser().resolve()
    trusted_roots = [root.expanduser().resolve() for root in roots]
    for root in trusted_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    allowed = ", ".join(str(root) for root in trusted_roots)
    raise ValueError(
        f"{label} must stay under a trusted root. Got {resolved}; trusted roots: {allowed}"
    )


def read_response_text_bounded(
    response: "httpx.Response", *, max_bytes: int, label: str
) -> str:
    """Read an HTTP response body with a hard byte ceiling."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise ByteLimitExceededError(
                f"{label} exceeded byte limit: {total} > {max_bytes}"
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    encoding = response.encoding or "utf-8"
    return data.decode(encoding, errors="replace")


def response_json_or_raw_text_bounded(
    response: "httpx.Response", *, max_bytes: int, label: str
) -> Any:
    """Read a response with a hard byte ceiling and parse JSON when possible."""
    text = read_response_text_bounded(response, max_bytes=max_bytes, label=label)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}
