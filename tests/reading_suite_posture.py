"""Harness-side admission posture for the synthetic reading suite.

The runtime requires its caller to establish the stub-only posture before any
generation. For tests the harness is that caller. Specified by
test_program_reading_suite_posture.py.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# The exact admission posture the runtime requires from its caller.
READING_SUITE_POSTURE = {
    "DSPX_PROVIDER": "stub",
    "MLFLOW_ENABLE": "0",
    "DSPX_POLICY_ALLOW_NETWORK_MUTATE": "0",
    "DSPX_POLICY_DISALLOWED_CAPS": "network.read,network.mutate",
}


@contextlib.contextmanager
def reading_suite_posture_context(cache_root: Path) -> Iterator[Path]:
    """Establish the posture for module-scoped generation, then restore.

    Ambient DSPx/MLflow variables would be rejected by admission, and the
    default shared ``generated/cache`` lets concurrent xdist workers overwrite
    the entry a candidate receipt is bound to; both are replaced, not relaxed.
    """
    cache_root.mkdir(parents=True, exist_ok=True)
    with pytest.MonkeyPatch.context() as patch:
        for key in [k for k in os.environ if k.startswith(("DSPX_", "MLFLOW_"))]:
            patch.delenv(key)
        for key, value in READING_SUITE_POSTURE.items():
            patch.setenv(key, value)
        patch.setenv("DSPX_CACHE_DIR", str(cache_root))
        yield cache_root.resolve()


@pytest.fixture(scope="module")
def reading_suite_posture(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    with reading_suite_posture_context(
        tmp_path_factory.mktemp("reading-cache")
    ) as cache_root:
        yield cache_root
