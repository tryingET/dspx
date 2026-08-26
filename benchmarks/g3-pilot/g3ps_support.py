"""G3 SUCCESSOR support (AK 5095; decision 138).

Fixture materialization, frozen request compilation for B/H-class instances,
reference solutions (calibration Y=1) and stubs (calibration Y=0). Frozen v3/v3b
modules are untouched; this module imports g3ps_corpus builders only.

Grading-binding note (freeze-recorded): B/H-class advise-response grading
validates the executor's response against the request compiled at freeze time
from the PRISTINE instance fixture. (v3b recompiled from the executor tree,
which works for inert fixtures but not for TH2, where the executor repairs the
policy the request is compiled from.)
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

import g3ps_corpus as corpus

GIT_ENV = {
    "GIT_AUTHOR_NAME": "g3ps", "GIT_AUTHOR_EMAIL": "g3ps@localhost",
    "GIT_COMMITTER_NAME": "g3ps", "GIT_COMMITTER_EMAIL": "g3ps@localhost",
}


# ------------------------------------------------------------------ replicas

def materialize_fixture(fixture_key: str, inst: str, dest: Path) -> Path:
    if dest.exists():
        subprocess.run(["rm", "-rf", str(dest)], check=True)
    files = corpus.FIXTURE_BUILDERS[fixture_key](inst)
    for rel, content in files.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True, env=GIT_ENV)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=dest, check=True, env=GIT_ENV)
    return dest


def make_replica(task: dict, dest: Path) -> Path:
    return materialize_fixture(task["fixture_key"], task["instance"], dest)


def fixture_bytes(fixture_key: str, inst: str) -> dict[str, bytes]:
    return {k: v.encode() for k, v in corpus.FIXTURE_BUILDERS[fixture_key](inst).items()}


# ------------------------------------------------------- request compilation

BUILD_REQUEST_CODE = r"""
import json, sys, hashlib
sys.path.insert(0, "{site}")
from engineering_core.catalog import load_catalog
from engineering_core.engineering_plan import compile_plan
from engineering_core.advisor import build_request
from pathlib import Path
repo = Path(sys.argv[1])
task = json.loads(sys.argv[2])
catalog = load_catalog()
ids = set(catalog.ids("lanes")) | set(catalog.ids("disciplines"))
grounding = {{p: hashlib.sha256((repo / p).read_bytes()).hexdigest()
             for p in task.get("focus_files", []) if (repo / p).exists()}}
try:
    plan = compile_plan(repo, catalog)
except Exception:
    plan = {{"schema": "engineering-plan-v1", "evidence": []}}
