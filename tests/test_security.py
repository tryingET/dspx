from __future__ import annotations

from pathlib import Path

import pytest

from dspx.security import UnsafePathComponentError, confine_relative_path


def test_confine_relative_path_rejects_empty_and_dot_components(tmp_path: Path) -> None:
    for unsafe in ("", "."):
        with pytest.raises(UnsafePathComponentError):
            confine_relative_path(tmp_path, unsafe, "artifact.txt")


def test_confine_relative_path_rejects_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathComponentError):
        confine_relative_path(tmp_path, "..", "artifact.txt")
