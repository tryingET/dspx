"""Feature: a closure may never mount over the gate's runtime or private state.

Found by the first real in-container run: there pytest's tmp root is
``/fixture/tmp``, so the gate's own unit tests validate fixture repositories that
live under ``/fixture``. The guard must keep protecting the real private state
without rejecting a target inside the very repository being validated.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
import verify_full_closure as closure  # noqa: E402

REPO = Path("/home/tryinget/ai-society/softwareco/owned/dspx")


@pytest.mark.parametrize(
    "target", ["/fixture", "/fixture/home", "/proc/1", "/sys/x", "/dev/null", "/run/y"]
)
def test_runtime_and_private_roots_are_protected(target):
    """Scenario: a manifest tries to mount over container state.

    Given the production repository root
    When a closure target lies under /proc, /sys, /dev, /run or /fixture
    Then it is classified as replacing private state
    """
    assert closure.replaces_private_state(Path(target), REPO)


def test_gate_self_tests_inside_the_container_are_not_rejected():
    """Scenario: the gate validates a fixture repository under /fixture/tmp.

    Given a repository that itself lives below /fixture/tmp
    When a closure target is that repository's own .venv
    Then it does not replace private state
    But a sibling path under /fixture outside that repository still does
    """
    repo = Path("/fixture/tmp/pytest-of-tryinget/pytest-0/test_x0/repo")
    assert not closure.replaces_private_state(repo / ".venv", repo)
    assert closure.replaces_private_state(Path("/fixture/tmp/elsewhere"), repo)
    assert closure.replaces_private_state(Path("/fixture/oracle"), repo)


def test_ordinary_targets_are_unaffected():
    """Scenario: the reviewed venv and home tool paths."""
    assert not closure.replaces_private_state(REPO / ".venv", REPO)
    assert not closure.replaces_private_state(
        Path("/home/tryinget/.local/bin/prek"), REPO
    )
