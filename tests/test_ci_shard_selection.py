"""Feature: generic CI shards run only what a generic runner can run.

Some full-gate tests are pinned, by design, to the owner's workstation: its
``/usr/bin/just``, its scratch root, and a private network namespace that the
real hook fixtures refuse to run without. They belong to the workstation gate.
Reclassifying them must be explicit and counted, never a silent skip.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests/fixtures/workstation-tests.txt"


def _shard_offline_expression() -> str:
    script = (ROOT / "scripts/ci/test-shard.sh").read_text()
    match = re.search(r"^offline='([^']+)'$", script, flags=re.MULTILINE)
    assert match, "test-shard.sh must declare one offline marker expression"
    return match.group(1)


def test_workstation_marker_is_registered():
    """Scenario: the reclassification uses a declared marker.

    Given pytest markers are declared in pyproject.toml
    When the marker list is read
    Then ``workstation`` is declared with a description
    """
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    markers = config["tool"]["pytest"]["ini_options"]["markers"]
    assert any(row.startswith("workstation:") for row in markers)


def test_generic_shards_exclude_workstation_tests():
    """Scenario: GitHub's runner is not the owner's workstation.

    Given the shard script's offline marker expression
    When a core, forge or slow shard is selected
    Then workstation-bound tests are deselected
    """
    assert "not workstation" in _shard_offline_expression()


def test_workstation_gate_still_selects_them():
    """Scenario: reclassified tests keep a home.

    Given the full gate's own offline selection
    When its marker expression is read
    Then it does not exclude workstation-bound tests
    """
    sys.path.insert(0, str(ROOT / "scripts/ci"))
    try:
        import verify_full_membership as membership
    finally:
        sys.path.pop(0)
    assert "workstation" not in membership.OFFLINE
    assert "workstation" not in membership.RESIDUAL


def test_workstation_inventory_is_exact_and_counted():
    """Scenario: nobody can quietly grow the excluded set.

    Given a checked-in inventory of workstation-bound test nodes
    When pytest collects everything carrying the marker
    Then the collected node ids equal that inventory exactly
    """
    expected = [
        row
        for row in BASELINE.read_text().splitlines()
        if row and not row.startswith("#")
    ]
    assert expected == sorted(expected) and len(set(expected)) == len(expected)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-m",
            "workstation",
            "tests",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    collected = sorted(row for row in result.stdout.splitlines() if "::" in row)
    assert collected == expected
