#!/usr/bin/env python3
"""

v3b COPY (DSPx AK task 5085, G3 v3b re-run after the AK-5082 advise-surface fix).
Derived from the frozen v3 module by EXACT string replacement only; every delta is
recorded in docs/v1-proof/g3pilot-v3b-state.json under v3b_deviations. The v3
originals are untouched.
G3 v3 pilot support mechanics (DIAGNOSTIC ONLY; DSPx AK task 5081).

Replica materialization, reference-solution installation, and stub installation
for calibration. Reference solutions prove each frozen checker is satisfiable;
stubs prove the checkers are not trivially passable. Neither is ever shown to
an executor.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

import g3p3b_corpus as corpus_mod

HERE = Path(__file__).resolve().parent
REF = HERE / "ref3b"
V3BROOT = Path(__import__("os").environ.get("TMPDIR", "/tmp")) / "g3pilot-v3b-5085"

TOOLS = {
    "wheel_bin": str(V3BROOT / "venv/bin/engineering-core"),
    "wheel_py": str(V3BROOT / "venv/bin/python"),
    "wheel_site": str(V3BROOT / "venv/lib/python3.13/site-packages"),
    "biome": "/home/tryinget/ai-society/softwareco/owned/pi-extensions/packages/pi-context-packer/node_modules/.bin/biome",
    "dspx_ruff": "/home/tryinget/ai-society/softwareco/owned/dspx/.venv/bin/ruff",
    "dspx_python": "/home/tryinget/ai-society/softwareco/owned/dspx/.venv/bin/python",
}

GIT_ENV = {
    "GIT_AUTHOR_NAME": "g3p3", "GIT_AUTHOR_EMAIL": "g3p3@localhost",
    "GIT_COMMITTER_NAME": "g3p3", "GIT_COMMITTER_EMAIL": "g3p3@localhost",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def materialize_fixture(fixture_key: str, dest: Path) -> Path:
    if dest.exists():
        subprocess.run(["rm", "-rf", str(dest)], check=True)
    for rel, content in corpus_mod.FIXTURES[fixture_key].items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True, env=GIT_ENV)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=dest, check=True, env=GIT_ENV)
    return dest


def clone_repo(repo_key: str, dest: Path) -> Path:
    cfg = corpus_mod.REPOS[repo_key]
    if dest.exists():
        subprocess.run(["rm", "-rf", str(dest)], check=True)
    proc = subprocess.run(["git", "clone", "-q", "--no-hardlinks", cfg["local_path"], str(dest)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"clone failed: {proc.stderr[:300]}")
    subprocess.run(["git", "checkout", "-q", "--detach", cfg["pin"]], cwd=dest, check=True)
    return dest


def make_replica(task: dict, dest: Path) -> Path:
    acc = task["acceptance"]
    if acc.get("fixture"):
        return materialize_fixture(acc["fixture"], dest)
    return clone_repo(task["repo"], dest)


def write_claim(replica: Path, task: dict, note: str) -> None:
    anchors = list(task.get("new_files", [])) + list(task.get("new_symbols", []))
    lines = [
        "# G3P3 claim",
        "",
        f"note: {note}",
        "",
        "## Files changed or created",
    ]
    lines += [f"- `{a}`" for a in anchors]
    lines += [
        "",
        "## Specification clauses",
        "- All clauses satisfied by the deliverables above.",
        "",
        "## Verification",
        "- Reference solution installed for calibration; checker-verified.",
    ]
    (replica / "G3P3_CLAIM.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- B reference

PLAN_SELECTIONS = (
    "import json, sys\n"
    "sys.path.insert(0, {site!r})\n"
    "from pathlib import Path\n"
    "from engineering_core.catalog import load_catalog\n"
    "from engineering_core.engineering_plan import compile_plan\n"
    "catalog = load_catalog()\n"
    "plan = compile_plan(Path(sys.argv[1]), catalog)\n"
    "print(json.dumps([s['id'] for s in plan['selections'] if s.get('requested')]))\n"
)


def compile_request(replica: Path, out_path: Path) -> dict:
    proc = subprocess.run([TOOLS["wheel_bin"], "advise", "--repo", str(replica),
                           "--request-out", str(out_path)],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"advise --request-out failed: {proc.stderr[-300:]}")
    return json.loads(out_path.read_text(encoding="utf-8"))


def build_b_reference(task: dict, replica: Path) -> None:
    """Construct a product-valid reference response bound to the compiled request."""
    req_path = replica.parent / f"req-{task['task_id']}.json"
    if req_path.exists():
        req_path.unlink()
    request = compile_request(replica, req_path)
    proc = subprocess.run([TOOLS["wheel_py"], "-c",
                           PLAN_SELECTIONS.format(site=TOOLS["wheel_site"]), str(replica)],
                          capture_output=True, text=True, timeout=120)
    expected = sorted(json.loads(proc.stdout.strip().splitlines()[-1]))
    evidence = request["evidence"]
    primary = evidence[0]
    span_end = primary["span"]["end"]
    citation = {"evidence_id": primary["id"], "path": primary["path"],
                "start": 0, "end": min(120, span_end - 1) if span_end > 1 else span_end}
    lanes = [i for i in expected if i in ("py", "ts", "ts-frontend", "pi-ts", "rust", "go")]
    disciplines = [i for i in expected if i not in lanes]
    response = {
        "schema": "engineering-advice-response-v1",
        "request_sha256": request["request_sha256"],
        "provenance": {
            "provider": "reference", "model": "ref", "model_version": "1",
            "adapter": "calibrate", "adapter_version": "1",
            "prompt_id": request["prompt"]["id"], "prompt_version": request["prompt"]["version"],
        },
        "status": "advice",
        "summary": "Reference calibration response: select the repository's lanes and default disciplines.",
        "recommendations": [
            {
                "id": "r1",
                "catalog_ids": lanes,
                "recommendation": f"Adopt the {', '.join(lanes)} lane selection for this repository.",
                "confidence": 0.9,
                "unknowns": [],
                "counterevidence": [],
                "falsification": ["A manifest change that invalidates lane inference would falsify this."],
                "citations": [citation],
                "competes_with": [],
            },
            {
                "id": "r2",
                "catalog_ids": disciplines,
                "recommendation": "Adopt the default cross-language disciplines for this repository state.",
                "confidence": 0.85,
                "unknowns": [],
                "counterevidence": [],
                "falsification": ["A policy declaring a different discipline set would falsify this."],
                "citations": [citation],
                "competes_with": ["r1"],
            },
        ],
        "critiques": [
            {
                "recommendation_id": "r1",
                "critique": "Lane inference depends on manifests remaining declarative and readable.",
                "severity": "low",
                "falsification": "Removing the manifest would change lane inference.",
            }
        ],
        "patch_proposals": [],
    }
    if span_end <= 1:
        raise RuntimeError("fixture evidence too small to cite")
    out = replica / "g3p3-advice-response.json"
    out.write_text(json.dumps(response, indent=1) + "\n", encoding="utf-8")
    check = subprocess.run([TOOLS["wheel_bin"], "advise", "--repo", str(replica),
                            "--response", str(out)],
                           capture_output=True, text=True, timeout=120)
    if check.returncode != 0:
        raise RuntimeError(f"reference B response failed product validation: {check.stderr[-400:]}")


# ---------------------------------------------------------------- reference install

def install_reference(task: dict, replica: Path) -> None:
    tid = task["task_id"]
    if tid == "A1":
        (replica / "policy").mkdir(exist_ok=True)
        (replica / "policy/engineering-lane.json").write_bytes((REF / "a_policy.json").read_bytes())
        (replica / "docs").mkdir(exist_ok=True)
        (replica / "docs/engineering.local.md").write_bytes((REF / "a1_doc.md").read_bytes())
        (replica / "policy/stack-lane.json").unlink()
        (replica / "docs/tech-stack.local.md").unlink()
    elif tid == "A2":
        policy = json.loads((REF / "a_policy.json").read_text(encoding="utf-8"))
        policy["engineering_core"]["deviations"] = [{
            "id": "keep-local-uv-mirror",
            "reason": "CI mirrors PyPI through a local uv cache; upstream freshness gates do not apply",
            "owner": "platform-team",
            "evidence": ["gitlab/ci/uv-config.toml"],
            "review_date": "2026-09-30",
        }]
        (replica / "policy/engineering-lane.json").write_text(
            json.dumps(policy, indent=2) + "\n", encoding="utf-8")
        (replica / "docs/engineering.local.md").write_bytes((REF / "a2_doc.md").read_bytes())
    elif tid == "A3":
        _install_a3_reference(task, replica)
    elif tid in ("B1", "B2", "B3"):
        build_b_reference(task, replica)
    elif tid == "C1":
        pkg = replica / "packages/pi-context-packer"
        (pkg / "src/g3p3-header-audit.js").write_bytes((REF / "c1_header_audit.js").read_bytes())
        (pkg / "tests/g3p3-header-audit.test.js").write_bytes(
            (REF / "c1_header_audit.test.js").read_bytes())
    elif tid == "C2":
        package_path = replica / "package.json"
        package = json.loads(package_path.read_text(encoding="utf-8"))
        package.setdefault("scripts", {})["g3p3-contracts-quick"] = "npm run release:contracts:validate"
        package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
        justfile = replica / "Justfile"
        justfile.write_text(
            justfile.read_text(encoding="utf-8").rstrip("\n")
            + "\n\n# G3P3 quick contract validation (thin alias over the package script)\n"
              "g3p3-contracts-quick:\n"
              "    npm run g3p3-contracts-quick\n",
            encoding="utf-8")
    elif tid == "C3":
        (replica / "packages/dspx-core/src/dspx/g3p3_token_budget.py").write_bytes(
            (REF / "c3_token_budget.py").read_bytes())
        (replica / "tests/test_g3p3_token_budget.py").write_bytes(
            (REF / "c3_token_budget.test.py").read_bytes())
    elif tid == "C4":
        (replica / "docs/validation-tier-map.md").write_bytes((REF / "c4_tier_map.md").read_bytes())
    else:
        raise ValueError(tid)


def _install_a3_reference(task: dict, replica: Path) -> None:
    policy_bytes = (REF / "a_policy.json").read_bytes()
    doc_bytes = (REF / "a1_doc.md").read_bytes()
    legacy_policy = corpus_mod.FIXTURES[task["acceptance"]["fixture"]]["policy/stack-lane.json"].encode()
    legacy_doc = corpus_mod.FIXTURES[task["acceptance"]["fixture"]]["docs/tech-stack.local.md"].encode()
    policy = json.loads(policy_bytes.decode("utf-8"))

    def entry(path, action, before: bytes | None, after: bytes | None) -> dict:
        return {
            "path": path, "action": action,
            "before_sha256": sha256_bytes(before) if before is not None else None,
            "after_sha256": sha256_bytes(after) if after is not None else None,
            "before_b64": base64.b64encode(before).decode("ascii") if before is not None else None,
            "after_b64": base64.b64encode(after).decode("ascii") if after is not None else None,
        }

    apply_rec = {
        "mode": "migrate", "repo": str(replica.resolve()),
        "lanes": ["py"], "disciplines": policy["engineering_core"]["disciplines"],
        "changes": [
            entry("policy/engineering-lane.json", "create", None, policy_bytes),
            entry("docs/engineering.local.md", "create", None, doc_bytes),
            entry("policy/stack-lane.json", "delete", legacy_policy, None),
            entry("docs/tech-stack.local.md", "delete", legacy_doc, None),
        ],
        "safe_to_apply": True, "applied": True,
    }
    rollback_rec = {
        "command": "rollback", "repo": str(replica.resolve()), "status": "rolled_back",
        "restored": [
            {"path": "policy/stack-lane.json", "action": "restored"},
            {"path": "docs/tech-stack.local.md", "action": "restored"},
            {"path": "policy/engineering-lane.json", "action": "removed"},
            {"path": "docs/engineering.local.md", "action": "removed"},
        ],
        "journal_removed": True,
    }
    txn = replica / ".g3p3-transaction"
    txn.mkdir(parents=True, exist_ok=True)
    (txn / "apply.json").write_text(json.dumps(apply_rec, indent=1) + "\n", encoding="utf-8")
    (txn / "rollback.json").write_text(json.dumps(rollback_rec, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- stubs

STUB_POLICY = {"engineering_core": {"tool": "engineering-core", "lanes": ["python"],
                                    "disciplines": ["testing"], "ref": "1.0.0",
                                    "deviations": []}}


def install_stub(task: dict, replica: Path) -> None:
    """Plausible-but-nonconforming deliverables: must NOT pass the frozen checkers."""
    tid = task["task_id"]
    if tid in ("A1", "A2"):
        (replica / "policy/engineering-lane.json").write_text(json.dumps(STUB_POLICY, indent=1),
                                                              encoding="utf-8")
        (replica / "docs/engineering.local.md").write_text(
            "# engineering\n\nAdopted. See policy.\n", encoding="utf-8")
        if tid == "A1":
            # stub keeps legacy files (wrong) — also exercises absence check
            pass
    elif tid == "A3":
        txn = replica / ".g3p3-transaction"
        txn.mkdir(parents=True, exist_ok=True)
        (txn / "apply.json").write_text(json.dumps({"mode": "migrate", "changes": []}), encoding="utf-8")
        (txn / "rollback.json").write_text(json.dumps({"command": "rollback", "status": "ok"}),
                                           encoding="utf-8")
    elif tid in ("B1", "B2", "B3"):
        req_path = replica.parent / f"req-{tid}-stub.json"
        if req_path.exists():
            req_path.unlink()
        request = compile_request(replica, req_path)
        (replica / "g3p3-advice-response.json").write_text(json.dumps({
            "schema": "engineering-advice-response-v1",
            "request_sha256": request["request_sha256"],
            "provenance": {"provider": "stub", "model": "stub", "model_version": "1",
                           "adapter": "stub", "adapter_version": "1",
                           "prompt_id": request["prompt"]["id"],
                           "prompt_version": request["prompt"]["version"]},
            "status": "abstain", "summary": "stub abstains",
            "recommendations": [], "critiques": [], "patch_proposals": [],
        }, indent=1), encoding="utf-8")
    elif tid == "C1":
        pkg = replica / "packages/pi-context-packer"
        (pkg / "src/g3p3-header-audit.js").write_text(
            "export function auditDocHeaders(sources) {\n  return [];\n}\n\n"
            "export function summarizeHeaderAudit(sources) {\n  return {total: 0, withHeader: 0, missingHeader: 0};\n}\n",
            encoding="utf-8")
        (pkg / "tests/g3p3-header-audit.test.js").write_text(
            'import test from "node:test";\n'
            'import { auditDocHeaders } from "../src/g3p3-header-audit.js";\n'
            'test("stub", () => { auditDocHeaders([]); });\n',
            encoding="utf-8")
    elif tid == "C2":
        justfile = replica / "Justfile"
        justfile.write_text(
            justfile.read_text(encoding="utf-8").rstrip("\n")
            + "\n\ng3p3-contracts-quick:\n"
              "    cd packages/pi-context-packer && node ./scripts/validate-package-release-contracts.mjs\n",
            encoding="utf-8")
    elif tid == "C3":
        (replica / "packages/dspx-core/src/dspx/g3p3_token_budget.py").write_text(
            "def split_token_budget(total, weights):\n    return {k: 0 for k in weights}\n",
            encoding="utf-8")
        (replica / "tests/test_g3p3_token_budget.py").write_text(
            "from dspx.g3p3_token_budget import split_token_budget\n\n\n"
            "def test_stub() -> None:\n    assert split_token_budget(0, {\"a\": 1.0}) == {\"a\": 0}\n",
            encoding="utf-8")
    elif tid == "C4":
        (replica / "docs/validation-tier-map.md").write_text(
            "# Tiers\n\nWe test things before shipping.\n", encoding="utf-8")
