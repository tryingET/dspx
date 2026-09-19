"""Read exact-source CI and protected-environment facts; never authorize release."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from typing import Any

REPO = "tryingET/dspx"
OWNER_ID = 260287438
JOBS = {
    "Quality and contracts",
    "Runtime invariants",
    "Coverage ratchet",
    "Build and package smoke",
    *(
        f"Tests ({shard})"
        for shard in ("core-0", "core-1", "core-2", "core-3", "forge", "slow")
    ),
}


def api(path: str) -> Any:
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/{path}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_run(run: dict[str, Any], jobs: list[dict[str, Any]], commit: str) -> None:
    require(
        run.get("head_sha") == commit and run.get("head_branch") == "main",
        "CI source mismatch",
    )
    require(
        run.get("path") == ".github/workflows/ci.yml" and run.get("event") == "push",
        "wrong CI workflow/event",
    )
    require(
        run.get("head_repository", {}).get("full_name") == REPO, "foreign CI source"
    )
    require(
        run.get("conclusion") == "success"
        and run.get("status") == "completed"
        and run.get("run_attempt") == 1,
        "CI not first-attempt successful",
    )
    names = [row.get("name") for row in jobs]
    require(
        len(names) == len(JOBS) and set(names) == JOBS,
        "CI jobs incomplete or duplicated",
    )
    require(
        all(row.get("conclusion") == "success" for row in jobs), "CI job not successful"
    )


def validate_environment(
    environment: dict[str, Any], branches: dict[str, Any], *, name: str = "pypi-core"
) -> None:
    require(environment.get("name") == name, "wrong publication environment")
    require(
        environment.get("can_admins_bypass") is False,
        "approval bypass must be disabled",
    )
    rules = [
        r
        for r in environment.get("protection_rules", [])
        if r.get("type") == "required_reviewers"
    ]
    require(len(rules) == 1, "required reviewer rule missing")
    reviewers = rules[0].get("reviewers", [])
    require(
        len(reviewers) == 1
        and reviewers[0].get("type") == "User"
        and reviewers[0].get("reviewer", {}).get("id") == OWNER_ID,
        "owner reviewer protection mismatch",
    )
    require(
        environment.get("deployment_branch_policy")
        == {"protected_branches": False, "custom_branch_policies": True},
        "explicit main-only deployment policy required",
    )
    rows = branches.get("branch_policies", [])
    require(
        len(rows) == 1
        and rows[0].get("name") == "main"
        and rows[0].get("type") == "branch",
        "deployment branch is not main-only",
    )


def clearance(commit: str) -> dict[str, Any]:
    require(re.fullmatch(r"[a-f0-9]{40}", commit) is not None, "invalid commit")
    require(api("branches/main").get("protected") is True, "main is not protected")
    comparison = api(f"compare/{commit}...main")
    require(comparison.get("status") in ("ahead", "identical"), "source is not on main")
    parents = api(f"git/commits/{commit}")["parents"]
    require(bool(parents), "release commit has no parent")
    evidence = []
    for sha in (commit, parents[0]["sha"]):
        runs = api(
            f"actions/workflows/ci.yml/runs?head_sha={sha}&event=push&branch=main&per_page=100"
        )
        require(
            runs.get("total_count") == 1 and len(runs.get("workflow_runs", [])) == 1,
            "exactly one CI push observation required for source and parent",
        )
        run = runs["workflow_runs"][0]
        response = api(f"actions/runs/{run['id']}/attempts/1/jobs?per_page=100")
        require(
            response.get("total_count") == len(response.get("jobs", [])),
            "CI jobs truncated",
        )
        validate_run(run, response["jobs"], sha)
        evidence.append({"commit": sha, "run_id": run["id"], "url": run["html_url"]})
    for name in ("pypi-core", "pypi-forge"):
        validate_environment(
            api(f"environments/{name}"),
            api(f"environments/{name}/deployment-branch-policies"),
            name=name,
        )
    return {
        "source": commit,
        "ci": evidence,
        "environment_checked": True,
        "owner_approval": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    print(json.dumps(clearance(args.commit), indent=2))
