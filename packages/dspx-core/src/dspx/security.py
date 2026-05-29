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
from typing import TYPE_CHECKING, Any, Iterable, Optional

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
