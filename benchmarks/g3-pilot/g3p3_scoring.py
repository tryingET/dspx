#!/usr/bin/env python3
"""G3 v3 pilot scoring + masked verification (DIAGNOSTIC ONLY; DSPx AK 5081).

Verification is masked by construction: `verify_arm` receives ONLY the task
descriptor, the worktree path, and tool paths — never the arm label or the
guidance. Y rules (v3 contract-conformance):

- intention-to-treat; Y=1 iff the arm's worktree satisfies ALL of:
  (a) claim file present, non-trivial, mentions the new file/symbol anchors,
  (b) grounding integrity: protected repository content byte-unchanged (or, for
      the rollback task, byte-EXACTLY restored), required-absent paths absent,
      no stray files beyond the allowed deliverables,
  (c) the frozen objective acceptance suite passes (deterministic, no network,
      <=180s; graded by the engineering-core 1.0.0 wheel itself for class A/B
      and by the real repos' pinned toolchain for class C),
- arm-attributable no-output (crash/timeout/no worktree change) is Y=0.

NOT gate evidence. NOT protocol authority. Diagnostic pilot only.
Checkers are FROZEN before execution and never relaxed after seeing results.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

import g3p3_corpus as corpus_mod

CLAIM_FILE = "G3P3_CLAIM.md"
MIN_CLAIM_CHARS = 200
VERIFY_TIMEOUT_S = 180
CMD_TIMEOUT_S = 120

DEFAULT_DISCIPLINES = {
    "validation", "testing", "security-privacy", "documentation", "dependency-governance",
}
RELEASE_REF = "v1.0.0"  # catalog release of the candidate-4 wheel (frozen)


def _run(cmd: list[str], cwd: Path, timeout: int = CMD_TIMEOUT_S) -> dict:
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        result = {
            "cmd": cmd[:3],
            "exit": proc.returncode,
            "stdout_tail": proc.stdout[-600:],
            "stderr_tail": proc.stderr[-300:],
            "duration_s": round(time.monotonic() - started, 1),
        }
        try:
            result["json"] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result["json"] = None
        return result
    except subprocess.TimeoutExpired:
        return {"cmd": cmd[:3], "exit": -1, "stdout_tail": "", "stderr_tail": "TIMEOUT",
                "duration_s": timeout, "json": None}


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _wheel(tools: dict, name: str) -> str:
    return tools[name]  # "wheel_bin" | "wheel_py"


# ---------------------------------------------------------------- claim + grounding

def check_claim(replica: Path, task: dict) -> dict:
    claim_path = replica / CLAIM_FILE
    text = claim_path.read_text(encoding="utf-8", errors="replace") if claim_path.exists() else ""
    anchors = list(task.get("new_files", [])) + list(task.get("new_symbols", []))
    ok = len(text) >= MIN_CLAIM_CHARS and any(a in text for a in anchors)
    return {"ok": bool(ok), "bytes": len(text)}


def _fixture_grounding(replica: Path, task: dict) -> dict:
    """Fixture repos: protected bytes vs frozen corpus contents + absence + no strays."""
    fixture = corpus_mod.FIXTURES[task["acceptance"]["fixture"]]
    deliverables = set(task.get("new_files", []))
    required_absent = set(task["acceptance"].get("required_absent", []))
    # A3's transaction dir is an allowed deliverable tree
    allowed_prefixes = tuple(p for p in deliverables if p.endswith("/"))
    restore_exact = task["acceptance"].get("restore_exact", False)

    problems: list[str] = []
    for rel, content in fixture.items():
        path = replica / rel
        if rel in required_absent:
            continue  # handled by absence check
        if rel in deliverables:
            # deliverable files are replaced/created by the task and are
            # validated by the acceptance checker; only presence is checked here
            if not path.exists():
                problems.append(f"deliverable file missing: {rel}")
            continue
        if not path.exists():
            problems.append(f"missing protected file: {rel}")
        elif path.read_bytes() != content.encode():
            problems.append(f"protected file modified: {rel}")
    for rel in required_absent:
        if (replica / rel).exists():
            problems.append(f"required-absent path present: {rel}")
    # stray files (anything not part of the frozen fixture or the deliverables)
    allowed_roots = set(fixture) | {CLAIM_FILE} | deliverables
    allowed_prefixes = tuple(p for p in deliverables if p.endswith("/"))
    fixture_dirs: set[str] = set()
    for rel in fixture:
        parent = Path(rel).parent
        while str(parent) != ".":
            fixture_dirs.add(str(parent))
            parent = parent.parent
    deliverable_parents = {str(Path(d).parent) for d in deliverables if "/" in d}
    for path in sorted(replica.rglob("*")):
        if ".git/" in str(path.relative_to(replica)) or path.name == ".git":
            continue
        rel = path.relative_to(replica).as_posix()
        if path.is_dir():
            if rel.startswith(".g3p3-transaction") or rel == ".engineering-core" \
                    or rel in deliverable_parents or rel in fixture_dirs:
                continue
            problems.append(f"unexpected directory: {rel}/")
            continue
        if rel in allowed_roots or rel.startswith(allowed_prefixes) \
                or rel.startswith(".g3p3-transaction/"):
            continue
        problems.append(f"unexpected extra file: {rel}")
    return {"ok": not problems, "problems": problems[:12]}


def _repo_grounding(replica: Path, task: dict) -> dict:
    """Real-repo replicas: tracked files unchanged except allowed modifications;
    untracked files limited to allowed deliverables (+claim)."""
    allowed_mod = set(task["acceptance"].get("allowed_modified", []))
    deliverables = set(task.get("new_files", []))
    diff = _run(["git", "diff", "--name-only", "HEAD"], replica)["stdout_tail"]
    modified = [l for l in diff.splitlines() if l.strip()]
    bad_mod = [m for m in modified if m.strip() not in allowed_mod]
    status = _run(["git", "status", "--porcelain"], replica)["stdout_tail"]
    untracked = [l[3:] for l in status.splitlines() if l.startswith("??")]
    allowed_new = deliverables | {CLAIM_FILE}
    bad_new = [u for u in untracked if u.rstrip("/") not in allowed_new
               and not u.startswith(tuple(d for d in deliverables if d.endswith("/")))]
    problems = ([f"modified tracked file: {m}" for m in bad_mod]
                + [f"unexpected new file: {u}" for u in bad_new])
    return {"ok": not problems, "problems": problems[:12]}


# ---------------------------------------------------------------- class A checkers

def _policy_doc_checks(replica: Path, preserve_deviation: str | None) -> list[str]:
    problems: list[str] = []
    policy_path = replica / "policy/engineering-lane.json"
    doc_path = replica / "docs/engineering.local.md"
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"policy unreadable: {exc}"]
    ec = policy.get("engineering_core") if isinstance(policy, dict) else None
    if not isinstance(ec, dict):
        return ["policy has no engineering_core object"]
    if ec.get("tool") != "engineering-core":
        problems.append("engineering_core.tool != engineering-core")
    if ec.get("lanes") != ["py"]:
        problems.append(f"lanes != ['py']: {ec.get('lanes')!r}")
    if ec.get("ref") != RELEASE_REF:
        problems.append(f"ref != {RELEASE_REF}: {ec.get('ref')!r}")
    for field in ("catalog_command", "list_disciplines_command", "list_templates_command"):
        value = ec.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"missing/empty command field: {field}")
    disciplines = ec.get("disciplines")
    if not isinstance(disciplines, list) or not disciplines:
        problems.append("disciplines is not a non-empty array")
    else:
        if not isinstance(disciplines[0], str):
            problems.append("disciplines entries must be strings")
        missing = DEFAULT_DISCIPLINES - set(disciplines)
        if missing:
            problems.append(f"disciplines missing defaults: {sorted(missing)}")
    if not isinstance(ec.get("deviations"), list):
        problems.append("deviations is not a list")
    if preserve_deviation:
        entries = [d for d in ec.get("deviations", []) if isinstance(d, dict)
                   and d.get("id") == preserve_deviation]
        if len(entries) != 1:
            problems.append(f"deviation {preserve_deviation!r} not preserved exactly once")
        else:
            entry = entries[0]
            for key in ("reason", "owner", "evidence", "review_date"):
                if key not in entry:
                    problems.append(f"deviation lost field {key}")
            if entry.get("review_date") != "2026-09-30":
                problems.append("deviation review_date changed")
    doc = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""
    if not doc:
        problems.append("docs/engineering.local.md missing")
    else:
        fm = re.match(r"^---\n(.*?)\n---\n", doc, re.S)
        if not fm:
            problems.append("doc lacks YAML front matter")
        else:
            head = fm.group(1)
            if "summary:" not in head:
                problems.append("front matter lacks summary")
            if "read_when" not in head:
                problems.append("front matter lacks read_when")
        low = doc.lower()
        if "`py`" not in low and "py" not in low:
            problems.append("doc does not name the selected lane")
        if "validation" not in low:
            problems.append("doc lacks validation-evidence expectation")
        if "deviation" not in low:
            problems.append("doc lacks deliberate-deviations section")
        if isinstance(disciplines, list):
            for d in disciplines:
                if isinstance(d, str) and d not in doc:
                    problems.append(f"doc does not list discipline {d}")
                    break
    return problems


def _doctor_scan(replica: Path, tools: dict) -> tuple[dict, list[str]]:
    problems: list[str] = []
    doctor = _run([tools["wheel_bin"], "doctor", "--repo", str(replica)], replica)
    report = doctor.get("json") if isinstance(doctor.get("json"), dict) else {}
    doctor_ok = bool(report)
    if not doctor_ok:
        problems.append(f"doctor produced no JSON report: exit={doctor['exit']} "
                        f"{doctor['stderr_tail'][-140:]}")
    if doctor_ok and report:
        if report.get("pin_posture") != "released-match":
            problems.append(f"pin posture: {report.get('pin_posture')!r}")
        for check in report.get("checks", []):
            if check.get("status") != "pass":
                problems.append(f"doctor check {check.get('id')}={check.get('status')}")
    scan = _run([tools["wheel_bin"], "scan-adoption", "--scope", str(replica),
                 "--include-scope-root", "--format", "json"], replica)
    payload = scan.get("json") if isinstance(scan.get("json"), dict) else {}
    records = payload.get("records", [])
    scan_ok = bool(payload)
    if not scan_ok:
        problems.append(f"scan produced no JSON report: exit={scan['exit']} "
                        f"{scan['stderr_tail'][-140:]}")
    else:
        if payload.get("completeness") != "complete":
            problems.append(f"scan completeness: {payload.get('completeness')!r}")
    if scan_ok and records:
        record = records[0]
        if record.get("status") != "adopted":
            problems.append(f"scan status: {record.get('status')!r} notes={record.get('notes', [])[:4]}")
    results = {"doctor": doctor, "scan": scan}
    return results, problems


def check_adoption(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    results, problems = _doctor_scan(replica, tools)
    problems += _policy_doc_checks(replica, task["acceptance"].get("preserve_deviation"))
    return results, problems


def check_adoption_rollback(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    problems: list[str] = []
    fixture = corpus_mod.FIXTURES[task["acceptance"]["fixture"]]
    results: dict = {}
    apply_path = replica / ".g3p3-transaction/apply.json"
    rollback_path = replica / ".g3p3-transaction/rollback.json"
    if not apply_path.exists() or not rollback_path.exists():
        return results, ["transaction record missing (.g3p3-transaction/apply.json|rollback.json)"]
    try:
        apply_rec = json.loads(apply_path.read_text(encoding="utf-8"))
        rollback_rec = json.loads(rollback_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return results, [f"transaction record unreadable: {exc}"]
    if apply_rec.get("mode") != "migrate" or apply_rec.get("safe_to_apply") is not True \
            or apply_rec.get("applied") is not True:
        problems.append("apply.json mode/safe_to_apply/applied wrong")
    if apply_rec.get("lanes") != ["py"]:
        problems.append("apply.json lanes != ['py']")
    disciplines = apply_rec.get("disciplines")
    if not isinstance(disciplines, list) or not DEFAULT_DISCIPLINES.issubset(set(disciplines)):
        problems.append("apply.json disciplines missing the five defaults")
    changes = apply_rec.get("changes")
    if not isinstance(changes, list) or len(changes) != 4:
        problems.append("apply.json must record exactly 4 changes")
        changes = []
    import base64
    expected_actions = {
        "policy/engineering-lane.json": "create",
        "docs/engineering.local.md": "create",
        "policy/stack-lane.json": "delete",
        "docs/tech-stack.local.md": "delete",
    }
    decoded_policy: dict | None = None
    decoded_doc: str | None = None
    for change in changes:
        path = change.get("path")
        action = change.get("action")
        if expected_actions.get(path) != action:
            problems.append(f"change {path!r} action {action!r} unexpected")
            continue
        before_b64, after_b64 = change.get("before_b64"), change.get("after_b64")
        before_sha, after_sha = change.get("before_sha256"), change.get("after_sha256")
        if action == "create":
            if before_b64 is not None or before_sha is not None:
                problems.append(f"{path}: create must have null before")
            if not isinstance(after_b64, str) or not isinstance(after_sha, str):
                problems.append(f"{path}: create missing after bytes/digest")
                continue
            raw = base64.b64decode(after_b64)
            if _sha_bytes(raw) != after_sha:
                problems.append(f"{path}: after digest mismatch")
            if path == "policy/engineering-lane.json":
                try:
                    decoded_policy = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    problems.append("decoded apply-phase policy is not valid JSON")
            else:
                decoded_doc = raw.decode("utf-8", errors="replace")
        else:
            if after_b64 is not None or after_sha is not None:
                problems.append(f"{path}: delete must have null after")
            if not isinstance(before_b64, str) or not isinstance(before_sha, str):
                problems.append(f"{path}: delete missing before bytes/digest")
                continue
            raw = base64.b64decode(before_b64)
            if _sha_bytes(raw) != before_sha:
                problems.append(f"{path}: before digest mismatch")
            frozen = fixture.get(path, "")
            if raw != frozen.encode():
                problems.append(f"{path}: recorded before bytes != repository original bytes")
    if isinstance(decoded_policy, dict):
        ec = decoded_policy.get("engineering_core")
        if not isinstance(ec, dict):
            problems.append("apply-phase policy lacks engineering_core")
        else:
            if ec.get("tool") != "engineering-core" or ec.get("lanes") != ["py"] \
                    or ec.get("ref") != RELEASE_REF:
                problems.append("apply-phase policy tool/lanes/ref wrong")
            for field in ("catalog_command", "list_disciplines_command", "list_templates_command"):
                if not isinstance(ec.get(field), str) or not ec.get(field, "").strip():
                    problems.append(f"apply-phase policy missing {field}")
            ds = ec.get("disciplines")
            if not isinstance(ds, list) or not DEFAULT_DISCIPLINES.issubset(set(ds or [])):
                problems.append("apply-phase policy disciplines missing defaults")
    else:
        problems.append("apply-phase policy not decodable from apply.json")
    if decoded_doc is not None:
        if not re.match(r"^---\n(.*?)\n---\n", decoded_doc, re.S):
            problems.append("apply-phase doc lacks front matter")
    if rollback_rec.get("command") != "rollback" or rollback_rec.get("status") != "rolled_back" \
            or rollback_rec.get("journal_removed") is not True:
        problems.append("rollback.json command/status/journal_removed wrong")
    restored = {(e.get("path"), e.get("action")) for e in rollback_rec.get("restored", [])
                if isinstance(e, dict)}
    expected_restored = {
        ("policy/stack-lane.json", "restored"),
        ("docs/tech-stack.local.md", "restored"),
        ("policy/engineering-lane.json", "removed"),
        ("docs/engineering.local.md", "removed"),
    }
    if restored != expected_restored:
        problems.append(f"rollback restored set wrong: {sorted(restored)}")
    return results, problems


# ---------------------------------------------------------------- class B checker

PLAN_SELECTIONS_CODE = """
import json, sys
sys.path.insert(0, "{site}")
from pathlib import Path
from engineering_core.catalog import load_catalog
from engineering_core.engineering_plan import compile_plan
repo = Path(sys.argv[1])
catalog = load_catalog()
plan = compile_plan(repo, catalog)
print(json.dumps({{"status": plan["status"],
                   "requested": [s["id"] for s in plan["selections"] if s.get("requested")]}}))
