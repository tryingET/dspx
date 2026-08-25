#!/usr/bin/env python3
"""G3 campaign runner (DSPx task 5059; AK decision 132).

Lifecycle per pair (frozen order):
  1. disposable replica from the population-manifest pin (scratch clone)
  2. advice surface: engineering-core candidate-4 wheel (verified digest)
     build_request -> advisor model -> validate_response -> FORECAST recorded
     BEFORE any arm execution (hidden from verification)
  3. static arm and evidence arm executed back-to-back in frozen arm_order,
     each in a fresh replica, identical prompt except the declared advice slot
  4. masked verification (g3_scoring.verify_arm) -> per-pair receipt
  5. frozen harm-stop evaluation appended after every pair

Usage:
  g3_runner.py freeze
  g3_runner.py run --pair P-holdingco-fam-gpt-01 [--allow-blocked-family]
  g3_runner.py status
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g3_corpus as corpus_mod  # noqa: E402
import g3_scoring as scoring  # noqa: E402

REPO = HERE.parents[1]
PROOF = REPO / "docs" / "v1-proof"
STATE_PATH = PROOF / "g3-campaign-state.json"
RECEIPTS_PATH = PROOF / "g3-campaign-receipts.jsonl"
FORECASTS_PATH = PROOF / "g3-campaign-forecasts.json"
HARM_LOG_PATH = PROOF / "g3-harm-monitor.jsonl"
SCRATCH = Path(__import__("os").environ.get("TMPDIR", "/tmp")) / "g3-campaign-5059-runs"

WHEEL = SCRATCH.parent / "g3-campaign-5059" / "venv" / "bin" / "python"
MANIFEST = PROOF / "g3-protocol-manifest.json"

EXECUTOR_TIMEOUT_S = 1500
ADVISOR_TIMEOUT_S = 420

ADVISOR_IDENTITY = "openai-codex/gpt-5.6-terra"
ADVISOR_RATIONALE = (
    "manifest freezes executor families only; advice-surface provider is a "
    "campaign-freeze decision: the single consistently available frozen-family "
    "identity is used identically for every pair in every cell (uniform "
    "treatment slot); recorded as a declared limitation"
)

FORECAST_RULE = (
    "forecast = max(recommendations[].confidence) of the validated "
    "engineering-advice-response-v1 when status==advice; abstain/unknown or "
    "advice-surface failure => forecast missing (excluded from calibration "
    "metrics; pair remains ITT for superiority)"
)

HARM_READING = (
    "cell/marginal rates over planned denominators (28 per ownerxfamily cell, "
    "56 per owner marginal); pending or administratively missing arms are "
    "pessimistically Y=0; stop when static_rate - evidence_rate > 0.05; "
    "aggregate cannot waive a cell stop"
)

PROMPT_TEMPLATE = """You are executing a bounded work task in a disposable replica of {repo_identity} at pinned revision {pin}.

REPO: {repo_identity} (working tree only; this is a scratch replica)
TASK ({task_id}): {title}

SPECIFICATION (satisfy exactly; verification is objective and automated):
{spec}

DELIVERABLES:
1. The changes/files required by the specification.
2. A claim file at path `G3_CLAIM.md` in the repository root stating:
   (a) which files you changed or created,
   (b) how each specification clause is satisfied,
   (c) how you verified it (commands you ran and their results).
   The claim must mention the new file path(s) or symbol(s) you added.

