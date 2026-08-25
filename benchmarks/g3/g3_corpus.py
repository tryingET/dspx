#!/usr/bin/env python3
"""G3 campaign corpus builder (frozen; DSPx task 5059, AK decision 132).

Deterministic construction of the 168 paired task instances required by
docs/v1-proof/g3-protocol-manifest.json (digest ea05ba3c...2ff5fa0).

Grounding: every task instance targets real entities enumerated at the
population-manifest pinned revision of each positive baseline repo. Tasks
require NEW symbols/files with a `g3_`/`g3-` prefix asserted absent at the
pin, so every acceptance suite initially fails (real work) and is
objectively verifiable without repo-external dependencies.

This module is a frozen campaign artifact: sha256 is recorded in
docs/v1-proof/g3-campaign-state.json before any execution.
"""

from __future__ import annotations

import ast
import hashlib
import json
import random
import re
import subprocess
import unicodedata
from pathlib import Path

CAMPAIGN_SEED = 20260825
SCHEMA = "dspx.g3-campaign-corpus/1"

REPOS = {
    "fcos": {
        "baseline": "fcos-control-board",
        "owner_group": "holdingco",
        "repo_identity": "holdingco/fcos-control-board",
        "local_path": "/home/tryinget/ai-society/holdingco/fcos-control-board",
        "pin": "7e23210a08e38bcd93c91967af7152ed504aacc3",
        "kind": "python",
        "tasks_needed": 56,
    },
    "mathe": {
        "baseline": "mathe",
        "owner_group": "teachingco",
        "repo_identity": "teachingco/mathe",
        "local_path": "/home/tryinget/ai-society/teachingco/mathe",
        "pin": "ba719160dd89bae5d53f0c959719533ca4b49c2f",
        "kind": "docs",
        "tasks_needed": 28,
    },
    "wib": {
        "baseline": "wib",
        "owner_group": "teachingco",
        "repo_identity": "teachingco/wib",
        "local_path": "/home/tryinget/ai-society/teachingco/wib",
        "pin": "316c45747560392fdab03498849652e8d7e94fcb",
        "kind": "docs",
        "tasks_needed": 28,
    },
    "piext": {
        "baseline": "pi-extensions",
        "owner_group": "softwareco",
        "repo_identity": "softwareco/owned/pi-extensions",
        "local_path": "/home/tryinget/ai-society/softwareco/owned/pi-extensions",
        "pin": "a2dbccdde192b2795764bc282de503c8991b5433",
        "kind": "ts",
        "tasks_needed": 56,
    },
}

FAMILIES = {"fam-grok": "xai/grok-4.6", "fam-gpt": "openai-codex/gpt-5.6-terra"}


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {proc.stderr[:300]}")
    return proc.stdout


def ls_tree(repo: Path, pin: str, prefix: str = "") -> list[str]:
    out = _git(repo, "ls-tree", "-r", "--name-only", pin)
    return [line for line in out.splitlines() if line.startswith(prefix)]


def show(repo: Path, pin: str, path: str) -> str:
    return _git(repo, "show", f"{pin}:{path}")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


# ---------------------------------------------------------------- grounding

def _stdlib_only(path: str, repo: Path, pin: str) -> bool:
    """Module imports must be stdlib/typing-only so acceptance exec() is hermetic."""
    try:
        tree = ast.parse(show(repo, pin, path))
    except SyntaxError:
        return False
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    allowed = {"__future__", "typing", "json", "pathlib", "hashlib", "re", "sys", "os", "io", "math", "datetime", "collections", "functools", "itertools", "dataclasses", "enum", "textwrap", "unicodedata", "subprocess", "shutil", "tempfile", "argparse", "csv", "statistics", "time", "copy", "glob"}
    return imported <= allowed


def python_functions(repo: Path, pin: str) -> list[dict]:
    """Real top-level functions in packages/ *.py modules at the pin."""
    out = []
    for path in ls_tree(repo, pin, "packages/"):
        if not path.endswith(".py") or path.endswith("_test.py"):
            continue
        if not _stdlib_only(path, repo, pin):
            continue
        try:
            tree = ast.parse(show(repo, pin, path))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                out.append({"module": path, "function": node.name})
    return out


