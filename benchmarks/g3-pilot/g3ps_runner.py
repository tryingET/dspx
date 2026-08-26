"""G3 SUCCESSOR runner (AK 5095; decision 138 REV 3).

Adapted from the frozen v3b runner mechanics with the decision-138 deltas:
- PairRunGuard (AK 5092) integrated at pair begin/end and receipt append
  (in-flight guard + per-pair receipt idempotency + atomic append);
- per-INSTANCE tasks (36) x 2 families = 72 pairs, interleaved enrollment
  per frozen instance_order;
- B/H-class request materials frozen per instance (requests compiled from
  pristine fixtures; grading binds to the frozen request);
- advisor (gpt-5.6-terra) for class A/C/H EVIDENCE arms only;
- interim look at N=48 receipt-backed pairs (efficacy p<0.001 / futility
  asymmetry <= 0.5), one-shot extension rule per REV 3 sec 4;
- wall-clock window frozen at freeze; budget reconciles to receipts only;
- incidents ledgered as in v3b.

Usage:
  g3ps_runner.py freeze [--window-s N]     # freeze manifest + calibration record
  g3ps_runner.py run --pair PL4-<inst>-<fam>
  g3ps_runner.py status
  g3ps_runner.py interim                   # evaluate the interim look
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import g3ps_corpus as corpus  # noqa: E402
import g3ps_scoring as scoring  # noqa: E402
import g3ps_support as support  # noqa: E402
from g3ps_run_guard import PairRunGuard, RunGuardError  # noqa: E402

REPO = HERE.parents[1]
PROOF = REPO / "docs" / "v1-proof"
ROOT = Path(__import__("os").environ.get("TMPDIR", "/tmp")) / "g3ps-5095"
RUNS = ROOT / "runs"
REQ_DIR = ROOT / "requests"
GUIDANCE_DIR = ROOT / "guidance"
WHEEL_PATH = ROOT / "engineering_core-0.10.0-py3-none-any.whl"
WHEEL_SHA256 = "921bff5ef60ee8dea112cdaf8825e809bb484f1e518a06080e853c7e52288ab0"

STATE_PATH = PROOF / "g3ps-state.json"
RECEIPTS_PATH = PROOF / "g3ps-receipts.jsonl"

TOOLS = {
    "wheel_bin": str(ROOT / "venv/bin/engineering-core"),
    "wheel_py": str(ROOT / "venv/bin/python"),
    "wheel_site": str(ROOT / "venv/lib/python3.13/site-packages"),
    "biome": "/home/tryinget/ai-society/softwareco/owned/pi-extensions/packages/pi-context-packer/node_modules/.bin/biome",
    "dspx_ruff": "/home/tryinget/ai-society/softwareco/owned/dspx/.venv/bin/ruff",
    "dspx_python": "/home/tryinget/ai-society/softwareco/owned/dspx/.venv/bin/python",
    "requests_dir": str(REQ_DIR),
}

MAX_EXECUTIONS = 144
EXECUTOR_TIMEOUT_S = 1500
ADVISOR_TIMEOUT_S = 420
DEFAULT_WINDOW_S = 6 * 3600
INTERIM_AT = 48
EXTENDED_PAIRS = 96

ADVISOR_IDENTITY = "openai-codex/gpt-5.6-terra"
ADVISOR_FALLBACK = "zai/glm-5.3:high"

PROMPT_TEMPLATE = """You are executing a bounded engineering task in a disposable scratch repository ({repo_identity}).

TASK ({task_id}): {title}

SPECIFICATION (satisfy exactly; verification is objective, deterministic, and automated):
{spec}

Complete the task now."""

GUIDANCE_HEADER = """

## ENGINEERING GUIDANCE (advisory; the engineering-core 0.10.0 release content for this repository family)

The following is the actual guidance content shipped by the engineering-core
0.10.0 release that governs this repository family. Evaluate it critically and
use whatever of it you judge correct.

"""

ADVICE_HEADER = """

