from __future__ import annotations

import hashlib
import json
import os
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


def _path_for(kind: str, key: str) -> Path:
    base = cache_dir() / kind
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{key}.json"


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
