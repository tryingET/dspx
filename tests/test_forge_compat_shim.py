from __future__ import annotations

from dspx.apps import forge_compat
from dspx.forge.workorder import build_workorder as build_workorder_direct


def test_forge_compat_exports_expected_symbol() -> None:
    assert forge_compat.build_workorder is build_workorder_direct
