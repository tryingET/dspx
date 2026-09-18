"""Feature: the fixture-plane audit blocks native authority, not look-alike fixtures.

Found by the first real in-container run: a test that builds a synthetic
``agent-kernel/`` directory under pytest's private tmp root was denied, because
the audit matched the path text alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
import verify_full_membership as membership  # noqa: E402

NATIVE = "/home/tryinget/ai-society/softwareco/owned/agent-kernel/policy/x.json"


@pytest.fixture
def private_tmp(monkeypatch):
    monkeypatch.setenv("TMPDIR", "/fixture/tmp")


def test_a_synthetic_fixture_under_private_tmp_is_allowed(private_tmp):
    """Scenario: a test writes ``<tmp>/agent-kernel/docs/x.json``.

    Given the gate's private TMPDIR
    When a file below it is opened whose path merely contains ``/agent-kernel/``
    Then the audit allows it
    """
    membership.authority_audit(
        "open", ("/fixture/tmp/pytest-0/t0/agent-kernel/docs/x.json", "w", 0)
    )
    membership.authority_audit(
        "open", ("/fixture/tmp/pytest-0/t0/society.v2.db", "r", 0)
    )


@pytest.mark.parametrize(
    "path",
    [
        NATIVE,
        "/home/tryinget/ai-society/society.v2.db",
        "/fixture/tmp/../../home/tryinget/ai-society/softwareco/owned/agent-kernel/x",
        "/fixture/tmpevil/agent-kernel/x",
    ],
)
def test_native_authority_paths_stay_blocked(private_tmp, path):
    """Scenario: real authority, a traversal out of tmp, or a tmp look-alike prefix."""
    with pytest.raises(PermissionError, match="native authority"):
        membership.authority_audit("open", (path, "r", 0))


def test_without_a_private_tmp_nothing_is_exempt(monkeypatch):
    """Scenario: TMPDIR is unset, so no exemption can apply."""
    monkeypatch.delenv("TMPDIR", raising=False)
    with pytest.raises(PermissionError):
        membership.authority_audit("open", ("/fixture/tmp/t0/agent-kernel/x", "w", 0))
