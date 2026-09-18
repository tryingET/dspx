"""Feature: a green CI run on an exact commit clears release *evidence*.

Owner decision 2026-09-18 (docs/adr/20260918-ci-evidence-clearance.md): the
hosted run is the evidence gate, so "green" has to mean what it claims. Green is
worthless if a shard silently drops tests, if a new skip hides a failure, or if
the files that define the gate change without anyone noticing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import ci_evidence_predicate as predicate  # noqa: E402


# --- Rule: the shards partition the offline suite exactly -------------------


def test_complete_disjoint_shards_are_accepted():
    """Scenario: every offline test lands in exactly one shard.

    Given the full offline collection
    And shard collections whose union equals it without overlap
    When the partition is checked
    Then no problem is reported
    """
    full = ["t.py::a", "t.py::b", "u.py::c"]
    shards = {"core-0": ["t.py::a"], "core-1": ["t.py::b"], "slow": ["u.py::c"]}
    assert predicate.partition_problems(shards, full) == []


def test_a_test_missing_from_every_shard_is_reported():
    """Scenario: a marker typo or sharding bug drops a test from CI.

    Given an offline test that no shard collects
    When the partition is checked
    Then that node id is reported as never run
    """
    problems = predicate.partition_problems(
        {"core-0": ["t.py::a"]}, ["t.py::a", "t.py::b"]
    )
    assert problems == ["never run by any shard: t.py::b"]


def test_a_test_collected_twice_is_reported():
    """Scenario: two shards overlap.

    Given one node id collected by two shards
    When the partition is checked
    Then the duplicate and both shards are reported
    """
    problems = predicate.partition_problems(
        {"core-0": ["t.py::a"], "slow": ["t.py::a"]}, ["t.py::a"]
    )
    assert problems == ["run by more than one shard (core-0, slow): t.py::a"]


def test_a_shard_cannot_run_something_outside_the_offline_suite():
    """Scenario: a shard collects a test the offline selection excludes.

    Given a shard node id absent from the full offline collection
    When the partition is checked
    Then it is reported
    """
    problems = predicate.partition_problems(
        {"core-0": ["t.py::a", "t.py::live"]}, ["t.py::a"]
    )
    assert problems == ["collected by core-0 but outside the offline suite: t.py::live"]


# --- Rule: no test leaves the pass/fail set without a reviewed baseline entry


RUN_LOG = (
    "SKIPPED [3] tests/test_x.py:10: needs the bwrap namespace\n"
    "SKIPPED [1] tests/test_x.py:99: needs the bwrap namespace\n"
    "XFAIL tests/test_z.py::test_known - tracked: bug 12\n"
    "XPASS tests/test_z.py::test_fixed - tracked: bug 12\n"
    "9 passed, 4 skipped, 1 xfailed, 1 xpassed in 0.10s\n"
)


def test_outcomes_are_keyed_by_file_and_reason_and_counted():
    """Scenario: unrelated edits move a skipping test down the file.

    Given pytest ``-rsxX`` rows for one skip reason at two line numbers
    When outcomes are parsed
    Then they collapse into one (file, reason) key whose count is their sum
    And xfail and xpass rows are captured too, not ignored
    """
    assert predicate.parse_outcomes(RUN_LOG) == {
        ("tests/test_x.py", "needs the bwrap namespace"): 4,
        ("tests/test_z.py", "XFAIL: test_known - tracked: bug 12"): 1,
        ("tests/test_z.py", "XPASS: test_fixed - tracked: bug 12"): 1,
    }


def test_xfail_rows_with_awkward_parametrize_ids_are_still_itemised():
    """Scenario: a parametrize id contains spaces or " - ".

    Given xfail rows whose node ids contain whitespace and a dash separator
    When outcomes are parsed
    Then each row is itemised under its full node id, so totals still reconcile
    """
    log = (
        "XFAIL tests/test_x.py::test_p[a b] - param\n"
        "XFAIL tests/test_x.py::test_p[c - d] - param\n"
        "XFAIL tests/test_x.py::Class::test_m\n"
        "3 xfailed in 0.10s\n"
    )
    assert predicate.parse_outcomes(log) == {
        ("tests/test_x.py", "XFAIL: test_p[a b] - param"): 1,
        ("tests/test_x.py", "XFAIL: test_p[c - d] - param"): 1,
        ("tests/test_x.py", "XFAIL: Class::test_m"): 1,
    }
    assert predicate.summary_problems(log) == []


def test_a_new_skip_or_xfail_is_reported():
    """Scenario: someone parks a red test behind ``skip`` or ``xfail``.

    Given a baseline listing one known skip
    When a run also reports an xfail nobody reviewed
    Then only the xfail is reported
    """
    baseline = predicate.parse_baseline(
        "# comment\n\ntests/test_x.py :: needs the bwrap namespace :: 4\n"
    )
    seen = predicate.parse_outcomes(RUN_LOG)
    assert predicate.outcome_problems(seen, baseline) == [
        "unreviewed: tests/test_z.py :: XFAIL: test_known - tracked: bug 12",
        "unreviewed: tests/test_z.py :: XPASS: test_fixed - tracked: bug 12",
    ]


def test_hiding_one_more_test_behind_a_known_reason_is_reported():
    """Scenario: a new red test reuses an already baselined skip reason.

    Given a baseline allowing at most 3 skips for a (file, reason)
    When a run reports 4
    Then the excess is reported with both numbers
    """
    baseline = {("tests/test_x.py", "needs the bwrap namespace"): 3}
    seen = {("tests/test_x.py", "needs the bwrap namespace"): 4}
    assert predicate.outcome_problems(seen, baseline) == [
        "count 4 exceeds reviewed maximum 3: tests/test_x.py :: needs the bwrap namespace"
    ]


def test_rows_must_account_for_pytests_own_totals():
    """Scenario: the report rows are suppressed or change shape.

    Given a final line announcing 2 skipped but no SKIPPED rows at all
    When the log is reconciled
    Then the check fails closed instead of reporting zero skips
    """
    assert predicate.summary_problems("1 passed, 2 skipped in 0.10s\n") == [
        "pytest reported 2 skipped but 0 were itemised; refusing to pass"
    ]
    assert predicate.summary_problems(RUN_LOG) == []


def test_a_log_without_a_pytest_summary_fails_closed():
    """Scenario: pytest died, or its terminal summary was disabled.

    Given a log with no final totals line
    When the log is reconciled
    Then it is a failure, not an empty success
    """
    assert predicate.summary_problems("some unrelated output\n") == [
        "no pytest totals line found; refusing to pass"
    ]


def test_the_checked_in_baseline_is_well_formed():
    """Scenario: the real baseline parses, is sorted and unique, and carries counts."""
    rows = [
        row
        for row in predicate.SKIP_BASELINE.read_text().splitlines()
        if row and not row.startswith("#")
    ]
    assert rows == sorted(set(rows))
    parsed = predicate.parse_baseline(predicate.SKIP_BASELINE.read_text())
    assert len(parsed) == len(rows)
    assert all(count >= 1 for count in parsed.values())


# --- Rule: tests cannot leave the offline suite unnoticed -------------------


def test_marking_a_red_test_live_changes_the_excluded_count():
    """Scenario: a failing test is given a ``live`` marker to drop it from CI.

    Given the approved number of tests outside the offline selection
    When one more test is excluded
    Then the collection check reports the drift
    And an empty collection is never accepted as a partition
    """
    assert predicate.exclusion_problems(total=20, offline=17, approved_excluded=3) == []
    assert predicate.exclusion_problems(total=20, offline=16, approved_excluded=3) == [
        "4 tests are excluded from the offline suite but 3 are approved"
    ]
    assert predicate.exclusion_problems(total=0, offline=0, approved_excluded=0) == [
        "collected no offline tests; refusing to treat an empty suite as partitioned"
    ]


# --- Rule: the gate's own definition cannot drift silently ------------------


def _approval(**overrides):
    base = {
        "approved_by": "owner",
        "reviewed_by": "independent reviewer",
        "excluded_node_count": 0,
        "files": {},
    }
    return base | overrides


def test_gate_defining_files_match_their_recorded_approval():
    """Scenario: CI is edited to make a red build green.

    Given the recorded approval of every gate-defining file
    When the current files are hashed
    Then each digest equals its approved digest and nobody is PENDING
    """
    assert predicate.approval_problems() == []


def test_the_gate_set_covers_everything_that_can_neuter_it():
    """Scenario: the workflow only calls recipes, so hashing it alone pins nothing.

    Given the gate-defining file set
    Then it includes the recipes, pytest configuration, shared fixtures and
        the specs that enforce the inventories
    """
    for path in (
        ".github/workflows/ci.yml",
        "Justfile",
        "pyproject.toml",
        "tests/conftest.py",
        "scripts/ci/test-shard.sh",
        "scripts/ci/package-check.sh",
        "tests/test_ci_evidence_predicate.py",
        "tests/test_ci_shard_selection.py",
    ):
        assert path in predicate.GATE_FILES


def test_an_unapproved_gate_edit_is_detected(tmp_path):
    """Scenario: a gate-defining file changes but the approval does not."""
    target = tmp_path / "gate.sh"
    target.write_text("original\n")
    approved = _approval(files={"gate.sh": predicate.sha256_file(target)})
    target.write_text("edited to pass\n")
    assert predicate.approval_problems(
        approved, root=tmp_path, gate_files=("gate.sh",)
    ) == ["gate file changed without a recorded approval: gate.sh"]


def test_an_approval_that_omits_a_gate_file_is_rejected(tmp_path):
    """Scenario: the approval is emptied so that nothing can mismatch.

    Given an approval whose file map lacks a gate file
    When it is checked from the gate file set, not from its own keys
    Then the omission is reported
    """
    (tmp_path / "gate.sh").write_text("x\n")
    assert predicate.approval_problems(
        _approval(), root=tmp_path, gate_files=("gate.sh",)
    ) == ["gate file has no recorded approval: gate.sh"]


@pytest.mark.parametrize("field", ["approved_by", "reviewed_by"])
@pytest.mark.parametrize("value", ["", "PENDING", "pending", "TBD"])
def test_a_placeholder_reviewer_is_not_an_approval(tmp_path, field, value):
    """Scenario: the record is committed before anyone reviewed it."""
    problems = predicate.approval_problems(
        _approval(**{field: value}), root=tmp_path, gate_files=()
    )
    assert problems == [f"approval field {field} is a placeholder: {value!r}"]


# --- Rule: the workflow actually wires the predicate in ---------------------


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())


def test_ci_runs_the_runtime_checks(workflow):
    """Scenario: runtime invariants are part of the evidence.

    Given the CI workflow
    When its jobs are read
    Then a ``runtime`` job runs replay provenance, monorepo and module-synthesis checks
    """
    steps = " ".join(
        str(s.get("run", "")) for s in workflow["jobs"]["runtime"]["steps"]
    )
    assert "just ci-runtime" in steps
    justfile = (ROOT / "Justfile").read_text()
    recipe = justfile[justfile.index("\nci-runtime:\n") :].split("\n\n", 1)[0]
    for check in (
        "replay-provenance-check",
        "monorepo-check",
        "module-synthesis-quality-check",
    ):
        assert f"just {check}" in recipe


def test_ci_checks_the_partition_and_the_skip_baseline(workflow):
    """Scenario: the integrity checks are not optional extras.

    Given the CI workflow and the shard script
    When they are read
    Then the quality job checks the shard partition
    And every shard run is checked against the skip baseline
    """
    quality = " ".join(
        str(s.get("run", "")) for s in workflow["jobs"]["quality"]["steps"]
    )
    assert "ci-collection-integrity" in quality
    shard = (ROOT / "scripts/ci/test-shard.sh").read_text()
    assert "ci_evidence_predicate.py skips" in shard
