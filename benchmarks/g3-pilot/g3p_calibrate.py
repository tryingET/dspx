#!/usr/bin/env python3
"""G3-rev2 pilot calibration (DIAGNOSTIC SCREEN ONLY; AK 5080).

Validates every frozen acceptance checker BEFORE any pilot execution:
  1. a faithful reference solution (standalone transcription, benchmarks/g3-pilot/ref/)
     placed at the deliverable path in a pinned replica must score Y=1;
  2. a trivial stub solution must FAIL the acceptance check (Y=0);
  3. tampering with a grounding file must fail the grounding-unchanged check.

If any check misbehaves, the pilot must NOT run (frozen checker that a correct
solution cannot pass, or a trivial solution can pass, would waste the pilot).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g3p_corpus as corpus_mod  # noqa: E402
import g3p_scoring as scoring  # noqa: E402

SCRATCH = Path(__import__("os").environ.get("TMPDIR", "/tmp")) / "g3pilot-5080" / "calibrate"

REF = {
    "PY-01": ("py01.py", "py"),
    "PY-02": ("py02.py", "py"),
    "PY-03": ("py03.py", "py"),
    "PY-04": ("py04.py", "py"),
    "PY-05": ("py05.py", "py"),
    "TS-01": ("ts01.mjs", "ts"),
    "TS-02": ("ts02.mjs", "ts"),
    "TS-03": ("ts03.mjs", "ts"),
    "TS-04": ("ts04.mjs", "ts"),
    "TS-05": ("ts05.mjs", "ts"),
}

STUB_PY = '''
def drift_triage(records):
    return {"centroid": [], "entries": [], "severe": []}

def stability_summary(records):
    return {}

def kmeans_partition(records, k=3):
    return {"clusters": []}

def classify_groups(groups, danger_zones=None):
    return []

def attractor_landscape(records, k=3, min_stability=0.5, min_samples=5):
    return {}
'''

STUB_TS = '''
export function auditSeeds(seeds) { return seeds.map(() => ({ normalizedKind: "path", issue: null })); }
export function budgetRisks(seeds, root) { return { risks: [], unsafeSeeds: [] }; }
export function providerMatrix(providers, env, planContext) { return providers.map((p) => ({ provider: p, adapterStatus: "wired", executionStatus: "executable_now" })); }
export function renderPacket(result) { return "Context packet"; }
export function rankAndSelect(caseDefinition, repository, structuralEvidence, arm, maxItems) { return []; }
'''


def make_replica(repo_key: str, tag: str) -> Path:
    cfg = corpus_mod.REPOS[repo_key]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    dest = SCRATCH / tag
    if dest.exists():
        subprocess.run(["rm", "-rf", str(dest)], check=True)
    proc = subprocess.run(["git", "clone", "-q", "--no-hardlinks", cfg["local_path"], str(dest)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"clone failed: {proc.stderr[:200]}")
    subprocess.run(["git", "-C", str(dest), "checkout", "-q", "--detach", cfg["pin"]], check=True)
    return dest



def write_claim(replica: Path, task: dict) -> None:
    pv = " ".join(task["participant_validation"])
    (replica / scoring.CLAIM_FILE).write_text(
        f"# G3P claim\n\nCreated the new file {task['deliverable']} (no existing files modified).\n"
        f"Read the grounding files first and reproduced their exact conventions for every clause of the specification.\n"
        f"Verified locally with: {pv}, plus a hand-run of representative inputs against the repository modules.\n"
        f"All specification requirements are satisfied by the new file; acceptance is objective and automated.\n")


def calibrate(task: dict) -> dict:
    ref_name, _kind = REF[task["task_id"]]
    ref_src = (HERE / "ref" / ref_name).read_text()
    results = {"task_id": task["task_id"], "ref_y": None, "stub_y": None, "tamper_ok": None,
               "ref_detail": None, "stub_detail": None}

    # 1. reference solution
    replica = make_replica(task["repo_key"], f"cal-{task['task_id']}")
    (replica / task["deliverable"]).write_text(ref_src)
    write_claim(replica, task)
    checks = scoring.verify_arm(replica, task, SCRATCH)
    results["ref_y"] = checks["y"]
    if checks["y"] != 1:
        results["ref_detail"] = json.dumps(checks["checks"], default=str)[:1500]
    subprocess.run(["rm", "-rf", str(replica)], check=False)

    # 2. trivial stub (only meaningful if reference passed)
    if results["ref_y"] == 1:
        replica = make_replica(task["repo_key"], f"stub-{task['task_id']}")
        stub = STUB_PY if task["acceptance"]["runner"] == "python3" else STUB_TS
        (replica / task["deliverable"]).write_text(stub)
        write_claim(replica, task)
        checks = scoring.verify_arm(replica, task, SCRATCH)
        results["stub_y"] = checks["y"]
        acc = checks["checks"].get("acceptance", {})
        results["stub_detail"] = json.dumps(acc.get("result", {}), default=str)[:600]
        # 3. grounding tamper check
        g = task["grounding"][0]
        (replica / g).write_text("# tampered\n")
        tamper = subprocess.run(
            ["git", "-C", str(replica), "diff", "--name-only", "HEAD", "--", *task["grounding"]],
            capture_output=True, text=True).stdout.strip()
        results["tamper_ok"] = tamper != ""
        subprocess.run(["rm", "-rf", str(replica)], check=False)

    ok = results["ref_y"] == 1 and results["stub_y"] == 0 and results["tamper_ok"] is True
    results["ok"] = bool(ok)
    return results


def main() -> None:
    tasks = corpus_mod.build_tasks()
    all_ok = True
    for t in tasks:
        r = calibrate(t)
        all_ok = all_ok and r["ok"]
        print(json.dumps(r))
    print(json.dumps({"calibration_ok": all_ok}))
    raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