def ts_modules(repo: Path, pin: str) -> list[dict]:
    """Real package modules (any .ts under packages/) with real export names."""
    out = []
    for path in ls_tree(repo, pin, "packages/"):
        if not path.endswith(".ts") or path.endswith((".test.ts", ".spec.ts", ".d.ts")):
            continue
        if "/node_modules/" in path:
            continue
        pkg = path.split("/")[1]
        src = show(repo, pin, path)
        exports = re.findall(r"export\s+(?:async\s+)?(?:function|const|class)\s+(\w+)", src)
        for block in re.findall(r"export\s+(?:type\s+)?\{([^}]+)\}", src):
            for item in block.split(","):
                name = item.strip().split(" as ")[-1].strip()
                if re.fullmatch(r"\w+", name or ""):
                    exports.append(name)
        if not exports:
            continue
        out.append({"package": pkg, "entry": path, "exports": exports[:8], "n_exports": len(exports)})
    return out


def markdown_docs(repo: Path, pin: str, min_bytes: int = 2000) -> list[dict]:
    """Real markdown documents at the pin, with size and heading count."""
    out = []
    for path in ls_tree(repo, pin):
        if not path.endswith(".md") or path.startswith(("diary/", "docs/decisions/")):
            continue
        try:
            text = show(repo, pin, path)
        except RuntimeError:
            continue
        if len(text.encode()) < min_bytes:
            continue
        headings = re.findall(r"^##\s+(.+)$", text, re.M)
        if len(headings) < 2:
            continue
        out.append({"path": path, "bytes": len(text.encode()), "sections": len(headings)})
    return out


# ---------------------------------------------------------------- templates

PYTHON_HELPER_SPEC = """In the module `{module}` (which already exists at this revision and defines
`{anchor}` among its symbols), add a new pure top-level function:

    def g3_margin_report(value: float, reference: float = {reference}) -> dict:

Contract (exact):
- returns a dict with exactly the keys "ok", "margin", "band"
- "ok" is True iff abs(value - reference) <= {tolerance}
- "margin" is round(value - reference, 4)
- "band" is "inside" when abs(value - reference) <= {tolerance}, else "outside"
- raises ValueError("g3: non-finite value") when value is NaN or infinite
- no module-level side effects; stdlib only; no changes to existing symbols"""

PYTHON_HELPER_TEST = '''
import ast, json, math, pathlib, sys

MODULE = "{module}"

def load():
    src = pathlib.Path(MODULE).read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert "g3_margin_report" in names, "g3_margin_report missing from %s" % MODULE
    ns = {{"__name__": "g3_mod"}}
    exec(compile(src, MODULE, "exec"), ns)
    return ns["g3_margin_report"]

def main():
    fn = load()
    r1 = fn({value_a}, {reference})
    assert r1 == {{"ok": {ok_a}, "margin": {margin_a}, "band": "{band_a}"}}, r1
    r2 = fn({value_b}, {reference})
    assert r2 == {{"ok": {ok_b}, "margin": {margin_b}, "band": "{band_b}"}}, r2
    r3 = fn({value_c})
    assert r3["band"] == "{band_c}" and r3["ok"] is {ok_c}, r3
    for bad in (float("nan"), float("inf"), float("-inf")):
        try:
            fn(bad)
        except ValueError as exc:
            assert "non-finite" in str(exc), exc
        else:
            raise AssertionError("expected ValueError for %r" % bad)
    print("ACCEPT")

main()
'''

PYTHON_JSON_SPEC = """The repository carries `{json_path}` (present at this revision; read it from the
worktree). Add a new module `{module}` (new file) exposing:

    def g3_state_facts() -> dict:

Contract (exact):
- reads `{json_path}` from the repository root (pathlib, relative to the module file via
  Path(__file__).resolve().parents[{parents_up}])
- returns a dict with exactly the keys "entries", "top_level_keys", "digest8"
- "entries": int — number of top-level entries if the JSON is a list, else number of
  top-level keys if it is an object, else 0
- "top_level_keys": sorted list of the first {n_keys} top-level key names (lexicographically
  sorted, [] when not an object)
- "digest8": first 8 hex chars of sha256 over the file's raw bytes
- raises FileNotFoundError if the data file is missing; stdlib only"""

