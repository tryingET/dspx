"""Feature: generated programs cannot leak between tests in one worker.

Every generated program imports the same generic top-level names, ``module``
and ``signature``. A test that executes one leaves them in ``sys.modules``; the
next test on the same xdist worker then imports a stranger's ``module`` and
fails with an ImportError that depends only on scheduling.

Known product limitation, tracked separately: a user who puts two generated
programs on ``sys.path`` in one process hits the same collision. The product
loaders save and restore ``sys.modules``; ad hoc imports do not.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from conftest import GENERATED_TOP_LEVEL_MODULES, evict_generated_top_level_modules


def _import_generated(root: Path, marker: str) -> str:
    root.mkdir()
    (root / "module.py").write_text(f"MARKER = {marker!r}\n", encoding="utf-8")
    (root / "signature.py").write_text(f"MARKER = {marker!r}\n", encoding="utf-8")
    sys.path.insert(0, str(root))
    try:
        importlib.import_module("signature")
        return importlib.import_module("module").MARKER
    finally:
        # Deliberately the incomplete cleanup real tests perform.
        sys.path.remove(str(root))


def test_a_second_candidate_is_not_served_the_first_ones_module(tmp_path):
    """Scenario: two tests on one worker each execute a generated program.

    Given a first candidate was imported and only ``sys.path`` was restored
    And, without isolation, a second candidate is served the first one's ``module``
    When the harness evicts the generic generated names between the two
    Then the second candidate imports its own ``module``
    """
    assert _import_generated(tmp_path / "first", "first") == "first"
    # The hazard itself, so this spec fails if eviction ever becomes a no-op.
    assert _import_generated(tmp_path / "stale", "second") == "first"

    evict_generated_top_level_modules()

    assert not set(GENERATED_TOP_LEVEL_MODULES) & set(sys.modules)
    assert _import_generated(tmp_path / "second", "second") == "second"


def test_eviction_targets_only_the_generic_generated_names():
    """Scenario: isolation must not evict real packages.

    Given a real module is imported
    When generated names are evicted
    Then the real module stays imported
    """
    import json

    evict_generated_top_level_modules()
    assert sys.modules["json"] is json
    assert GENERATED_TOP_LEVEL_MODULES == ("module", "signature")
