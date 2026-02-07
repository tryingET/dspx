from __future__ import annotations

from dspx.apps.forge_app.workorder import build_workorder as app_build_workorder
from dspx.forge.workorder import build_workorder as legacy_build_workorder


def test_forge_app_boundary_workorder_forwarder_is_compatible() -> None:
    assert app_build_workorder is legacy_build_workorder