"""


def check_advise_response(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    problems: list[str] = []
    response_path = replica / "g3p3-advice-response.json"
    if not response_path.exists():
        return {}, ["g3p3-advice-response.json missing"]
    validate = _run([tools["wheel_bin"], "advise", "--repo", str(replica),
                     "--response", str(response_path)], replica)
    results = {"advise_validate": validate}
    # The CLI exits nonzero (SystemExit "advice rejected: ...") on any validation
    # failure; exit 0 means the product accepted the response.
    if validate["exit"] != 0:
        problems.append(f"product validator rejected the response: exit={validate['exit']} "
                        f"{(validate['stderr_tail'] or validate['stdout_tail'])[-220:]}")
        return results, problems
    plan_info = _run([tools["wheel_py"], "-c",
                      PLAN_SELECTIONS_CODE.format(site=tools["wheel_site"]), str(replica)], replica)
    expected: set[str] = set()
    if plan_info["exit"] == 0:
        try:
            expected = set(json.loads(plan_info["stdout_tail"].strip().splitlines()[-1])["requested"])
        except (json.JSONDecodeError, IndexError, KeyError):
            problems.append("could not derive expected plan selections")
    else:
        problems.append("plan compilation failed during grading")
    try:
        response = json.loads(response_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return results, [f"response unreadable: {exc}"]
    if response.get("status") != "advice":
        problems.append(f"status {response.get('status')!r} != advice")
    recs = response.get("recommendations", [])
    if len(recs) < 2:
        problems.append(f"only {len(recs)} recommendations (need >=2)")
    union: set[str] = set()
    for rec in recs:
        union.update(rec.get("catalog_ids", []) or [])
    if expected and union != expected:
        problems.append(f"catalog id union != plan requested selections: "
                        f"missing={sorted(expected - union)} extra={sorted(union - expected)}")
    cited = 0
    for rec in recs:
        if rec.get("citations"):
            cited += 1
    if len(recs) and cited < len(recs):
        problems.append("not every recommendation carries a citation")
    if not response.get("critiques"):
        problems.append("no critique present")
    return results, problems


# ---------------------------------------------------------------- class C checkers

def _budget_check(replica: Path, files: list[str]) -> list[str]:
    problems = []
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
    pkg = replica / "packages/pi-context-packer"
    src = "src/g3p3-header-audit.js"
    tst = "tests/g3p3-header-audit.test.js"
    problems: list[str] = []
    results: dict = {}
    for rel in (src, tst):
        check = _run(["node", "--check", rel], pkg)
        results[f"node_check_{rel.split('/')[-1]}"] = check
        if check["exit"] != 0:
            problems.append(f"node --check failed: {rel}: {check['stderr_tail'][-120:]}")
    test_run = _run(["node", "--test", "--test-reporter=tap", tst], pkg)
    results["node_test"] = test_run
    if test_run["exit"] != 0:
        problems.append(f"node --test failed: {test_run['stdout_tail'][-160:]} "
                        f"{test_run['stderr_tail'][-120:]}")
    else:
        match = re.search(r"# pass (\d+)", test_run["stdout_tail"] or "")
        if not match or int(match.group(1)) < 3:
            problems.append(f"node --test passed too few tests: {match.group(1) if match else 'n/a'}")
    biome = _run([tools["biome"], "check", src, tst], pkg)
    results["biome_check"] = biome
    if biome["exit"] != 0:
        problems.append(f"biome check failed: {(biome['stdout_tail'] or biome['stderr_tail'])[-200:]}")
    problems += _budget_check(pkg, [src, tst])
    return results, problems


def _full_output(cmd: list[str], cwd: Path, timeout: int = 60) -> str:
    """Combined stdout+stderr (bounded) for substring checks on chatty tools."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return (proc.stdout + "\n" + proc.stderr)[-20000:]
    except subprocess.TimeoutExpired:
        return ""


