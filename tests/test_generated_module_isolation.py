"""Feature: generated programs cannot leak between tests in one worker.

Every generated program imports the same generic top-level names, ``module``
and ``signature``. A test that executes one leaves them in ``sys.modules``; the
next test on the same xdist worker then imports a stranger's ``module`` and
fails with an ImportError that depends only on scheduling.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def _import_generated(root: Path, marker: str) -> str:
    (root / "module.py").write_text(f"MARKER = {marker!r}\n", encoding="utf-8")
    (root / "signature.py").write_text(f"MARKER = {marker!r}\n", encoding="utf-8")
    sys.path.insert(0, str(root))
    try:
        importlib.import_module("signature")
        return importlib.import_module("module").MARKER
    finally:
        # Deliberately the incomplete cleanup real tests perform.
        sys.path.remove(str(root))


def test_first_candidate_is_imported_and_left_behind(tmp_path):
    """Scenario: a test executes generated code and forgets ``sys.modules``.

    Given a generated candidate on ``sys.path``
    When the test imports its ``module`` and only restores ``sys.path``
    Then the import itself works
    """
    assert _import_generated(tmp_path, "first") == "first"
    assert "module" in sys.modules and "signature" in sys.modules


def test_next_test_on_the_same_worker_sees_its_own_candidate(tmp_path):
    """Scenario: the following test materializes a different candidate.

    Given the previous test left ``module`` and ``signature`` imported
    When this test starts
    Then neither generic name is cached any more
    And importing ``module`` yields this test's candidate, not the stranger's
    """
    assert "module" not in sys.modules
    assert "signature" not in sys.modules
    assert _import_generated(tmp_path, "second") == "second"


@pytest.mark.parametrize("name", ["module", "signature"])
def test_isolation_only_targets_the_generic_generated_names(name):
    """Scenario: isolation must not evict real packages.

    Given the harness evicts generated top-level names between tests
    When the evicted names are listed
    Then they are exactly the generic generated-surface names
    """
    from conftest import GENERATED_TOP_LEVEL_MODULES

    assert name in GENERATED_TOP_LEVEL_MODULES
    assert set(GENERATED_TOP_LEVEL_MODULES) == {"module", "signature"}