PYTHON_JSON_TEST = '''
import ast, hashlib, json, pathlib, subprocess, sys

MODULE = "{module}"
DATA = "{json_path}"

def load():
    src = pathlib.Path(MODULE).read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert "g3_state_facts" in names, "g3_state_facts missing"
    ns = {{"__name__": "g3_mod", "__file__": str(pathlib.Path(MODULE).resolve())}}
    exec(compile(src, MODULE, "exec"), ns)
    return ns["g3_state_facts"]

def main():
    raw = pathlib.Path(DATA).read_bytes()
    parsed = json.loads(raw)
    expect_entries = len(parsed) if isinstance(parsed, (list, dict)) else 0
    expect_keys = sorted(parsed.keys())[:{n_keys}] if isinstance(parsed, dict) else []
    expect_d8 = hashlib.sha256(raw).hexdigest()[:8]
    fn = load()
    r = fn()
    assert set(r) == {{"entries", "top_level_keys", "digest8"}}, sorted(r)
    assert r["entries"] == expect_entries, (r["entries"], expect_entries)
    assert r["top_level_keys"] == expect_keys, (r["top_level_keys"], expect_keys)
    assert r["digest8"] == expect_d8, (r["digest8"], expect_d8)
    print("ACCEPT")

main()
'''

TS_HELPER_SPEC = """The package `packages/{package}` (entry file `{entry}`, which already exports
`{anchor}` among its symbols at this revision) gains a new self-contained module
`{new_file}` (new file, ESM JavaScript, no imports, no dependencies, runs on plain
node >= 18) exporting exactly one named function:

    export function g3ThresholdReport(samples, options = {opts_default})

Contract (exact):
- `samples` is an array of numbers; `options` is {{ reference: number (default {reference}), tolerance: number (default {tolerance}) }}
- returns {{ ok, inside, worst }} where:
  - `inside` is the count of samples with Math.abs(s - reference) <= tolerance
  - `ok` is true iff ALL samples are inside
  - `worst` is the sample with the largest Math.abs(s - reference); null for an empty array
- throws RangeError("g3: samples must be finite") if any sample is not finite
- empty array returns {{ ok: true, inside: 0, worst: null }}
- CommonJS require of the file must also work via default interop being unnecessary:
  the file is ESM only (package `.mjs`)"""

TS_HELPER_TEST = '''
import test from "node:test";
import assert from "node:assert/strict";
import {{ g3ThresholdReport }} from "./{import_target}";

test("contract", () => {{
  const a = g3ThresholdReport([{v1}], {{ reference: {reference}, tolerance: {tolerance} }});
  assert.deepEqual(a, {{ ok: {ok1}, inside: {inside1}, worst: {w1} }});
  const b = g3ThresholdReport([{v2}]);
  assert.equal(b.ok, {ok2});
  assert.equal(b.inside, {inside2});
  const c = g3ThresholdReport([]);
  assert.deepEqual(c, {{ ok: true, inside: 0, worst: null }});
  assert.throws(() => g3ThresholdReport([1, NaN]), RangeError);
  const d = g3ThresholdReport([{v3}, {v4}]);
  assert.equal(d.worst, {w2});
}});
console.log("ACCEPT");
'''

DOC_SUMMARY_SPEC = """Read the existing document `{source_doc}` (present at this revision, {source_bytes}
bytes, {source_sections} `##` sections). Produce ONE new file `{out_path}` that is a
faithful structured summary of that document.

Exact requirements (all machine-checked):
1. The file starts with YAML frontmatter delimited by `---` lines containing exactly
   these keys: `g3_task`, `source`, `title`, `facts_count`, `generated_for`. Values:
   `g3_task: "{task_id}"`, `source: "{source_doc}"`, `title:` a non-empty string,
   `facts_count: {n_facts}`, `generated_for: "g3-campaign-5059"`.
2. After the frontmatter, exactly these H2 sections in order:
   `## Purpose`, `## Key facts`, `## Open questions`, `## Coverage`
3. `## Key facts` contains at least {n_facts} list items (`- `), each item at least
   {min_fact_chars} characters and each containing at least one backticked
   reference `like this` to a path, symbol, or term that appears verbatim in
   `{source_doc}`.
4. `## Open questions` contains between 1 and {n_questions} list items.
5. `## Coverage` contains exactly one fenced code block whose content is a JSON
   object with keys `sections_seen` (integer, the number of `##` headings in the
   source document) and `bytes` (integer, the byte length of the source document).
6. The summary body (excluding frontmatter and the Coverage code block) must not
   exceed {max_body_chars} characters; facts must be derivable from the source
   document (no invented numbers)."""

