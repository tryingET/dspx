from __future__ import annotations

import tomllib
from pathlib import Path


def test_forge_depends_on_bounded_core_version_range() -> None:
    pyproject = tomllib.loads(
        Path("apps/forge/pyproject.toml").read_text(encoding="utf-8")
    )
    deps = pyproject["project"]["dependencies"]
    core_dep = next((d for d in deps if d.startswith("dspx-core")), "")

    assert core_dep, "apps/forge must declare dspx-core dependency"
    assert ">=" in core_dep, "dspx-core dependency must include a lower bound"
    assert "<" in core_dep, "dspx-core dependency must include an upper bound"
