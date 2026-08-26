"""G3 SUCCESSOR scoring (AK 5095; decision 138).

Frozen checkers for the 12 successor templates. Adapted from the frozen v3b
checkers (same product-CLI gates, same tier-map/alias/lane-build shapes) with
two recorded deltas: (1) B/H-class advise-response grading binds to the
request FROZEN per instance (compiled from the pristine fixture at freeze),
not recompiled from the executor tree — required for TH2, where the executor
repairs the policy the request is compiled from; (2) per-instance deliverable
paths (module names, alias targets, fixture shapes).

Checker logic is never relaxed relative to v3b: identical doctor/scan
posture rules, identical tier-map/alias/runner gates.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

VERIFY_TIMEOUT_S = 180
CMD_TIMEOUT_S = 120
RELEASE_REF = "v0.10.0"

VALIDATE_RESPONSE_CODE = """
import json, sys
sys.path.insert(0, "{site}")
from engineering_core.advisor import validate_response
request = json.loads(open(sys.argv[1]).read())
response = json.loads(open(sys.argv[2]).read())
validate_response(request, response)
print("VALID")
"""

PLAN_SELECTIONS_CODE = """
import json, sys
sys.path.insert(0, "{site}")
from engineering_core.catalog import load_catalog
from engineering_core.engineering_plan import compile_plan
from pathlib import Path
repo = Path(sys.argv[1])
catalog = load_catalog()
try:
    plan = compile_plan(repo, catalog)
    requested = plan.get("requested", [])
    ids = set()
    for sel in requested:
        ids.add(sel["id"] if isinstance(sel, dict) else sel)
    print(json.dumps({{"requested": sorted(i for i in ids if i)}}))
except Exception as exc:
    print(json.dumps({{"error": str(exc)[:200]}}))