DOC_JSON_SPEC = """Build a machine-verifiable index over one directory of this repository.
Create ONE new file `{out_path}` containing a single JSON object:

{{
  "generated_for": "g3-campaign-5059",
  "g3_task": "{task_id}",
  "documents": [ ... exactly {n_docs} entries ... ]
}}

Each entry object has exactly the keys `path`, `sha8`, `sections`, `h1`.
- `documents` covers the {n_docs} markdown files DIRECTLY inside `{index_dir}/`
  (non-recursive, no subdirectories), sorted by path.
- `path`: repo-relative posix path
- `sha8`: first 8 hex chars of sha256 over the file's raw bytes (as present in the
  worktree at generation time)
- `sections`: number of `##` headings in the file
- `h1`: the first `# ` heading text of the file, or null when absent
The file must be valid UTF-8 JSON with no trailing commas."""

DOC_JSON_TEST = '''
import hashlib, json, pathlib, re, sys

OUT = pathlib.Path("{out_path}")
INDEX_DIR = pathlib.Path("{index_dir}")
N_DOCS = {n_docs}

def main():
    assert OUT.exists(), "missing output file"
    doc = json.loads(OUT.read_text(encoding="utf-8"))
    assert set(doc) == {{"generated_for", "g3_task", "documents"}}, sorted(doc)
    assert doc["generated_for"] == "g3-campaign-5059"
    assert doc["g3_task"] == "{task_id}"
    files = sorted(p for p in INDEX_DIR.glob("*.md") if p.is_file())
    assert N_DOCS <= len(files), (N_DOCS, len(files))
    assert len(doc["documents"]) == N_DOCS, (len(doc["documents"]), N_DOCS)
    for entry, f in zip(doc["documents"], files[:N_DOCS]):
        raw = f.read_bytes()
        text = raw.decode("utf-8", "replace")
        h1 = re.search(r"^# (.+)$", text, re.M)
        assert set(entry) == {{"path", "sha8", "sections", "h1"}}, sorted(entry)
        assert entry["path"] == f.as_posix(), entry["path"]
        assert entry["sha8"] == hashlib.sha256(raw).hexdigest()[:8], entry["path"]
        assert entry["sections"] == len(re.findall(r"^## ", text, re.M)), entry["path"]
        assert entry["h1"] == (h1.group(1).strip() if h1 else None), entry["path"]
    print("ACCEPT")

main()
'''


# ---------------------------------------------------------------- builders

