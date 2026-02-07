from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def stable_sha256(obj: Any) -> str:
    blob = stable_json(obj).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(s: str, *, max_len: int = 32) -> str:
    s = (s or "").strip().lower()
    s = _slug_re.sub("_", s).strip("_")
    s = re.sub(r"_+", "_", s)
    if not s:
        return "work"
    return s[:max_len].strip("_") or "work"


def workorder_id_from_title(title: str, fingerprint: str) -> str:
    fp = fingerprint.split(":", 1)[-1]
    return f"wo_{slugify(title)}_{fp[:8]}"