CONSTRAINTS:
- Work only inside this repository working tree. No pushes, no remotes.
- No network installs (no npm install / pip install / uv sync); use only what is present.
- Do not modify anything under .git/.
- Do not delete or rewrite existing repository content beyond what the task requires.

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
- patch_proposals: [] (no patch proposals in this campaign)
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
        raise SystemExit("state already frozen; refusing to refreeze (protocol revisions are prospective only)")
    manifest = json.loads(MANIFEST.read_text())
    corpus = corpus_mod.build_corpus()
    corpus_mod.assert_initially_failing(corpus)

    order = ([p["pair_id"] for p in sorted(corpus["pairs"], key=lambda x: x["pair_id"]) if p["stage"] == "dev"]
             + [p["pair_id"] for p in sorted(corpus["pairs"], key=lambda x: x["pair_id"]) if p["stage"] == "confirm"])

    state = {
        "schema": "dspx.g3-campaign-state/1",
        "frozen_at": now(),
        "campaign_seed": corpus_mod.CAMPAIGN_SEED,
        "protocol": {
            "manifest": "docs/v1-proof/g3-protocol-manifest.json",
            "manifest_sha256": sha256_file(MANIFEST),
            "validated_digest": "ea05ba3cd118e7ebb2cb37a2df8736dd0c0ebfd9784eb8edb5c86a3542ff5fa0",
            "template_digest": manifest["template_digest"],
            "protocol_stage": manifest["protocol_stage"],
            "decision": "ak://decision/132",
            "task": "ak://task/5059",
        },
        "candidate": {
            "repo": "/home/tryinget/ai-society/core/engineering-core",
            "branch": "proof/v1-candidate-4",
            "commit": "bc43bb972121bf6c02792bf318cb14aa974b7e17",
            "wheel_sha256": "94b6a2bd5d34ef82dce0f7f40e209e4d55b00c478ce8e49ecd9cd1bc5edb54f8",
            "built_from": "scratch detached worktree under $TMPDIR; digest verified",
        },
        "models": {
            "executor_families": corpus_mod.FAMILIES,
            "advisor_identity": ADVISOR_IDENTITY,
            "advisor_rationale": ADVISOR_RATIONALE,
        },
        "forecasts": {
            "rule": FORECAST_RULE,
            "emitted_before_execution": True,
            "storage": "docs/v1-proof/g3-campaign-forecasts.json (separate from receipts; verification never reads it)",
        },
        "frozen_artifacts": {
            "corpus_digest": corpus_mod.digest(corpus),
            "scoring_sha256": sha256_file(HERE / "g3_scoring.py"),
            "runner_sha256": sha256_file(HERE / "g3_runner.py"),
            "prompt_template_sha256": sha256_text(PROMPT_TEMPLATE),
            "advisor_wrapper_sha256": sha256_text(ADVISOR_WRAPPER),
            "advice_section_sha256": sha256_text(ADVICE_SECTION),
        },
        "budgets": {"executor_timeout_s": EXECUTOR_TIMEOUT_S, "advisor_timeout_s": ADVISOR_TIMEOUT_S,
                    "verify_timeout_s": scoring.VERIFY_TIMEOUT_S},
        "harm_policy": {"reading": HARM_READING, "aggregate_cannot_waive_cell_stop": True,
                        "no_optional_stopping": True},
        "arm_neutrality": {
            "prompt": "identical frozen template for both arms; the declared advice slot is the only difference",
            "verification": "g3_scoring.verify_arm receives only task + worktree (no arm, pair, or forecast)",
            "itt": "arm-attributable no-output is Y=0; administrative missingness pessimistically bounded",
        },
        "blockers": {
            "fam-grok": {
                "model": "xai/grok-4.6",
                "status": "infrastructure_blocked",
                "evidence": "pi headless call returns 403 out-of-credits (verified twice 2026-08-25)",
                "disposition": "cells containing fam-grok are not executed while blocked; recorded, resumable; no substitution (frozen identity; substitution requires fresh accepted protocol decision)",
            }
        },
        "allocations": [
            {"pair_id": p["pair_id"], "owner_group": p["owner_group"], "base_model_family": p["base_model_family"],
             "repo_key": p["repo_key"], "stage": p["stage"], "task_id": p["task"]["task_id"]}
            for p in corpus["pairs"]
        ],
        "execution_order": order,
        "progress": {pid: {"status": "pending", "updated_at": None} for pid in order},
        "harm_stop": None,
        "corpus": corpus,
    }
    PROOF.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    FORECASTS_PATH.write_text("{}\n")
    print(json.dumps({
        "frozen": True, "state": str(STATE_PATH.relative_to(REPO)),
        "pairs": len(order), "corpus_digest": state["frozen_artifacts"]["corpus_digest"],
        "scoring_sha256": state["frozen_artifacts"]["scoring_sha256"],
    }, indent=1))


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text())


def find_pair(state: dict, pair_id: str) -> dict:
    for p in state["corpus"]["pairs"]:
        if p["pair_id"] == pair_id:
            return p
    raise SystemExit(f"unknown pair {pair_id}")


# ---------------------------------------------------------------- replicas