def build_repo_tasks(repo_key: str, rng: random.Random) -> list[dict]:
    cfg = REPOS[repo_key]
    repo = Path(cfg["local_path"])
    pin = cfg["pin"]
    need = cfg["tasks_needed"]
    tasks: list[dict] = []

    if cfg["kind"] == "python":
        fns = python_functions(repo, pin)
        rng.shuffle(fns)
        jsons = [p for p in ls_tree(repo, pin) if p.endswith(".json") and not p.startswith(".")]
        rng.shuffle(jsons)
        i = 0
        for fn in fns:
            if len(tasks) >= need:
                break
            slug = f"g3-margin-{slugify(fn['module']).replace('-py', '')}-{fn['function']}"[:60]
            reference = round(rng.uniform(0.5, 5.0), 3)
            tolerance = round(rng.uniform(0.25, 1.75), 3)
            va = round(reference + tolerance * rng.uniform(-0.9, 0.9), 4)
            vb = round(reference + tolerance * rng.choice([-1.4, 1.4]), 4)
            vc = round(reference + tolerance * rng.uniform(-0.5, 0.5), 4)
            test = PYTHON_HELPER_TEST.format(
                module=fn["module"], value_a=va, reference=reference,
                ok_a=str(abs(va - reference) <= tolerance),
                margin_a=round(va - reference, 4), band_a="inside" if abs(va - reference) <= tolerance else "outside",
                value_b=vb, ok_b=str(abs(vb - reference) <= tolerance),
                margin_b=round(vb - reference, 4), band_b="inside" if abs(vb - reference) <= tolerance else "outside",
                value_c=vc, ok_c=str(abs(vc - reference) <= tolerance),
                band_c="inside" if abs(vc - reference) <= tolerance else "outside",
            )
            tasks.append({
                "task_kind": "python_helper",
                "grounding": [fn["module"]],
                "anchor_symbol": fn["function"],
                "title": f"Add pure reporting helper to {fn['module']}",
                "spec": PYTHON_HELPER_SPEC.format(module=fn["module"], anchor=fn["function"],
                                                  reference=reference, tolerance=tolerance),
                "acceptance": {"runner": "python3", "file_name": f"accept_{slug}.py", "file_content": test},
                "participant_validation": ["python3", "-m", "compileall", "-q", fn["module"]],
                "new_symbols": ["g3_margin_report"],
            })
            i += 1
        for jp in jsons:
            if len(tasks) >= need:
                break
            module = f"packages/fcos-cli/g3_facts_{slugify(jp)}.py"
            n_keys = rng.randint(3, 7)
            parents_up = 2
            test = PYTHON_JSON_TEST.format(module=module, json_path=jp, n_keys=n_keys)
            tasks.append({
                "task_kind": "python_json_facts",
                "grounding": [jp],
                "anchor_symbol": jp,
                "title": f"Add state-facts module over {jp}",
                "spec": PYTHON_JSON_SPEC.format(json_path=jp, module=module, n_keys=n_keys, parents_up=parents_up),
                "acceptance": {"runner": "python3", "file_name": f"accept_{slugify(module)}.py", "file_content": test},
                "participant_validation": ["python3", "-m", "compileall", "-q", module],
                "new_symbols": ["g3_state_facts"],
                "new_files": [module],
            })

    elif cfg["kind"] == "ts":
        pkgs = ts_modules(repo, pin)
        rng.shuffle(pkgs)
        variants = ("a", "b") + (("c",) if len(pkgs) * 2 < need else ())
        for pkg in pkgs:
            for variant in variants:
                if len(tasks) >= need:
                    break
                new_file = f"packages/{pkg['package']}/g3-threshold-{variant}.mjs"
                reference = round(rng.uniform(1.0, 9.0), 3)
                tolerance = round(rng.uniform(0.5, 2.5), 3)
                v1 = round(reference + tolerance * rng.uniform(-0.8, 0.8), 4)
                v2 = round(reference + tolerance * rng.choice([-1.5, 1.5]), 4)
                v3 = round(reference + tolerance * rng.uniform(-1.2, -0.6), 4)
                v4 = round(reference + tolerance * rng.uniform(0.7, 1.3), 4)
                inside1 = int(abs(v1 - reference) <= tolerance)
                inside2 = int(abs(v2 - reference) <= tolerance)
                test = TS_HELPER_TEST.format(
                    import_target=new_file.split("/")[-1], v1=v1, v2=v2, v3=v3, v4=v4,
                    reference=reference, tolerance=tolerance,
                    ok1="true" if inside1 else "false", inside1=inside1, w1=v1,
                    ok2="true" if inside2 else "false", inside2=inside2,
                    w2=(v4 if abs(v4 - reference) >= abs(v3 - reference) else v3),
                )
                tasks.append({
                    "task_kind": "ts_helper",
                    "grounding": [pkg["entry"]],
                    "anchor_symbol": pkg["exports"][0],
                    "title": f"Add threshold-report module to packages/{pkg['package']}",
                    "spec": TS_HELPER_SPEC.format(
                        package=pkg["package"], entry=pkg["entry"], anchor=pkg["exports"][0],
                        new_file=new_file, opts_default="{ reference: " + str(reference) + ", tolerance: " + str(tolerance) + " }",
                        reference=reference, tolerance=tolerance),
                    "acceptance": {"runner": "node", "file_name": f"accept-{pkg['package']}-{variant}.test.mjs",
                                   "file_content": test, "run_dir": f"packages/{pkg['package']}"},
                    "participant_validation": ["node", "--check", new_file],
                    "new_symbols": ["g3ThresholdReport"],
                    "new_files": [new_file],
                })

    elif cfg["kind"] == "docs":
        docs = markdown_docs(repo, pin)
        rng.shuffle(docs)
        docs = docs[:need]
        half = need // 2
        for d in docs[:half]:
            n_facts = rng.randint(4, 7)
            out_path = f"g3-work/summary-{slugify(d['path'])}.md"
            test = DOC_SUMMARY_CHECKER.format(
                task_id="TASKID", source_doc=d["path"], out_path=out_path,
                n_facts=n_facts, min_fact_chars=40, n_questions=rng.randint(2, 4),
                source_sections=d["sections"], source_bytes=d["bytes"],
                max_body_chars=9000,
            )
            tasks.append({
                "task_kind": "doc_summary",
                "grounding": [d["path"]],
                "anchor_symbol": d["path"],
                "title": f"Structured summary of {d['path']}",
                "spec": DOC_SUMMARY_SPEC.format(
                    source_doc=d["path"], source_bytes=d["bytes"], source_sections=d["sections"],
                    out_path=out_path, task_id="TASKID", n_facts=n_facts, min_fact_chars=40,
                    n_questions=rng.randint(2, 4), max_body_chars=9000),
                "acceptance": {"runner": "python3", "file_name": f"accept-summary-{slugify(d['path'])}.py",
                               "file_content": test},
                "participant_validation": ["python3", "-c", "print('doc-repo structural check deferred to acceptance')"],
                "new_files": [out_path],
            })
        used_dirs: set[str] = set()
        for d in docs[half:need]:
            index_dir = str(Path(d["path"]).parent)
            if index_dir in used_dirs:
                continue
            dir_md = sorted(
                f for f in ls_tree(repo, pin, index_dir + "/")
                if f.endswith(".md") and str(Path(f).parent) == index_dir and not f.startswith("diary/")
            )
            if len(dir_md) < 3:
                continue
            used_dirs.add(index_dir)
            n_docs = rng.randint(3, min(6, len(dir_md)))
            out_path = f"g3-work/index-{slugify(d['path'])}.json"
            test = DOC_JSON_TEST.format(out_path=out_path, index_dir=index_dir,
                                        n_docs=n_docs, task_id="TASKID")
            tasks.append({
                "task_kind": "doc_index",
                "grounding": [d["path"]],
                "anchor_symbol": d["path"],
                "title": f"Verified markdown index of {index_dir}/",
                "spec": DOC_JSON_SPEC.format(out_path=out_path, n_docs=n_docs,
                                             index_dir=index_dir, task_id="TASKID"),
                "acceptance": {"runner": "python3", "file_name": f"accept-index-{slugify(d['path'])}.py",
                               "file_content": test},
                "participant_validation": ["python3", "-c", "print('doc-repo structural check deferred to acceptance')"],
                "new_files": [out_path],
            })

    if cfg["kind"] == "docs" and len(tasks) < need:
        used = {t["grounding"][0] for t in tasks}
        for d in docs:
            if len(tasks) >= need:
                break
            if d["path"] in used:
                continue
            n_facts = rng.randint(4, 7)
            out_path = f"g3-work/summary-{slugify(d['path'])}.md"
            test = DOC_SUMMARY_CHECKER.format(
                task_id="TASKID", source_doc=d["path"], out_path=out_path,
                n_facts=n_facts, min_fact_chars=40, n_questions=rng.randint(2, 4),
                source_sections=d["sections"], source_bytes=d["bytes"],
                max_body_chars=9000,
            )
            tasks.append({
                "task_kind": "doc_summary",
                "grounding": [d["path"]],
                "anchor_symbol": d["path"],
                "title": f"Structured summary of {d['path']}",
                "spec": DOC_SUMMARY_SPEC.format(
                    source_doc=d["path"], source_bytes=d["bytes"], source_sections=d["sections"],
                    out_path=out_path, task_id="TASKID", n_facts=n_facts, min_fact_chars=40,
                    n_questions=rng.randint(2, 4), max_body_chars=9000),
                "acceptance": {"runner": "python3", "file_name": f"accept-summary-{slugify(d['path'])}.py",
                               "file_content": test},
                "participant_validation": ["python3", "-c", "print('doc-repo structural check deferred to acceptance')"],
                "new_files": [out_path],
            })
    if len(tasks) < need:
        raise RuntimeError(f"{repo_key}: only {len(tasks)}/{need} grounded tasks available")
    return tasks[:need]


