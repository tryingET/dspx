#!/usr/bin/env python3
"""G3 v3 pilot calibration (DIAGNOSTIC ONLY; DSPx AK task 5081).

Validates every frozen acceptance checker BEFORE any pilot execution:
  1. REFERENCE solution -> Y=1 (each checker is satisfiable);
  2. plausible STUB -> Y=0 (no checker is trivially passable);
  3. grounding TAMPER -> grounding check fails (protection is real).
Also enforces per-task verify <= 180s and prints the check detail so a frozen
checker that passes/fails for the WRONG reason is caught before execution.
If any check misbehaves, the pilot must NOT run.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import g3p3_corpus as corpus_mod  # noqa: E402
import g3p3_scoring as scoring  # noqa: E402
import g3p3_support as support  # noqa: E402

CAL = support.V3ROOT / "calibrate"


def run_case(name: str, task: dict, mutate) -> dict:
    dest = CAL / f"{task['task_id']}-{name}"
    replica = support.make_replica(task, dest)
    mutate(replica)
    support.write_claim(replica, task, name)
    result = scoring.verify_arm(replica, task, CAL, support.TOOLS)
    detail = result["checks"]
    acc = detail["acceptance"]
    print(json.dumps({
        "task": task["task_id"], "case": name, "y": result["y"],
        "claim_ok": detail["claim"]["ok"], "grounding_ok": detail["grounding"]["ok"],
        "acceptance_ok": acc["ok"],
        "problems": (acc["problems"] or detail["grounding"]["problems"] or [])[:4],
        "verify_s": result["verify_duration_s"],
    }))
    shutil.rmtree(dest, ignore_errors=True)
    return result


def main() -> None:
    corpus = corpus_mod.build_corpus()
    tasks = {p["task"]["task_id"]: p["task"] for p in corpus["pairs"]}
    failures: list[str] = []
    for tid in sorted(tasks):
        task = tasks[tid]
        ref = run_case("ref", task, lambda r, t=task: support.install_reference(t, r))
        if ref["y"] != 1:
            failures.append(f"{tid}: reference did not score Y=1")
        stub = run_case("stub", task, lambda r, t=task: support.install_stub(t, r))
        if stub["y"] != 0:
            failures.append(f"{tid}: stub scored Y=1 (checker too weak)")
    # grounding tamper probes: protected content modified after correct deliverables
    for tid, tamper in (
        ("A1", lambda r: (r / "README.md").write_text("tampered\n")),
        ("C3", lambda r: (r / "packages/dspx-core/src/dspx/coordinates/metrics.py"
                          ).write_text("# tampered\n")),
    ):
        task = tasks[tid]
        result = run_case("tamper", task, lambda r, t=task, tp=tamper: (
            support.install_reference(t, r), tp(r)))
        if result["checks"]["grounding"]["ok"]:
            failures.append(f"{tid}: tamper not detected by grounding check")
    print(json.dumps({"calibration": "PASS" if not failures else "FAIL",
                      "failures": failures}, indent=1))
    raise SystemExit(0 if not failures else 1)


if __name__ == "__main__":
    main()
