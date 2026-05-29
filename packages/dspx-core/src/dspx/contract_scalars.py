from __future__ import annotations

from typing import Any

_TRUE_STRINGS = {"1", "true", "yes", "on"}
_FALSE_STRINGS = {"0", "false", "no", "off"}


def contract_bool(value: Any, *, default: bool, label: str) -> bool:
    """Parse a contract-bearing boolean without Python truthiness drift.

    YAML/JSON-adjacent operator inputs often arrive as quoted strings.  Python's
    ``bool("false")`` turns those into ``True``, which corrupts policy and
    authority contracts.  Accept only real booleans and canonical boolean
    strings; reject everything else so ambiguous config cannot silently widen
    authority.
    """

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_STRINGS:
            return True
        if normalized in _FALSE_STRINGS:
            return False
    raise ValueError(f"{label} must be a boolean")