DOC_SUMMARY_CHECKER = '''
import pathlib, re, sys

SOURCE = pathlib.Path("{source_doc}")
OUT = pathlib.Path("{out_path}")
N_FACTS = {n_facts}
MIN_CHARS = {min_fact_chars}
N_QMAX = {n_questions}
SRC_SECTIONS = {source_sections}
SRC_BYTES = {source_bytes}
MAX_BODY = {max_body_chars}
TASK_ID = "{task_id}"

def fail(msg):
    raise SystemExit("REJECT: " + msg)

def main():
    if not OUT.exists():
        fail("output missing")
    text = OUT.read_text(encoding="utf-8")
    if not text.startswith("---\\n"):
        fail("no frontmatter")
    parts = text.split("\\n---\\n", 2)
    if len(parts) < 2:
        fail("frontmatter not closed")
    fm = parts[0][4:]
    keys = dict(re.findall(r"^(\\w+):\\s*(.+)$", fm, re.M))
    for k in ("g3_task", "source", "title", "facts_count", "generated_for"):
        if k not in keys or not keys[k].strip():
            fail("frontmatter key " + k)
    if keys["g3_task"].strip().strip('\\"') != TASK_ID:
        fail("task id")
    if keys["source"].strip().strip('\\"') != SOURCE.as_posix():
        fail("source path")
    if keys["facts_count"].strip() != str(N_FACTS):
        fail("facts_count")
    body = parts[1] if len(parts) == 2 else parts[1] + "\\n---\\n" + parts[2]
    heads = re.findall(r"^## (.+)$", body, re.M)
    if heads != ["Purpose", "Key facts", "Open questions", "Coverage"]:
        fail("sections " + repr(heads))
    facts = re.findall(r"^- (.+)$", body.split("## Open questions")[0].split("## Key facts")[-1], re.M)
    if len(facts) < N_FACTS:
        fail("facts count %d < %d" % (len(facts), N_FACTS))
    src_text = SOURCE.read_text(encoding="utf-8")
    for f in facts:
        if len(f) < MIN_CHARS:
            fail("fact too short")
        for ref in re.findall(r"`([^`]+)`", f):
            if ref not in src_text and ref != SOURCE.as_posix():
                fail("reference not in source: " + ref)
    oq = re.findall(r"^- (.+)$", body.split("## Open questions")[-1].split("## Coverage")[0], re.M)
    if not (1 <= len(oq) <= N_QMAX):
        fail("open questions count %d" % len(oq))
    cov = re.findall(r"```[a-z]*\\n(\\{{.*?\\}})\\n```", body, re.S)
    if len(cov) != 1:
        fail("coverage block")
    import json
    c = json.loads(cov[0])
    if c.get("sections_seen") != SRC_SECTIONS or c.get("bytes") != SRC_BYTES:
        fail("coverage numbers %r" % c)
    body_no_cov = re.sub(r"```[a-z]*\\n\\{{.*?\\}}\\n```", "", body, flags=re.S)
    if len(body_no_cov) > MAX_BODY:
        fail("body too long")
    print("ACCEPT")

main()
'''


