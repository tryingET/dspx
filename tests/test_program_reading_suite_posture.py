"""Feature: the synthetic reading suite runs under any plain pytest invocation.

The reading runtime refuses to generate or run unless its caller has already
established the exact stub-only posture. For these tests the harness is that
caller, so it must not depend on hand-exported shell variables, on a clean
developer shell, or on the repository's shared ``generated/cache``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dspx.cache import cache_dir
from dspx.services.program_reading_runtime import stub_only_environment
import reading_suite_posture as posture
from reading_suite_posture import READING_SUITE_POSTURE, reading_suite_posture_context
from test_program_reading_contracts import (
    reading_test_environment as reading_test_environment,
)

reading_suite_posture = posture.reading_suite_posture
REPO_ROOT = Path(__file__).resolve().parents[1]


def test_plain_invocation_gets_the_stub_only_posture(reading_suite_posture):
    """Scenario: nobody exported the reading posture before running pytest.

    Given a pytest process whose caller exported no DSPx policy variables
    When the reading suite's module-scoped posture fixture is active
    Then the production admission check accepts the process environment
    """
    for key, value in READING_SUITE_POSTURE.items():
        assert os.environ[key] == value
    stub_only_environment()


def test_posture_is_in_place_before_module_scoped_candidates(tmp_path):
    """Scenario: candidates are materialized before any function fixture runs.

    Given an environment with none of the posture variables set
    When the posture context is entered ahead of module-scoped generation
    Then admission passes inside it and the prior environment returns after it
    """
    stripped = {k: v for k, v in os.environ.items() if k not in READING_SUITE_POSTURE}
    with pytest.MonkeyPatch.context() as ambient:
        for key in READING_SUITE_POSTURE:
            ambient.delenv(key, raising=False)
        with pytest.raises(ValueError, match="stub-only"):
            stub_only_environment()
        with reading_suite_posture_context(tmp_path / "cache"):
            stub_only_environment()
        assert {
            k: v for k, v in os.environ.items() if k not in READING_SUITE_POSTURE
        } == stripped
        assert not any(key in os.environ for key in READING_SUITE_POSTURE)


def test_stray_ambient_activation_variables_do_not_leak_in(tmp_path):
    """Scenario: a developer shell carries unrelated DSPx/MLflow variables.

    Given ambient ``MLFLOW_*`` and ``DSPX_*`` variables outside the allowlist
    When the posture context is entered
    Then they are absent inside it, so admission passes
    And they are restored unchanged when it exits
    """
    with pytest.MonkeyPatch.context() as ambient:
        ambient.setenv("MLFLOW_DISABLE_TELEMETRY", "1")
        ambient.setenv("DSPX_CONFIG", "somewhere")
        with reading_suite_posture_context(tmp_path / "cache"):
            assert "MLFLOW_DISABLE_TELEMETRY" not in os.environ
            assert "DSPX_CONFIG" not in os.environ
            stub_only_environment()
        assert os.environ["MLFLOW_DISABLE_TELEMETRY"] == "1"
        assert os.environ["DSPX_CONFIG"] == "somewhere"


def test_candidate_cache_is_private_to_the_suite(reading_suite_posture):
    """Scenario: xdist workers generate the same candidate concurrently.

    Given the default cache is the repository's shared ``generated/cache``
    When the posture fixture is active
    Then generation uses a private cache below pytest's temporary root
    And one worker can no longer overwrite the entry another worker's
        candidate receipt is bound to
    """
    private = cache_dir()
    assert private == reading_suite_posture
    assert private.is_dir()
    assert not private.is_relative_to(REPO_ROOT)


def test_each_activation_gets_its_own_cache(tmp_path):
    """Scenario: two modules (or two workers) activate the posture.

    Given two independent activations
    When each resolves its cache directory
    Then the directories differ
    """
    seen = []
    for name in ("first", "second"):
        with reading_suite_posture_context(tmp_path / name):
            seen.append(cache_dir())
    assert seen[0] != seen[1]
