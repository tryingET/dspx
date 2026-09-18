"""Feature: a generated program always imports its OWN sibling modules.

Every generated program says ``from module import ...`` and
``from signature import ...``: generic, process-global names. If anything imported
a ``module`` earlier in the process, Python serves that cached stranger instead of
the file next to the program. Loaders must evict before importing, not only
restore afterwards (AK-5756).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from dspx.services.optimize_service import _import_program_module


def _candidate(root: Path, marker: str) -> Path:
    root.mkdir(parents=True)
    (root / "module.py").write_text(f"VALUE = {marker!r}\n", encoding="utf-8")
    (root / "signature.py").write_text(f"VALUE = {marker!r}\n", encoding="utf-8")
    (root / "program.py").write_text(
        "from module import VALUE as MODULE_VALUE\n"
        "from signature import VALUE as SIGNATURE_VALUE\n",
        encoding="utf-8",
    )
    return root / "program.py"


@pytest.fixture
def trusted(tmp_path, monkeypatch):
    monkeypatch.setenv("DSPX_TRUSTED_PROGRAM_ROOTS", str(tmp_path))
    return tmp_path


def test_a_stale_generic_module_is_not_served_to_the_program(trusted, monkeypatch):
    """Scenario: something imported a ``module`` before the program is loaded.

    Given ``module`` and ``signature`` are already cached from elsewhere
    When a generated program is imported by the optimizer's loader
    Then the program binds the values from its own sibling files
    And the earlier cached modules are back in place afterwards
    """
    stale = {}
    for name in ("module", "signature"):
        stale[name] = types.ModuleType(name)
        stale[name].VALUE = "stranger"
        monkeypatch.setitem(sys.modules, name, stale[name])

    program = _import_program_module(_candidate(trusted / "own", "own"))

    bound = (getattr(program, "MODULE_VALUE"), getattr(program, "SIGNATURE_VALUE"))
    assert bound == ("own", "own")
    assert sys.modules["module"] is stale["module"]
    assert sys.modules["signature"] is stale["signature"]


def test_two_programs_in_one_process_each_get_their_own_siblings(trusted):
    """Scenario: two candidates are loaded back to back, as a comparison does.

    Given two generated programs with differently valued siblings
    When both are imported in the same process
    Then neither sees the other's ``module``
    And no generic name is left behind
    """
    first = _import_program_module(_candidate(trusted / "a", "first"))
    second = _import_program_module(_candidate(trusted / "b", "second"))

    assert getattr(first, "MODULE_VALUE") == "first"
    assert getattr(second, "MODULE_VALUE") == "second"
    assert "module" not in sys.modules and "signature" not in sys.modules
