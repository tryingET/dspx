from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional


def _truthy(v: Optional[str]) -> bool:
    if v is None:
        return True
    return str(v).strip().lower() not in {"", "0", "false", "no", "off"}


def cache_enabled() -> bool:
    return _truthy(os.getenv("DSPX_CACHE_ENABLE", "1"))


def cache_dir() -> Path:
    d = os.getenv("DSPX_CACHE_DIR")
    return Path(d).expanduser().resolve() if d else Path.cwd() / "generated" / "cache"


def _canonical_json(data: Any) -> str:
    def _default(o: Any) -> str:
        try:
            return str(o)
        except Exception:
            return repr(o)

    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_default)


def make_key(payload: Dict[str, Any]) -> str:
    s = _canonical_json(payload)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


_CACHE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _validate_cache_segment(value: str, *, label: str) -> str:
    text = str(value or "").strip()
    if not text or text in {".", ".."} or not _CACHE_SEGMENT_RE.fullmatch(text):
        raise ValueError(f"invalid cache {label}: {value!r}")
    return text


def validate_cache_segment(value: str, *, label: str) -> str:
    """Validate one user-controlled cache path segment.

    Cache kinds and keys are intentionally single path segments. Public CLI
    surfaces must use this helper family instead of joining raw user input onto
    ``cache_dir()``.
    """

    return _validate_cache_segment(value, label=label)


def cache_kind_dir(kind: str, *, create: bool = False) -> Path:
    """Return a validated cache kind directory inside ``cache_dir()``."""

    safe_kind = validate_cache_segment(kind, label="kind")
    root = cache_dir().resolve()
    base = (root / safe_kind).resolve()
    try:
        base.relative_to(root)
    except ValueError as exc:
        raise ValueError("cache path escapes DSPX_CACHE_DIR") from exc
    if create:
        root.mkdir(parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        base.mkdir(parents=True, exist_ok=True)
        os.chmod(base, 0o700)
    return base


def cache_entry_path(kind: str, key: str, *, create_dir: bool = False) -> Path:
    """Return a validated cache entry path inside ``cache_dir()``."""

    safe_key = validate_cache_segment(key, label="key")
    base = cache_kind_dir(kind, create=create_dir)
    root = cache_dir().resolve()
    path = (base / f"{safe_key}.json").resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("cache path escapes DSPX_CACHE_DIR") from exc
    return path


def _path_for(kind: str, key: str, *, create_dir: bool = True) -> Path:
    return cache_entry_path(kind, key, create_dir=create_dir)


def read(kind: str, key: str) -> Optional[Dict[str, Any]]:
    p = _path_for(kind, key, create_dir=False)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def write(kind: str, key: str, data: Dict[str, Any]) -> Path:
    p = _path_for(kind, key)
    txt = _canonical_json(data)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(p, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fd = -1
            fh.write(txt)
        os.chmod(p, 0o600)
    finally:
        if fd >= 0:
            os.close(fd)
    return p


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
