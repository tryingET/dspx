"""Local custody manifests and actual pytest membership/outcome accounting.

No imports of installed packages until pytest explicitly loads this as a plugin
inside the prepared fixture plane. A reviewed manifest is an input, not authority.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from datetime import datetime, timezone

from verify_full_closure import (
    strict_json as strict_json,
    digest as digest,
    file_hash as file_hash,
    inventory as inventory,
    assert_inventory as assert_inventory,
    validate_closure as validate_closure,
    read_review as read_review,
)

OFFLINE = "not live and not network and not model and not gpu and not postgres"
RESIDUAL = "live or network or model or gpu or postgres"


def lease_time(lease) -> datetime:
    if not isinstance(lease, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)", lease
    ):
        raise ValueError("lease must be RFC3339 with timezone")
    if lease[-1] != "Z" and (int(lease[-5:-3]) > 23 or int(lease[-2:]) > 59):
        raise ValueError("invalid RFC3339 UTC offset")
    return datetime.fromisoformat(lease.replace("Z", "+00:00"))


def claimed_id(
    payload, repo: Path, claimant: str, expected: int, *, now: datetime | None = None
) -> int:
    if not isinstance(payload, list) or not all(
        isinstance(row, dict) for row in payload
    ):
        raise ValueError("claimed task payload must be a list of objects")
    seen = set()
    for row in payload:
        if (
            type(row.get("id")) is not int
            or row["id"] <= 0
            or row["id"] in seen
            or not isinstance(row.get("repo"), str)
            or not Path(row["repo"]).is_absolute()
            or row.get("status") != "claimed"
            or not isinstance(row.get("claimed_by"), str)
            or not row["claimed_by"]
        ):
            raise ValueError("malformed/duplicate claimed task row")
        seen.add(row["id"])
        lease_time(row.get("lease_expires_at"))
    rows = [row for row in payload if row["repo"] == str(repo)]
    if len(rows) != 1:
        raise ValueError("expected exactly one repo claim (duplicates reject)")
    row = rows[0]
    if type(row.get("id")) is not int or row["id"] != expected:
        raise ValueError("observed claim ID differs from admitted task")
    if (
        row.get("claimed_by") != claimant
        or not claimant
        or row.get("status") != "claimed"
    ):
        raise ValueError("claimant/status mismatch")
    expiry = lease_time(row["lease_expires_at"])
    if expiry <= (now or datetime.now(timezone.utc)):
        raise ValueError("claim lease expired")
    return row["id"]


def validate_membership(
    offline: dict, residual: dict, expected_skips: dict, collection: dict
):
    expected_nodes = collection["nodes"]
    if not expected_nodes or len(expected_nodes) != len(set(expected_nodes)):
        raise ValueError("independent reviewed collection baseline required")

    def collectors(report):
        skipped = {}
        for row in report["collectors"]:
            if row["outcome"] not in {"passed", "skipped"}:
                raise ValueError("collector error")
            if row["outcome"] == "skipped":
                if row["nodeid"] in skipped or not isinstance(row["reason"], str):
                    raise ValueError("duplicate/malformed collector skip")
                skipped[row["nodeid"]] = digest(row["reason"])
        if skipped != collection["skips"]:
            raise ValueError("unknown/new/changed collection skip")
        return skipped

    collectors(offline)
    collectors(residual)

    def lane(report):
        if report.get("exit") != 0 or report.get("errors"):
            raise ValueError("pytest failure/collection error")
        all_nodes, selected = report["all"], report["selected"]
        if len(all_nodes) != len(set(all_nodes)) or len(selected) != len(set(selected)):
            raise ValueError("duplicate node IDs")
        if not set(selected) <= set(all_nodes):
            raise ValueError("selected node absent from collection")
        outcomes = report["outcomes"]
        if set(outcomes) != set(selected):
            raise ValueError("missing/extra outcome node IDs")
        for node, phases in outcomes.items():
            by_phase = {phase["when"]: phase for phase in phases}
            if (
                len(by_phase) != len(phases)
                or not {"setup", "teardown"} <= by_phase.keys()
            ):
                raise ValueError("duplicate/missing test phase")
            if (
                any(p["outcome"] == "failed" for p in phases)
                or by_phase["teardown"]["outcome"] != "passed"
            ):
                raise ValueError("failed teardown/test")
            skipped = [p["reason"] for p in phases if p["outcome"] == "skipped"]
            if skipped:
                if skipped != [expected_skips.get(node)]:
                    raise ValueError(f"newly induced or changed skip: {node}")
            elif by_phase.get("call", {}).get("outcome") != "passed":
                raise ValueError("no successful call")
        return set(all_nodes), set(selected)

    all_a, a = lane(offline)
    all_b, b = lane(residual)
    if all_a != set(expected_nodes) or all_a != all_b or a & b or a | b != all_a:
        raise ValueError("pytest partition is not a complete disjoint union")
    observed_skips = {
        node
        for report in (offline, residual)
        for node, phases in report["outcomes"].items()
        if any(p["outcome"] == "skipped" for p in phases)
    }
    if observed_skips != set(expected_skips):
        raise ValueError("reviewed skip inventory changed")
    return {
        "collected": len(all_a),
        "offline": len(a),
        "residual": len(b),
        "skips": len(observed_skips),
        "collector_skips": len(collection["skips"]),
    }


_report: dict[str, Any] = {
    "all": [],
    "selected": [],
    "outcomes": {},
    "errors": [],
    "collectors": [],
}


def authority_audit(event, args):
    if event == "open":
        path = args[0]
        if isinstance(path, (str, bytes)) and any(
            part in os.fsdecode(path)
            for part in ("society.v2.db", "/agent-kernel/", "/agent-kernel-")
        ):
            raise PermissionError(
                "verify-full fixture plane: unexpected native authority access"
            )
    if event == "subprocess.Popen":
        executable, argv, _cwd, env = args
        values = [os.fsdecode(executable), *(str(v) for v in argv)]
        if any(
            "agent-kernel" in v or Path(v).name in {"ak", "ak.sh", "ak-bin"}
            for v in values
        ):
            # The dedicated real missing-executable proof uses an EMPTY PATH and
            # bare ak; allow OS ENOENT, never a fake response or executable.
            environment = os.environ if env is None else env
            if values[0] == "ak" and environment.get("PATH") == "":
                return
            raise PermissionError(
                "verify-full fixture plane: unexpected native authority invocation"
            )


def pytest_collection_modifyitems(session, config, items):
    _report["all"] = [item.nodeid for item in items]


setattr(pytest_collection_modifyitems, "pytest_impl", {"tryfirst": True})


def pytest_collection_finish(session):
    _report["selected"] = [item.nodeid for item in session.items]


def pytest_collectreport(report):
    _report["collectors"].append(
        {
            "nodeid": report.nodeid,
            "outcome": report.outcome,
            "reason": str(report.longrepr) if report.skipped or report.failed else None,
        }
    )
    if report.failed:
        _report["errors"].append(str(report.longrepr))


def pytest_runtest_logreport(report):
    _report["outcomes"].setdefault(report.nodeid, []).append(
        {
            "when": report.when,
            "outcome": report.outcome,
            "reason": str(report.longrepr) if report.skipped else None,
        }
    )


def pytest_xdist_node_collection_finished(node, ids):
    if _report["selected"] and _report["selected"] != ids:
        _report["errors"].append("worker collection mismatch")
    _report["selected"] = list(ids)


setattr(pytest_xdist_node_collection_finished, "pytest_impl", {"optionalhook": True})


def pytest_sessionfinish(session, exitstatus):
    directory = Path(os.environ["DSPX_VERIFY_FULL_REPORTS"])
    directory.mkdir(parents=True, exist_ok=True)
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    _report["exit"] = int(exitstatus)
    (directory / f"{worker}.json").write_text(
        json.dumps(_report, sort_keys=True) + "\n"
    )


def merge_reports(directory: Path):
    reports = [json.loads(p.read_text()) for p in sorted(directory.glob("*.json"))]
    master = json.loads((directory / "master.json").read_text())
    collections = [r["all"] for r in reports if r["all"]]
    if not collections or any(c != collections[0] for c in collections):
        raise ValueError("absent/inconsistent worker collection")
    if any(r["exit"] != 0 or r["errors"] for r in reports):
        raise ValueError("worker/collection failure")
    collector_reports = [report["collectors"] for report in reports if report["all"]]
    if any(rows != collector_reports[0] for rows in collector_reports):
        raise ValueError("inconsistent worker collector outcomes")
    master["all"] = collections[0]
    master["collectors"] = collector_reports[0]
    return master


if os.environ.get("DSPX_VERIFY_FULL_FIXTURE") == "1":
    sys.addaudithook(authority_audit)
