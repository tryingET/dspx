# summary: "Source-size ratchet: no over-budget module grows; no other module exceeds 500 lines."
# read_when:
#   - "A source module grows past 500 lines, or an over-budget module changes size."

"""Brownfield ratchet for the workspace code budget (500 lines per module).

`tests/fixtures/source-size-baseline.json` records every module that already exceeded
the budget when the ratchet was introduced (AK6769). Those may shrink but never grow;
every other module must stay within 500 lines. When a recorded module shrinks, lower
its entry in the same change so the ratchet tightens. Splitting modules is separate,
owner-prioritized refactoring, not something this test demands.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOTS = ("packages/dspx-core/src", "apps/forge/src")
BUDGET = 500
BASELINE = REPO / "tests/fixtures/source-size-baseline.json"


def _sizes() -> dict[str, int]:
    return {
        path.relative_to(REPO).as_posix(): path.read_bytes().count(b"\n")
        for root in ROOTS
        for path in sorted((REPO / root).rglob("*.py"))
    }


def _baseline() -> dict[str, int]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_no_source_module_grows_past_its_ratchet() -> None:
    baseline = _baseline()
    over = {
        name: lines
        for name, lines in _sizes().items()
        if lines > baseline.get(name, BUDGET)
    }
    assert over == {}, (
        f"modules over budget ({BUDGET} lines, or their recorded baseline): {over}"
    )


def test_baseline_records_only_existing_over_budget_modules() -> None:
    sizes = _sizes()
    stale = {
        name: lines
        for name, lines in _baseline().items()
        if name not in sizes or lines <= BUDGET
    }
    assert stale == {}, f"remove or fix stale baseline entries: {stale}"


def test_baseline_tightens_when_a_recorded_module_shrinks() -> None:
    """A shrunk module must lower its entry, so it cannot regrow to the old size."""
    sizes = _sizes()
    loose = {
        name: lines for name, lines in _baseline().items() if sizes.get(name) != lines
    }
    assert loose == {}, f"lower these baseline entries to the current sizes: {loose}"
