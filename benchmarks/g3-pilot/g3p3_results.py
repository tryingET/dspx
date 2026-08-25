#!/usr/bin/env python3
"""G3 v3 pilot closeout: build docs/v1-proof/g3pilot-v3-results.json (dspx.g3pilot/1).

Reads the frozen state + receipts, computes per-class per-family per-arm Y
rates and split tasks, records the discrimination verdict, explicit non-claims,
and all frozen digests. DIAGNOSTIC ONLY — not Gate G3, no gate claims.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g3p3_corpus as corpus_mod  # noqa: E402

REPO = HERE.parents[1]
PROOF = REPO / "docs" / "v1-proof"
STATE_PATH = PROOF / "g3pilot-v3-state.json"
RECEIPTS_PATH = PROOF / "g3pilot-v3-receipts.jsonl"
RESULTS_PATH = PROOF / "g3pilot-v3-results.json"

INTERFERENCE_CHECK = {
    "directive": "operator interference check (duplicate-session writes under benchmarks/g3p3/ "
                 "between ~21:04-21:29Z, killed ~21:29Z)",
    "performed_at": "2026-08-25T21:33:30+00:00",
    "method": "every execution-path artifact re-hashed and compared against the digests frozen "
              "in g3pilot-v3-state.json BEFORE any execution result was counted",
    "scope": [
        "benchmarks/g3-pilot/g3p3_scoring.py (sha256)",
        "benchmarks/g3-pilot/g3p3_support.py (sha256)",
        "benchmarks/g3-pilot/g3p3_runner.py (sha256)",
        "benchmarks/g3-pilot/g3p3_calibrate.py (sha256)",
        "corpus rebuilt from disk g3p3_corpus.py (content digest f4659290...)",
        "all 10 guidance bundles ($TMPDIR/g3pilot-v3-5081/guidance/)",
        "all 3 advise-request bundles + materials ($TMPDIR/g3pilot-v3-5081/requests/)",
        "all ref3 reference files",
    ],
    "verdict": "CLEAN - no drift. The duplicate session wrote only into the separate "
               "benchmarks/g3p3/ directory (no hyphen); the frozen execution path lives in "
               "benchmarks/g3-pilot/ and every digest matched. No execution was discarded; "
               "no re-run required.",
    "cleanup": "duplicate-session directory benchmarks/g3p3/ and the literal-name "
               "benchmarks/g3-pilot/$TMPDIR/ directory were removed at closeout (not in the "
               "frozen artifact set)",
}

OPERATOR_DIRECTIVES_APPLIED = [
    "reshape directive (pre-execution; docs/v1-proof/g3pilot-v3-DIRECTIVE-reshape.md, marked "
    "APPLIED on the file): 10 tasks, 5 per family, static+evidence once per task in its "
    "assigned family = 20 executions; corpus table reviewed and approved by the operator "
    "(GO) before execution",
    "interference-check + cleanup directive: applied (see interference_check; post-run "
    "re-verification CLEAN); duplicate-session dir benchmarks/g3p3/ and the literal "
    "benchmarks/g3-pilot/$TMPDIR/ dir removed at closeout",
]

NON_CLAIMS = [
    "This is a DIAGNOSTIC PILOT, not Gate G3; it makes no gate, protocol, or promotion claims.",
    "With one execution per arm per task (n=1 per cell), any single-task split is a signal to "
    "investigate, not a measured effect size; no statistical significance is claimed.",
    "Conformance is measured against frozen checkers and the engineering-core 1.0.0 candidate-4 "
    "wheel / pinned repo toolchains; it is not a general capability claim about either model family.",
    "The evidence arm differs from the static arm only by guidance presence (rendered wheel "
    "content and, for classes A/C, a product-validated advisor response); no claim is made that "
    "any specific guidance element caused an outcome.",
    "Class B tasks received the compiled advise-request materials in the spec for both arms and "
    "no advisor model call (a call would fabricate the deliverable); recorded per receipt.",
    "Acceptance checkers were frozen and calibrated before execution (reference Y=1, stub Y=0, "
    "tamper detection) and were never relaxed after seeing results.",
    "Anti-contamination relied on an explicit spec constraint (no filesystem roaming for "
    "pre-installed tools); no independent sandbox verification of executor behavior is claimed.",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    state = json.loads(STATE_PATH.read_text())
    receipts = [json.loads(l) for l in RECEIPTS_PATH.read_text().splitlines() if l.strip()]
    corpus = state["corpus"]
    tasks = {p["task"]["task_id"]: p for p in corpus["pairs"]}

    # per-class per-family per-arm Y rates
    cells: dict = {}
    for r in receipts:
        key = (r["task_class"], r["family"])
        cell = cells.setdefault(key, {"tasks": 0, "static_y": 0, "evidence_y": 0})
        cell["tasks"] += 1
        cell["static_y"] += r["arms"].get("static", {}).get("y", 0)
        cell["evidence_y"] += r["arms"].get("evidence", {}).get("y", 0)
    rates = {}
    for (cls, fam), cell in sorted(cells.items()):
        n = cell["tasks"]
        rates[f"{cls}/{fam}"] = {
            "tasks": n,
            "static_y_rate": cell["static_y"] / n,
            "evidence_y_rate": cell["evidence_y"] / n,
            "static_y": cell["static_y"], "evidence_y": cell["evidence_y"],
        }

    # overall + per-class rollups
    def rollup(pred) -> dict:
        rs = [r for r in receipts if pred(r)]
        n = len(rs)
        return {
            "tasks": n,
            "static_y_rate": (sum(r["arms"].get("static", {}).get("y", 0) for r in rs) / n) if n else None,
            "evidence_y_rate": (sum(r["arms"].get("evidence", {}).get("y", 0) for r in rs) / n) if n else None,
        }
    overall = rollup(lambda r: True)
    per_class = {cls: rollup(lambda r, c=cls: r["task_class"] == c) for cls in ("A", "B", "C")}
    per_family = {fam: rollup(lambda r, f=fam: r["family"] == f) for fam in corpus_mod.FAMILIES}

    splits = []
    for r in receipts:
        s = r["arms"].get("static", {}).get("y")
        e = r["arms"].get("evidence", {}).get("y")
        if s != e:
            splits.append({
                "task_id": r["task_id"], "task_class": r["task_class"],
                "family": r["family"], "model_identity": r["model_identity"],
                "static_y": s, "evidence_y": e,
                "direction": "evidence-only" if e and not s else "static-only" if s and not e else "?",
                "static_problems": (r["arms"]["static"]["checks"].get("acceptance", {}).get("problems") or [])[:5],
                "evidence_problems": (r["arms"]["evidence"]["checks"].get("acceptance", {}).get("problems") or [])[:5],
            })

    separation = bool(splits)
    verdict_lines = []
    if separation:
        for split in splits:
            verdict_lines.append(
                f"{split['task_id']} ({split['task_class']}/{split['family']}, "
                f"{split['model_identity']}): static Y={split['static_y']} vs "
                f"evidence Y={split['evidence_y']} ({split['direction']})")
        ev_only = [s for s in splits if s["direction"] == "evidence-only"]
        verdict = (
            f"SEPARATION OBSERVED: {len(splits)} of {len(receipts)} tasks split between arms "
            f"({len(ev_only)} evidence-only). " + "; ".join(verdict_lines)
        )
    else:
        st = overall.get("static_y_rate")
        ev = overall.get("evidence_y_rate")
        if st is not None and ev is not None and st == 1.0 and ev == 1.0:
            verdict = ("NULL CEILING: all tasks passed in both arms — the corpus failed to "
                       "challenge the models (same shape as v2); next step is harder/narrower "
                       "convention space, not more executions.")
        elif st == ev:
            verdict = ("NO SEPARATION: arms tied on every task "
                       f"(overall static={st}, evidence={ev}).")
        else:
            verdict = f"NO TASK-LEVEL SPLIT but aggregate rates differ (static={st}, evidence={ev})."

    results = {
        "schema": "dspx.g3pilot/1",
        "diagnostic_label": state["diagnostic_label"],
        "recorded_at": state.get("budget", {}).get("started_at"),
        "completed_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(timespec="seconds"),
        "operator_intent_quote": state["operator_intent_quote"],
        "operator_reshape_quote": state["operator_reshape_quote"],
        "design": {
            "shape": "10 tasks x 1 assigned family x 2 arms = 20 executions (operator reshape)",
            "classes": {"A": 3, "B": 3, "C": 4},
            "families": corpus["design"]["families"],
            "arms": {
                "static": "identical task spec, no engineering-core content",
                "evidence": ("spec + rendered candidate-4 wheel guidance (README, shipped skill, "
                             "lanes/addenda, disciplines, templates, catalog) and, for classes A/C, "
                             "a product-validated advisor response"),
                "advisor_identity": state["models"]["advisor_identity"],
                "advisor_fallback": state["models"]["advisor_fallback"],
                "advisor_scope": state["models"]["advisor_scope"],
                "differ_only_by": "guidance presence",
            },
            "budget": {
                "planned_max_executions": state["budgets"]["max_executions"],
                "actual_executions": state["budget"]["executions"],
                "planned_wall_s": state["budgets"]["pilot_wall_s"],
                "stopped_reason": state["budget"]["stopped_reason"],
            },
            "candidate": state["candidate"],
            "calibration": state["calibration"],
        },
        "corpus_table": [
            {
                "task_id": tid,
                "task_class": p["task"]["task_class"],
                "family": p["family"],
                "model_identity": p["model_identity"],
                "repo_identity": p["repo_identity"],
                "repo_pin": p["repo_pin"],
                "title": p["task"]["title"],
                "convention_rationale": p["task"]["convention_rationale"],
                "acceptance_kind": p["task"]["acceptance"]["kind"],
            }
            for tid, p in sorted(tasks.items())
        ],
        "results": {
            "overall": overall,
            "per_class": per_class,
            "per_family": per_family,
            "per_class_family": rates,
            "splits": splits,
        },
        "discrimination_verdict": {
            "separation_observed": separation,
            "n_split_tasks": len(splits),
            "verdict": verdict,
        },
        "non_claims": NON_CLAIMS,
        "interference_check": INTERFERENCE_CHECK,
        "operator_directives_applied": OPERATOR_DIRECTIVES_APPLIED,
        "artifacts": {
            "state": str(STATE_PATH.relative_to(REPO)),
            "receipts": str(RECEIPTS_PATH.relative_to(REPO)),
            "receipts_sha256": sha256_file(RECEIPTS_PATH),
            "state_sha256": sha256_file(STATE_PATH),
            "frozen_digests": state["frozen_artifacts"],
            "machinery": [
                "benchmarks/g3-pilot/g3p3_corpus.py",
                "benchmarks/g3-pilot/g3p3_scoring.py",
                "benchmarks/g3-pilot/g3p3_support.py",
                "benchmarks/g3-pilot/g3p3_calibrate.py",
                "benchmarks/g3-pilot/g3p3_runner.py",
                "benchmarks/g3-pilot/g3p3_results.py",
                "benchmarks/g3-pilot/drive_family_v3.sh",
                "benchmarks/g3-pilot/ref3/",
            ],
        },
        "progress_final": state["progress"],
        "blockers": state.get("blockers", {}),
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "written": str(RESULTS_PATH.relative_to(REPO)),
        "receipts": len(receipts),
        "overall": overall,
        "per_class": {k: v for k, v in per_class.items()},
        "splits": len(splits),
        "verdict": verdict[:300],
    }, indent=1))


if __name__ == "__main__":
    main()
