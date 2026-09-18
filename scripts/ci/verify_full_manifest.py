#!/usr/bin/env python3
# ---
# summary: "Generates a dspx-full-local-custody-v3 manifest for the optional hermetic verify-full run from the live workstation state."
# read_when:
#   - "Provisioning or re-provisioning the optional hermetic local full run (AK-5754)."
# ---
"""Manifest generator for the optional hermetic local full run.

This records what IS on the workstation; it does not review it. A manifest and hash
produced here by the party that also runs the gate are self-attested custody, not
the independent review the v3 schema was designed around. The run is an optional
deep-assurance instrument, not a release gate (docs/adr/20260918-ci-evidence-clearance.md).

Run with the same closed interpreter posture as the gate:
    /usr/bin/python3 -I -S -B scripts/ci/verify_full_manifest.py --image sha256:... --out <file>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_full_closure import (  # noqa: E402
    PYTHON_MINOR,
    PYTHON_PHYSICAL,
    file_hash,
    inventory,
    validate_closure,
)
from verify_full_git import read_git, source_index, source_inventory, source_names  # noqa: E402
from verify_full_isolation import H, R, fixture_environment  # noqa: E402
from verify_full_membership import digest, merge_reports, validate_membership  # noqa: E402
from verify_full_processes import Processes  # noqa: E402

PREK_CACHE = H / ".cache/prek"


def closure_rows() -> list[dict]:
    rows = [
        {"source": str(R / ".venv"), "target": str(R / ".venv"), "role": "venv"},
        {
            "source": str(PYTHON_PHYSICAL),
            "target": str(PYTHON_PHYSICAL),
            "role": "python",
            "aliases": [str(PYTHON_MINOR)],
        },
        {
            # The PATH entry is a symlink on the host; bind the concrete binary there.
            "source": str((H / ".local/bin/prek").resolve(strict=True)),
            "target": str(H / ".local/bin/prek"),
            "role": "tool",
        },
        {
            "source": str(H / "ai-society/core/agent-scripts"),
            "target": str(H / "ai-society/core/agent-scripts"),
            "role": "docs",
        },
    ]
    for group in ("hooks", "repos", "cache"):
        for child in sorted((PREK_CACHE / group).iterdir()):
            rows.append({"source": str(child), "target": str(child), "role": "hooks"})
    for row in rows:
        row["members"] = inventory(Path(row["source"]))
    return rows


def executable_pth(rows: list[dict]) -> dict[str, str]:
    found = {}
    for row in rows:
        for name, member in row["members"].items():
            if name.endswith(".pth") and "sha256" in member:
                text = (Path(row["source"]) / name).read_text()
                if any(
                    line.startswith(("import ", "import\t"))
                    for line in text.splitlines()
                ):
                    found[str(Path(row["target"]) / name)] = member["sha256"]
    return found


def baseline_from_reports(offline_dir: Path, residual_dir: Path) -> dict:
    """Observed node/skip baseline from a discovery run in the gate's container posture.

    Observed, not independently reviewed: it records what that run did. It is checked
    here with the gate's own membership validation so an inconsistent observation
    (failures, collection errors, an incomplete partition) cannot become a baseline.
    """
    offline, residual = merge_reports(offline_dir), merge_reports(residual_dir)
    skips = {
        node: next(p["reason"] for p in phases if p["outcome"] == "skipped")
        for report in (offline, residual)
        for node, phases in report["outcomes"].items()
        if any(p["outcome"] == "skipped" for p in phases)
    }
    collector_skips = {
        row["nodeid"]: row["reason"]
        for row in offline["collectors"]
        if row["outcome"] == "skipped"
    }
    baseline = {
        "nodes": offline["all"],
        "collector_skips": collector_skips,
        "skips": skips,
    }
    validate_membership(
        offline,
        residual,
        skips,
        {
            "nodes": offline["all"],
            "skips": {n: digest(r) for n, r in collector_skips.items()},
        },
    )
    return baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", required=True, help="existing local sha256: image ID"
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--logs", required=True, type=Path, help="fresh private log root"
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="JSON {nodes, collector_skips, skips} observed by a discovery run",
    )
    parser.add_argument(
        "--from-reports",
        nargs=2,
        type=Path,
        metavar=("OFFLINE_REPORTS", "RESIDUAL_REPORTS"),
        help="derive the baseline from a discovery run's membership reports",
    )
    args = parser.parse_args(argv)
    run = Processes(args.logs).run
    rows = closure_rows()
    if args.from_reports:
        baseline = baseline_from_reports(*args.from_reports)
    elif args.baseline:
        baseline = json.loads(args.baseline.read_text())
    else:
        baseline = {"nodes": ["unobserved"], "collector_skips": {}, "skips": {}}
    review = {
        "schema": "dspx-full-local-custody-v3",
        "head": read_git(run, "head", ["rev-parse", "HEAD"], R).strip(),
        "source": source_inventory(R, source_names(run, R)),
        "index": source_index(R),
        "closure": rows,
        "pth_imports": executable_pth(rows),
        "image": args.image,
        "skips": baseline["skips"],
        "fixtures": {"AK5456_REVIEW_PROBES": None, "host_interpreter": None},
        "environment": fixture_environment(),
        "collection": {
            "nodes": baseline["nodes"],
            "skips": {n: digest(r) for n, r in baseline["collector_skips"].items()},
        },
    }
    validate_closure(review, R)
    args.out.write_text(json.dumps(review, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "manifest": str(args.out),
                "sha256": file_hash(args.out),
                "head": review["head"],
                "source_files": len(review["source"]),
                "closure_rows": [
                    (r["role"], r["target"], len(r["members"])) for r in rows
                ],
                "executable_pth": review["pth_imports"],
                "nodes": len(baseline["nodes"]),
                "skips": len(baseline["skips"]),
                "custody": "self-attested by the generating party; not independent review",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
