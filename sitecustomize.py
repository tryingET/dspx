"""Ensure `src/` is on sys.path for in-repo runs.

Python automatically imports `sitecustomize` if found on sys.path.
This file keeps `uv run python -m ...` commands working after switching
to a `src/` layout without requiring installation.
"""

from __future__ import annotations

import sys
from pathlib import Path

root = Path(__file__).resolve().parent
src = root / "src"
if src.is_dir():
    sys.path.insert(0, str(src))
