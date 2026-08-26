#!/usr/bin/env python3
"""

v3b COPY (DSPx AK task 5085, G3 v3b re-run after the AK-5082 advise-surface fix).
Derived from the frozen v3 runner by recorded deltas (see V3B_DEVIATIONS);
v3 originals untouched.
G3 v3 pilot runner (DIAGNOSTIC SCREEN ONLY; DSPx AK task 5081).

CONTRACT-CONFORMANCE pilot, reshaped by operator directive pre-execution:
10 tasks x 1 assigned family x 2 arms = 20 executions. NOT Gate G3, NOT
protocol evidence, no gate claims. One diagnostic question: on tasks whose
correct answers live in convention space the engineering-core candidate-4
guidance encodes, do the static and evidence arms separate?

Arms differ ONLY by guidance presence:
- static:   identical task spec, no engineering-core content
- evidence: spec + the ACTUAL guidance content rendered from the verified
            candidate-4 wheel (lanes/disciplines/templates/README/catalog) and,
            for class A/C tasks, a product-mediated advisor response
            (gpt-5.6-terra uniformly; glm-5.3 fallback recorded if used).
- class B tasks receive the compiled advise request materials in the spec
  (both arms — it is the task fixture); no advisor model call for class B
  because that would fabricate the deliverable itself.

Usage:
  g3p3_runner.py freeze
  g3p3_runner.py render-guidance      (done inside freeze; prints digests)
  g3p3_runner.py advise --task A1
  g3p3_runner.py run --pair PL3-A1-fam-gpt [--deadline <iso8601>]
  g3p3_runner.py status
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g3p3_corpus as corpus_v3  # noqa: E402 (frozen v3 base: re-verified at v3b freeze)
import g3p3b_corpus as corpus_b  # noqa: E402
import g3p3b_scoring as scoring  # noqa: E402
import g3p3b_support as support  # noqa: E402

REPO = HERE.parents[1]
PROOF = REPO / "docs" / "v1-proof"
STATE_PATH = PROOF / "g3pilot-v3b-state.json"
RECEIPTS_PATH = PROOF / "g3pilot-v3b-receipts.jsonl"
SCRATCH = support.V3BROOT
RUNS = SCRATCH / "runs"
GUIDANCE_DIR = SCRATCH / "guidance"
REQUESTS_DIR = SCRATCH / "requests"
WHEEL_PATH = SCRATCH / "wheel/engineering_core-0.10.0-py3-none-any.whl"
WHEEL_SHA256 = "921bff5ef60ee8dea112cdaf8825e809bb484f1e518a06080e853c7e52288ab0"  # main@cde7f14 (AK-5082 fix)

EXECUTOR_TIMEOUT_S = 1500
ADVISOR_TIMEOUT_S = 420
PILOT_BUDGET_S = 6 * 3600
MAX_EXECUTIONS = 20

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

# wheel file paths for guidance rendering
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


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- guidance

def wheel_read(member: str) -> str:
    with zipfile.ZipFile(WHEEL_PATH) as zf:
        return zf.read(f"engineering_core/{member}").decode("utf-8")


def render_guidance(task: dict) -> str:
    tid, cls = task["task_id"], task["task_class"]
    parts: list[str] = []
    with zipfile.ZipFile(WHEEL_PATH) as zf:
        meta = zf.read("engineering_core-0.10.0.dist-info/METADATA").decode("utf-8")
        readme = meta.split("\n\n", 1)[1]
    parts.append("### README (engineering-core 0.10.0)\n\n" + readme)
    if cls == "A":
        parts.append("### Shipped skill (adoption procedure)\n\n" + wheel_read("skill/SKILL.md"))
        parts.append("### Template: engineering.local\n\n" + wheel_read(TEMPLATE_FILES["engineering.local"]))
        parts.append("### Template: discipline adoption checklist\n\n"
                     + wheel_read(TEMPLATE_FILES["discipline-adoption-checklist"]))
        for lane in ("py",):
            parts.append(f"### Lane: {lane}\n\n" + wheel_read(LANE_FILES[lane]))
        for d in ("validation", "testing", "security-privacy", "documentation", "dependency-governance"):
            parts.append(f"### Discipline: {d}\n\n" + wheel_read(DISCIPLINE_FILE.format(name=d)))
    elif cls == "B":
        lanes = {"B1": ["py"], "B2": ["ts", "ts-frontend"], "B3": ["py"]}[tid]
        for lane in lanes:
            parts.append(f"### Lane: {lane}\n\n" + wheel_read(LANE_FILES[lane]))
        for d in ("validation", "testing"):
            parts.append(f"### Discipline: {d}\n\n" + wheel_read(DISCIPLINE_FILE.format(name=d)))
    elif tid in ("C1", "C2"):
        parts.append("### Lane: pi-ts\n\n" + wheel_read(LANE_FILES["pi-ts"]))
        parts.append("### Addendum: pi-ts justfile\n\n" + wheel_read(LANE_FILES["pi-ts.justfile"]))
        for d in ("validation", "testing", "documentation"):
            parts.append(f"### Discipline: {d}\n\n" + wheel_read(DISCIPLINE_FILE.format(name=d)))
    elif tid == "C3":
        parts.append("### Lane: py\n\n" + wheel_read(LANE_FILES["py"]))
        parts.append("### Addendum: py justfile\n\n" + wheel_read(LANE_FILES["py.justfile"]))
        for d in ("validation", "testing", "documentation"):
            parts.append(f"### Discipline: {d}\n\n" + wheel_read(DISCIPLINE_FILE.format(name=d)))
    elif tid == "C4":
        parts.append("### Lane: py\n\n" + wheel_read(LANE_FILES["py"]))
        parts.append("### Addendum: py justfile\n\n" + wheel_read(LANE_FILES["py.justfile"]))
        for d in ("validation", "testing", "documentation"):
            parts.append(f"### Discipline: {d}\n\n" + wheel_read(DISCIPLINE_FILE.format(name=d)))
        parts.append("### Template: validation-tier-map\n\n" + wheel_read(TEMPLATE_FILES["validation-tier-map"]))
    catalog = subprocess.run([support.TOOLS["wheel_bin"], "catalog", "--pretty"],
                             capture_output=True, text=True, timeout=60)
    parts.append("### Catalog (machine-readable id vocabulary and version)\n\n```json\n"
                 + catalog.stdout + "\n```")
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------- B request materials

def request_materials(task: dict) -> str:
    """Compile the advise request on a pristine fixture and build the redacted
    advisor view (plan withheld — it is the answer key)."""
    work = SCRATCH / "reqbuild"
    work.mkdir(parents=True, exist_ok=True)
    replica = support.make_replica(task, work / task["task_id"])
    req_path = work / f"{task['task_id']}.json"
    if req_path.exists():
        req_path.unlink()
    request = support.compile_request(replica, req_path)
    view = {k: v for k, v in request.items() if k != "plan"}
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
        + json.dumps([{ "id": e["id"], "path": e["path"], "content": e["content"]}
                      for e in request["evidence"]], indent=1)
        + "\n```"
    )
    subprocess.run(["rm", "-rf", str(replica)], check=False)
    REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
    (REQUESTS_DIR / f"{task['task_id']}-request.json").write_text(
        json.dumps(request, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (REQUESTS_DIR / f"{task['task_id']}-materials.txt").write_text(materials, encoding="utf-8")
    return materials


def spec_for(task: dict) -> str:
    spec = task["spec"]
    if "{request_materials}" in spec:
        materials_path = REQUESTS_DIR / f"{task['task_id']}-materials.txt"
        if not materials_path.exists():
            request_materials(task)
        spec = spec.replace("{request_materials}", materials_path.read_text(encoding="utf-8"))
    return spec


# ---------------------------------------------------------------- freeze

CALIBRATION_SUMMARY = ("PASS (pre-freeze, 0.10.0 wheel + v3b checkers: 10/10 reference Y=1, "
                        "10/10 stub Y=0, A1+C3 tamper detected; max verify 2.0s)")

V3B_DEVIATIONS = [
    {"file": "benchmarks/g3-pilot/g3p3b_corpus.py", "delta": "2 executor-visible spec strings "
     "'engineering-core 1.0.0 CLI' -> 'engineering-core 0.10.0 CLI' (A1_SPEC, A2_SPEC)",
     "why": "operator directive #2: honest released pin for the 0.10.0 wheel; the frozen v3 "
            "spec text named the v3-grading CLI version"},
    {"file": "benchmarks/g3-pilot/g3p3b_scoring.py", "delta": "RELEASE_REF 'v1.0.0' -> 'v0.10.0' "
     "(constant only; checker logic unchanged)",
     "why": "operator directive #2: the checker hardcoded a version string; the posture RULE "
            "(ref must equal the currently released catalog version + doctor released-match) "
            "is unchanged and is made honest for the 0.10.0 wheel"},
    {"file": "benchmarks/g3-pilot/ref3b/a_policy.json", "delta": "engineering_core.ref "
     "'v1.0.0' -> 'v0.10.0' (reference solution copy; v3 ref3/ untouched)",
     "why": "class-A reference policies must pin the released version of the wheel actually "
            "grading v3b so calibration Y=1 stays truthful"},
    {"file": "benchmarks/g3-pilot/g3p3b_runner.py", "delta": "wheel identity main@cde7f14 "
     "(sha 921bff5e...), scratch root g3pilot-v3b-5085, state/receipt paths g3pilot-v3b-*, "
     "guidance header + README title + dist-info version strings 1.0.0 -> 0.10.0, receipts "
     "schema dspx.g3pilot-v3b-receipt/1 + run_label='v3b'",
     "why": "v3b run identity; guidance bundles re-rendered from the FIXED wheel (SKILL.md "
            "now carries the response grammar + default disciplines)"},
    {"file": "class-A fixtures", "delta": "NONE (FIX_LEGACY_PY / FIX_DEGRADED_PY byte-identical "
     "to v3; FIX_DEGRADED_PY keeps its degraded ref 'v0.9.0', which remains a real past "
     "release under the 0.10.0 catalog history)",
     "why": "task difficulty must not change; only the correct repair TARGET moved to v0.10.0"},
    {"file": "FIX_ADOPTED_REDACT_PY (B3 fixture)", "delta": "NONE (keeps ref 'v1.0.0')",
     "why": "B-class checkers never grade pin posture; the fixture is inert for grading and "
            "byte-stays v3 for comparability"},
    {"file": "advisor wrapper / prompt template / advice header", "delta": "NONE "
     "(byte-identical to v3)",
     "why": "the fix under test is the PRODUCT advise surface (validator grammar + "
            "self-describing request), not the harness prompt"},
]


def verify_v3_base() -> dict:
    """Re-verify the frozen v3 base before any v3b execution."""
    v3_state = json.loads((PROOF / "g3pilot-v3-state.json").read_text())
    recorded = v3_state["frozen_artifacts"]
    corpus_now = corpus_v3.digest(corpus_v3.build_corpus())
    checks = {
        "v3_corpus_digest": {"recorded": recorded["corpus_digest"], "now": corpus_now,
                             "match": recorded["corpus_digest"] == corpus_now},
        "v3_scoring_sha256": {"recorded": recorded["scoring_sha256"],
                              "now": sha256_file(HERE / "g3p3_scoring.py"),
                              "match": recorded["scoring_sha256"] == sha256_file(HERE / "g3p3_scoring.py")},
        "v3_support_sha256": {"recorded": recorded["support_sha256"],
                              "now": sha256_file(HERE / "g3p3_support.py"),
                              "match": recorded["support_sha256"] == sha256_file(HERE / "g3p3_support.py")},
        "v3_runner_sha256": {"recorded": recorded["runner_sha256"],
                             "now": sha256_file(HERE / "g3p3_runner.py"),
                             "match": recorded["runner_sha256"] == sha256_file(HERE / "g3p3_runner.py")},
    }
    ok = all(c["match"] for c in checks.values())
    if not ok:
        raise SystemExit(f"frozen v3 base drifted; refusing to freeze v3b: {checks}")
    return {"ok": True, "checked_at": now(), "checks": checks}


def cmd_freeze() -> None:
    if STATE_PATH.exists():
        raise SystemExit("state already frozen; refusing to refreeze")
    if not WHEEL_PATH.exists():
        raise SystemExit(f"candidate wheel missing at {WHEEL_PATH}")
    wheel_digest = sha256_file(WHEEL_PATH)
    if wheel_digest != WHEEL_SHA256:
        raise SystemExit(f"candidate wheel digest mismatch: {wheel_digest}")
    corpus = corpus_b.build_corpus()
    GUIDANCE_DIR.mkdir(parents=True, exist_ok=True)
    guidance_digests = {}
    for pair in corpus["pairs"]:
        task = pair["task"]
        text = render_guidance(task)
        path = GUIDANCE_DIR / f"{task['task_id']}.md"
        path.write_text(text, encoding="utf-8")
        guidance_digests[task["task_id"]] = sha256_file(path)
    request_digests = {}
    for pair in corpus["pairs"]:
        if pair["task"]["task_class"] == "B":
            request_materials(pair["task"])
            request_digests[pair["task"]["task_id"]] = {
                "request": sha256_file(REQUESTS_DIR / f"{pair['task']['task_id']}-request.json"),
                "materials": sha256_file(REQUESTS_DIR / f"{pair['task']['task_id']}-materials.txt"),
            }
    state = {
        "schema": "dspx.g3pilot-v3b-state/1",
        "diagnostic_label": (
            "G3 v3b CONTRACT-CONFORMANCE re-run - DIAGNOSTIC ONLY; not Gate G3, "
            "not protocol evidence, no gate claims; measures the AK-5082 fixed "
            "advise surface (uniform falsification grammar + self-describing request)"
        ),
        "frozen_at": now(),
        "operator_intent_quote": (
            "after the AK-5082 advise-surface fix, does glm-5.3:high's EVIDENCE-arm "
            "conformance recover on the same tasks it failed?"
        ),
        "operator_reshape_quote": (
            "directive #2: 5 tasks per arm-slot, BOTH families - no single-family bias "
            "in the recovery read; glm must include A2+B2; sol must include a v3 "
            "evidence-win; all classes represented per family"
        ),
        "repos": {k: {"identity": v["repo_identity"], "pin": v["pin"]}
                  for k, v in corpus_b.REPOS.items()},
        "models": {
            "executors": corpus_b.FAMILIES,
            "advisor_identity": ADVISOR_IDENTITY,
            "advisor_fallback": ADVISOR_FALLBACK,
            "advisor_scope": "class A/C evidence arms only (a class B advisor call would fabricate the deliverable)",
        },
        "candidate": {
            "repo": "/home/tryinget/ai-society/core/engineering-core",
            "branch": "main",
            "commit": "cde7f142ebd07527d865eded4bbbadf9fda9400f",
            "wheel_sha256": WHEEL_SHA256,
            "built_from": "pre-built dist at pi-quests tmp ec5082wheel.ZCucu5; digest verified before use",
            "wheel_path": str(WHEEL_PATH),
            "note": ("engineering-core 0.10.0 on main WITH the AK-5082 advise-surface fix; "
                     "deliberately NOT the frozen candidate-4 (bc43bb9) - v3b measures the "
                     "FIXED advise surface; candidate rebinding is a later decision"),
        },
        "budgets": {
            "max_executions": MAX_EXECUTIONS,
            "pilot_wall_s": PILOT_BUDGET_S,
            "executor_timeout_s": EXECUTOR_TIMEOUT_S,
            "advisor_timeout_s": ADVISOR_TIMEOUT_S,
            "verify_timeout_s": scoring.VERIFY_TIMEOUT_S,
        },
        "frozen_artifacts": {
            "corpus_digest": corpus_b.digest(corpus),
            "scoring_sha256": sha256_file(HERE / "g3p3_scoring.py"),
            "support_sha256": sha256_file(HERE / "g3p3_support.py"),
            "runner_sha256": sha256_file(HERE / "g3p3_runner.py"),
            "calibrate_sha256": sha256_file(HERE / "g3p3_calibrate.py"),
            "prompt_template_sha256": sha256_text(PROMPT_TEMPLATE),
            "guidance_header_sha256": sha256_text(GUIDANCE_HEADER),
            "advice_header_sha256": sha256_text(ADVICE_HEADER),
            "advisor_wrapper_sha256": sha256_text(ADVISOR_WRAPPER),
            "guidance_digests": guidance_digests,
            "request_digests": request_digests,
            "ref3b_digests": {p.name: sha256_file(p) for p in sorted((HERE / "ref3b").iterdir())},
            "v3_base_reverification": verify_v3_base(),
            "v3b_deviations": V3B_DEVIATIONS,
        },
        "calibration": CALIBRATION_SUMMARY,
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
        "frozen": True, "state": str(STATE_PATH.relative_to(REPO)),
        "pairs": len(corpus["execution_order"]), "tasks": 10,
        "corpus_digest": state["frozen_artifacts"]["corpus_digest"],
        "guidance_bundles": len(guidance_digests),
        "request_bundles": len(request_digests),
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
    with state_lock():
        state = load_state()
        mutate(state)
        STATE_PATH.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
        return state


def find_pair(state: dict, pair_id: str) -> dict:
    for p in state["corpus"]["pairs"]:
        if p["pair_id"] == pair_id:
            return p
    raise SystemExit(f"unknown pair {pair_id}")


# ---------------------------------------------------------------- advice (class A/C evidence)

BUILD_REQUEST_CODE = r"""
import json, sys, hashlib
sys.path.insert(0, "{here}")
from engineering_core.catalog import load_catalog
from engineering_core.engineering_plan import compile_plan
from engineering_core.advisor import build_request
from pathlib import Path
repo = Path(sys.argv[1])
task = json.loads(sys.argv[2])
catalog = load_catalog()
ids = set(catalog.ids("lanes")) | set(catalog.ids("disciplines"))
grounding = {{p: hashlib.sha256((repo / p).read_bytes()).hexdigest() for p in task.get("focus_files", []) if (repo / p).exists()}}
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
}}
plan["evidence"] = [{{"path": p, "sha256": s}} for p, s in grounding.items()]
request = build_request(repo, plan, ids, focus_files=grounding)
Path(sys.argv[3]).write_text(json.dumps(request))
""".format(here=support.TOOLS["wheel_site"])

VALIDATE_CODE = r"""
import json, sys
sys.path.insert(0, "{here}")
from engineering_core.advisor import validate_response
request = json.loads(open(sys.argv[1]).read())
response = json.loads(sys.argv[2])
validate_response(request, response)
print("VALID")
""".format(here=support.TOOLS["wheel_site"])

FOCUS_FILES = {
    "A1": ["pyproject.toml", "policy/stack-lane.json", "docs/tech-stack.local.md"],
    "A2": ["pyproject.toml", "policy/engineering-lane.json", "docs/engineering.local.md"],
    "A3": ["pyproject.toml", "policy/stack-lane.json"],
    "C1": ["packages/pi-context-packer/package.json", "packages/pi-context-packer/biome.jsonc"],
    "C2": ["Justfile", "package.json"],
    "C3": ["pyproject.toml", "Justfile"],
    "C4": ["Justfile", "docs/engineering.local.md"],
}


def advice_for_task(pair: dict, identity: str) -> dict:
    task = dict(pair["task"])
    task["focus_files"] = FOCUS_FILES.get(task["task_id"], [])
    replica = support.make_replica(task, RUNS / f"{pair['pair_id']}-advice")
    req_path = SCRATCH / f"request-{pair['pair_id']}.json"
    if req_path.exists():
        req_path.unlink()
    proc = subprocess.run([support.TOOLS["wheel_py"], "-c", BUILD_REQUEST_CODE,
                           str(replica), json.dumps(task), str(req_path)],
                          capture_output=True, text=True, timeout=300)
    subprocess.run(["rm", "-rf", str(replica)], check=False)
    if proc.returncode != 0:
        return {"response": None, "failure": f"build_request failed: {proc.stderr[-300:]}"}
    request = json.loads(req_path.read_text())
    wrapper = ADVISOR_WRAPPER.format(model=identity.split("/", 1)[1],
                                     request_sha256=request["request_sha256"],
                                     request_json=json.dumps(request, indent=1))

    def call(model_identity: str) -> str:
        adv = subprocess.run(["pi", "-p", "--no-session", "--model", model_identity, wrapper],
                             capture_output=True, text=True, timeout=ADVISOR_TIMEOUT_S)
        return adv.stdout.strip()

    last_error = None
    parsed = None
    used_identity = identity
    for attempt in (1, 2):
        try:
            out = call(identity)
            candidates = [out] + re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", out, re.S) \
                + re.findall(r"\{.*\}", out, re.S)
            chosen = None
            for text in candidates:
                try:
                    chosen = json.loads(text)
                    break
                except json.JSONDecodeError:
                    continue
            if chosen is None:
                raise RuntimeError(f"advisor produced no JSON: {out[-200:]}")
            v = subprocess.run([support.TOOLS["wheel_py"], "-c", VALIDATE_CODE,
                                str(req_path), json.dumps(chosen)],
                               capture_output=True, text=True, timeout=120)
            if v.returncode != 0 or "VALID" not in v.stdout:
                raise RuntimeError(f"validate_response failed: {v.stderr[-300:]}")
            parsed = chosen
            break
        except RuntimeError as exc:
            last_error = exc
    if parsed is None and identity == ADVISOR_IDENTITY:
        # recorded fallback per operator rule
        try:
            out = call(ADVISOR_FALLBACK)
            chosen = json.loads(re.findall(r"\{.*\}", out, re.S)[-1])
            v = subprocess.run([support.TOOLS["wheel_py"], "-c", VALIDATE_CODE,
                                str(req_path), json.dumps(chosen)],
                               capture_output=True, text=True, timeout=120)
            if v.returncode == 0 and "VALID" in v.stdout:
                parsed = chosen
                used_identity = ADVISOR_FALLBACK
        except Exception as exc:  # noqa: BLE001 - recorded, not raised
            last_error = exc
    if parsed is None:
        return {"response": None, "failure": str(last_error)[:400],
                "request_sha256": request.get("request_sha256")}
    return {"response": parsed, "request_sha256": request.get("request_sha256"),
            "advisor_identity": used_identity}


# ---------------------------------------------------------------- execution

def looks_provider_blocked(run: dict) -> bool:
    if run["exit"] == 0:
        return False
    blob = (run.get("stderr_tail", "") + " " + run.get("stdout_tail", "")).lower()
    return any(sig in blob for sig in ("403", "429", "quota", "credit", "insufficient",
                                       "rate limit", "exceeded your"))


def execute_arm(pair: dict, arm: str, guidance_text: str | None,
                advice_response: dict | None) -> dict:
    task = pair["task"]
    replica = support.make_replica(task, RUNS / f"{pair['pair_id']}-{arm}")
    repo_identity = pair["repo_identity"] if not pair["repo_identity"].startswith("fixture:") \
        else f"scratch fixture ({pair['repo_identity'].split(':', 1)[1]})"
    prompt = PROMPT_TEMPLATE.format(
        repo_identity=repo_identity, task_id=task["task_id"], title=task["title"],
        spec=spec_for(task))
    if arm == "evidence":
        prompt += GUIDANCE_HEADER + guidance_text
        if advice_response is not None:
            prompt += ADVICE_HEADER.format(advice_json=json.dumps(advice_response, indent=1))
    started = time.monotonic()
    try:
        proc = subprocess.run(["pi", "-p", "--no-session", "--model", pair["model_identity"], prompt],
                              cwd=replica, capture_output=True, text=True, timeout=EXECUTOR_TIMEOUT_S)
        run = {"exit": proc.returncode, "stdout_tail": proc.stdout[-1200:],
               "stderr_tail": proc.stderr[-300:]}
    except subprocess.TimeoutExpired:
        run = {"exit": -1, "stdout_tail": "", "stderr_tail": "EXECUTOR TIMEOUT"}
    duration = round(time.monotonic() - started, 1)
    changed = subprocess.run(["git", "-C", str(replica), "status", "--porcelain"],
                             capture_output=True, text=True).stdout.splitlines()
    if not changed:
        checks = {"checks": {
            "claim": {"ok": False, "bytes": 0},
            "grounding": {"ok": True, "problems": []},
            "acceptance": {"ok": False, "problems": ["no worktree changes (arm-attributable no-output)"],
                           "tool_results": {}},
        }}
        checks["y"] = 0
        checks["verify_duration_s"] = 0.0
        outcome = {"y": 0, "checks": checks["checks"], "run": run,
                   "duration_s": duration, "changed_files": []}
    else:
        verified = scoring.verify_arm(replica, task, SCRATCH, support.TOOLS)
        outcome = {"y": verified["y"], "checks": verified["checks"], "run": run,
                   "duration_s": duration, "changed_files": changed[:50],
                   "verify_duration_s": verified["verify_duration_s"]}
    subprocess.run(["rm", "-rf", str(replica)], check=False)
    return outcome


# ---------------------------------------------------------------- commands

def cmd_advise(task_id: str) -> None:
    state = load_state()
    pair = next(p for p in state["corpus"]["pairs"] if p["task"]["task_id"] == task_id)
    if pair["task"]["task_class"] == "B":
        print(json.dumps({"task_id": task_id, "ok": True, "note":
                          "class B: no advisor call (would fabricate the deliverable); "
                          "request materials are frozen in the spec"}))
        return
    advice = advice_for_task(pair, ADVISOR_IDENTITY)

    def store(st):
        st["advice"][task_id] = {
            "request_sha256": advice.get("request_sha256"),
            "response": advice.get("response"),
            "advisor_identity": advice.get("advisor_identity", ADVISOR_IDENTITY),
            "failure": advice.get("failure"),
            "recorded_at": now(),
        }
    update_state(store)
    ok = advice.get("response") is not None
    print(json.dumps({"task_id": task_id, "ok": ok,
                      "status": (advice.get("response") or {}).get("status"),
                      "n_recommendations": len((advice.get("response") or {}).get("recommendations", [])),
                      "advisor_identity": advice.get("advisor_identity", ADVISOR_IDENTITY),
                      "failure": advice.get("failure")}, indent=1))


def budget_deadline(state: dict) -> float | None:
    started = state["budget"]["started_at"]
    if not started:
        return None
    return dt.datetime.fromisoformat(started).timestamp() + PILOT_BUDGET_S


def cmd_run(pair_id: str, deadline_iso: str | None) -> None:
    state = load_state()
    pair = find_pair(state, pair_id)
    family = pair["family"]
    if state["progress"][pair_id]["status"] == "completed":
        print(f"{pair_id} already completed")
        return
    blocker = state.get("blockers", {}).get(family)
    if blocker and blocker.get("status") != "resolved":
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

    if update_state(budget_gate) == "max_executions":
        print("budget: max executions reached; stop")
        return
    deadline = dt.datetime.fromisoformat(deadline_iso).timestamp() if deadline_iso \
        else budget_deadline(load_state())
    if deadline and time.time() > deadline:
        def mark_deadline(st):
            st["budget"]["stopped_reason"] = st["budget"]["stopped_reason"] or "wall_budget"
        update_state(mark_deadline)
        print("budget: wall clock exceeded; stop")
        return

    task_id = pair["task"]["task_id"]
    advice_summary = {"used": False, "note": None}
    advice_response = None
    if pair["task"]["task_class"] == "B":
        advice_summary["note"] = "class B: no advisor call (would fabricate the deliverable)"
    else:
        print(f"[{now()}] {pair_id}: advice surface ({ADVISOR_IDENTITY})")
        advice = advice_for_task(pair, ADVISOR_IDENTITY)

        def store(st):
            st["advice"][task_id] = {
                "request_sha256": advice.get("request_sha256"),
                "response": advice.get("response"),
                "advisor_identity": advice.get("advisor_identity", ADVISOR_IDENTITY),
                "failure": advice.get("failure"),
                "recorded_at": now(),
            }
        update_state(store)
        if advice.get("response") is None:
            def mark_advice(st):
                st["progress"][pair_id].update({
                    "status": "advice_blocked", "updated_at": now(),
                    "advice_failure": str(advice.get("failure"))[:400]})
            update_state(mark_advice)
            print(f"{pair_id}: advice surface failed; pair administratively blocked; resumable")
            return
        advice_response = advice["response"]
        advice_summary = {
            "used": True,
            "status": advice_response.get("status"),
            "n_recommendations": len(advice_response.get("recommendations", [])),
            "request_sha256": advice.get("request_sha256"),
            "advisor_identity": advice.get("advisor_identity", ADVISOR_IDENTITY),
        }

    guidance_text = (GUIDANCE_DIR / f"{task_id}.md").read_text(encoding="utf-8")
    arms: dict = {}
    blocked_family = False
    for arm in pair["arm_order"]:
        if deadline and time.time() > deadline:
            def mark_wall(st):
                st["budget"]["stopped_reason"] = st["budget"]["stopped_reason"] or "wall_budget"
            update_state(mark_wall)
            print("budget: wall clock exceeded mid-pair; stopping (resumable)")
            return
        if load_state()["budget"]["executions"] >= MAX_EXECUTIONS:
            def mark_max(st):
                st["budget"]["stopped_reason"] = st["budget"]["stopped_reason"] or "max_executions"
            update_state(mark_max)
            print("budget: max executions reached mid-pair; stopping")
            return
        print(f"[{now()}] {pair_id}: executing {arm} arm ({pair['model_identity']})")
        arms[arm] = execute_arm(pair, arm,
                                guidance_text if arm == "evidence" else None,
                                advice_response if arm == "evidence" else None)

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
                    "disposition": "remaining pairs of this family marked blocked_family; "
                                   "other family continues; resumable",
                }
            update_state(mark_block)
            blocked_family = True
            break

    if len(arms) == 2:
        receipt = {
            "schema": "dspx.g3pilot-v3b-receipt/1",
            "run_label": "v3b",
            "pair_id": pair_id, "task_id": task_id,
            "task_class": pair["task_class"],
            "family": family, "model_identity": pair["model_identity"],
            "repo_identity": pair["repo_identity"], "repo_pin": pair["repo_pin"],
            "arm_order": pair["arm_order"],
            "advice": advice_summary,
            "guidance_sha256": state["frozen_artifacts"]["guidance_digests"][task_id],
            "arms": arms,
            "verification_basis": {
                "scoring_sha256": state["frozen_artifacts"]["scoring_sha256"],
                "corpus_digest": state["frozen_artifacts"]["corpus_digest"],
                "masked": "verify_arm received only task + worktree",
                "checks": {arm: {"y": arms[arm]["y"],
                                 "ok": {k: v.get("ok") for k, v in arms[arm]["checks"].items()}}
                           for arm in arms},
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
            st["progress"][pair_id].update({
                "status": ("blocked_family_partial" if blocked_family else "partial_")
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
    per_class: dict = {}
    for r in receipts:
        key = (r["task_class"], r["family"])
        bucket = per_class.setdefault(key, {"tasks": 0, "static": 0, "evidence": 0})
        bucket["tasks"] += 1
        bucket["static"] += r["arms"].get("static", {}).get("y", 0)
        bucket["evidence"] += r["arms"].get("evidence", {}).get("y", 0)
    print(json.dumps({
        "pairs_total": len(state["progress"]), "progress": counts,
        "receipts": len(receipts), "executions": state["budget"]["executions"],
        "budget_started_at": state["budget"]["started_at"],
        "stopped_reason": state["budget"]["stopped_reason"],
        "blockers": {k: v["status"] for k, v in state.get("blockers", {}).items()},
        "per_class_family": {f"{c}/{f}": v for (c, f), v in sorted(per_class.items())},
        "next_pending_in_order": next((pid for pid in state["execution_order"]
                                       if state["progress"][pid]["status"] == "pending"), None),
    }, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    sub.add_parser("render-guidance")
    adv = sub.add_parser("advise"); adv.add_argument("--task", required=True)
    run_p = sub.add_parser("run"); run_p.add_argument("--pair", required=True)
    run_p.add_argument("--deadline", default=None)
    sub.add_parser("status")
    args = ap.parse_args()
    if args.cmd == "freeze":
        cmd_freeze()
    elif args.cmd == "render-guidance":
        corpus = corpus_b.build_corpus()
        for pair in corpus["pairs"]:
            print(pair["task"]["task_id"], sha256_text(render_guidance(pair["task"]))[:16])
    elif args.cmd == "advise":
        cmd_advise(args.task)
    elif args.cmd == "run":
        cmd_run(args.pair, args.deadline)
    else:
        cmd_status()


if __name__ == "__main__":
    main()