plan = dict(plan)
plan["goal"] = task["title"]
plan["task_context"] = {{
    "task_id": task["instance_id"], "title": task["title"],
    "specification": task["spec"], "new_symbols": [], "new_files": [],
}}
plan["evidence"] = [{{"path": p, "sha256": s}} for p, s in grounding.items()]
request = build_request(repo, plan, ids, focus_files=grounding)
Path(sys.argv[3]).write_text(json.dumps(request))
""".format(site="{site}")  # placeholder replaced by caller


def compile_request(replica: Path, task: dict, out_path: Path, tools: dict) -> dict:
    code = BUILD_REQUEST_CODE.replace("{site}", tools["wheel_site"])
    proc = subprocess.run(
        [tools["wheel_py"], "-c", code, str(replica), json.dumps(task), str(out_path)],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"compile_request failed: {proc.stderr[-400:]}")
    return json.loads(out_path.read_text())


# ------------------------------------------------- acceptance metadata (frozen)

def acceptance_for(template: str, inst: str) -> dict:
    """Acceptance metadata for scoring, derived deterministically from the
    corpus builders (recorded in the freeze manifest via module sha)."""
    a: dict = {"fixture": _fixture_for(template)}
    if template == "TA1":
        a["kind"] = "adoption_migration"
        a["required_absent"] = ["policy/stack-lane.json", "docs/tech-stack.local.md"]
    elif template == "TA2":
        a["kind"] = "adoption_repair"
        a["preserve_deviation"] = "keep-local-uv-mirror"
        a["required_absent"] = ["policy/stack-lane.json", "docs/tech-stack.local.md"]
    elif template == "TA3":
        a["kind"] = "adoption_rollback"
        a["required_absent"] = ["policy/engineering-lane.json", "docs/engineering.local.md", ".engineering-core"]
        a["restore_exact"] = True
    elif template in ("TB1", "TB2", "TB3", "TH2"):
        a["kind"] = "advise_response"
    elif template == "TC1":
        a["kind"] = "lane_build_ts"
        fn = {"a": ("g3ps-changelog-audit", "auditChangelogEntries", "summarizeChangelogAudit"),
              "b": ("g3ps-todo-audit", "auditTodoMarkers", "summarizeTodoAudit"),
              "c": ("g3ps-license-audit", "auditLicenseHeaders", "summarizeLicenseAudit")}[inst]
        a["module"] = f"{fn[0]}.js"
        a["test"] = f"{fn[0]}.test.js"
        a["exports"] = [fn[1], fn[2]]
    elif template == "TC2":
        a["kind"] = "lane_alias_pair"
        a["target_script"] = {"a": "release:contracts:validate", "b": "lint:docs", "c": "typecheck:web"}[inst]
        a["alias"] = "g3ps-quick-check"
    elif template == "TC3":
        a["kind"] = "lane_build_py"
        mod = {"a": "seat_budget", "b": "quorum", "c": "backoff"}[inst]
        a["module"] = mod
        a["function"] = {"a": "split_seat_budget", "b": "compute_quorum_round", "c": "backoff_schedule"}[inst]
        a["module_path"] = f"packages/dspx-core/src/dspx/g3ps_{mod}.py"
        a["test_path"] = f"tests/test_g3ps_{mod}.py"
    elif template == "TC4":
        a["kind"] = "tier_map"
        a["surface"] = {"a": ["check", "test", "lint"],
                        "b": ["check", "test", "lint", "ci"],
                        "c": ["check", "test", "lint"]}[inst]
    elif template == "TH1":
        a["kind"] = "compound_migration_tiermap"
        a["required_absent"] = ["policy/stack-lane.json", "docs/tech-stack.local.md"]
        a["surface"] = ["check", "test", "lint"]
    if template == "TH2":
        a["kind"] = "compound_advice_repair"
        a["preserve_deviation"] = "keep-local-uv-mirror"
        a["required_absent"] = ["policy/stack-lane.json", "docs/tech-stack.local.md"]
    return a


def _fixture_for(template: str) -> str:
    return corpus.TEMPLATES[template]["fixture"]


TASK_TITLES = {
    "TA1": "Legacy -> v1 adoption migration", "TA2": "Degraded adoption repair",
    "TA3": "Adoption apply -> rollback lifecycle", "TB1": "Advise response: legacy py repo",
    "TB2": "Advise response: ts web repo (frontend lane)", "TB3": "Advise response: adopted repo, redacted evidence",
    "TC1": "pi-ts lane module + built-in-runner tests", "TC2": "thin-alias command-surface pair",
    "TC3": "py lane service function + property test", "TC4": "validation-tier-map artifact",
    "TH1": "COMPOUND: migration + validation tier map", "TH2": "COMPOUND: advise response + policy repair",
}


def task_for(instance_id: str) -> dict:
    template, inst = instance_id.rsplit("-", 1)
    return {
        "instance_id": instance_id, "template": template, "instance": inst,
        "task_class": corpus.TEMPLATES[template]["cls"],
        "fixture_key": _fixture_for(template),
        "title": TASK_TITLES[template] + f" ({inst})",
        "spec": corpus.TEMPLATES[template]["spec"](inst),
        "acceptance": acceptance_for(template, inst),
    }


# ------------------------------------------------------ reference solutions

def _write(replica: Path, rel: str, content: str) -> None:
    p = replica / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _remove(replica: Path, rel: str) -> None:
    (replica / rel).unlink(missing_ok=True)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def ref_adoption_files(template: str, inst: str) -> tuple[str, str]:
    """(policy_json, doc_md) satisfying the v1 contract for an A-style repo."""
    deviations = []
    if template in ("TA2", "TH2"):
        deviations = [{
            "id": "keep-local-uv-mirror", "reason": "offline workstation mirror required",
            "owner": "platform", "evidence": "infra/mirror.md", "review_date": "2026-09-30",
        }]
    policy = json.dumps({
        "engineering_core": {
            "tool": "engineering-core", "ref": corpus.RELEASE_REF, "lanes": ["py"],
            "catalog_command": "engineering-core catalog --pretty",
            "list_disciplines_command": "engineering-core list-disciplines",
            "list_templates_command": "engineering-core list-templates",
            "disciplines": corpus.DEFAULT_DISCIPLINES,
            "deviations": deviations,
        }}, indent=2) + "\n"
    doc = corpus._v1_doc(  # noqa: SLF001 (reference reuses frozen builders)
        f"Local engineering surface ({template}-{inst}).",
        "Changing local engineering adoption.",
        ["keep-local-uv-mirror"] if deviations else None,
    )
    return policy, doc


REF_TIER_MAP = """---
summary: "Validation tiers for this repository."
read_when:
  - "You are deciding which checks run at which tier before handoff."
