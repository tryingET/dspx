"""Feature: hooks leave the disposable source byte-identical, caches included.

Found by the first official ``--execute``: the ruff hook wrote ``.ruff_cache`` into
the source tree. The hook guard inventories ignored files as well, so it correctly
reported a rewrite and stopped the gate after five stages.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
import verify_full_isolation as gate  # noqa: E402


def test_tool_caches_are_redirected_into_private_state():
    """Scenario: a hook that caches by default runs inside the gate.

    Given the gate's closed environment
    When ruff resolves its cache directory
    Then it lies under the private /fixture state, never in the source tree
    """
    cache = Path(gate.fixture_environment()["RUFF_CACHE_DIR"])
    assert cache.is_relative_to("/fixture")
    assert not cache.is_relative_to(gate.R)
