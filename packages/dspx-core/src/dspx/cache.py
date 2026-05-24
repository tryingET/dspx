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
    return v not in {"", "0", "false", "False", "no", "No"}


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


def _path_for(kind: str, key: str) -> Path:
    safe_kind = _validate_cache_segment(kind, label="kind")
    safe_key = _validate_cache_segment(key, label="key")
    root = cache_dir().resolve()
    base = (root / safe_kind).resolve()
    path = (base / f"{safe_key}.json").resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("cache path escapes DSPX_CACHE_DIR") from exc
    base.mkdir(parents=True, exist_ok=True)
    return path


def read(kind: str, key: str) -> Optional[Dict[str, Any]]:
    p = _path_for(kind, key)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        return data
    except Exception:
        return None


def write(kind: str, key: str, data: Dict[str, Any]) -> Path:
    p = _path_for(kind, key)
    txt = _canonical_json(data)
    p.write_text(txt, encoding="utf-8")
    return p


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