---

# Validation Tier Map

Repo: this repository
Owner surface: docs/engineering.local.md

## Commands

| Tier | Command | Scope | Target runtime | Required before |
|---|---|---|---|---|
| editor/save | `python -m compileall src` | file-local+instant | local python | save |
| pre-commit | `just check` | staged slice+p95<10s | local python | commit |
| task-scope | `just test` | changed behavior+minutes | local python | handoff |
| pre-push | `just check && just test` | repo full gate | local python | push |
| CI | `just check && just test` | authoritative matrix+complete | ci runner | merge |
| release | `just check && just test` | shipped artifact+strongest | release runner | release |

## Standard surface

- `just check`: `python -m compileall src` (check recipe)
- `just test`: `python -m pytest tests -q` (test recipe)
- `just build`: n/a — no build step in this repository (library sources shipped as-is)
- `just ci`: n/a — no ci recipe in this repository Justfile
- `just doctor`: n/a — no doctor recipe in this repository Justfile

## Evidence rule

Every handoff records: command, scope, result, warning acceptance (if any),
and artifact path (if any).
"""


def install_reference(task: dict, replica: Path, tools: dict) -> None:
    """Install the reference (calibration Y=1) solution for an instance."""
    t, inst = task["template"], task["instance"]
    policy, doc = ref_adoption_files(t, inst)
    if t == "TH2":
        # compound: advise response (frozen request) + policy repair
        req_path = Path(tools["requests_dir"]) / f"{task['instance_id']}-request.json"
        if req_path.exists():
            request = json.loads(req_path.read_text())
            _write(replica, "g3p3-advice-response.json",
                   json.dumps(reference_response_for(request, task), indent=1))
        _write(replica, "policy/engineering-lane.json", policy)
        _write(replica, "docs/engineering.local.md", doc)
    elif t in ("TA1", "TH1"):
        _write(replica, "policy/engineering-lane.json", policy)
        _write(replica, "docs/engineering.local.md", doc)
        _remove(replica, "policy/stack-lane.json")
        _remove(replica, "docs/tech-stack.local.md")
    elif t == "TA2":
        _write(replica, "policy/engineering-lane.json", policy)
        _write(replica, "docs/engineering.local.md", doc)
    elif t == "TA3":
        legacy = fixture_bytes(task["fixture_key"], inst)
        created = {"policy/engineering-lane.json": policy.encode(), "docs/engineering.local.md": doc.encode()}
        changes = []
        for path in ("policy/engineering-lane.json", "docs/engineering.local.md"):
            data = created[path]
            changes.append({"path": path, "action": "create", "before_sha256": None,
                            "after_sha256": hashlib.sha256(data).hexdigest(),
                            "before_b64": None, "after_b64": _b64(data)})
            _write(replica, path, data.decode())
        for path in ("policy/stack-lane.json", "docs/tech-stack.local.md"):
            data = legacy[path]
            changes.append({"path": path, "action": "delete",
                            "before_sha256": hashlib.sha256(data).hexdigest(),
                            "after_sha256": None, "before_b64": _b64(data), "after_b64": None})
            _remove(replica, path)
        _write(replica, ".g3p3-transaction/apply.json", json.dumps({
            "mode": "migrate", "repo": str(replica.resolve()), "lanes": ["py"],
            "disciplines": corpus.DEFAULT_DISCIPLINES, "changes": changes,
            "safe_to_apply": True, "applied": True}, indent=1))
        # rollback: restore exact bytes, remove adoption files
        for path in ("policy/stack-lane.json", "docs/tech-stack.local.md"):
            _write(replica, path, legacy[path].decode())
        for path in ("policy/engineering-lane.json", "docs/engineering.local.md"):
            _remove(replica, path)
        _write(replica, ".g3p3-transaction/rollback.json", json.dumps({
            "command": "rollback", "repo": str(replica.resolve()), "status": "rolled_back",
            "restored": [
                {"path": "policy/stack-lane.json", "action": "restored"},
                {"path": "docs/tech-stack.local.md", "action": "restored"},
                {"path": "policy/engineering-lane.json", "action": "removed"},
                {"path": "docs/engineering.local.md", "action": "removed"}],
            "journal_removed": True}, indent=1))
    elif t in ("TB1", "TB2", "TB3"):
        req_path = Path(tools["requests_dir"]) / f"{task['instance_id']}-request.json"
        if req_path.exists():
            request = json.loads(req_path.read_text())
            resp = reference_response_for(request, task)
            _write(replica, "g3p3-advice-response.json", json.dumps(resp, indent=1))
    elif t == "TC1":
        fn = {"a": ("g3ps-changelog-audit", "auditChangelogEntries", "summarizeChangelogAudit"),
              "b": ("g3ps-todo-audit", "auditTodoMarkers", "summarizeTodoAudit"),
              "c": ("g3ps-license-audit", "auditLicenseHeaders", "summarizeLicenseAudit")}[inst]
        _write(replica, fn[0] + ".js", _ref_tc1_module(fn))
        _write(replica, fn[0] + ".test.js", _ref_tc1_test(fn))
    elif t == "TC2":
        tgt = {"a": "release:contracts:validate", "b": "lint:docs", "c": "typecheck:web"}[inst]
        pkg = json.loads((replica / "package.json").read_text())
        pkg.setdefault("scripts", {})[task["acceptance"]["alias"]] = f"npm run {tgt}"
        _write(replica, "package.json", json.dumps(pkg, indent=2) + "\n")
        just = (replica / "Justfile").read_text() if (replica / "Justfile").exists() else ""
        just += f"\n# G3PS quick check (thin alias over the package script)\n{task['acceptance']['alias']}:\n    npm run {task['acceptance']['alias']}\n"
        _write(replica, "Justfile", just)
    elif t == "TC3":
        mod = {"a": "seat_budget", "b": "quorum", "c": "backoff"}[inst]
        _write(replica, f"packages/dspx-core/src/dspx/g3ps_{mod}.py", _ref_tc3_module(inst))
        _write(replica, f"tests/test_g3ps_{mod}.py", _ref_tc3_test(inst))
    elif t == "TC4":
        _write(replica, "docs/validation-tier-map.md", REF_TIER_MAP)
    if t == "TH1":
        _write(replica, "docs/validation-tier-map.md", REF_TIER_MAP)
    _write(replica, "G3P3_CLAIM.md",
           f"# Claim (reference solution)\n\nInstance: {task['instance_id']}\n\n"
           f"## Files changed or created\n\n"
           + "\n".join(f"- {rel}" for rel in sorted(set(replica.rglob('*')) - {replica})[:0]) +
           "\nAll deliverables listed in the specification for this instance were created "
           "exactly as required.\n\n## Clause satisfaction\n\nEach specification clause "
           "is satisfied by the corresponding deliverable content.\n\n## Verification\n\n"
           "Verified by the frozen checker during calibration (reference pass).\n")


def reference_response_for(request: dict, task: dict) -> dict:
    """Construct a valid engineering-advice-response-v1 for a compiled request.
    Calibration-only (executors must derive selections from the repository)."""
    ev = request["evidence"]
    cited = [{"evidence_id": ev[0]["id"], "path": ev[0]["path"], "start": 0,
              "end": max(1, min(ev[0]["span"]["end"], ev[0]["bytes"]))}]
    prompt = request["prompt"]
    return {
        "schema": "engineering-advice-response-v1",
        "request_sha256": request["request_sha256"],
        "provenance": {
            "provider": "g3ps-calibration", "model": "reference",
            "model_version": "0", "adapter": "calibration", "adapter_version": "0",
            "prompt_id": prompt["id"], "prompt_version": prompt["version"],
        },
        "status": "advice",
        "summary": f"Calibration reference advice for {task['instance_id']}.",
        "recommendations": [
            {"id": "r1", "catalog_ids": sorted(_plan_ids(request)),
             "recommendation": "Adopt the plan-selected lanes and default disciplines for this repository.",
             "confidence": 0.9, "unknowns": [], "counterevidence": [],
             "falsification": ["checker rejects the union if it differs from plan requested"],
             "citations": cited, "competes_with": []},
            {"id": "r2", "catalog_ids": sorted(_plan_ids(request))[:1] or ["validation"],
             "recommendation": "Record validation evidence at handoff per the validation discipline.",
             "confidence": 0.8, "unknowns": [], "counterevidence": [],
             "falsification": ["checker rejects a recommendation without a citation"],
             "citations": cited, "competes_with": []},
        ],
        "critiques": [
            {"recommendation_id": "r1", "severity": "low",
             "critique": "Union must equal the compiler's requested selections exactly.",
             "falsification": ["any extra or missing id fails grading"]},
        ],
        "patch_proposals": [],
    }


def _plan_ids(request: dict) -> set[str]:
    """Ids the plan compiler SELECTED as requested (selections[].requested ==
    True), excluding catalog.requires auto-additions."""
    ids: set[str] = set()
    for sel in (request.get("plan") or {}).get("selections", []):
        if isinstance(sel, dict) and sel.get("requested") is True and sel.get("id"):
            ids.add(sel["id"])
    return ids


def install_stub(task: dict, replica: Path) -> None:
    """Install a non-conforming stub (calibration Y=0)."""
    t = task["template"]
    if t in ("TA1", "TA2", "TH1", "TH2"):
        _write(replica, "policy/engineering-lane.json", json.dumps({
            "engineering_core": {"tool": "engineering-core", "ref": "v0.0.1",
                                 "lanes": ["py"], "disciplines": ["made-up"],
                                 "deviations": []}}, indent=2))
    elif t == "TA3":
        _write(replica, ".g3p3-transaction/apply.json", json.dumps({"changes": []}))
        _write(replica, ".g3p3-transaction/rollback.json", json.dumps({"status": "?"}))
    elif t in ("TB1", "TB2", "TB3"):
        _write(replica, "g3p3-advice-response.json", json.dumps({
            "schema": "engineering-advice-response-v1",
            "request_sha256": "0" * 64,
            "provenance": {"provider": "x", "model": "x", "model_version": "0",
                           "adapter": "x", "adapter_version": "0",
                           "prompt_id": "wrong", "prompt_version": "0"},
            "status": "advice", "summary": "stub",
            "recommendations": [{"id": "r1", "catalog_ids": ["not-a-real-id"],
                                 "recommendation": "stub", "confidence": 0.1,
                                 "unknowns": [], "counterevidence": [], "falsification": [],
                                 "citations": [], "competes_with": []}],
            "critiques": [], "patch_proposals": []}))
    elif t in ("TC1", "TC2", "TC3", "TC4"):
        _write(replica, "stub.txt", "not a conforming deliverable\n")
    _write(replica, "G3P3_CLAIM.md", f"stub claim for {task['instance_id']}")


# ------------------------------------------------------------ TC references

def _ref_tc1_module(fn: tuple[str, str, str]) -> str:
    audit, summ = fn[1], fn[2]
    return (r"""export function AUDIT(entries) {
  const results = [];
  for (const { file, text } of entries) {
    const lines = text.split("\n");
    const headerIdx = lines.findIndex(
      (line, i) =>
        lines[i].trim() === "<!-- changelog -->" ||
        lines[i].trim().startsWith("// SPDX-License-Identifier:") ||
        /^\s*(\/\/|#)\s*TODO:/.test(line),
    );
    let hasHeader = false;
    let summary = null;
    let extra = null;
    if (headerIdx !== -1) {
      hasHeader = true;
      const head = lines[headerIdx].trim();
      if (head === "<!-- changelog -->") {
        const h2 = lines.slice(headerIdx + 1).find((l) => l.startsWith("## "));
        summary = h2 ? h2.slice(3).trim() : null;
        const trig = lines
          .slice(headerIdx + 1, headerIdx + 20)
          .filter((l) => l.trim().startsWith("read_when:"));
        extra = trig.map((l) => l.trim());
      } else if (head.startsWith("// SPDX-License-Identifier:")) {
        summary = head.slice("// SPDX-License-Identifier:".length).trim();
        const cr = lines.find((l) => l.startsWith("// Copyright (c) "));
        extra = cr ? [cr] : [];
      } else {
        const todos = lines.filter((l) => /^\s*(\/\/|#)\s*TODO:/.test(l));
        summary = todos.length > 0 ? todos[0] : null;
        extra = todos;
      }
    }
    results.push({ file, hasHeader, summary, extra });
  }
  return results;
}

export function SUMM(entries) {
  const audited = AUDIT(entries);
  return {
    total: audited.length,
    withHeader: audited.filter((r) => r.hasHeader).length,
    missingHeader: audited.filter((r) => !r.hasHeader).length,
  };
}
""".replace("AUDIT", audit).replace("SUMM", summ))


def _ref_tc1_test(fn: tuple[str, str, str]) -> str:
    audit, summ = fn[1], fn[2]
    return (r"""import assert from "node:assert/strict";
import test from "node:test";
import { AUDIT, SUMM } from "./MOD.js";

test("parses headers", () => {
  const [r] = AUDIT([
    { file: "a", text: '<!-- changelog -->\n## Added thing\nread_when: "x"' },
  ]);
  assert.equal(r.hasHeader, true);
  assert.ok(r.summary !== null);
});

test("missing header case", () => {
  const [r] = AUDIT([{ file: "b", text: "plain text only" }]);
  assert.equal(r.hasHeader, false);
});

test("summary over 8 fixtures", () => {
  const entries = Array.from({ length: 8 }, (_, i) => ({
    file: `f${i}`,
    text: i % 2 ? "plain" : "<!-- changelog -->\n## H",
  }));
  const s = SUMM(entries);
  assert.equal(s.total, 8);
  assert.equal(s.withHeader, 4);
  assert.equal(s.missingHeader, 4);
});
""".replace("AUDIT", audit).replace("SUMM", summ).replace("MOD", fn[0]))


def _ref_tc3_module(inst: str) -> str:
    if inst == "a":
        return '''"""Seat budget splitting by largest-remainder rounding."""
from collections.abc import Mapping


def split_seat_budget(total: int, weights: Mapping[str, float]) -> dict[str, int]:
    """Split `total` whole seats across keys by largest-remainder rounding."""
    if total < 0:
        raise ValueError("total must be >= 0")
    if not weights:
        raise ValueError("weights must not be empty")
    if any(w < 0 for w in weights.values()):
        raise ValueError("weights must be non-negative")
    wsum = sum(weights.values())
    if wsum <= 0:
        raise ValueError("weight sum must be > 0")
    exact = {k: total * w / wsum for k, w in weights.items()}
    base = {k: int(v) for k, v in exact.items()}
    remaining = total - sum(base.values())
    order = sorted(weights, key=lambda k: (-(exact[k] - base[k]), k))
    for k in order[:remaining]:
        base[k] += 1
    return base
'''
    if inst == "b":
        return '''"""Quorum round computation."""


def compute_quorum_round(votes, quorum):
    """Return the 1-indexed round at which cumulative votes reach quorum."""
    if quorum < 0:
        raise ValueError("quorum must be >= 0")
    running = 0
    for i, v in enumerate(votes, start=1):
        running += v
        if running >= quorum:
            return i
    raise ValueError("quorum never reached")
'''
    return '''"""Retry backoff schedule."""


def backoff_schedule(n, base, cap):
    """Return the first n retry delays in ms."""
    if n < 0:
        raise ValueError("n must be >= 0")
    if base <= 0:
        raise ValueError("base must be > 0")
    if cap < 0:
        raise ValueError("cap must be >= 0")
    return [int(base * 2 ** min(i, cap)) for i in range(n)]
'''


def _ref_tc3_test(inst: str) -> str:
    if inst == "a":
        return '''import random

import pytest

from dspx.g3ps_seat_budget import split_seat_budget


def test_exact_split() -> None:
    assert split_seat_budget(100, {"a": 1}) == {"a": 100}


def test_errors() -> None:
    with pytest.raises(ValueError):
        split_seat_budget(-1, {"a": 1.0})
    with pytest.raises(ValueError):
        split_seat_budget(1, {})
    with pytest.raises(ValueError):
        split_seat_budget(1, {"a": -1.0})
    with pytest.raises(ValueError):
        split_seat_budget(1, {"a": 0.0})


def test_property_sum_invariant() -> None:
    rng = random.Random(20260826)
    for _ in range(8):
        total = rng.randrange(0, 100)
        weights = {f"k{i}": rng.random() for i in range(4)}
        got = split_seat_budget(total, weights)
        assert sum(got.values()) == total
        assert all(v >= 0 for v in got.values())
        assert set(got) == set(weights)
'''
    if inst == "b":
        return '''import pytest

from dspx.g3ps_quorum import compute_quorum_round


def test_basic() -> None:
    assert compute_quorum_round([1, 2, 3], 4) == 3


def test_errors() -> None:
    with pytest.raises(ValueError):
        compute_quorum_round([1], -1)
    with pytest.raises(ValueError):
        compute_quorum_round([1, 1], 5)


def test_property_prefix_minimality() -> None:
    import random

    rng = random.Random(20260826)
    for _ in range(8):
        votes = [rng.randrange(0, 5) for _ in range(6)]
        total = sum(votes)
        if total == 0:
            continue
        q = rng.randrange(0, total + 1)
        if q == 0:
            continue
        r = compute_quorum_round(votes, q)
        assert sum(votes[:r]) >= q
        assert sum(votes[: r - 1]) < q
'''
    return '''import pytest

from dspx.g3ps_backoff import backoff_schedule


def test_basic() -> None:
    assert backoff_schedule(3, 100.0, 2) == [100, 200, 400]


def test_errors() -> None:
    with pytest.raises(ValueError):
        backoff_schedule(-1, 1.0, 0)
    with pytest.raises(ValueError):
        backoff_schedule(1, 0.0, 0)
    with pytest.raises(ValueError):
        backoff_schedule(1, 1.0, -1)


def test_property_non_decreasing() -> None:
    import random

    rng = random.Random(20260826)
    for _ in range(8):
        n = rng.randrange(0, 10)
        base = rng.random() * 100 + 1
        cap = rng.randrange(0, 4)
        got = backoff_schedule(n, base, cap)
        assert len(got) == n
        assert all(b <= a for b, a in zip(got, got[1:]))
'''