def check_lane_alias_pair(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    problems: list[str] = []
    results: dict = {}
    try:
        package = json.loads((replica / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return results, [f"package.json unreadable: {exc}"]
    script = package.get("scripts", {}).get("g3p3-contracts-quick")
    if script != "npm run release:contracts:validate":
        problems.append(f"package script value wrong: {script!r}")
    justfile = (replica / "Justfile").read_text(encoding="utf-8")
    match = re.search(r"^g3p3-contracts-quick:\n((?:[ \t]+.*\n?)*)", justfile, re.M)
    if not match:
        problems.append("Justfile recipe g3p3-contracts-quick missing")
    else:
        body = [line.strip().lstrip("@").strip() for line in match.group(1).splitlines() if line.strip()]
        if body != ["npm run g3p3-contracts-quick"]:
            problems.append(f"recipe body is not the exact thin alias: {body!r}")
    listing = _run(["just", "--list"], replica)
    results["just_list"] = listing
    # just prints --list to stdout (long) and --dry-run output to stderr; check
    # combined full output, not the truncated tails.
    listing_text = _full_output(["just", "--list"], replica)
    if listing["exit"] != 0 or "g3p3-contracts-quick" not in listing_text:
        problems.append("just --list failed or recipe not listed")
    dry = _run(["just", "--dry-run", "g3p3-contracts-quick"], replica)
    results["just_dry_run"] = dry
    dry_text = _full_output(["just", "--dry-run", "g3p3-contracts-quick"], replica)
    if dry["exit"] != 0 or "npm run g3p3-contracts-quick" not in dry_text:
        problems.append(f"just --dry-run failed: {dry['stdout_tail'][-120:]} {dry['stderr_tail'][-120:]}")
    return results, problems


def check_lane_build_py(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    module = "packages/dspx-core/src/dspx/g3p3_token_budget.py"
    test = "tests/test_g3p3_token_budget.py"
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
    if "sum(" not in content:
        problems.append("property test does not assert the sum invariant")
    problems += _budget_check(replica, [module, test])
    return results, problems


def check_tier_map(replica: Path, task: dict, tools: dict) -> tuple[dict, list[str]]:
    path = replica / "docs/validation-tier-map.md"
    problems: list[str] = []
    if not path.exists():
        return {}, ["docs/validation-tier-map.md missing"]
    doc = path.read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", doc, re.S)
    if not fm:
        problems.append("no YAML front matter")
    else:
        head = fm.group(1)
        if "summary:" not in head or "read_when" not in head:
            problems.append("front matter lacks summary/read_when")
    if "# Validation Tier Map" not in doc:
        problems.append("H1 title missing")
    if "docs/engineering.local.md" not in doc:
        problems.append("owner surface line missing")
    tiers = ["editor/save", "pre-commit", "task-scope", "pre-push", "CI", "release"]
    header = "| Tier | Command | Scope | Target runtime | Required before |"
    if header not in doc:
        problems.append("tier table header not exact")
    else:
        rows = [l for l in doc.splitlines() if l.startswith("| ") and not l.startswith("| Tier")
                and "---" not in l]
        tier_cells = [r.split("|")[1].strip() for r in rows if len(r.split("|")) > 2]
        if tier_cells != tiers:
            problems.append(f"tier rows wrong: {tier_cells}")
        for row in rows:
            cells = [c.strip() for c in row.split("|")]
            if len(cells) > 2 and not cells[2]:
                problems.append(f"tier row has empty command: {row[:60]}")
    section = re.search(r"## Standard surface\n(.*?)(?:\n## |\Z)", doc, re.S)
    if not section:
        problems.append("## Standard surface section missing")
    else:
        justfile = (replica / "Justfile").read_text(encoding="utf-8") if (replica / "Justfile").exists() else ""
        recipes = set(re.findall(r"^([a-zA-Z0-9_-]+):", justfile, re.M))
        keys = ["just check", "just test", "just build", "just ci", "just doctor"]
        bullets = re.findall(r"^- `(just [a-z]+)`:\s*`([^`]*)`", section.group(1), re.M)
        got_keys = [b[0] for b in bullets]
        if got_keys != keys:
            problems.append(f"standard surface bullets wrong/order: {got_keys}")
        for key, mapping in bullets:
            target = key.split()[1]
            tokens = set(re.findall(r"[A-Za-z0-9_./-]+", mapping))
            hits_recipe = bool(tokens & recipes) or any(t in recipes for t in tokens)
            is_na = "n/a" in mapping.lower()
            if target == "build":
                # dspx has no build recipe: a truthful mapping is n/a (+reason);
                # referencing a real recipe here would invent a fake build target.
                if not is_na:
                    problems.append(f"`just build` must be n/a with a reason (no build "
                                    f"recipe exists): {mapping!r}")
            elif not (hits_recipe or is_na or "scripts/" in mapping):
                problems.append(f"`{key}` mapping not a real command: {mapping!r}")
    evidence = re.search(r"## Evidence rule\n(.*?)(?:\n## |\Z)", doc, re.S)
    if not evidence:
        problems.append("## Evidence rule section missing")
    else:
        block = evidence.group(1).lower()
        for word in ("command", "scope", "result", "warning", "artifact"):
            if word not in block:
                problems.append(f"evidence rule lacks '{word}'")
                break
    return {}, problems


# ---------------------------------------------------------------- dispatch

def verify_arm(replica: Path, task: dict, scratch: Path, tools: dict) -> dict:
    started = time.monotonic()
    checks: dict = {"checks": {}}
    checks["checks"]["claim"] = check_claim(replica, task)

    acc = task["acceptance"]
    if acc.get("fixture"):
        grounding = _fixture_grounding(replica, task)
    else:
        grounding = _repo_grounding(replica, task)
    checks["checks"]["grounding"] = grounding

    kind = acc["kind"]
    if kind in ("adoption_migration", "adoption_repair"):
        results, problems = check_adoption(replica, task, tools)
    elif kind == "adoption_rollback":
        results, problems = check_adoption_rollback(replica, task, tools)
    elif kind == "advise_response":
        results, problems = check_advise_response(replica, task, tools)
    elif kind == "lane_build_ts":
        results, problems = check_lane_build_ts(replica, task, tools)
    elif kind == "lane_alias_pair":
        results, problems = check_lane_alias_pair(replica, task, tools)
    elif kind == "lane_build_py":
        results, problems = check_lane_build_py(replica, task, tools)
    elif kind == "tier_map":
        results, problems = check_tier_map(replica, task, tools)
    else:
        results, problems = {}, [f"unknown acceptance kind {kind}"]
    checks["checks"]["acceptance"] = {
        "ok": not problems,
        "problems": problems,
        "tool_results": {k: v for k, v in results.items()},
    }
    if time.monotonic() - started > VERIFY_TIMEOUT_S:
        checks["checks"]["acceptance"]["problems"] = \
            checks["checks"]["acceptance"]["problems"] + ["verify exceeded 180s budget"]
    y = int(checks["checks"]["claim"]["ok"] and grounding["ok"]
            and checks["checks"]["acceptance"]["ok"])
    checks["y"] = y
    checks["verify_duration_s"] = round(time.monotonic() - started, 1)
    return checks