def make_replica(pair: dict, tag: str) -> Path:
    cfg = corpus_mod.REPOS[pair["repo_key"]]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    dest = SCRATCH / f"{pair['pair_id']}-{tag}"
    if dest.exists():
        subprocess.run(["rm", "-rf", str(dest)], check=True)
    proc = subprocess.run(["git", "clone", "-q", "--no-hardlinks", cfg["local_path"], str(dest)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"clone failed: {proc.stderr[:200]}")
    subprocess.run(["git", "-C", str(dest), "checkout", "-q", "--detach", cfg["pin"]], check=True)
    return dest


# ---------------------------------------------------------------- advice

def advice_for_pair(pair: dict, state: dict, scratch: Path) -> dict:
    """Forecast + advice payload emitted BEFORE arm execution."""
    replica = make_replica(pair, "advice")
    env = dict(**__import__("os").environ)
    code = r"""
import json, sys
sys.path.insert(0, "{here}")
from engineering_core.catalog import load_catalog
from engineering_core.engineering_plan import compile_plan
from engineering_core.advisor import build_request, validate_response
from pathlib import Path
repo = Path(sys.argv[1])
task = json.loads(sys.argv[2])
catalog = load_catalog()
ids = set(catalog.ids("lanes")) | set(catalog.ids("disciplines"))
import hashlib
grounding = {{p: hashlib.sha256((repo / p).read_bytes()).hexdigest() for p in task["task"]["grounding"] if (repo / p).exists()}}
try:
    plan = compile_plan(repo, catalog)
except Exception:
    plan = {{"schema": "engineering-plan-v1", "evidence": []}}
plan = dict(plan)
plan["goal"] = task["task"]["title"]
plan["task_context"] = {{
    "task_id": task["task"]["task_id"],
    "title": task["task"]["title"],
    "specification": task["task"]["spec"],
    "new_symbols": task["task"].get("new_symbols", []),
    "new_files": task["task"].get("new_files", []),
    "acceptance_runner": task["task"]["acceptance"]["runner"],
}}
plan["evidence"] = [{{"path": p, "sha256": s}} for p, s in grounding.items()]
request = build_request(repo, plan, ids, focus_files=grounding)
Path(sys.argv[3]).write_text(json.dumps(request))
""".format(here=str(Path(WHEEL).parent.parent / "lib" / "python3.13" / "site-packages"))
    req_path = scratch / "request.json"
    proc = subprocess.run([WHEEL, "-c", code, str(replica), json.dumps(pair), str(req_path)],
                          capture_output=True, text=True, env=env, timeout=300)
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

    validate_code = r"""
import json, sys
sys.path.insert(0, "{here}")
from engineering_core.advisor import validate_response
request = json.loads(open(sys.argv[1]).read())
response = json.loads(sys.argv[2])
validate_response(request, response)
print("VALID")
""".format(here=str(Path(WHEEL).parent.parent / "lib" / "python3.13" / "site-packages"))

    last_error = None
    for attempt in (1, 2):
        try:
            parsed = call_advisor()
            v = subprocess.run([WHEEL, "-c", validate_code, str(req_path), json.dumps(parsed)],
                               capture_output=True, text=True, timeout=120)
            if v.returncode != 0 or "VALID" not in v.stdout:
                raise RuntimeError(f"validate_response failed: {v.stderr[-400:]}")
            break
        except RuntimeError as exc:
            last_error = exc
            parsed = None
    if parsed is None:
        return {"request": request, "response": None, "forecast": None,
                "advice_failure": str(last_error)[:500]}
    forecast = None
    if parsed.get("status") == "advice" and parsed.get("recommendations"):
        forecast = max(r["confidence"] for r in parsed["recommendations"])
    return {"request": request, "response": parsed, "forecast": forecast}


# ---------------------------------------------------------------- execution

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
        outcome = {"y": 0, "checks": {"claim": {"ok": False, "bytes": 0},
                                      "acceptance": {"ok": False, "result": {"exit": -1, "stderr_tail": "no worktree changes (arm-attributable no-output)"}},
                                      "participant_validation": {"ok": False, "result": {"exit": -1, "stderr_tail": "not run: no output"}}},
                   "run": run, "duration_s": duration, "changed_files": []}
    else:
        checks = scoring.verify_arm(replica, pair["task"], scratch)
        outcome = {"y": checks["y"], "checks": checks["checks"], "run": run,
                   "duration_s": duration, "changed_files": changed[:50]}
    subprocess.run(["rm", "-rf", str(replica)], check=False)
    return outcome


# ---------------------------------------------------------------- run pair

def cmd_run(pair_id: str) -> None:
    state = load_state()
    if state.get("harm_stop"):
        raise SystemExit(f"harm stop active: {state['harm_stop'].get('kind')}; campaign halted")
    pair = find_pair(state, pair_id)
    prog = state["progress"][pair_id]
    if prog["status"] == "completed":
        print(f"{pair_id} already completed"); return

    family = pair["base_model_family"]
    blocker = state.get("blockers", {}).get(family)
    blocked = bool(blocker) and blocker.get("status") != "resolved"
    if blocked and prog["status"] == "pending":
        prog.update({"status": "blocked_family", "updated_at": now()})
        STATE_PATH.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
        print(f"{pair_id}: family {family} infrastructure-blocked; recorded (no substitution)")
        return

    SCRATCH.mkdir(parents=True, exist_ok=True)
    print(f"[{now()}] {pair_id}: advice surface (forecast before execution)")
    advice = advice_for_pair(pair, state, SCRATCH)
    if advice["response"] is None:
        prog.update({"status": "advice_blocked", "updated_at": now(),
                     "advice_failure": advice.get("advice_failure")})
        STATE_PATH.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
        print(f"{pair_id}: advice surface failed twice; pair administratively blocked "
              f"(no arm execution, no forecast recorded); resumable")
        return
    forecasts = json.loads(FORECASTS_PATH.read_text() or "{}")
    forecasts[pair_id] = {"task_id": pair["task"]["task_id"], "family": family, "stage": pair["stage"],
                          "forecast": advice["forecast"], "status": advice["response"]["status"],
                          "n_recommendations": len(advice["response"].get("recommendations", [])),
                          "recorded_at": now(), "before_execution": True}
    FORECASTS_PATH.write_text(json.dumps(forecasts, indent=1, sort_keys=True) + "\n")
    prog.update({"status": "advised", "updated_at": now()})
    STATE_PATH.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")

    arms = {}
    for arm in pair["arm_order"]:
        print(f"[{now()}] {pair_id}: executing {arm} arm ({pair['model_identity']})")
        arms[arm] = execute_arm(pair, arm,
                                advice["response"] if arm == "evidence" else None, SCRATCH)
        print(f"[{now()}] {pair_id}: {arm} y={arms[arm]['y']} ({arms[arm]['duration_s']}s)")

    receipt = {
        "schema": "dspx.g3-receipt/1",
        "pair_id": pair_id, "task_id": pair["task"]["task_id"],
        "owner_group": pair["owner_group"], "base_model_family": family,
        "baseline": pair["baseline"], "repo_pin": pair["repo_pin"],
        "model_identity": pair["model_identity"], "stage": pair["stage"],
        "arm_order": pair["arm_order"],
        "advice": {"status": advice["response"]["status"],
                   "n_recommendations": len(advice["response"].get("recommendations", [])),
                   "forecast_emitted": advice["forecast"] is not None,
                   "forecast_storage": "g3-campaign-forecasts.json",
                   "request_sha256": advice["request"].get("request_sha256")},
        "arms": arms,
        "verification_basis": {
            "scoring_sha256": state["frozen_artifacts"]["scoring_sha256"],
            "checks": {arm: sorted(arms[arm]["checks"]) for arm in arms},
            "masked": "verify_arm received only task + worktree",
        },
        "recorded_at": now(),
    }
    with RECEIPTS_PATH.open("a") as fh:
        fh.write(json.dumps(receipt, sort_keys=True) + "\n")

    prog.update({"status": "completed", "updated_at": now()})
    receipts = [json.loads(line) for line in RECEIPTS_PATH.read_text().splitlines() if line.strip()]
    evaluation = scoring.evaluate_harm_stops(state, receipts)
    with HARM_LOG_PATH.open("a") as fh:
        fh.write(json.dumps({"at": now(), "after_pair": pair_id, **evaluation}, sort_keys=True) + "\n")
    if evaluation["triggered"]:
        state["harm_stop"] = {"at": now(), "triggered_by": pair_id, "stops": evaluation["triggered"]}
        print(f"HARM STOP TRIGGERED: {json.dumps(evaluation['triggered'])}")
    STATE_PATH.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    print(f"[{now()}] {pair_id}: completed; harm stops triggered={bool(evaluation['triggered'])}")


# ---------------------------------------------------------------- status

def cmd_status() -> None:
    state = load_state()
    counts: dict[str, int] = {}
    for pid, p in state["progress"].items():
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    receipts = [json.loads(l) for l in RECEIPTS_PATH.read_text().splitlines() if l.strip()] if RECEIPTS_PATH.exists() else []
    print(json.dumps({
        "pairs_total": len(state["progress"]), "progress": counts,
        "receipts": len(receipts),
        "harm_stop": state.get("harm_stop"),
        "blockers": {k: v["status"] for k, v in state.get("blockers", {}).items()},
        "next_pending_in_order": next((pid for pid in state["execution_order"]
                                       if state["progress"][pid]["status"] == "pending"), None),
    }, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    run_p = sub.add_parser("run"); run_p.add_argument("--pair", required=True)
    sub.add_parser("status")
    args = ap.parse_args()
    if args.cmd == "freeze":
        cmd_freeze()
    elif args.cmd == "run":
        cmd_run(args.pair)
    else:
        cmd_status()


if __name__ == "__main__":
    main()