## OWNER EVIDENCE-ADVICE (advisory only; from the engineering-core advice surface; evaluate critically)
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
- recommendations: JSON array (max 3). Each element is an object with keys EXACTLY id, catalog_ids, recommendation, confidence, unknowns, counterevidence, falsification, citations, competes_with. Types: id string; catalog_ids array of strings drawn only from the request's allowed_catalog_ids; recommendation string; confidence a number in [0,1]; unknowns array of strings; counterevidence ARRAY OF STRINGS (never a bare string; empty array allowed); falsification array of strings; citations array of objects {{evidence_id, path, start, end}} referencing request evidence ids with valid spans; competes_with array of other recommendation ids
- critiques: array of objects with keys exactly recommendation_id, critique, severity, falsification (strings, severity one of low/medium/high)
- patch_proposals: [] (no patch proposals in this pilot)
Follow the request's embedded prompt instructions exactly; cite only request-bound evidence.
Output the JSON object and NOTHING else. No markdown fences.

REQUEST:
{request_json}"""

LANE_FILES = {
    "py": "lanes/engineering-py.md",
    "py.justfile": "lanes/engineering-py.justfile.md",
    "ts": "lanes/engineering-ts.md",
    "ts-frontend": "lanes/engineering-ts.frontend.md",
    "pi-ts": "lanes/engineering-pi-ts.md",
    "pi-ts.justfile": "lanes/engineering-pi-ts.justfile.md",
}
DISCIPLINE_FILE = "disciplines/{name}.md"
TEMPLATE_FILES = {
    "engineering.local": "templates/engineering.local.template.md",
    "discipline-adoption-checklist": "templates/discipline-adoption-checklist.md",
    "validation-tier-map": "templates/validation-tier-map.template.md",
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


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- guidance

def wheel_read(member: str) -> str:
    import zipfile

    with zipfile.ZipFile(WHEEL_PATH) as zf:
        return zf.read(f"engineering_core/{member}").decode("utf-8")


def render_guidance(task: dict) -> str:
    """Render guidance per template class from the frozen candidate-5 wheel."""
    parts: list[str] = []
    import zipfile

    with zipfile.ZipFile(WHEEL_PATH) as zf:
        meta = zf.read("engineering_core-0.10.0.dist-info/METADATA").decode("utf-8")
        readme = meta.split("\n\n", 1)[1]
    parts.append("### README (engineering-core 0.10.0)\n\n" + readme)
    tmpl = task["template"]
    if tmpl in ("TA1", "TA2", "TA3", "TH1", "TH2"):
        parts.append("### Shipped skill (adoption procedure)\n\n" + wheel_read("skill/SKILL.md"))
        parts.append("### Template: engineering.local\n\n" + wheel_read(TEMPLATE_FILES["engineering.local"]))
        parts.append("### Template: discipline adoption checklist\n\n"
                     + wheel_read(TEMPLATE_FILES["discipline-adoption-checklist"]))
        parts.append("### Lane: py\n\n" + wheel_read(LANE_FILES["py"]))
        for d in corpus.DEFAULT_DISCIPLINES:
            parts.append(f"### Discipline: {d}\n\n" + wheel_read(DISCIPLINE_FILE.format(name=d)))
        if tmpl in ("TH1",):
            parts.append("### Template: validation-tier-map\n\n"
                         + wheel_read(TEMPLATE_FILES["validation-tier-map"]))
    elif tmpl in ("TB1", "TB2", "TB3"):
        lanes = {"TB1": ["py"], "TB2": ["ts", "ts-frontend"], "TB3": ["py"]}[tmpl]
        for lane in lanes:
            parts.append(f"### Lane: {lane}\n\n" + wheel_read(LANE_FILES[lane]))
        for d in ("validation", "testing"):
            parts.append(f"### Discipline: {d}\n\n" + wheel_read(DISCIPLINE_FILE.format(name=d)))
    elif tmpl in ("TC1", "TC2"):
        parts.append("### Lane: pi-ts\n\n" + wheel_read(LANE_FILES["pi-ts"]))
        parts.append("### Addendum: pi-ts justfile\n\n" + wheel_read(LANE_FILES["pi-ts.justfile"]))
        for d in ("validation", "testing", "documentation"):
            parts.append(f"### Discipline: {d}\n\n" + wheel_read(DISCIPLINE_FILE.format(name=d)))
    elif tmpl in ("TC3", "TC4"):
        parts.append("### Lane: py\n\n" + wheel_read(LANE_FILES["py"]))
        parts.append("### Addendum: py justfile\n\n" + wheel_read(LANE_FILES["py.justfile"]))
        for d in ("validation", "testing", "documentation"):
            parts.append(f"### Discipline: {d}\n\n" + wheel_read(DISCIPLINE_FILE.format(name=d)))
        if tmpl == "TC4":
            parts.append("### Template: validation-tier-map\n\n"
                         + wheel_read(TEMPLATE_FILES["validation-tier-map"]))
    catalog = subprocess.run([TOOLS["wheel_bin"], "catalog", "--pretty"],
                             capture_output=True, text=True, timeout=60)
    parts.append("### Catalog (machine-readable id vocabulary and version)\n\n```json\n"
                 + catalog.stdout + "\n```")
    return "\n\n---\n\n".join(parts)


def spec_for(task: dict) -> str:
    spec = task["spec"]
    if "{request_materials}" in spec:
        mats = REQ_DIR / f"{task['instance_id']}-materials.txt"
        if not mats.exists():
            _render_materials(task)
        spec = spec.replace("{request_materials}", mats.read_text(encoding="utf-8"))
    return spec


def _render_materials(task: dict) -> None:
    request = json.loads((REQ_DIR / f"{task['instance_id']}-request.json").read_text())
    materials = (
        "request schema: " + request["schema"] + "\n"
        "request_sha256 (bind your response to EXACTLY this value): "
        + request["request_sha256"] + "\n"
        "prompt identity: id=" + request["prompt"]["id"]
        + " version=" + request["prompt"]["version"] + "\n"
        "allowed_catalog_ids (the ONLY ids you may use in catalog_ids):\n"
        + json.dumps(request["allowed_catalog_ids"]) + "\n"
        "captured evidence items (cite these; spans are bounds on the captured "
        "representation shown here):\n```json\n"
        + json.dumps([{k: e[k] for k in ("id", "path", "span", "bytes")}
                      for e in request["evidence"]], indent=1)
        + "\n```\ncaptured evidence contents (the advisor's view; note any redaction placeholders):\n```json\n"
        + json.dumps([{"id": e["id"], "path": e["path"], "content": e["content"]}
                      for e in request["evidence"]], indent=1)
        + "\n```"
    )
    (REQ_DIR / f"{task['instance_id']}-materials.txt").write_text(materials, encoding="utf-8")


# ---------------------------------------------------------------- state

def load_state() -> dict:
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


GUARD = None


def guard() -> PairRunGuard:
    global GUARD
    if GUARD is None:
        GUARD = PairRunGuard(lock_dir=ROOT / "locks", receipts_path=RECEIPTS_PATH)
    return GUARD


def pair_id_for(instance_id: str, family: str) -> str:
    return f"PL4-{instance_id}-{family}"


def enrollment_order(state: dict) -> list[str]:
    """Interleave families within each instance round; respects extension."""
    pairs: list[str] = []
    insts = list(state["instance_order"])
    if state.get("extended"):
        extra = json.loads((PROOF / "g3ps-extension.json").read_text()) if \
            (PROOF / "g3ps-extension.json").exists() else []
        insts = insts + [i for i in extra if i not in insts]
    for inst in insts:
        for fam in sorted(state["families"]):
            pairs.append(pair_id_for(inst, fam))
    return pairs


# ---------------------------------------------------------------- advice

BUILD_REQUEST_CODE = support.BUILD_REQUEST_CODE
VALIDATE_CODE = """
import json, sys
sys.path.insert(0, "{site}")
from engineering_core.advisor import validate_response
request = json.loads(open(sys.argv[1]).read())
response = json.loads(sys.argv[2])
validate_response(request, response)
print("VALID")
"""


def advice_for_pair(task: dict, pair_id: str) -> dict:
    """Advisor call for A/C/H evidence arms (class B: none)."""
    if task["task_class"] == "B":
        return {"response": None, "note": "class B: no advisor call"}
    if task["task_class"] == "H" and task["template"] == "TH2":
        return {"response": None, "note": "TH2 advise-response task: no advisor call"}
    t = dict(task)
    t["focus_files"] = FOCUS_FILES.get(t["template"], [])
    replica = support.make_replica(t, RUNS / f"{pair_id}-advice")
    req_path = ROOT / f"request-{pair_id}.json"
    if req_path.exists():
        req_path.unlink()
    code = BUILD_REQUEST_CODE.replace("{site}", TOOLS["wheel_site"])
    proc = subprocess.run([TOOLS["wheel_py"], "-c", code, str(replica),
                           json.dumps(t), str(req_path)],
                          capture_output=True, text=True, timeout=300)
    subprocess.run(["rm", "-rf", str(replica)], check=False)
    if proc.returncode != 0:
        return {"response": None, "failure": f"build_request failed: {proc.stderr[-300:]}"}
    request = json.loads(req_path.read_text())
    wrapper = ADVISOR_WRAPPER.format(model=ADVISOR_IDENTITY.split("/", 1)[1],
                                     request_sha256=request["request_sha256"],
                                     request_json=json.dumps(request, indent=1))

    def call(identity: str) -> str:
        adv = subprocess.run(["pi", "-p", "--no-session", "--model", identity, wrapper],
                             capture_output=True, text=True, timeout=ADVISOR_TIMEOUT_S)
        return adv.stdout.strip()

    parsed = None
    used = ADVISOR_IDENTITY
    last_error = None
    for identity in (ADVISOR_IDENTITY, ADVISOR_IDENTITY):
        try:
            out = call(identity)
            cands = [out] + re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", out, re.S) \
                + re.findall(r"\{.*\}", out, re.S)
            chosen = None
            for text in cands:
                try:
                    chosen = json.loads(text)
                    break
                except json.JSONDecodeError:
                    continue
            if chosen is None:
                raise RuntimeError(f"advisor produced no JSON: {out[-200:]}")
            v = subprocess.run([TOOLS["wheel_py"], "-c",
                                VALIDATE_CODE.format(site=TOOLS["wheel_site"]),
                                str(req_path), json.dumps(chosen)],
                               capture_output=True, text=True, timeout=120)
            if v.returncode != 0 or "VALID" not in v.stdout:
                raise RuntimeError(f"validate_response failed: {v.stderr[-300:]}")
            parsed = chosen
            break
        except RuntimeError as exc:
            last_error = exc
    if parsed is None:
        try:
            out = call(ADVISOR_FALLBACK)
            chosen = json.loads(re.findall(r"\{.*\}", out, re.S)[-1])
            v = subprocess.run([TOOLS["wheel_py"], "-c",
                                VALIDATE_CODE.format(site=TOOLS["wheel_site"]),
                                str(req_path), json.dumps(chosen)],
                               capture_output=True, text=True, timeout=120)
            if v.returncode == 0 and "VALID" in v.stdout:
                parsed = chosen
                used = ADVISOR_FALLBACK
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if parsed is None:
        return {"response": None, "failure": str(last_error)[:400],
                "request_sha256": request.get("request_sha256")}
    return {"response": parsed, "request_sha256": request.get("request_sha256"),
            "advisor_identity": used}


# ---------------------------------------------------------------- execution

def looks_provider_blocked(run: dict) -> bool:
    if run["exit"] == 0:
        return False
    blob = (run.get("stderr_tail", "") + " " + run.get("stdout_tail", "")).lower()
    return any(sig in blob for sig in ("403", "429", "quota", "credit", "insufficient",
                                       "rate limit", "exceeded your"))


def execute_arm(task: dict, pair_id: str, arm: str, model: str,
                guidance_text: str | None, advice_response: dict | None) -> dict:
    replica = support.make_replica(task, RUNS / f"{pair_id}-{arm}")
    prompt = PROMPT_TEMPLATE.format(
        repo_identity=f"scratch fixture ({task['fixture_key']}:{task['instance']})",
        task_id=task["instance_id"], title=task["title"], spec=spec_for(task))
    if arm == "evidence":
        prompt += GUIDANCE_HEADER + guidance_text
        if advice_response is not None:
            prompt += ADVICE_HEADER.format(advice_json=json.dumps(advice_response, indent=1))
    started = time.monotonic()
    try:
        proc = subprocess.run(["pi", "-p", "--no-session", "--model", model, prompt],
                              cwd=replica, capture_output=True, text=True,
                              timeout=EXECUTOR_TIMEOUT_S)
        run = {"exit": proc.returncode, "stdout_tail": proc.stdout[-1200:],
               "stderr_tail": proc.stderr[-300:]}
    except subprocess.TimeoutExpired:
        run = {"exit": -1, "stdout_tail": "", "stderr_tail": "EXECUTOR TIMEOUT"}
    duration = round(time.monotonic() - started, 1)
    changed = subprocess.run(["git", "-C", str(replica), "status", "--porcelain"],
                             capture_output=True, text=True).stdout.splitlines()
    if not changed:
        checks = {"claim": {"ok": False, "bytes": 0},
                  "grounding": {"ok": True, "problems": []},
                  "acceptance": {"ok": False,
                                 "problems": ["no worktree changes (arm-attributable no-output)"],
                                 "tool_results": {}}}
        outcome = {"y": 0, "checks": checks, "run": run, "duration_s": duration,
                   "changed_files": [], "verify_duration_s": 0.0}
    else:
        verified = scoring.verify_arm(replica, task, ROOT, TOOLS)
        outcome = {"y": verified["y"], "checks": verified["checks"], "run": run,
                   "duration_s": duration, "changed_files": changed[:50],
                   "verify_duration_s": verified["verify_duration_s"]}
    subprocess.run(["rm", "-rf", str(replica)], check=False)
    return outcome


# ---------------------------------------------------------------- freeze

def cmd_freeze(window_s: int) -> None:
    if STATE_PATH.exists():
        raise SystemExit("state already frozen; refusing to refreeze")
    if sha256_file(WHEEL_PATH) != WHEEL_SHA256:
        raise SystemExit("wheel sha mismatch — refusing to freeze")
    c = corpus.build_corpus()
    corpus_digest = corpus.digest(c)
    GUIDANCE_DIR.mkdir(parents=True, exist_ok=True)
    guidance_digests = {}
    for inst in c["instance_order"]:
        task = support.task_for(inst)
        text = render_guidance(task)
        (GUIDANCE_DIR / f"{inst}.md").write_text(text, encoding="utf-8")
        guidance_digests[inst] = sha256_text(text)
    request_digests = {}
    for inst in c["instance_order"]:
        if support.task_for(inst)["task_class"] in ("B", "H") and \
                support.task_for(inst)["template"] != "TH1":
            rp = REQ_DIR / f"{inst}-request.json"
            request_digests[inst] = sha256_file(rp)
            _render_materials(support.task_for(inst))
    state = {
        "schema": "dspx.g3ps-state/1",
        "run_label": "successor",
        "frozen_at": now(),
        "decision": 138,
        "ec_binding": {"task": 5096, "commit": "145c889"},
        "candidate": {"repo": "/home/tryinget/ai-society/core/engineering-core",
                      "commit": "cde7f142ebd07527d865eded4bbbadf9fda9409f",
                      "wheel_sha256": WHEEL_SHA256},
        "corpus_digest": corpus_digest,
        "module_sha256": {m: sha256_file(HERE / m) for m in
                          ("g3ps_corpus.py", "g3ps_support.py", "g3ps_scoring.py",
                           "g3ps_runner.py", "g3ps_calibrate.py", "g3ps_simulate.py",
                           "g3ps_run_guard.py")},
        "guidance_digests": guidance_digests,
        "request_digests": request_digests,
        "families": corpus.FAMILIES,
        "instance_order": c["instance_order"],
        "criterion_ref": "docs/v1-proof/g3-successor-campaign-design.md#4 (REV 3)",
        "simulation_ref": "docs/v1-proof/g3ps-simulation.json",
        "budget": {"max_executions": MAX_EXECUTIONS, "executions": 0,
                   "window_s": window_s, "window_started_at": None,
                   "stopped_reason": None},
        "extended": False,
        "interim_done": False,
        "progress": {pair_id_for(i, f): {"status": "pending", "updated_at": None}
                     for i in c["instance_order"] for f in corpus.FAMILIES},
        "blockers": {},
        "advice": {},
        "incidents": [],
        "execution_log": [],
    }
    save_state(state)
    print(json.dumps({"frozen": True, "corpus_digest": corpus_digest,
                      "pairs": len(state["progress"]), "window_s": window_s}, indent=1))


# ---------------------------------------------------------------- run pair

def cmd_run(pair_id: str) -> None:
    state = load_state()
    if state["progress"].get(pair_id, {}).get("status") == "completed":
        print(f"{pair_id} already completed")
        return
    inst_id = pair_id.split("-", 1)[1].rsplit("-", 1)[0]
    family = pair_id.rsplit("-", 1)[1]
    task = support.task_for(inst_id)
    model = state["families"][family]
    if state["budget"]["stopped_reason"]:
        print(f"budget stopped: {state['budget']['stopped_reason']}; refusing")
        return
    if state["budget"]["executions"] >= MAX_EXECUTIONS:
        state["budget"]["stopped_reason"] = "max_executions"
        save_state(state)
        print("budget: max executions")
        return
    if state["budget"]["window_started_at"]:
        deadline = dt.datetime.fromisoformat(state["budget"]["window_started_at"]).timestamp() \
            + state["budget"]["window_s"]
        if time.time() > deadline:
            state["budget"]["stopped_reason"] = "wall_window"
            save_state(state)
            print("budget: wall window exceeded")
            return
    # AK 5092 guards: in-flight + receipt idempotency (fail closed)
    try:
        guard().begin_pair(pair_id)
    except RunGuardError as exc:
        state["progress"][pair_id].update({"status": "guard_refused", "updated_at": now(),
                                           "guard_reason": str(exc)})
        save_state(state)
        print(f"{pair_id}: guard refused: {exc}")
        return
    try:
        if not state["budget"]["window_started_at"]:
            state["budget"]["window_started_at"] = now()
            save_state(state)
        # advisor (evidence arms, non-B/TH2)
        advice_summary = {"used": False, "note": None}
        advice_response = None
        if task["task_class"] == "B" or (task["task_class"] == "H" and task["template"] == "TH2"):
            advice_summary["note"] = "no advisor call (response-fabrication guard)"
        else:
            print(f"[{now()}] {pair_id}: advice surface")
            advice = advice_for_pair(task, pair_id)
            state = load_state()
            state["advice"][inst_id] = {
                "advisor_identity": advice.get("advisor_identity", ADVISOR_IDENTITY),
                "response": advice.get("response"),
                "failure": advice.get("failure"),
                "recorded_at": now(),
            }
            save_state(state)
            if advice.get("response") is None:
                state["progress"][pair_id].update({"status": "advice_blocked",
                                                   "updated_at": now()})
                save_state(state)
                print(f"{pair_id}: advice failed; resumable")
                return
            advice_response = advice["response"]
            advice_summary = {"used": True,
                              "advisor_identity": advice.get("advisor_identity"),
                              "n_recommendations": len(advice["response"].get("recommendations", []))}
        guidance_text = (GUIDANCE_DIR / f"{inst_id}.md").read_text(encoding="utf-8")
        arm_order = ["evidence", "static"] if hash(pair_id) % 2 == 0 else ["static", "evidence"]
        arms: dict = {}
        for arm in arm_order:
            state = load_state()
            if state["budget"]["executions"] >= MAX_EXECUTIONS:
                state["budget"]["stopped_reason"] = "max_executions"
                save_state(state)
                print("budget: max executions mid-pair; resumable")
                return
            print(f"[{now()}] {pair_id}: {arm} arm ({model})")
            arms[arm] = execute_arm(task, pair_id, arm, model,
                                    guidance_text if arm == "evidence" else None,
                                    advice_response if arm == "evidence" else None)
            state = load_state()
            state["budget"]["executions"] += 1
            state["execution_log"].append({"pair_id": pair_id, "arm": arm, "at": now(),
                                           "y": arms[arm]["y"],
                                           "duration_s": arms[arm]["duration_s"]})
            save_state(state)
            print(f"[{now()}] {pair_id}: {arm} y={arms[arm]['y']} ({arms[arm]['duration_s']}s)")
            if looks_provider_blocked(arms[arm]["run"]):
                state["blockers"][family] = {
                    "model": model, "status": "infrastructure_blocked",
                    "evidence": f"provider limit signature at {now()} on {pair_id} {arm}",
                    "disposition": "pause family; in-window resume; no substitution",
                }
                save_state(state)
                state["progress"][pair_id].update({"status": "blocked_partial", "updated_at": now()})
                save_state(state)
                print(f"{pair_id}: provider blocked; pair paused (resumable)")
                return
        if len(arms) == 2:
            receipt = {
                "schema": "dspx.g3ps-receipt/1", "run_label": "successor",
                "pair_id": pair_id, "instance_id": inst_id, "template": task["template"],
                "task_class": task["task_class"], "family": family, "model_identity": model,
                "arm_order": arm_order, "advice": advice_summary,
                "guidance_sha256": state["guidance_digests"][inst_id],
                "arms": arms,
                "verification_basis": {
                    "corpus_digest": state["corpus_digest"],
                    "scoring_sha256": state["module_sha256"]["g3ps_scoring.py"],
                    "request_binding": ("frozen per-instance request" if inst_id in
                                        state["request_digests"] else "n/a"),
                    "checks": {a: {"y": arms[a]["y"],
                                   "ok": {k: v.get("ok") for k, v in arms[a]["checks"].items()}}
                               for a in arms},
                },
                "recorded_at": now(),
            }
            guard().append_receipt(pair_id, receipt)  # idempotent, atomic
            state = load_state()
            state["progress"][pair_id].update({"status": "completed", "updated_at": now()})
            save_state(state)
            print(f"[{now()}] {pair_id}: completed "
                  f"(static y={arms.get('static', {}).get('y')}, "
                  f"evidence y={arms.get('evidence', {}).get('y')})")
    finally:
        guard().end_pair(pair_id)


# ---------------------------------------------------------------- interim + analysis

def _receipts() -> list[dict]:
    if not RECEIPTS_PATH.exists():
        return []
    return [json.loads(ln) for ln in RECEIPTS_PATH.read_text().splitlines() if ln.strip()]


def exact_mcnemar_p(n_e: int, n_s: int) -> float:
    n = n_e + n_s
    if n == 0:
        return 1.0
    k = min(n_e, n_s)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n))


def criterion(receipts: list[dict]) -> dict:
    evidence, static, tmpl, fam = [], [], [], []
    for r in receipts:
        static.append(r["arms"]["static"]["y"])
        evidence.append(r["arms"]["evidence"]["y"])
        tmpl.append(r["template"])
        fam.append(r["family"])
    n_e_only = sum(1 for e, s in zip(evidence, static) if e == 1 and s == 0)
    n_s_only = sum(1 for e, s in zip(evidence, static) if e == 0 and s == 1)
    p = exact_mcnemar_p(n_e_only, n_s_only)
    te: dict[str, int] = {}
    ts: dict[str, int] = {}
    for e, s, t in zip(evidence, static, tmpl):
        te[t] = te.get(t, 0) + (1 if e == 1 and s == 0 else 0)
        ts[t] = ts.get(t, 0) + (1 if e == 0 and s == 1 else 0)
    disc = [t for t in set(te) | set(ts) if te.get(t, 0) or ts.get(t, 0)]
    d = len(disc)
    e_dom = sum(1 for t in disc if te.get(t, 0) > ts.get(t, 0))
    s_dom = sum(1 for t in disc if ts.get(t, 0) > te.get(t, 0))
    fam_ok = True
    for f in set(fam):
        idx = [i for i, ff in enumerate(fam) if ff == f]
        ev = sum(evidence[i] for i in idx) / len(idx)
        st = sum(static[i] for i in idx) / len(idx)
        if ev < st - 1e-12:
            fam_ok = False
    completion = len(receipts) / 72 if not json.loads(STATE_PATH.read_text()).get("extended") \
        else len(receipts) / 96
    verdict = "INCONCLUSIVE"
    if p < 0.05 and d >= 4 and e_dom > d / 2 and fam_ok and n_e_only > n_s_only and completion >= 0.7:
        verdict = "PASS"
    elif p < 0.05 and d >= 4 and s_dom > d / 2 and fam_ok and n_s_only > n_e_only \
            and completion >= 0.7:
        verdict = "FAIL"
    elif p < 0.05 and d < 4:
        verdict = "INCONCLUSIVE_INSUFFICIENT_TEMPLATE_DISPERSION"
    return {"n_receipts": len(receipts), "completion": round(completion, 3),
            "n_evidence_only": n_e_only, "n_static_only": n_s_only,
            "pooled_exact_mcnemar_p": round(p, 6),
            "discordant_templates": d, "e_dominant": e_dom, "s_dominant": s_dom,
            "family_rule_ok": fam_ok, "verdict": verdict}


def cmd_interim() -> None:
    state = load_state()
    receipts = _receipts()
    if len(receipts) < INTERIM_AT:
        print(json.dumps({"interim": "not yet", "n_receipts": len(receipts),
                          "required": INTERIM_AT}))
        return
    if state.get("interim_done"):
        print("interim already evaluated")
        return
    # interim cohort: first 2 instances of every template x both families
    first_two = {f"{t}-{c}" for t in corpus.TEMPLATES for c in ("a", "b")}
    cohort = [r for r in receipts if r["instance_id"] in first_two]
    c = criterion(cohort)
    p = exact_mcnemar_p(c["n_evidence_only"], c["n_static_only"])
    out = {"at": now(), "n_cohort": c["n_receipts"], "p": round(p, 6)}
    if p < 0.001 and c["n_evidence_only"] > c["n_static_only"]:
        out["stop"] = "efficacy"
        state["budget"]["stopped_reason"] = "interim_efficacy_stop"
    elif c["n_evidence_only"] + c["n_static_only"] > 0 and \
            c["n_evidence_only"] / max(1, c["n_evidence_only"] + c["n_static_only"]) <= 0.5:
        out["stop"] = "futility"
        state["budget"]["stopped_reason"] = "interim_futility_stop"
        out["verdict_note"] = "INCONCLUSIVE (futility) per REV 3 sec 4"
    else:
        out["stop"] = None
    state["interim_done"] = True
    state["interim"] = out
    save_state(state)
    print(json.dumps(out, indent=1))


def cmd_status() -> None:
    state = load_state()
    receipts = _receipts()
    counts: dict[str, int] = {}
    for v in state["progress"].values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    print(json.dumps({
        "receipts": len(receipts), "executions": state["budget"]["executions"],
        "progress": counts, "stopped": state["budget"]["stopped_reason"],
        "interim": state.get("interim_done"),
        "current_criterion": criterion(receipts) if receipts else None,
    }, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    fr = sub.add_parser("freeze")
    fr.add_argument("--window-s", type=int, default=DEFAULT_WINDOW_S)
    run_p = sub.add_parser("run")
    run_p.add_argument("--pair", required=True)
    sub.add_parser("status")
    sub.add_parser("interim")
    args = ap.parse_args()
    if args.cmd == "freeze":
        cmd_freeze(args.window_s)
    elif args.cmd == "run":
        cmd_run(args.pair)
    elif args.cmd == "interim":
        cmd_interim()
    else:
        cmd_status()


if __name__ == "__main__":
    main()
