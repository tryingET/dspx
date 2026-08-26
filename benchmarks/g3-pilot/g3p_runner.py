#!/usr/bin/env python3
"""G3-rev2 feasibility pilot runner (DIAGNOSTIC SCREEN ONLY; DSPx AK task 5080).

20 pairs (10 harder tasks x 2 model families), 2 arms each (static vs
evidence), interleaved, max 40 executions / 6 hours, per-pair receipts.

This is NOT Gate G3, NOT protocol evidence, and claims no gate authority.
It answers ONE diagnostic question: on harder multi-file tasks grounded in
real softwareco/owned repos, do the static and evidence arms separate AT ALL?

Usage:
  g3p_runner.py freeze
  g3p_runner.py advise --task PY-01
  g3p_runner.py run --pair PL-PY-01-fam-gpt [--deadline <iso8601>]
  g3p_runner.py status
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g3p_corpus as corpus_mod  # noqa: E402
import g3p_scoring as scoring  # noqa: E402

REPO = HERE.parents[1]
PROOF = REPO / "docs" / "v1-proof"
STATE_PATH = PROOF / "g3pilot-state.json"
RECEIPTS_PATH = PROOF / "g3pilot-receipts.jsonl"
SCRATCH = Path(os.environ.get("TMPDIR", "/tmp")) / "g3pilot-5080"
RUNS = SCRATCH / "runs"
WHEEL_PY = SCRATCH / "venv" / "bin" / "python"
ECORE_SITE = SCRATCH / "venv" / "lib" / "python3.13" / "site-packages"

EXECUTOR_TIMEOUT_S = 1500
ADVISOR_TIMEOUT_S = 420
PILOT_BUDGET_S = 6 * 3600
MAX_EXECUTIONS = 40

ADVISOR_IDENTITY = "openai-codex/gpt-5.6-terra"
ADVISOR_NOTE = (
    "uniform across ALL pairs (campaign preference); glm-5.3 fallback unused "
    "because the preferred identity was live at pilot start (probe recorded)"
)

PROMPT_TEMPLATE = """You are executing a bounded work task in a disposable replica of {repo_identity} at pinned revision {pin}.

REPO: {repo_identity} (working tree only; this is a scratch replica)
TASK ({task_id}): {title}

SPECIFICATION (satisfy exactly; verification is objective and automated):
{spec}

DELIVERABLES:
1. The changes/files required by the specification.
2. A claim file at path `G3P_CLAIM.md` in the repository root stating:
   (a) which files you changed or created,
   (b) how each specification clause is satisfied,
   (c) how you verified it (commands you ran and their results).
   The claim must mention the new file path(s) or symbol(s) you added.

CONSTRAINTS:
- Work only inside this repository working tree. No pushes, no remotes.
- No network installs (no npm install / pip install / uv sync); use only what is present.
- Do not modify anything under .git/.
- Do not modify or delete any existing repository content; your changes must be NEW files only.

Complete the task now."""

ADVICE_SECTION = """

## OWNER EVIDENCE-ADVICE (advisory only, from the engineering-core advice surface; evaluate critically)
```json
{advice_json}
```
"""

ADVISOR_WRAPPER = """You are the provider behind the engineering-core bounded advisor surface.
Below is a frozen engineering-advice-request-v1 JSON for one specific bounded work task (the task is in plan.goal and plan.task_context).

