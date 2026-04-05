"""Path-confinement and error-bearing primitives for dspx.

These utilities enforce that user/receipt/config-supplied paths cannot
escape an intended root directory, and provide structured error types
for provider results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


class PathEscapeError(ValueError):
    """Raised when a resolved path escapes its confinement root."""

    def __init__(self, root: Path, resolved: Path, detail: str = "") -> None:
        self.root = root
        self.resolved = resolved
        msg = f"Path escapes confinement root: {resolved} is not under {root}" + (
            f" ({detail})" if detail else ""
        )
        super().__init__(msg)


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
