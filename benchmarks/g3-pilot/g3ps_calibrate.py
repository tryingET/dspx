"""G3 SUCCESSOR calibration (AK 5095; decision 138).

Pre-freeze calibration per decision 138 implementation plan:
- compile frozen requests for B/H-class instances (pristine fixtures);
- reference solutions -> every template's checker must yield Y=1 (satisfiable);
- stubs -> every template's checker must yield Y=0 (not trivially passable);
- tamper detection (A-style + C-style) on a reference solution;
- record verify durations (VERIFY_TIMEOUT_S budget check).
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import g3ps_corpus as corpus
import g3ps_scoring as scoring
import g3ps_support as support

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ROOT = Path(__import__("os").environ["TMPDIR"]) / "g3ps-5095"
REQ_DIR = ROOT / "requests"
WORK = ROOT / "calibrate"

TOOLS = {
    "wheel_bin": str(ROOT / "venv/bin/engineering-core"),
    "wheel_py": str(ROOT / "venv/bin/python"),
    "wheel_site": str(ROOT / "venv/lib/python3.13/site-packages"),
    "biome": "/home/tryinget/ai-society/softwareco/owned/pi-extensions/packages/pi-context-packer/node_modules/.bin/biome",
    "dspx_ruff": "/home/tryinget/ai-society/softwareco/owned/dspx/.venv/bin/ruff",
    "dspx_python": "/home/tryinget/ai-society/softwareco/owned/dspx/.venv/bin/python",
    "requests_dir": str(REQ_DIR),
}

FOCUS_FILES = {
    "TA1": ["pyproject.toml", "policy/stack-lane.json", "docs/tech-stack.local.md"],
    "TA2": ["pyproject.toml", "policy/engineering-lane.json", "docs/engineering.local.md"],
    "TA3": ["pyproject.toml", "policy/stack-lane.json"],
    "TB1": ["pyproject.toml", "policy/stack-lane.json"],
    "TB2": ["package.json", "src/index.js"],
    "TB3": ["pyproject.toml", "policy/engineering-lane.json"],
    "TC1": ["package.json", "biome.jsonc"],
    "TC2": ["Justfile", "package.json"],
    "TC3": ["pyproject.toml", "Justfile"],
    "TC4": ["Justfile"],
    "TH1": ["pyproject.toml", "policy/stack-lane.json", "Justfile"],
    "TH2": ["pyproject.toml", "policy/engineering-lane.json"],
}


def compile_frozen_requests() -> dict:
    REQ_DIR.mkdir(parents=True, exist_ok=True)
    digests = {}
    for template in sorted(corpus.TEMPLATES):
        if corpus.TEMPLATES[template]["cls"] not in ("B", "H"):
            continue
        for inst in ("a", "b", "c"):
            task = support.task_for(f"{template}-{inst}")
            task["focus_files"] = FOCUS_FILES.get(template, [])
            work = WORK / f"req-{template}-{inst}"
            replica = support.make_replica(task, work)
            out = REQ_DIR / f"{task['instance_id']}-request.json"
            try:
                request = support.compile_request(replica, task, out, TOOLS)
                digests[task["instance_id"]] = {
                    "request_sha256": request["request_sha256"],
                    "plan_requested": sorted(
                        {s["id"] for s in (request.get("plan") or {}).get("selections", [])
                         if isinstance(s, dict) and s.get("requested") is True and s.get("id")},
                    ),
                    "n_evidence": len(request.get("evidence", [])),
                }
            finally:
                shutil.rmtree(work, ignore_errors=True)
    return digests


def calibrate_reference() -> dict:
    results = {}
    for template in sorted(corpus.TEMPLATES):
        task = support.task_for(f"{template}-a")
        work = WORK / f"ref-{template}-a"
        replica = support.make_replica(task, work)
        try:
            support.install_reference(task, replica, TOOLS)
            t0 = time.monotonic()
            verdict = scoring.verify_arm(replica, task, ROOT, TOOLS)
            results[template] = {
                "y": verdict["y"],
                "problems": verdict["checks"]["acceptance"]["problems"][:6],
                "grounding": verdict["checks"]["grounding"]["problems"][:3],
                "verify_s": verdict["verify_duration_s"],
            }
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return results


def calibrate_stub() -> dict:
    results = {}
    for template in sorted(corpus.TEMPLATES):
        task = support.task_for(f"{template}-a")
        work = WORK / f"stub-{template}-a"
        replica = support.make_replica(task, work)
        try:
            support.install_stub(task, replica)
            verdict = scoring.verify_arm(replica, task, ROOT, TOOLS)
            results[template] = {
                "y": verdict["y"],
                "rejecting_problems": verdict["checks"]["acceptance"]["problems"][:3],
            }
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return results


def calibrate_tamper() -> dict:
    """Tamper with an accepted reference: A-style (wrong ref) and C-style
    (drop the tests) must be detected."""
    out = {}
    task = support.task_for("TA1-a")
    work = WORK / "tamper-A"
    replica = support.make_replica(task, work)
    try:
        support.install_reference(task, replica, TOOLS)
        policy_p = replica / "policy/engineering-lane.json"
        policy = json.loads(policy_p.read_text())
        policy["engineering_core"]["ref"] = "v0.9.0"  # tamper: stale pin
        policy_p.write_text(json.dumps(policy, indent=2))
        verdict = scoring.verify_arm(replica, task, ROOT, TOOLS)
        out["TA1_wrong_ref"] = {"y": verdict["y"],
                                 "detected": verdict["y"] == 0,
                                 "problem": verdict["checks"]["acceptance"]["problems"][:2]}
    finally:
        shutil.rmtree(work, ignore_errors=True)
    task = support.task_for("TC3-a")
    work = WORK / "tamper-C"
    replica = support.make_replica(task, work)
    try:
        support.install_reference(task, replica, TOOLS)
        (replica / task["acceptance"]["test_path"]).unlink()  # tamper: no tests
        verdict = scoring.verify_arm(replica, task, ROOT, TOOLS)
        out["TC3_no_tests"] = {"y": verdict["y"], "detected": verdict["y"] == 0,
                               "problem": verdict["checks"]["acceptance"]["problems"][:2]}
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def main(stage: str) -> None:
    if stage == "requests":
        print(json.dumps(compile_frozen_requests(), indent=1, sort_keys=True))
        return
    WORK.mkdir(parents=True, exist_ok=True)
    if stage == "reference":
        print(json.dumps(calibrate_reference(), indent=1, sort_keys=True))
    elif stage == "stub":
        print(json.dumps(calibrate_stub(), indent=1, sort_keys=True))
    elif stage == "tamper":
        print(json.dumps(calibrate_tamper(), indent=1, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "reference")