# ---------------------------------------------------------------- assembly

def build_corpus() -> dict:
    """Deterministic 168-pair corpus: {pairs: [...]} with cell/stage allocation."""
    rng = random.Random(CAMPAIGN_SEED)
    repo_tasks = {k: build_repo_tasks(k, random.Random(CAMPAIGN_SEED + i))
                  for i, k in enumerate(sorted(REPOS))}

    cells = [
        ("holdingco", "fam-grok", ["fcos"] * 28),
        ("holdingco", "fam-gpt", ["fcos"] * 28),
        ("teachingco", "fam-grok", ["mathe"] * 14 + ["wib"] * 14),
        ("teachingco", "fam-gpt", ["mathe"] * 14 + ["wib"] * 14),
        ("softwareco", "fam-grok", ["piext"] * 28),
        ("softwareco", "fam-gpt", ["piext"] * 28),
    ]

    counters: dict[str, int] = {k: 0 for k in REPOS}
    pairs: list[dict] = []
    for owner, family, repo_seq in cells:
        cell_pool: list[dict] = []
        for repo_key in repo_seq:
            task = dict(repo_tasks[repo_key][counters[repo_key]])
            counters[repo_key] += 1
            task["task_id"] = f"{repo_key}-{counters[repo_key]:03d}"
            task["repo_key"] = repo_key
            task["baseline"] = REPOS[repo_key]["baseline"]
            task["owner_group"] = REPOS[repo_key]["owner_group"]
            # bind TASKID placeholders in spec/checker
            task["spec"] = task["spec"].replace("TASKID", task["task_id"])
            task["acceptance"] = dict(task["acceptance"])
            task["acceptance"]["file_content"] = task["acceptance"]["file_content"].replace("TASKID", task["task_id"])
            cell_pool.append(task)
        rng.shuffle(cell_pool)
        for idx, task in enumerate(cell_pool):
            pairs.append({
                "pair_id": f"P-{owner}-{family}-{idx + 1:02d}",
                "owner_group": owner,
                "base_model_family": family,
                "model_identity": FAMILIES[family],
                "repo_key": task["repo_key"],
                "baseline": task["baseline"],
                "repo_identity": REPOS[task["repo_key"]]["repo_identity"],
                "repo_pin": REPOS[task["repo_key"]]["pin"],
                "stage": "dev" if idx < 4 else "confirm",
                "arm_order": ["static", "evidence"] if rng.random() < 0.5 else ["evidence", "static"],
                "task": task,
            })

    assert len(pairs) == 168, len(pairs)
    for owner in ("holdingco", "teachingco", "softwareco"):
        for family in ("fam-grok", "fam-gpt"):
            cell = [p for p in pairs if p["owner_group"] == owner and p["base_model_family"] == family]
            assert len(cell) == 28
            assert sum(1 for p in cell if p["stage"] == "dev") == 4
    # distinctness of task instances across the whole corpus
    ids = [p["task"]["task_id"] + "@" + p["base_model_family"] for p in pairs]
    assert len(set((p["task"]["task_id"], p["repo_key"]) for p in pairs)) == 168
    return {"schema": SCHEMA, "campaign_seed": CAMPAIGN_SEED, "pairs": pairs}


