# summary: "Serializes process-global bytecode suppression for observational candidate imports."
# read_when:
#   - "Changing any DSPx path that imports candidate-owned Python without allowing __pycache__ writes."

from __future__ import annotations

from _thread import RLock as ReentrantLock
from contextlib import contextmanager
from collections.abc import Iterator
import sys

_BYTECODE_SUPPRESSION_LOCK = ReentrantLock()


@contextmanager
def suppress_bytecode_writes() -> Iterator[None]:
    """Set and exactly restore sys.dont_write_bytecode under one shared lock."""

    with _BYTECODE_SUPPRESSION_LOCK:
        previous = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            yield
        finally:
            sys.dont_write_bytecode = previous