Emit ONLY a JSON object conforming to engineering-advice-response-v1, bound to this request:
- top-level keys EXACTLY: schema, request_sha256, provenance, status, summary, recommendations, critiques, patch_proposals
- schema value: "engineering-advice-response-v1"
- request_sha256 value: "{request_sha256}"
- provenance exactly: {{"provider":"openai-codex","model":"{model}","model_version":"as-configured","adapter":"pi-headless","adapter_version":"pi-cli","prompt_id":"engineering-core-bounded-advisor","prompt_version":"1"}}
- status: "advice" when the captured evidence plus your engineering judgment supports at least one actionable recommendation for the task; "abstain" or "unknown" otherwise (then recommendations and patch_proposals must be empty arrays)
- summary: bounded text
- recommendations: JSON array (max 3). Each element is an object with keys EXACTLY id, catalog_ids, recommendation, confidence, unknowns, counterevidence, falsification, citations, competes_with. Types: id string; catalog_ids array of strings drawn only from the request's allowed_catalog_ids; recommendation string; confidence a number in [0,1] = your calibrated probability that a competent executor following the recommendation completes the task's objective verification (Y=1); unknowns array of strings; counterevidence ARRAY OF STRINGS (never a bare string; empty array allowed); falsification array of strings; citations array of objects {{evidence_id, path, start, end}} referencing request evidence ids with valid spans; competes_with array of other recommendation ids
- critiques: JSON array of objects with keys exactly recommendation_id, critique, severity, falsification (strings, severity one of low/medium/high)
- patch_proposals: [] (no patch proposals in this pilot)
Follow the request's embedded prompt instructions exactly; cite only request-bound evidence.
Output the JSON object and NOTHING else. No markdown fences.

REQUEST:
{request_json}"""


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- freeze

def cmd_freeze() -> None:
    if STATE_PATH.exists():
        raise SystemExit("state already frozen; refusing to refreeze")
    corpus = corpus_mod.build_corpus()
    tasks = {p["task"]["task_id"]: p["task"] for p in corpus["pairs"]}
    state = {
        "schema": "dspx.g3pilot-state/1",
        "diagnostic_label": (
            "G3 rev2 feasibility pilot - DIAGNOSTIC SCREEN ONLY; not Gate G3, "
            "not protocol evidence, no gate claims"
        ),
        "frozen_at": now(),
        "operator_intent_quote": "10 tasks to see if there is any difference at all",
        "repos": {k: {"identity": v["repo_identity"], "pin": v["pin"]} for k, v in corpus_mod.REPOS.items()},
        "models": {
            "executors": corpus_mod.FAMILIES,
            "advisor_identity": ADVISOR_IDENTITY,
            "advisor_note": ADVISOR_NOTE,
        },
        "candidate": {
            "repo": "/home/tryinget/ai-society/core/engineering-core",
            "branch": "proof/v1-candidate-4",
            "commit": "bc43bb972121bf6c02792bf318cb14aa974b7e17",
            "wheel_sha256": "94b6a2bd5d34ef82dce0f7f40e209e4d55b00c478ce8e49ecd9cd1bc5edb54f8",
            "built_from": "scratch detached worktree under $TMPDIR; digest verified",
        },
        "budgets": {
            "max_executions": MAX_EXECUTIONS,
            "pilot_wall_s": PILOT_BUDGET_S,
            "executor_timeout_s": EXECUTOR_TIMEOUT_S,
            "advisor_timeout_s": ADVISOR_TIMEOUT_S,
            "verify_timeout_s": scoring.VERIFY_TIMEOUT_S,
        },
        "frozen_artifacts": {
            "corpus_digest": corpus_mod.digest(corpus),
            "scoring_sha256": sha256_file(HERE / "g3p_scoring.py"),
            "runner_sha256": sha256_file(HERE / "g3p_runner.py"),
            "prompt_template_sha256": sha256_text(PROMPT_TEMPLATE),
            "advisor_wrapper_sha256": sha256_text(ADVISOR_WRAPPER),
            "advice_section_sha256": sha256_text(ADVICE_SECTION),
        },
        "corpus": corpus,
        "execution_order": corpus["execution_order"],
        "progress": {pid: {"status": "pending", "updated_at": None} for pid in corpus["execution_order"]},
        "blockers": {},
        "advice": {},
        "execution_log": [],
        "budget": {"started_at": None, "executions": 0, "stopped_reason": None},
    }
    PROOF.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "frozen": True,
        "state": str(STATE_PATH.relative_to(REPO)),
        "pairs": len(corpus["execution_order"]),
        "tasks": len(tasks),
        "corpus_digest": state["frozen_artifacts"]["corpus_digest"],
    }, indent=1))


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text())


@contextlib.contextmanager
def state_lock():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    lock_path = SCRATCH / "state.lock"
    with open(lock_path, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def update_state(mutate) -> dict:
    """Lock-guarded read-modify-write of the shared pilot state."""
    with state_lock():
        state = load_state()
        mutate(state)
        save_state(state)
        return state


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


def find_pair(state: dict, pair_id: str) -> dict:
    for p in state["corpus"]["pairs"]:
        if p["pair_id"] == pair_id:
            return p
    raise SystemExit(f"unknown pair {pair_id}")


# ---------------------------------------------------------------- replicas

def make_replica(pair: dict, tag: str) -> Path:
    cfg = corpus_mod.REPOS[pair["repo_key"]]
    RUNS.mkdir(parents=True, exist_ok=True)
    dest = RUNS / f"{pair['pair_id']}-{tag}"
    if dest.exists():
        subprocess.run(["rm", "-rf", str(dest)], check=True)
    proc = subprocess.run(["git", "clone", "-q", "--no-hardlinks", cfg["local_path"], str(dest)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"clone failed: {proc.stderr[:200]}")
    subprocess.run(["git", "-C", str(dest), "checkout", "-q", "--detach", cfg["pin"]], check=True)
    return dest


# ---------------------------------------------------------------- advice

BUILD_REQUEST_CODE = r"""
import json, sys, hashlib
sys.path.insert(0, "{here}")
from engineering_core.catalog import load_catalog
from engineering_core.engineering_plan import compile_plan
from engineering_core.advisor import build_request, validate_response
from pathlib import Path
repo = Path(sys.argv[1])
task = json.loads(sys.argv[2])
catalog = load_catalog()
ids = set(catalog.ids("lanes")) | set(catalog.ids("disciplines"))
grounding = {{p: hashlib.sha256((repo / p).read_bytes()).hexdigest() for p in task["grounding"] if (repo / p).exists()}}
try:
    plan = compile_plan(repo, catalog)