def assert_initially_failing(corpus: dict) -> None:
    """Every task's new symbols/files must be absent at its repo pin."""
    for pair in corpus["pairs"]:
        repo = Path(REPOS[pair["repo_key"]]["local_path"])
        pin = pair["repo_pin"]
        tree = set(ls_tree(repo, pin))
        for nf in pair["task"].get("new_files", []):
            assert nf not in tree, f"{nf} already exists at pin"
        if pair["task"]["task_kind"] in ("python_helper", "python_json_facts"):
            src = show(repo, pin, pair["task"]["grounding"][0])
            for sym in pair["task"]["new_symbols"]:
                assert f"def {sym}(" not in src, f"{sym} already defined at pin"
        if pair["task"]["task_kind"] == "ts_helper":
            src = show(repo, pin, pair["task"]["grounding"][0])
            for sym in pair["task"]["new_symbols"]:
                assert sym not in src, f"{sym} already exported at pin"


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


if __name__ == "__main__":
    corpus = build_corpus()
    assert_initially_failing(corpus)
    print(json.dumps({
        "schema": corpus["schema"],
        "n_pairs": len(corpus["pairs"]),
        "corpus_digest": digest(corpus),
        "by_repo": {k: sum(1 for p in corpus["pairs"] if p["repo_key"] == k) for k in REPOS},
        "by_cell": {f"{p['owner_group']}/{p['base_model_family']}": 0 for p in corpus["pairs"]} | {
            f"{p['owner_group']}/{p['base_model_family']}": sum(
                1 for q in corpus["pairs"]
                if q["owner_group"] == p["owner_group"] and q["base_model_family"] == p["base_model_family"])
            for p in corpus["pairs"]},
    }, indent=1))