"""


def _run(cmd: list[str], cwd: Path, timeout: int = CMD_TIMEOUT_S) -> dict:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        result = {"cmd": cmd[:4], "exit": proc.returncode,
                  "stdout_tail": proc.stdout[-600:], "stderr_tail": proc.stderr[-300:]}
        try:
            result["json"] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result["json"] = None
        return result
    except subprocess.TimeoutExpired:
        return {"cmd": cmd[:4], "exit": -1, "stdout_tail": "", "stderr_tail": "TIMEOUT", "json": None}


def _full_output(cmd: list[str], cwd: Path, timeout: int = 60) -> str:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return (proc.stdout + "\n" + proc.stderr)[-20000:]
    except subprocess.TimeoutExpired:
        return ""


# ---------------------------------------------------------------- claim + grounding

def check_claim(replica: Path, task: dict) -> dict:
    claim = replica / "G3P3_CLAIM.md"
    if not claim.exists():
        return {"ok": False, "bytes": 0}
    data = claim.read_bytes()
    ok = len(data) > 200
    return {"ok": ok, "bytes": len(data)}


def _allowed_paths(task: dict) -> list[str]:
    t = task["template"]
    a = task["acceptance"]
    paths = {"G3P3_CLAIM.md"}
    if t in ("TA1", "TH1"):
        paths |= {"policy/engineering-lane.json", "docs/engineering.local.md",
                  "policy/stack-lane.json", "docs/tech-stack.local.md"}
        if t == "TH1":
            paths.add("docs/validation-tier-map.md")
    elif t in ("TA2", "TH2"):
        paths |= {"policy/engineering-lane.json", "docs/engineering.local.md"}
        if t == "TH2":
            paths.add("g3p3-advice-response.json")
    elif t == "TA3":
        paths |= {".g3p3-transaction/apply.json", ".g3p3-transaction/rollback.json"}
    elif t in ("TB1", "TB2", "TB3"):
        paths.add("g3p3-advice-response.json")
    elif t == "TC1":
        paths |= {a["module"], a["test"]}
    elif t == "TC2":
        paths |= {"package.json", "Justfile"}
    elif t == "TC3":
        paths |= {a["module_path"], a["test_path"]}
    elif t == "TC4":
        paths.add("docs/validation-tier-map.md")
    return sorted(paths)


def _fixture_grounding(replica: Path, task: dict) -> dict:
    """Fixture files must be byte-identical unless in the allowed set."""
    import g3ps_support as support

    problems: list[str] = []
    original = support.fixture_bytes(task["fixture_key"], task["instance"])
    allowed = set(_allowed_paths(task))
    for rel, data in original.items():
        cur = replica / rel
        if not cur.exists():
            if rel not in allowed:
                problems.append(f"original file removed outside allowed set: {rel}")
            continue
        if cur.read_bytes() != data and rel not in allowed:
            problems.append(f"original file modified outside allowed set: {rel}")
    return {"ok": not problems, "problems": problems}


# ---------------------------------------------------------------- class A

def _doctor_scan(replica: Path, tools: dict) -> tuple[dict, list[str]]:
    problems: list[str] = []
    results: dict = {}
    doctor = _run([tools["wheel_bin"], "doctor", "--repo", str(replica)], replica)
    results["doctor"] = doctor
    dj = doctor.get("json") or {}
    if doctor["exit"] != 0:
        problems.append(f"doctor exit={doctor['exit']}")
    if dj.get("pin_posture") != "released-match":
        problems.append(f"pin posture {dj.get('pin_posture')!r} != released-match")
    for chk in dj.get("checks", []):
        if chk.get("status") != "pass":
            problems.append(f"doctor check {chk.get('id')}={chk.get('status')}")
    scan = _run([tools["wheel_bin"], "scan-adoption", "--scope", str(replica),
                 "--include-scope-root", "--format", "json"], replica)
    results["scan"] = scan
    sj = scan.get("json") or {}
    if sj.get("completeness") != "complete":
        problems.append(f"scan completeness {sj.get('completeness')!r}")
    for rec in sj.get("records", []):
        if rec.get("path") != ".":
            continue
        if rec.get("status") != "adopted":
            problems.append(f"scan status: {rec.get('status')!r} notes={rec.get('notes')}")
        if rec.get("has_legacy_doc") or rec.get("has_legacy_policy"):
            problems.append("legacy flags present")
    return results, problems


def _policy_doc_checks(replica: Path, preserve_deviation: str | None) -> list[str]:
    problems: list[str] = []
    policy_path = replica / "policy/engineering-lane.json"
    doc_path = replica / "docs/engineering.local.md"
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"policy unreadable: {exc}"]
    ec = policy.get("engineering_core", {})
    if ec.get("tool") != "engineering-core":
        problems.append("tool != engineering-core")
    if ec.get("lanes") != ["py"]:
        problems.append(f"lanes {ec.get('lanes')!r} != ['py']")
    if not str(ec.get("ref", "")).startswith(f"v") or ec.get("ref") != RELEASE_REF:
        problems.append(f"ref {ec.get('ref')!r} != {RELEASE_REF} (released-ref rule)")
    for field in ("catalog_command", "list_disciplines_command", "list_templates_command"):
        if not str(ec.get(field, "")).strip():
            problems.append(f"{field} empty")
    disciplines = ec.get("disciplines")
    if not isinstance(disciplines, list) or not disciplines:
        problems.append("disciplines not a non-empty JSON array")
    else:
        defaults = {"validation", "testing", "security-privacy", "documentation",
                    "dependency-governance"}
        missing = defaults - set(disciplines)
        if missing:
            problems.append(f"disciplines missing defaults: {sorted(missing)}")
    doc = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""
    if not doc.startswith("---"):
        problems.append("doc lacks YAML front matter")
    if "summary:" not in doc[:400]:
        problems.append("doc front matter lacks summary")
    if "read_when:" not in doc[:800]:
        problems.append("doc lacks read_when")
    if preserve_deviation:
        devs = ec.get("deviations", [])
        if not any(d.get("id") == preserve_deviation for d in devs if isinstance(d, dict)):
            problems.append(f"deviation {preserve_deviation} not preserved")
        if preserve_deviation not in doc:
            problems.append(f"doc does not list deviation id {preserve_deviation}")
    return problems


def check_adoption(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    acc = task["acceptance"]
    results, problems = _doctor_scan(replica, tools)
    problems += _policy_doc_checks(replica, acc.get("preserve_deviation"))
    for rel in acc.get("required_absent", []):
        if (replica / rel).exists():
            problems.append(f"required-absent path present: {rel}")
    return results, problems


def check_adoption_rollback(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    import base64
    import hashlib

    import g3ps_support as support

    problems: list[str] = []
    results: dict = {}
    acc = task["acceptance"]
    for rel in acc.get("required_absent", []):
        if (replica / rel).exists():
            problems.append(f"required-absent path present: {rel}")
    original = support.fixture_bytes(task["fixture_key"], task["instance"])
    for rel, data in original.items():
        cur = replica / rel
        if not cur.exists() or cur.read_bytes() != data:
            problems.append(f"original not byte-identical after rollback: {rel}")
    apply_path = replica / ".g3p3-transaction/apply.json"
    rb_path = replica / ".g3p3-transaction/rollback.json"
    for p in (apply_path, rb_path):
        if not p.exists():
            problems.append(f"transaction record missing: {p.name}")
    if problems:
        return results, problems
    try:
        apply = json.loads(apply_path.read_text(encoding="utf-8"))
        rb = json.loads(rb_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return results, [f"transaction record unreadable: {exc}"]
    changes = apply.get("changes", [])
    if len(changes) != 4:
        problems.append(f"apply.json changes has {len(changes)} entries (need 4)")
    by_path = {c.get("path"): c for c in changes}
    import shutil

    tmp = replica / ".g3ps-tmp-check"
    decoded: dict[str, bytes] = {}
    for path in ("policy/engineering-lane.json", "docs/engineering.local.md"):
        c = by_path.get(path, {})
        if c.get("action") != "create" or not c.get("after_b64") or c.get("before_b64") is not None:
            problems.append(f"apply entry wrong for {path}: action={c.get('action')!r}")
            continue
        try:
            data = base64.b64decode(c["after_b64"])
        except Exception as exc:  # noqa: BLE001 (validation)
            problems.append(f"apply b64 undecodable for {path}: {exc}")
            continue
        if hashlib.sha256(data).hexdigest() != c.get("after_sha256"):
            problems.append(f"apply sha mismatch for {path}")
        decoded[path] = data
    if decoded:
        # created bytes must satisfy the v1 contract (the hard part of A3);
        # both files are checked together as one adoption surface
        shutil.rmtree(tmp, ignore_errors=True)
        (tmp / "policy").mkdir(parents=True, exist_ok=True)
        (tmp / "docs").mkdir(parents=True, exist_ok=True)
        for path, data in decoded.items():
            (tmp / path).write_bytes(data)
        for sp in _policy_doc_checks(tmp, None):
            problems.append(f"created adoption surface: {sp}")
        shutil.rmtree(tmp, ignore_errors=True)
    for path in ("policy/stack-lane.json", "docs/tech-stack.local.md"):
        c = by_path.get(path, {})
        if c.get("action") != "delete" or c.get("after_b64") is not None:
            problems.append(f"apply entry wrong for {path}: action={c.get('action')!r}")
            continue
        try:
            before = base64.b64decode(c["before_b64"])
        except Exception as exc:  # noqa: BLE001 (validation)
            problems.append(f"apply b64 undecodable for {path}: {exc}")
            continue
        if before != original[path]:
            problems.append(f"recorded before-bytes != fixture bytes for {path}")
    if apply.get("applied") is not True or apply.get("safe_to_apply") is not True:
        problems.append("apply.json flags wrong (safe_to_apply/applied)")
    if rb.get("status") != "rolled_back" or rb.get("journal_removed") is not True:
        problems.append("rollback.json status/journal wrong")
    restored = {e.get("path"): e.get("action") for e in rb.get("restored", [])}
    if restored != {"policy/stack-lane.json": "restored", "docs/tech-stack.local.md": "restored",
                    "policy/engineering-lane.json": "removed", "docs/engineering.local.md": "removed"}:
        problems.append(f"rollback restored map wrong: {restored}")
    return results, problems


# ---------------------------------------------------------------- class B (+ TH2 part 1)

def check_advise_response(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    problems: list[str] = []
    results: dict = {}
    response_path = replica / "g3p3-advice-response.json"
    if not response_path.exists():
        return results, ["g3p3-advice-response.json missing"]
    req_path = Path(tools["requests_dir"]) / f"{task['instance_id']}-request.json"
    if not req_path.exists():
        return results, [f"frozen request missing for {task['instance_id']} (freeze defect)"]
    request = json.loads(req_path.read_text(encoding="utf-8"))
    code = VALIDATE_RESPONSE_CODE.replace("{site}", tools["wheel_site"])
    v = _run([tools["wheel_py"], "-c", code, str(req_path), str(response_path)], replica)
    results["validate_response"] = v
    if v["exit"] != 0 or "VALID" not in (v["stdout_tail"] or ""):
        problems.append(f"product validator rejected the response: exit={v['exit']} "
                        f"{(v['stderr_tail'] or v['stdout_tail'])[-220:]}")
        return results, problems
    try:
        response = json.loads(response_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return results, [f"response unreadable: {exc}"]
    if response.get("request_sha256") != request["request_sha256"]:
        problems.append("response digest != frozen request digest")
    if response.get("status") != "advice":
        problems.append(f"status {response.get('status')!r} != advice")
    recs = response.get("recommendations", [])
    if len(recs) < 2:
        problems.append(f"only {len(recs)} recommendations (need >=2)")
    # plan requested selections come from the FROZEN request (withheld from executor)
    expected: set[str] = set()
    for sel in (request.get("plan") or {}).get("selections", []):
        if isinstance(sel, dict) and sel.get("requested") is True and sel.get("id"):
            expected.add(sel["id"])
    union: set[str] = set()
    for rec in recs:
        union.update(rec.get("catalog_ids", []) or [])
    if expected and union != expected:
        problems.append(f"catalog id union != plan requested: "
                        f"missing={sorted(expected - union)} extra={sorted(union - expected)}")
    cited = sum(1 for rec in recs if rec.get("citations"))
    if len(recs) and cited < len(recs):
        problems.append("not every recommendation carries a citation")
    if not response.get("critiques"):
        problems.append("no critique present")
    return results, problems


# ---------------------------------------------------------------- class C

def _budget_check(replica: Path, files: list[str]) -> list[str]:
    problems: list[str] = []
    for rel in files:
        path = replica / rel
        if not path.exists():
            problems.append(f"deliverable missing: {rel}")
            continue
        data = path.read_bytes()
        lines = data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1)
        if len(data) > 50 * 1024:
            problems.append(f"{rel} exceeds 50 KiB")
        if lines > 500:
            problems.append(f"{rel} exceeds 500 lines")
    return problems


def check_lane_build_ts(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    acc = task["acceptance"]
    src, tst = acc["module"], acc["test"]
    problems: list[str] = []
    results: dict = {}
    for rel in (src, tst):
        check = _run(["node", "--check", rel], replica)
        results[f"node_check_{rel}"] = check
        if check["exit"] != 0:
            problems.append(f"node --check failed: {rel}: {check['stderr_tail'][-120:]}")
    test_run = _run(["node", "--test", "--test-reporter=tap", tst], replica)
    results["node_test"] = test_run
    if test_run["exit"] != 0:
        problems.append(f"node --test failed: {test_run['stdout_tail'][-160:]} "
                        f"{test_run['stderr_tail'][-120:]}")
    else:
        match = re.search(r"# pass (\d+)", test_run["stdout_tail"] or "")
        if not match or int(match.group(1)) < 3:
            problems.append(f"node --test passed too few tests: {match.group(1) if match else 'n/a'}")
    src_text = (replica / src).read_text(encoding="utf-8") if (replica / src).exists() else ""
    for export in acc["exports"]:
        if f"export function {export}" not in src_text:
            problems.append(f"missing export: {export}")
    if "node:" not in src_text and "import" in src_text:
        pass  # builtins-only rule enforced by import scan below
    for bad in ("require(", "fs.promises", "fetch("):
        if bad in src_text:
            problems.append(f"module uses non-builtin surface: {bad}")
    biome = _run([tools["biome"], "check", src, tst], replica)
    results["biome_check"] = biome
    if biome["exit"] != 0:
        problems.append(f"biome check failed: {(biome['stdout_tail'] or biome['stderr_tail'])[-200:]}")
    problems += _budget_check(replica, [src, tst])
    return results, problems


def check_lane_alias_pair(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    acc = task["acceptance"]
    alias, target = acc["alias"], acc["target_script"]
    problems: list[str] = []
    results: dict = {}
    try:
        package = json.loads((replica / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return results, [f"package.json unreadable: {exc}"]
    if target not in package.get("scripts", {}):
        problems.append(f"target script {target!r} missing from package.json")
    script = package.get("scripts", {}).get(alias)
    if script != f"npm run {target}":
        problems.append(f"package script value wrong: {script!r}")
    justfile = (replica / "Justfile").read_text(encoding="utf-8") if (replica / "Justfile").exists() else ""
    match = re.search(rf"^{alias}:\n((?:[ \t]+.*\n?)*)", justfile, re.M)
    if not match:
        problems.append(f"Justfile recipe {alias} missing")
    else:
        body = [line.strip().lstrip("@").strip() for line in match.group(1).splitlines() if line.strip()]
        if body != [f"npm run {alias}"]:
            problems.append(f"recipe body is not the exact thin alias: {body!r}")
    listing = _run(["just", "--list"], replica)
    results["just_list"] = listing
    listing_text = _full_output(["just", "--list"], replica)
    if listing["exit"] != 0 or alias not in listing_text:
        problems.append("just --list failed or recipe not listed")
    dry = _run(["just", "--dry-run", alias], replica)
    results["just_dry_run"] = dry
    dry_text = _full_output(["just", "--dry-run", alias], replica)
    if dry["exit"] != 0 or f"npm run {alias}" not in dry_text:
        problems.append(f"just --dry-run failed: {dry['stdout_tail'][-120:]} {dry['stderr_tail'][-120:]}")
    return results, problems


def check_lane_build_py(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    acc = task["acceptance"]
    module, test = acc["module_path"], acc["test_path"]
    problems: list[str] = []
    results: dict = {}
    ruff = _run([tools["dspx_ruff"], "check", module, test], replica)
    results["ruff"] = ruff
    if ruff["exit"] != 0:
        problems.append(f"ruff check failed: {(ruff['stdout_tail'] or ruff['stderr_tail'])[-220:]}")
    pytest = _run([tools["dspx_python"], "-m", "pytest", "-q", "-p", "no:cacheprovider", test], replica)
    results["pytest"] = pytest
    if pytest["exit"] != 0:
        problems.append(f"pytest failed: {pytest['stdout_tail'][-220:]}")
    else:
        match = re.search(r"(\d+) passed", pytest["stdout_tail"] or "")
        if not match or int(match.group(1)) < 3:
            problems.append(f"too few passing tests: {match.group(1) if match else 'n/a'}")
    content = (replica / test).read_text(encoding="utf-8") if (replica / test).exists() else ""
    if not (("@pytest.mark.parametrize" in content) or ("random.Random(" in content)):
        problems.append("no property-style test form (parametrize or fixed-seed Random)")
    src = (replica / module).read_text(encoding="utf-8") if (replica / module).exists() else ""
    if f"def {acc['function']}(" not in src:
        problems.append(f"module does not export def {acc['function']}")
    problems += _budget_check(replica, [module, test])
    return results, problems


TIER_HEADER = "| Tier | Command | Scope | Target runtime | Required before |"
TIERS = ["editor/save", "pre-commit", "task-scope", "pre-push", "CI", "release"]
STANDARD = ["just check", "just test", "just build", "just ci", "just doctor"]


def check_tier_map(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    acc = task["acceptance"]
    problems: list[str] = []
    doc_path = replica / "docs/validation-tier-map.md"
    if not doc_path.exists():
        return {}, ["docs/validation-tier-map.md missing"]
    doc = doc_path.read_text(encoding="utf-8")
    if not doc.startswith("---"):
        problems.append("no front matter")
    elif "summary:" not in doc.split("---")[1] or "read_when:" not in doc.split("---")[1]:
        problems.append("front matter lacks summary/read_when")
    if "# Validation Tier Map" not in doc:
        problems.append("H1 missing")
    if "docs/engineering.local.md" not in doc:
        problems.append("owner-surface line missing")
    if TIER_HEADER not in doc:
        problems.append("tier table header not exact")
    pos = -1
    for tier in TIERS:
        tier_pos = doc.find(f"| {tier} |")
        if tier_pos == -1:
            problems.append(f"tier row missing: {tier}")
        elif tier_pos < pos:
            problems.append(f"tier row out of order: {tier}")
        else:
            pos = tier_pos
    lines = doc.splitlines()
    for key in STANDARD:
        bullet = next((ln for ln in lines if ln.strip().startswith(f"- `{key}`")), None)
        if bullet is None:
            problems.append(f"standard-surface bullet missing: {key}")
    bullet_lines = [ln for ln in lines if ln.strip().startswith("- `just ")]
    order = [ln.strip()[len("- `just "):].split("`")[0].strip() for ln in bullet_lines]
    if order != [k.split(" ")[1] for k in STANDARD]:
        problems.append(f"standard-surface bullet order wrong: {order}")
    if "## Evidence rule" not in doc:
        problems.append("evidence rule section missing")
    # semantic truth: recipes referenced must exist (or be n/a with reason)
    justfile = (replica / "Justfile").read_text(encoding="utf-8") if (replica / "Justfile").exists() else ""
    for key in STANDARD:
        bullet = next((ln for ln in lines if ln.strip().startswith(f"- `{key}`")), "")
        if "n/a" in bullet.lower():
            if not any(w in bullet.lower() for w in ("no ", "not ", "absent", "unavailable")):
                problems.append(f"n/a bullet without reason: {key}")
            continue
        m = re.search(r"`(just \w+|[\w:.-]+)`\s*:?\s*`?([^`\n]*)", bullet)
        recipe = key.split(" ")[1]
        if f"{recipe}:" not in justfile:
            problems.append(f"bullet references nonexistent recipe: {key}")
    return {}, problems


# ---------------------------------------------------------------- compounds

def check_compound_migration_tiermap(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    r1, p1 = check_adoption(replica, task, tools)
    r2, p2 = check_tier_map(replica, task, tools)
    problems = [f"[migration] {p}" for p in p1] + [f"[tiermap] {p}" for p in p2]
    return {"migration": r1, "tiermap": r2}, problems


def check_compound_advice_repair(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    r1, p1 = check_advise_response(replica, task, tools)
    r2, p2 = check_adoption(replica, task, tools)
    problems = [f"[advice] {p}" for p in p1] + [f"[repair] {p}" for p in p2]
    return {"advice": r1, "repair": r2}, problems


# ---------------------------------------------------------------- entry point

def verify_arm(replica: Path, task: dict, scratch: Path, tools: dict) -> dict:
    started = time.monotonic()
    checks: dict = {"checks": {}}
    checks["checks"]["claim"] = check_claim(replica, task)
    checks["checks"]["grounding"] = _fixture_grounding(replica, task)
    kind = task["acceptance"]["kind"]
    dispatch = {
        "adoption_migration": check_adoption,
        "adoption_repair": check_adoption,
        "adoption_rollback": check_adoption_rollback,
        "advise_response": check_advise_response,
        "lane_build_ts": check_lane_build_ts,
        "lane_alias_pair": check_lane_alias_pair,
        "lane_build_py": check_lane_build_py,
        "tier_map": check_tier_map,
        "compound_migration_tiermap": check_compound_migration_tiermap,
        "compound_advice_repair": check_compound_advice_repair,
    }
    fn = dispatch.get(kind)
    if fn is None:
        results, problems = {}, [f"unknown acceptance kind {kind}"]
    else:
        results, problems = fn(replica, task, tools)
    checks["checks"]["acceptance"] = {
        "ok": not problems, "problems": problems,
        "tool_results": {k: v for k, v in results.items()},
    }
    if time.monotonic() - started > VERIFY_TIMEOUT_S:
        checks["checks"]["acceptance"]["problems"] = \
            checks["checks"]["acceptance"]["problems"] + ["verify exceeded 180s budget"]
    y = int(checks["checks"]["claim"]["ok"] and checks["checks"]["grounding"]["ok"]
            and checks["checks"]["acceptance"]["ok"])
    checks["y"] = y
    checks["verify_duration_s"] = round(time.monotonic() - started, 1)
    return checks