except Exception:
    plan = {{"schema": "engineering-plan-v1", "evidence": []}}
plan = dict(plan)
plan["goal"] = task["title"]
plan["task_context"] = {{
    "task_id": task["task_id"],
    "title": task["title"],
    "specification": task["spec"],
    "new_symbols": task.get("new_symbols", []),
    "new_files": task.get("new_files", []),
    "acceptance_runner": task["acceptance"]["runner"],
}}
plan["evidence"] = [{{"path": p, "sha256": s}} for p, s in grounding.items()]
request = build_request(repo, plan, ids, focus_files=grounding)
Path(sys.argv[3]).write_text(json.dumps(request))
""".format(here=str(ECORE_SITE))

VALIDATE_CODE = r"""
import json, sys
sys.path.insert(0, "{here}")
from engineering_core.advisor import validate_response
request = json.loads(open(sys.argv[1]).read())
response = json.loads(sys.argv[2])
validate_response(request, response)
print("VALID")
""".format(here=str(ECORE_SITE))


def advice_for_pair(pair: dict, state: dict, scratch: Path) -> dict:
    task = pair["task"]
    replica = make_replica(pair, "advice")
    req_path = scratch / f"request-{pair['pair_id']}.json"
    proc = subprocess.run([str(WHEEL_PY), "-c", BUILD_REQUEST_CODE, str(replica), json.dumps(task), str(req_path)],
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"build_request failed: {proc.stderr[-500:]}")
    request = json.loads(req_path.read_text())
    wrapper = ADVISOR_WRAPPER.format(model=ADVISOR_IDENTITY,
                                     request_sha256=request["request_sha256"],
                                     request_json=json.dumps(request, indent=1))

    def call_advisor() -> dict:
        adv = subprocess.run(["pi", "-p", "--no-session", "--model", ADVISOR_IDENTITY, wrapper],
                             capture_output=True, text=True, timeout=ADVISOR_TIMEOUT_S)
        out = adv.stdout.strip()
        candidates = [out]
        candidates += re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", out, re.S)
        candidates += re.findall(r"\{.*\}", out, re.S)
        for text in candidates:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                continue
        raise RuntimeError(f"advisor produced no JSON: {out[-300:]} {adv.stderr[-200:]}")

    last_error = None
    parsed = None
    for attempt in (1, 2):
        try:
            parsed = call_advisor()
            v = subprocess.run([str(WHEEL_PY), "-c", VALIDATE_CODE, str(req_path), json.dumps(parsed)],
                               capture_output=True, text=True, timeout=120)
            if v.returncode != 0 or "VALID" not in v.stdout:
                raise RuntimeError(f"validate_response failed: {v.stderr[-400:]}")
            break
        except RuntimeError as exc:
            last_error = exc
            parsed = None
    subprocess.run(["rm", "-rf", str(replica)], check=False)
    if parsed is None:
        return {"request_sha256": request.get("request_sha256"), "response": None,
                "advice_failure": str(last_error)[:500]}
    return {"request_sha256": request.get("request_sha256"), "response": parsed}


# ---------------------------------------------------------------- execution

def looks_provider_blocked(run: dict) -> bool:
    if run["exit"] == 0:
        return False
    blob = (run.get("stderr_tail", "") + " " + run.get("stdout_tail", "")).lower()
    return any(sig in blob for sig in ("403", "429", "quota", "credit", "insufficient", "rate limit", "exceeded your"))


def execute_arm(pair: dict, arm: str, advice_response: dict | None, scratch: Path) -> dict:
    replica = make_replica(pair, arm)
    prompt = PROMPT_TEMPLATE.format(
        repo_identity=pair["repo_identity"], pin=pair["repo_pin"],
        task_id=pair["task"]["task_id"], title=pair["task"]["title"], spec=pair["task"]["spec"])
    if arm == "evidence":
        prompt += ADVICE_SECTION.format(advice_json=json.dumps(advice_response, indent=1))
    started = time.monotonic()
    try:
        proc = subprocess.run(["pi", "-p", "--no-session", "--model", pair["model_identity"], prompt],
                              cwd=replica, capture_output=True, text=True, timeout=EXECUTOR_TIMEOUT_S)
        run = {"exit": proc.returncode, "stdout_tail": proc.stdout[-1200:], "stderr_tail": proc.stderr[-300:]}
    except subprocess.TimeoutExpired:
        run = {"exit": -1, "stdout_tail": "", "stderr_tail": "EXECUTOR TIMEOUT"}
    duration = round(time.monotonic() - started, 1)

    changed = subprocess.run(["git", "-C", str(replica), "status", "--porcelain"],
                             capture_output=True, text=True).stdout.splitlines()
    if not changed:
        checks = {"checks": {
            "claim": {"ok": False, "bytes": 0},
            "grounding_unchanged": {"ok": True, "modified": []},
            "acceptance": {"ok": False, "result": {"exit": -1, "stderr_tail": "no worktree changes (arm-attributable no-output)"}},
            "participant_validation": {"ok": False, "result": {"exit": -1, "stderr_tail": "not run: no output"}},
        }}
        checks["y"] = 0
        outcome = {"y": 0, "checks": checks["checks"], "run": run,
                   "duration_s": duration, "changed_files": []}
    else:
        checks = scoring.verify_arm(replica, pair["task"], scratch)
        outcome = {"y": checks["y"], "checks": checks["checks"], "run": run,
                   "duration_s": duration, "changed_files": changed[:50]}
    subprocess.run(["rm", "-rf", str(replica)], check=False)
    return outcome


# ---------------------------------------------------------------- commands

def cmd_advise(task_id: str) -> None:
    state = load_state()
    pair_like = next(p for p in state["corpus"]["pairs"] if p["task"]["task_id"] == task_id)
    advice = advice_for_pair(pair_like, state, SCRATCH)
    if advice["response"] is None:
        print(json.dumps({"task_id": task_id, "ok": False, "error": advice.get("advice_failure")}, indent=1))
        return
    def store(st):
        st["advice"][task_id] = {
            "request_sha256": advice["request_sha256"],
            "response": advice["response"],
            "advisor_identity": ADVISOR_IDENTITY,
            "recorded_at": now(),
        }
    update_state(store)
    print(json.dumps({"task_id": task_id, "ok": True,
                      "status": advice["response"]["status"],
                      "n_recommendations": len(advice["response"].get("recommendations", []))}, indent=1))


def budget_deadline(state: dict) -> float | None:
    started = state["budget"]["started_at"]
    if not started:
        return None
    t0 = dt.datetime.fromisoformat(started).timestamp()
    return t0 + PILOT_BUDGET_S


def cmd_run(pair_id: str, deadline_iso: str | None) -> None:
    state = load_state()
    pair = find_pair(state, pair_id)
    family = pair["family"]

    def blocked_check(st):
        return st.get("blockers", {}).get(family)

    if state["progress"][pair_id]["status"] == "completed":
        print(f"{pair_id} already completed")
        return
    if blocked_check(state) and blocked_check(state).get("status") != "resolved":
        def mark(st):
            st["progress"][pair_id].update({"status": "blocked_family", "updated_at": now()})
        update_state(mark)
        print(f"{pair_id}: family {family} blocked; skipped")
        return

    def budget_gate(st):
        if st["budget"]["started_at"] is None:
            st["budget"]["started_at"] = now()
        if st["budget"]["executions"] >= MAX_EXECUTIONS:
            st["budget"]["stopped_reason"] = st["budget"]["stopped_reason"] or "max_executions"
            return "max_executions"
        return None

    gate = update_state(budget_gate)
    if gate == "max_executions":
        print("budget: max executions reached; stop")
        return
    deadline = dt.datetime.fromisoformat(deadline_iso).timestamp() if deadline_iso else budget_deadline(load_state())
    if deadline and time.time() > deadline:
        def mark_deadline(st):
            st["budget"]["stopped_reason"] = st["budget"]["stopped_reason"] or "wall_budget"
        update_state(mark_deadline)
        print("budget: wall clock exceeded; stop")
        return

    task_id = pair["task"]["task_id"]
    print(f"[{now()}] {pair_id}: advice surface ({ADVISOR_IDENTITY})")
    advice = advice_for_pair(pair, state, SCRATCH)
    if advice["response"] is None:
        def mark_advice(st):
            st["progress"][pair_id].update({"status": "advice_blocked", "updated_at": now(),
                                            "advice_failure": advice.get("advice_failure")})
        update_state(mark_advice)
        print(f"{pair_id}: advice surface failed twice; pair administratively blocked (no arm executed); resumable")
        return
    advice_summary = {
        "status": advice["response"]["status"],
        "n_recommendations": len(advice["response"].get("recommendations", [])),
        "request_sha256": advice["request_sha256"],
        "advisor_identity": ADVISOR_IDENTITY,
    }

    arms: dict = {}
    blocked_family = False
    for arm in pair["arm_order"]:
        if deadline and time.time() > deadline:
            def mark_walls(st):
                st["budget"]["stopped_reason"] = st["budget"]["stopped_reason"] or "wall_budget"
            update_state(mark_walls)
            print("budget: wall clock exceeded mid-pair; stopping (pair resumable)")
            return
        if load_state()["budget"]["executions"] >= MAX_EXECUTIONS:
            def mark_max(st):
                st["budget"]["stopped_reason"] = st["budget"]["stopped_reason"] or "max_executions"
            update_state(mark_max)
            print("budget: max executions reached mid-pair; stopping")
            return
        print(f"[{now()}] {pair_id}: executing {arm} arm ({pair['model_identity']})")
        arms[arm] = execute_arm(pair, arm,
                                advice["response"] if arm == "evidence" else None, SCRATCH)

        def log_exec(st, arm=arm, res=arms[arm]):
            st["budget"]["executions"] += 1
            st["execution_log"].append({"pair_id": pair_id, "arm": arm, "at": now(),
                                        "y": res["y"], "duration_s": res["duration_s"]})
        update_state(log_exec)
        print(f"[{now()}] {pair_id}: {arm} y={arms[arm]['y']} ({arms[arm]['duration_s']}s)")
        if looks_provider_blocked(arms[arm]["run"]):
            def mark_block(st):
                st["blockers"][family] = {
                    "model": pair["model_identity"],
                    "status": "infrastructure_blocked",
                    "evidence": f"provider 403/limit signature at {now()} on {pair_id} {arm} arm",
                    "disposition": "remaining pairs of this family marked blocked_family; other family continues; resumable",
                }
            update_state(mark_block)
            blocked_family = True
            break

    if len(arms) == 2:
        receipt = {
            "schema": "dspx.g3pilot-receipt/1",
            "pair_id": pair_id, "task_id": task_id,
            "family": family, "model_identity": pair["model_identity"],
            "repo_identity": pair["repo_identity"], "repo_pin": pair["repo_pin"],
            "arm_order": pair["arm_order"],
            "advice": advice_summary,
            "arms": arms,
            "verification_basis": {
                "scoring_sha256": state["frozen_artifacts"]["scoring_sha256"],
                "masked": "verify_arm received only task + worktree",
                "checks": {arm: sorted(arms[arm]["checks"]) for arm in arms},
            },
            "recorded_at": now(),
        }
        with RECEIPTS_PATH.open("a") as fh:
            fh.write(json.dumps(receipt, sort_keys=True) + "\n")

        def mark_done(st):
            st["progress"][pair_id].update({"status": "completed", "updated_at": now()})
        update_state(mark_done)
        print(f"[{now()}] {pair_id}: completed "
              f"(static y={arms.get('static', {}).get('y')}, evidence y={arms.get('evidence', {}).get('y')})")
    else:
        def mark_partial(st):
            st["progress"][pair_id].update({"status": ("blocked_family_partial" if blocked_family else "partial_")
                                            + "_".join(arms), "updated_at": now()})
        update_state(mark_partial)
        print(f"{pair_id}: partial ({sorted(arms)}); family_blocked={blocked_family}; resumable")


def cmd_status() -> None:
    state = load_state()
    counts: dict[str, int] = {}
    for pid, p in state["progress"].items():
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    receipts = []
    if RECEIPTS_PATH.exists():
        receipts = [json.loads(l) for l in RECEIPTS_PATH.read_text().splitlines() if l.strip()]
    per_family: dict = {}
    for r in receipts:
        f = per_family.setdefault(r["family"], {"pairs": 0, "static": 0, "evidence": 0})
        f["pairs"] += 1
        f["static"] += r["arms"].get("static", {}).get("y", 0)
        f["evidence"] += r["arms"].get("evidence", {}).get("y", 0)
    print(json.dumps({
        "pairs_total": len(state["progress"]), "progress": counts,
        "receipts": len(receipts),
        "executions": state["budget"]["executions"],
        "budget_started_at": state["budget"]["started_at"],
        "stopped_reason": state["budget"]["stopped_reason"],
        "blockers": {k: v["status"] for k, v in state.get("blockers", {}).items()},
        "per_family": per_family,
        "next_pending_in_order": next((pid for pid in state["execution_order"]
                                       if state["progress"][pid]["status"] == "pending"), None),
    }, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    adv = sub.add_parser("advise"); adv.add_argument("--task", required=True)
    run_p = sub.add_parser("run"); run_p.add_argument("--pair", required=True)
    run_p.add_argument("--deadline", default=None)
    sub.add_parser("status")
    args = ap.parse_args()
    if args.cmd == "freeze":
        cmd_freeze()
    elif args.cmd == "advise":
        cmd_advise(args.task)
    elif args.cmd == "run":
        cmd_run(args.pair, args.deadline)
    else:
        cmd_status()


if __name__ == "__main__":
    main()
