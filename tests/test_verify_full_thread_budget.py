"""Feature: the gate's workers fit inside the container's task limit.

Found by the first real in-container run: numeric libraries size their thread
pools from the host core count (64 here), not from the ``--cpus`` quota. Threads
count against ``--pids-limit=1024``, so 16 xdist workers x 64 threads exhausted it
during startup and every fork failed with EAGAIN.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
import verify_full_isolation as gate  # noqa: E402

THREAD_POOL_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def test_numeric_thread_pools_are_capped_in_the_closed_environment():
    """Scenario: sixteen workers import numpy on a 64-core host.

    Given the gate's closed fixture environment
    When a worker imports a numeric library
    Then every thread-pool variable pins the pool to a single thread
    """
    env = gate.fixture_environment()
    assert {name: env.get(name) for name in THREAD_POOL_VARIABLES} == dict.fromkeys(
        THREAD_POOL_VARIABLES, "1"
    )


def test_the_environment_stays_closed():
    """Scenario: the caps must not open the environment to ambient activation."""
    env = gate.fixture_environment()
    assert env["DSPX_PROVIDER"] == "stub" and env["MLFLOW_ENABLE"] == "0"
    assert not any("KEY" in name or "TOKEN" in name for name in env)
