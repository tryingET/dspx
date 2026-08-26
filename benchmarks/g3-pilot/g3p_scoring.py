#!/usr/bin/env python3
"""G3-rev2 pilot scoring + masked verification (DIAGNOSTIC SCREEN ONLY; AK 5080).

Verification is masked by construction: `verify_arm` receives ONLY the task
spec, the replica worktree path, and a scratch dir — never the arm label,
pair metadata, or advice. Y rules (mirrors the frozen campaign shape):

- intention-to-treat; Y=1 iff the arm's worktree satisfies ALL of:
  (a) claim file present, non-trivial, mentions the new file/symbol,
  (b) grounding files are UNMODIFIED vs the pinned revision (reading, not
      rewriting — the acceptance derives expectations from the real code),
  (c) frozen objective acceptance suite passes (exit 0 + ACCEPT marker),
  (d) frozen bounded participant validation passes;
- arm-attributable no-output (crash/timeout/no worktree change) is Y=0.

NOT gate evidence. NOT protocol authority. Diagnostic pilot only.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

CLAIM_FILE = "G3P_CLAIM.md"
MIN_CLAIM_CHARS = 200
VERIFY_TIMEOUT_S = 300


def _run(cmd: list[str], cwd: Path, timeout: int = VERIFY_TIMEOUT_S) -> dict:
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return {
            "cmd": cmd[:2] + (["..."] if len(cmd) > 4 else cmd[2:]),
            "exit": proc.returncode,
            "stdout_tail": proc.stdout[-500:],
            "stderr_tail": proc.stderr[-500:],
            "duration_s": round(time.monotonic() - started, 1),
        }
    except subprocess.TimeoutExpired:
        return {"cmd": cmd[:2], "exit": -1, "stdout_tail": "", "stderr_tail": "VERIFY TIMEOUT",
                "duration_s": timeout}


def verify_arm(replica: Path, task: dict, scratch: Path) -> dict:
    """Masked objective verification of one arm's worktree (task + tree only)."""
    checks: dict = {"checks": {}}

    # (a) claim
    claim_path = replica / CLAIM_FILE
    claim_text = claim_path.read_text(encoding="utf-8", errors="replace") if claim_path.exists() else ""
    anchors = list(task.get("new_files", [])) + list(task.get("new_symbols", []))
    claim_ok = len(claim_text) >= MIN_CLAIM_CHARS and any(a in claim_text for a in anchors)
    checks["checks"]["claim"] = {"ok": bool(claim_ok), "bytes": len(claim_text)}

    # (b) grounding integrity vs pin (replica HEAD == pin; diff must be empty)
    diff = subprocess.run(
        ["git", "-C", str(replica), "diff", "--name-only", "HEAD", "--", *task["grounding"]],
        capture_output=True, text=True).stdout.strip()
    grounding_ok = diff == "" and all((replica / g).exists() for g in task["grounding"])
    checks["checks"]["grounding_unchanged"] = {"ok": bool(grounding_ok), "modified": diff.splitlines()}

    # (c) frozen acceptance suite (in a verify copy, not the arm's tree)
    verify_dir = scratch / ("verify-" + hashlib.sha256(str(replica).encode()).hexdigest()[:12])
    if verify_dir.exists():
        shutil.rmtree(verify_dir)
    shutil.copytree(replica, verify_dir, symlinks=False, ignore=shutil.ignore_patterns(".git"))
    acc = task["acceptance"]
    run_dir = verify_dir / acc.get("run_dir", ".")
    target = run_dir / acc["file_name"]
    target.write_text(acc["file_content"], encoding="utf-8")
    if acc["runner"] == "python3":
        cmd = ["python3", acc["file_name"], *acc["checker_input"]]
    elif acc["runner"] == "node":
        cmd = ["node", acc["file_name"], *acc["checker_input"]]
    else:
        cmd = [acc["runner"]]
    result = _run(cmd, run_dir)
    acceptance_ok = result["exit"] == 0 and "ACCEPT" in result["stdout_tail"]
    checks["checks"]["acceptance"] = {"ok": bool(acceptance_ok), "result": result}
    shutil.rmtree(verify_dir, ignore_errors=True)

    # (d) participant validation
    pv = _run(task["participant_validation"], replica)
    checks["checks"]["participant_validation"] = {"ok": pv["exit"] == 0, "result": pv}

    checks["y"] = int(claim_ok and grounding_ok and acceptance_ok and pv["exit"] == 0)
    return checks
