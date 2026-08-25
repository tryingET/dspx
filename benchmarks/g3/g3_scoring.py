#!/usr/bin/env python3
"""G3 campaign scoring + verification code (frozen; DSPx task 5059).

Verification is masked by construction: `verify_arm` receives ONLY the task
spec and a worktree path — never the arm label, pair metadata, or forecasts.

Y rules (frozen from docs/v1-proof/g3-protocol-manifest.json):
- intention-to-treat; Y=1 iff the arm's worktree satisfies ALL of:
  (a) claim file present and non-trivial,
  (b) frozen objective acceptance suite passes,
  (c) frozen bounded participant validation passes;
- arm-attributable no-output (crash/timeout/no worktree) is Y=0;
- evidence use / citations never set Y.

Harm monitor (frozen reading, recorded before execution): cell and owner-marginal
rates use the PLANNED pair denominators (28 per owner×family cell, 56 per owner
marginal) with every pending or administratively-missing arm pessimistically
scored Y=0; a stop triggers when static_rate - evidence_rate > 0.05.

This module is a frozen campaign artifact: sha256 recorded in
docs/v1-proof/g3-campaign-state.json before any execution.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

CLAIM_FILE = "G3_CLAIM.md"
MIN_CLAIM_CHARS = 200
VERIFY_TIMEOUT_S = 180
CELL_PLANNED_N = 28
OWNER_PLANNED_N = 56
HARM_MARGIN = 0.05


def _run(cmd: list[str], cwd: Path, timeout: int = VERIFY_TIMEOUT_S) -> dict:
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return {
            "cmd": cmd[:2] + (["..."] if len(cmd) > 4 else cmd[2:]),
            "exit": proc.returncode,
            "stdout_tail": proc.stdout[-400:],
            "stderr_tail": proc.stderr[-400:],
            "duration_s": round(time.monotonic() - started, 1),
        }
    except subprocess.TimeoutExpired:
        return {"cmd": cmd[:2], "exit": -1, "stdout_tail": "", "stderr_tail": "VERIFY TIMEOUT", "duration_s": timeout}


def verify_arm(worktree: Path, task: dict, scratch: Path) -> dict:
    """Masked objective verification of one arm's worktree. Returns check record."""
    checks: dict = {"pair_visible": None, "checks": {}}

    claim_path = worktree / CLAIM_FILE
    claim_text = claim_path.read_text(encoding="utf-8", errors="replace") if claim_path.exists() else ""
    anchors = list(task.get("new_files", [])) + list(task.get("new_symbols", []))
    claim_ok = (
        len(claim_text) >= MIN_CLAIM_CHARS
        and any(a in claim_text for a in anchors)
    )
    checks["checks"]["claim"] = {"ok": bool(claim_ok), "bytes": len(claim_text)}

    verify_dir = scratch / ("verify-" + hashlib.sha256(str(worktree).encode()).hexdigest()[:12])
    if verify_dir.exists():
        shutil.rmtree(verify_dir)
    shutil.copytree(worktree, verify_dir, symlinks=False, ignore=shutil.ignore_patterns(".git"))

    acc = task["acceptance"]
    run_dir = verify_dir / acc.get("run_dir", ".")
    target = run_dir / acc["file_name"]
    target.write_text(acc["file_content"], encoding="utf-8")
    if acc["runner"] == "python3":
        cmd = ["python3", acc["file_name"]] if run_dir == verify_dir else ["python3", target.name]
        result = _run(cmd, run_dir)
    elif acc["runner"] == "node":
        result = _run(["node", target.name], run_dir)
    else:
        result = {"cmd": [acc["runner"]], "exit": -9, "stdout_tail": "", "stderr_tail": "unknown runner", "duration_s": 0}
    acceptance_ok = result["exit"] == 0 and "ACCEPT" in result["stdout_tail"]
    checks["checks"]["acceptance"] = {"ok": bool(acceptance_ok), "result": result}

    pv_cmd = task["participant_validation"]
    pv = _run(pv_cmd, verify_dir)
    pv_ok = pv["exit"] == 0
    checks["checks"]["participant_validation"] = {"ok": bool(pv_ok), "result": pv}

    shutil.rmtree(verify_dir, ignore_errors=True)
    checks["y"] = int(claim_ok and acceptance_ok and pv_ok)
    return checks


def evaluate_harm_stops(state: dict, receipts: list[dict]) -> dict:
    """Frozen harm-stop evaluation. Pessimistic: planned-N denominators, pending=0."""
    done: dict[str, dict] = {}
    for r in receipts:
        done[r["pair_id"]] = r
    cells = {}
    for pair in state["allocations"]:
        key = (pair["owner_group"], pair["base_model_family"])
        cells.setdefault(key, {"static": 0, "evidence": 0, "n_done": 0, "n": CELL_PLANNED_N})
        if pair["pair_id"] in done:
            rec = done[pair["pair_id"]]
            cells[key]["n_done"] += 1
            for arm in ("static", "evidence"):
                cells[key][arm] += rec["arms"][arm]["y"]

    evaluation = {"cells": [], "marginals": [], "triggered": [], "policy": {
        "denominator": "planned per-cell N (28) / owner marginal N (56)",
        "pending_or_missing": "counted as Y=0 (pessimistic)",
        "margin": HARM_MARGIN}}
    for (owner, family), c in sorted(cells.items()):
        s_rate, e_rate = c["static"] / c["n"], c["evidence"] / c["n"]
        entry = {"cell": f"{owner}/{family}", **c,
                 "static_rate": round(s_rate, 4), "evidence_rate": round(e_rate, 4),
                 "gap_static_minus_evidence": round(s_rate - e_rate, 4)}
        evaluation["cells"].append(entry)
        if s_rate - e_rate > HARM_MARGIN:
            evaluation["triggered"].append({"kind": "cell", **entry})

    for owner in sorted({o for o, _ in cells}):
        agg = {"static": 0, "evidence": 0, "n": OWNER_PLANNED_N, "n_done": 0}
        for (o, _), c in cells.items():
            if o == owner:
                agg["static"] += c["static"]; agg["evidence"] += c["evidence"]; agg["n_done"] += c["n_done"]
        s_rate, e_rate = agg["static"] / agg["n"], agg["evidence"] / agg["n"]
        entry = {"owner_group": owner, **agg,
                 "static_rate": round(s_rate, 4), "evidence_rate": round(e_rate, 4),
                 "gap_static_minus_evidence": round(s_rate - e_rate, 4)}
        evaluation["marginals"].append(entry)
        if s_rate - e_rate > HARM_MARGIN:
            evaluation["triggered"].append({"kind": "marginal", **entry})
    return evaluation
