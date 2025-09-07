from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class StoreAdapter:
    """Base store adapter (very small surface for MVP)."""

    def put_text(self, rel_path: str, text: str) -> str:  # pragma: no cover
        raise NotImplementedError

    def get_text(self, rel_path: str) -> str:  # pragma: no cover
        raise NotImplementedError

    def exists(self, rel_path: str) -> bool:  # pragma: no cover
        raise NotImplementedError


@dataclass
class LocalObjectStore(StoreAdapter):
    """File-backed object store rooted at a directory.

    Intended for tests/examples; not a general artifact system.
    """

    root: str | Path
    create: bool = True

    def __post_init__(self) -> None:
        p = Path(self.root)
        if self.create:
            p.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            raise FileNotFoundError(p)
        self._root = p

    def _full(self, rel: str) -> Path:
        relp = Path(rel)
        # Prevent escaping the root via .. components
        full = (self._root / relp).resolve()
        if self._root not in full.parents and full != self._root:
            raise ValueError("path escapes store root")
        return full

    def put_text(self, rel_path: str, text: str) -> str:
        dest = self._full(rel_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        return str(dest)

    def get_text(self, rel_path: str) -> str:
        src = self._full(rel_path)
        return src.read_text(encoding="utf-8")

    def exists(self, rel_path: str) -> bool:
        return self._full(rel_path).exists()
