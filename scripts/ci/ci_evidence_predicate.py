#!/usr/bin/env python3
# ---
# summary: "Integrity checks that make an exact-SHA green CI run usable as release evidence: shard partition, skip baseline, gate-file approval."
# read_when:
#   - "Changing CI sharding, skip handling, or any file that defines the CI evidence gate."
# ---
"""CI evidence predicate helpers (docs/adr/20260918-ci-evidence-clearance.md).

Clears evidence only. Never release authorization, tagging, publishing, AK task
completion, or any live/model/gpu/postgres test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHARDS = ("core-0", "core-1", "core-2", "core-3", "forge", "slow")
SKIP_BASELINE = ROOT / "tests/fixtures/ci-skip-baseline.txt"
APPROVAL = ROOT / "governance/ci-gate-approval.json"
# Files whose bytes define what "green" means.
GATE_FILES = (
    ".github/workflows/ci.yml",
    "Justfile",
    "pyproject.toml",
    "scripts/ci/ci_evidence_predicate.py",
    "scripts/ci/package-check.sh",
    "scripts/ci/test-shard.sh",
    "tests/conftest.py",
    "tests/fixtures/ci-skip-baseline.txt",
    "tests/fixtures/workstation-tests.txt",
    "tests/test_ci_evidence_predicate.py",
    "tests/test_ci_shard_selection.py",
)
_PLACEHOLDERS = {"", "pending", "tbd", "todo", "none"}
_SKIP_ROW = re.compile(
    r"^SKIPPED \[(?P<n>\d+)\] (?P<file>[^:\s]+):\d+: (?P<reason>.+)$"
)
# Keyed on the whole node id plus reason: parametrize ids may contain spaces or " - ".
_X_ROW = re.compile(r"^(?P<kind>XFAIL|XPASS) (?P<file>[^:\s]+)::(?P<rest>.+)$")
_TOTALS = re.compile(r"^=*\s*(?:\d+ [a-z]+(?:, )?)+ in [0-9.]+s")
_TOTAL_PART = re.compile(r"(\d+) (skipped|xfailed|xpassed)\b")
Outcomes = dict[tuple[str, str], int]


def partition_problems(
    shards: Mapping[str, Iterable[str]], full: Iterable[str]
) -> list[str]:
    owners: dict[str, list[str]] = {}
    for shard, nodes in shards.items():
        for node in nodes:
            owners.setdefault(node, []).append(shard)
    expected = set(full)
    problems = [f"never run by any shard: {n}" for n in sorted(expected - set(owners))]
    for node in sorted(owners):
        names = sorted(owners[node])
        if len(names) > 1:
            problems.append(f"run by more than one shard ({', '.join(names)}): {node}")
        if node not in expected:
            problems.append(
                f"collected by {names[0]} but outside the offline suite: {node}"
            )
    return problems


def parse_outcomes(log: str) -> Outcomes:
    """Every test that left the pass/fail set: skips, xfails and xpasses."""
    seen: Outcomes = {}
    for row in log.splitlines():
        if match := _SKIP_ROW.match(row):
            key, count = (match["file"], match["reason"].strip()), int(match["n"])
        elif match := _X_ROW.match(row):
            key = (match["file"], f"{match['kind']}: {match['rest'].strip()}")
            count = 1
        else:
            continue
        seen[key] = seen.get(key, 0) + count
    return seen


def summary_problems(log: str) -> list[str]:
    """Fail closed unless the itemised rows account for pytest's own totals."""
    totals = [row for row in log.splitlines() if _TOTALS.match(row)]
    if not totals:
        return ["no pytest totals line found; refusing to pass"]
    announced = {name: int(n) for n, name in _TOTAL_PART.findall(totals[-1])}
    itemised = {"skipped": 0, "xfailed": 0, "xpassed": 0}
    for (_, reason), count in parse_outcomes(log).items():
        kind = "xfailed" if reason.startswith("XFAIL: ") else "skipped"
        itemised["xpassed" if reason.startswith("XPASS: ") else kind] += count
    return [
        f"pytest reported {announced.get(name, 0)} {name} but {count} were itemised; "
        "refusing to pass"
        for name, count in itemised.items()
        if announced.get(name, 0) != count
    ]


def parse_baseline(text: str) -> Outcomes:
    rows: Outcomes = {}
    for row in text.splitlines():
        if row.strip() and not row.startswith("#"):
            parts = [part.strip() for part in row.split(" :: ")]
            if len(parts) != 3 or not parts[2].isdigit() or int(parts[2]) < 1:
                raise ValueError(f"malformed skip baseline row: {row!r}")
            rows[(parts[0], parts[1])] = int(parts[2])
    return rows


