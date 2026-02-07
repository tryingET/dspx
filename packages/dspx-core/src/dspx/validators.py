from __future__ import annotations

import json
import re
from typing import Any, Callable, Iterable

Validator = Callable[..., bool]


def non_empty() -> Validator:
    def _v(text: str, **ctx) -> bool:
        return bool(text and str(text).strip())

    return _v


def contains_all(keywords: Iterable[str]) -> Validator:
    keys = [k for k in keywords if k]

    def _v(text: str, **ctx) -> bool:
        t = text or ""
        return all(k in t for k in keys)

    return _v


def regex(pattern: str, flags: int = 0) -> Validator:
    rx = re.compile(pattern, flags)

    def _v(text: str, **ctx) -> bool:
        return bool(rx.search(text or ""))

    return _v


def json_parsable() -> Validator:
    def _v(text: str, **ctx) -> bool:
        try:
            json.loads(text)
            return True
        except Exception:
            return False

    return _v


def json_has(path: str) -> Validator:
    parts = [p for p in path.split(".") if p]

    def _v(text: str, **ctx) -> bool:
        try:
            obj = json.loads(text)
        except Exception:
            return False
        cur: Any = obj
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return False
        return True

    return _v


def any_of(*validators: Validator) -> Validator:
    def _v(text: str, **ctx) -> bool:
        for f in validators:
            try:
                if f(text, **ctx):
                    return True
            except Exception:
                continue
        return False

    return _v


def all_of(*validators: Validator) -> Validator:
    def _v(text: str, **ctx) -> bool:
        for f in validators:
            try:
                if not f(text, **ctx):
                    return False
            except Exception:
                return False
        return True

    return _v


def from_metric(metric: Callable[..., Any]) -> Validator:
    """Wrap a DSPy-style metric callable into a validator.

    Accepts functions that return bool-like or numeric (positive=pass).
    """

    def _v(text: str, **ctx) -> bool:
        try:
            v = metric(text, **ctx)
            if isinstance(v, (int, float)):
                return v > 0
            return bool(v)
        except Exception:
            return False

    return _v