def outcome_problems(seen: Mapping, baseline: Mapping) -> list[str]:
    problems = []
    for (file, reason), count in sorted(seen.items()):
        if (file, reason) not in baseline:
            problems.append(f"unreviewed: {file} :: {reason}")
        elif count > baseline[(file, reason)]:
            problems.append(
                f"count {count} exceeds reviewed maximum {baseline[(file, reason)]}: "
                f"{file} :: {reason}"
            )
    return problems


def exclusion_problems(
    *, total: int, offline: int, approved_excluded: int
) -> list[str]:
    if offline <= 0:
        return [
            "collected no offline tests; refusing to treat an empty suite as partitioned"
        ]
    if total - offline != approved_excluded:
        return [
            f"{total - offline} tests are excluded from the offline suite "
            f"but {approved_excluded} are approved"
        ]
    return []


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_approval() -> dict:
    return json.loads(APPROVAL.read_text())


def approval_problems(
    approval: Mapping | None = None,
    *,
    root: Path = ROOT,
    gate_files: Iterable[str] = GATE_FILES,
) -> list[str]:
    approval = load_approval() if approval is None else approval
    problems = [
        f"approval field {field} is a placeholder: {approval.get(field, '')!r}"
        for field in ("approved_by", "reviewed_by")
        if str(approval.get(field, "")).strip().lower() in _PLACEHOLDERS
    ]
    recorded = approval.get("files", {})
    # Driven by the gate set, never by the record's own keys: an emptied record
    # must not be able to vouch for itself.
    for relative in sorted(gate_files):
        if relative not in recorded:
            problems.append(f"gate file has no recorded approval: {relative}")
        elif sha256_file(root / relative) != recorded[relative]:
            problems.append(
                f"gate file changed without a recorded approval: {relative}"
            )
    problems += [
        f"approval records a file outside the gate set: {relative}"
        for relative in sorted(set(recorded) - set(gate_files))
    ]
    return problems


def _collect(command: list[str], *, may_be_empty: bool, **extra: str) -> list[str]:
    # Ambient pytest options can reshape or suppress the collection listing.
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"} | extra
    result = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    allowed = (0, 5) if may_be_empty else (0,)  # 5: nothing matched this selection
    if result.returncode not in allowed:
        raise SystemExit(result.stdout + result.stderr)
    return [row for row in result.stdout.splitlines() if "::" in row]


def _offline_expression() -> str:
    match = re.search(
        r"^offline='([^']+)'$",
        (ROOT / "scripts/ci/test-shard.sh").read_text(),
        flags=re.MULTILINE,
    )
    if not match:
        raise SystemExit("test-shard.sh must declare one offline marker expression")
    return match.group(1)


def _report(title: str, problems: list[str]) -> int:
    for problem in problems:
        print(f"{title}: {problem}", file=sys.stderr)
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("collection")
    sub.add_parser("approval")
    sub.add_parser("hashes")
    sub.add_parser("skips").add_argument("log", type=Path)
    args = parser.parse_args(argv)
    if args.command == "collection":
        shards = {
            shard: _collect(
                ["bash", "scripts/ci/test-shard.sh", shard],
                may_be_empty=True,
                CI_COLLECT_ONLY="1",
            )
            for shard in SHARDS
        }
        collect = [sys.executable, "-m", "pytest", "--collect-only", "-q"]
        collect += ["-p", "no:cacheprovider"]
        full = _collect(
            [*collect, "-m", _offline_expression(), "tests"], may_be_empty=False
        )
        total = _collect([*collect, "tests"], may_be_empty=False)
        counts = ", ".join(f"{name}={len(nodes)}" for name, nodes in shards.items())
        print(f"all tests: {len(total)}; offline suite: {len(full)}; shards: {counts}")
        return _report(
            "collection-integrity",
            exclusion_problems(
                total=len(total),
                offline=len(full),
                approved_excluded=int(load_approval()["excluded_node_count"]),
            )
            + partition_problems(shards, full),
        )
    if args.command == "skips":
        log = args.log.read_text()
        seen = parse_outcomes(log)
        print(
            f"outcome baseline: {sum(seen.values())} skip/xfail/xpass in {args.log.name}"
        )
        return _report(
            "outcome-baseline",
            summary_problems(log)
            + outcome_problems(seen, parse_baseline(SKIP_BASELINE.read_text())),
        )
    if args.command == "hashes":
        print(json.dumps({f: sha256_file(ROOT / f) for f in GATE_FILES}, indent=2))
        return 0
    return _report("gate-approval", approval_problems())


if __name__ == "__main__":
    raise SystemExit(main())
