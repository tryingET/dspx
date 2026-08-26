"""G3 SUCCESSOR corpus (AK 5095; decision 138; design g3-successor-campaign-design.md REV 3).

12 templates x 3 DISTINCT derived instances = 36 instances. Anti-circularity:
no observed v3/v3b instance bytes are reused; every fixture is freshly
derived from per-instance parameters; promotion is difficulty-based only.

Freeze-time note (recorded in the manifest): the design's original wording
drew the 2 harder variants from g3pilot-harder-tasks.json; that line measures
DSPx tooling parity (oracle/attractor/context-packet), a DIFFERENT convention
domain. Importing it would break the instrument's construct
(engineering-core convention-conformance). The harder variants are therefore
COMPOSITIONS within the engineering-core convention space:
  TH1 = legacy->v1 migration + validation-tier-map (A+C4 conventions)
  TH2 = advise-response envelope + degraded-policy repair (B+A conventions)
"""

from __future__ import annotations

import hashlib
import json

RELEASE_REF = "v0.10.0"  # candidate-5 (main@cde7f14) released catalog version
WHEEL_SHA256 = "921bff5ef60ee8dea112cdaf8825e809bb484f1e518a06080e853c7e52288ab0"

FAMILIES = {"fam-gpt": "openai-codex/gpt-5.6-sol:high", "fam-glm": "zai/glm-5.3:high"}
DEFAULT_DISCIPLINES = [
    "validation", "testing", "security-privacy", "documentation", "dependency-governance",
]

COMMON_PREAMBLE = """You are executing a bounded work task in a disposable scratch repository.
Work only inside this repository working tree. No pushes, no remotes, no network
installs (no npm install / pip install / uv sync / uv add). Use only what is
already present in the tree. Do not modify anything under .git/. Do not search
the wider filesystem for pre-installed tools, packages, or wheels related to
this task; complete it from this repository and the task materials only.

Deliver a claim file at path `G3P3_CLAIM.md` in the repository root stating:
(a) which files you changed or created, (b) how each specification clause is
satisfied, (c) how you verified it (commands you ran and their results). The
claim must mention the new file path(s) or symbol(s) you added.
"""

CLAIM_NOTE = COMMON_PREAMBLE  # alias: preamble carries the claim contract


def _py_fixture(pkg: str, module: str, fn: str, doc: str) -> dict[str, str]:
    """Fresh minimal Python package fixture (distinct from v3b bytes)."""
    return {
        "pyproject.toml": (
            "[project]\n"
            f'name = "{pkg}"\n'
            'version = "0.1.0"\n'
            'requires-python = ">=3.11"\n'
            "[tool.hatch.build.targets.wheel]\n"
            'packages = ["src"]\n'
        ),
        "README.md": (
            f"# {pkg}\n\n{doc}\n\nRun checks with `just check`.\n"
        ),
        "Justfile": (
            "set shell := ['bash', '-cu']\n\n"
            "check:\n"
            "    python -m compileall src\n\n"
            "test:\n"
            "    python -m pytest tests -q\n"
        ),
        f"src/{pkg}/__init__.py": f'"""{doc}"""\n\n__all__ = ["{module}"]\n',
        f"src/{pkg}/{module}.py": (
            f'"""{doc}"""\n\n\ndef {fn}(value: str) -> str:\n'
            f'    """Return the normalized form of value."""\n'
            f"    return value.strip().lower()\n"
        ),
        "tests/__init__.py": "",
        f"tests/test_{module}.py": (
            f"from {pkg}.{module} import {fn}\n\n\n"
            f"def test_{fn}() -> None:\n"
            f'    assert {fn}(" X ") == "x"\n'
        ),
    }


def _legacy_overlay(legacy_doc: str, lane_note: str) -> dict[str, str]:
    return {
        "policy/stack-lane.json": (
            "{\n"
            '  "stack": {\n'
            f'    "lane": "py",\n'
            f'    "note": "{lane_note}",\n'
            '    "commands": {"lint": "python -m compileall src"}\n'
            "  }\n"
            "}\n"
        ),
        "docs/tech-stack.local.md": legacy_doc,
    }


def _v1_policy(ref: str, disciplines: list[str], deviations: list[dict] | None = None) -> str:
    return json.dumps(
        {
            "engineering_core": {
                "tool": "engineering-core",
                "ref": ref,
                "lanes": ["py"],
                "catalog_command": "engineering-core catalog --pretty",
                "list_disciplines_command": "engineering-core list-disciplines",
                "list_templates_command": "engineering-core list-templates",
                "disciplines": disciplines,
                "deviations": deviations or [],
            }
        },
        indent=2,
    ) + "\n"


def _v1_doc(summary: str, read_when: str, deviations: list[str] | None = None) -> str:
    dev = deviations or ["None at this time."]
    return (
        "---\n"
        f'summary: "{summary}"\n'
        "read_when:\n"
        f'  - "{read_when}"\n'
        "---\n\n"
        "# Engineering (local)\n\n"
        "## Selected lane\n\n- py\n\n"
        "## Selected disciplines\n\n"
        + "".join(f"- {d}\n" for d in DEFAULT_DISCIPLINES)
        + "\n## Validation evidence\n\n"
        "Every handoff records the commands run, their scope, and results "
        "(`just check`, `just test`) before merge.\n\n"
        "## Deliberate deviations\n\n"
        + "".join(f"- {d}\n" for d in dev)
    )


# ------------------------------------------------------------------ fixtures

def fixture_legacy_py(inst: str) -> dict[str, str]:
    """TA1/TA3/TH1 instance fixtures: legacy surfaces, no v1 surfaces."""
    pkg = {"a": "ledger_service", "b": "notifier_service", "c": "authz_service"}[inst]
    doc = {"a": "Ledger totals helper.", "b": "Notifier fan-out helper.", "c": "Authz check helper."}[inst]
    fx = _py_fixture(pkg, {"a": "totals", "b": "fanout", "c": "check"}[inst],
                     {"a": "normalize_account", "b": "normalize_topic", "c": "normalize_role"}[inst], doc)
    legacy = _legacy_overlay(
        {"a": "# Tech stack (local)\n\nLegacy stack note: py lane, compileall lint only.\n",
         "b": "# Tech stack (local)\n\nLegacy stack note: py lane; see policy/stack-lane.json.\n",
         "c": "# Tech stack (local)\n\nLegacy stack note: py lane, single package.\n"}[inst],
        {"a": "legacy stack-lane config", "b": "legacy stack selection", "c": "legacy lane pin"}[inst],
    )
    fx.update(legacy)
    return fx


def fixture_degraded_py(inst: str) -> dict[str, str]:
    """TA2 instance fixtures: v1 surfaces present but DEFECTIVE (distinct defect mixes)."""
    pkg = {"a": "pricing_service", "b": "routing_service", "c": "audit_service"}[inst]
    doc = {"a": "Pricing band helper.", "b": "Routing table helper.", "c": "Audit trail helper."}[inst]
    fx = _py_fixture(pkg, {"a": "bands", "b": "table", "c": "trail"}[inst],
                     {"a": "normalize_sku", "b": "normalize_prefix", "c": "normalize_event"}[inst], doc)
    dev = [{
        "id": "keep-local-uv-mirror",
        "reason": "offline workstation mirror required",
        "owner": "platform",
        "evidence": "infra/mirror.md",
        "review_date": "2026-09-30",
    }]
    if inst == "a":
        # defects: old ref + disciplines as comma string (schema violation)
        policy = json.dumps({
            "engineering_core": {
                "tool": "engineering-core", "ref": "v0.9.0", "lanes": ["py"],
                "catalog_command": "engineering-core catalog --pretty",
                "list_disciplines_command": "engineering-core list-disciplines",
                "list_templates_command": "engineering-core list-templates",
                "disciplines": ", ".join(DEFAULT_DISCIPLINES),
                "deviations": dev,
            }}, indent=2) + "\n"
    elif inst == "b":
        # defects: old ref + unknown lane id 'python'
        policy = json.dumps({
            "engineering_core": {
                "tool": "engineering-core", "ref": "v0.9.0", "lanes": ["python"],
                "catalog_command": "engineering-core catalog --pretty",
                "list_disciplines_command": "engineering-core list-disciplines",
                "list_templates_command": "engineering-core list-templates",
                "disciplines": DEFAULT_DISCIPLINES,
                "deviations": dev,
            }}, indent=2) + "\n"
    else:
        # defects: old ref + empty catalog/list command fields
        policy = json.dumps({
            "engineering_core": {
                "tool": "engineering-core", "ref": "v0.9.0", "lanes": ["py"],
                "catalog_command": "",
                "list_disciplines_command": "",
                "list_templates_command": "",
                "disciplines": DEFAULT_DISCIPLINES,
                "deviations": dev,
            }}, indent=2) + "\n"
    fx["policy/engineering-lane.json"] = policy
    fx["docs/engineering.local.md"] = (
        f"# Engineering (local)\n\n{doc}\n\nNo structure: lane and disciplines "
        "are described in prose only. Deviation keep-local-uv-mirror applies.\n"
    )
    return fx


def fixture_ts_web(inst: str) -> dict[str, str]:
    deps = {"a": ("react", "18.3.1"), "b": ("react-dom", "18.2.0"), "c": ("react", "19.0.0")}[inst]
    name = {"a": "shop-web", "b": "docs-web", "c": "admin-web"}[inst]
    return {
        "README.md": f"# {name}\n\nSmall web app.\n",
        "package.json": (
            "{\n"
            f'  "name": "{name}",\n'
            '  "version": "0.2.0",\n'
            '  "type": "module",\n'
            '  "scripts": {"start": "node src/index.js"},\n'
            f'  "dependencies": {{"{deps[0]}": "^{deps[1]}"}}\n'
            "}\n"
        ),
        "src/index.js": (
            f"import {{ render }} from '{deps[0]}';\n\n"
            f"export function main(root) {{\n  render(root, '{name} ready');\n}}\n"
        ),
    }


def fixture_adopted_redact_py(inst: str) -> dict[str, str]:
    pkg = {"a": "billing_service", "b": "search_service", "c": "report_service"}[inst]
    token = {"a": "ghp_SU1AAA", "b": "ghp_SU2BBB", "c": "ghp_SU3CCC"}[inst]
    email = {"a": "oncall-a@example.test", "b": "oncall-b@example.test", "c": "oncall-c@example.test"}[inst]
    fx = _py_fixture(pkg, {"a": "charges", "b": "index", "c": "sheets"}[inst],
                     {"a": "normalize_invoice", "b": "normalize_query", "c": "normalize_row"}[inst],
                     {"a": "Billing charge helper.", "b": "Search index helper.", "c": "Report sheet helper."}[inst])
    fx["policy/engineering-lane.json"] = _v1_policy("v1.0.0", DEFAULT_DISCIPLINES)  # inert for grading
    fx["docs/engineering.local.md"] = _v1_doc(
        f"{pkg} local engineering surface.", "Changing local engineering adoption.",
    )
    fx["ops/deploy.note.md"] = (
        f"# Deploy note\n\nRotate token {token} quarterly.\n"
        f"Escalations: {email}.\n"
    )
    return fx


def fixture_piext(inst: str) -> dict[str, str]:
    """TC1/TC2 instance fixtures: pi-context-packer-shaped package replicas."""
    fn = {"a": ("g3ps-changelog-audit", "auditChangelogEntries"),
          "b": ("g3ps-todo-audit", "auditTodoMarkers"),
          "c": ("g3ps-license-audit", "auditLicenseHeaders")}[inst]
    pkg_json = (
        "{\n"
        "  \"name\": \"pi-context-packer\",\n"
        "  \"version\": \"1.4.0\",\n"
        "  \"type\": \"module\",\n"
        "  \"scripts\": {\"" + fn[0] + "\": \"node src/" + fn[0] + ".js\"},\n"
        "  \"dependencies\": {}\n"
        "}\n"
    )
    return {
        "package.json": pkg_json,
        "biome.jsonc": (
            "{\n  \"formatter\": {\"enabled\": true, \"indentStyle\": \"space\", "
            "\"indentWidth\": 2, \"lineWidth\": 100},\n  \"javascript\": "
            "{\"formatter\": {\"quoteStyle\": \"double\", \"semicolons\": \"always\"}}\n}\n"
        ),
        "src/existing.js": (
            "/**\nsummary: \"Existing helper.\"\nread_when:\n  - \"Never.\"\n*/\n"
            "export const existing = 1;\n"
        ),
        "README.md": "# pi-context-packer\n\nContext packing extension package.\n",
    }


def fixture_dspx(inst: str) -> dict[str, str]:
    """TC3/TC4/TH1-tier instance fixtures: dspx-shaped python repo replicas."""
    pkg = {"a": "dspx-core", "b": "dspx-core", "c": "dspx-core"}[inst]
    mod = {"a": "seat_budget", "b": "quorum", "c": "backoff"}[inst]
    return {
        "pyproject.toml": (
            "[project]\nname = \"dspx-monorepo\"\nversion = \"0.9.0\"\n"
            "requires-python = \">=3.13\"\n"
        ),
        "README.md": "# dspx replica\n\nPython 3.13 + uv; ruff + pytest gates.\n",
        "Justfile": (
            "set shell := ['bash', '-cu']\n\n"
            "check:\n"
            "    ruff check .\n\n"
            "test:\n"
            "    python -m pytest tests -q\n\n"
            "lint:\n"
            "    ruff check .\n"
        ),
        "packages/dspx-core/pyproject.toml": (
            f"[project]\nname = \"{pkg}\"\nversion = \"0.9.0\"\n"
        ),
        "packages/dspx-core/src/dspx/__init__.py": '"""dspx core."""\n',
        "tests/__init__.py": "",
        "tests/conftest.py": (
            "import sys\nfrom pathlib import Path\n\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "
            "\"packages\" / \"dspx-core\" / \"src\"))\n"
        ),
        f"docs/engineering-note-{mod}.md": f"# Note {mod}\n\nExisting note.\n",
    }


FIXTURE_BUILDERS = {
    "FIX_LEGACY_PY": fixture_legacy_py,
    "FIX_DEGRADED_PY": fixture_degraded_py,
    "FIX_TS_WEB": fixture_ts_web,
    "FIX_ADOPTED_REDACT_PY": fixture_adopted_redact_py,
    "FIX_PIEXT": fixture_piext,
    "FIX_DSPX": fixture_dspx,
}


# ------------------------------------------------------------------ specs

def spec_ta1(inst: str) -> str:
    pkg = {"a": "ledger_service", "b": "notifier_service", "c": "authz_service"}[inst]
    return COMMON_PREAMBLE + f"""
TASK (TA1-{inst}): Complete this repository's migration from the legacy tech-stack
adoption surfaces to the v1 engineering adoption contract.

Current state: this repository ({pkg}) still carries the LEGACY surfaces
`policy/stack-lane.json` and `docs/tech-stack.local.md`, and has NO v1
adoption surfaces.

Required end state (verification is objective, deterministic, and automated;
the frozen checker runs the engineering-core 0.10.0 CLI against your tree):

1. `policy/engineering-lane.json` exists with an `engineering_core` object that
   has: `tool` == "engineering-core"; `lanes` == ["py"]; a release `ref` pinned
   to the currently released catalog version in the exact released-ref format;
   non-empty `catalog_command`, `list_disciplines_command`, and
   `list_templates_command` fields; `disciplines` as a non-empty JSON array of
   valid catalog discipline ids that includes the five default cross-language
   disciplines; `deviations` as a list.
2. `docs/engineering.local.md` exists and is structured repo-local engineering
   documentation: YAML front matter with a `summary` and at least one
   `read_when` trigger; the selected lane; the selected disciplines; the
   validation-evidence expectation before handoff; and a deliberate-deviations
   section.
3. The legacy files `policy/stack-lane.json` and `docs/tech-stack.local.md` are
   REMOVED.
4. `engineering-core doctor --repo .` exits 0 with EVERY check status "pass"
   and pin posture "released-match".
5. `engineering-core scan-adoption --scope . --include-scope-root --format
   json` reports completeness "complete" and this repository's record with
   structural status "adopted", no legacy flags, no unknown-id notes.
6. Every other repository file remains byte-identical to its current content.
"""


def spec_ta2(inst: str) -> str:
    defect = {
        "a": "the policy `ref` is pinned to an old release AND `engineering_core.disciplines` "
             "violates the schema (it is not a JSON array of ids);",
        "b": "the policy `ref` is pinned to an old release AND `engineering_core.lanes` "
             "contains an id that is not in the catalog;",
        "c": "the policy `ref` is pinned to an old release AND the three catalog/list "
             "command fields are empty;",
    }[inst]
    return COMMON_PREAMBLE + f"""
TASK (TA2-{inst}): Repair this repository's degraded v1 engineering adoption.

Current state: v1 adoption surfaces exist but are DEFECTIVE:
- {defect}
- `docs/engineering.local.md` is unstructured: no front matter, no sections.

Required end state (frozen checker runs the engineering-core 0.10.0 CLI):

1. `engineering-core doctor --repo .` exits 0 with EVERY check status "pass"
   and pin posture "released-match".
2. `engineering-core scan-adoption --scope . --include-scope-root --format
   json` reports completeness "complete" and this repository's record with
   structural status "adopted", no legacy flags, no unknown-id notes.
3. `policy/engineering-lane.json`: `tool` == "engineering-core"; `lanes` ==
   ["py"]; `ref` == the current released catalog version in the exact
   released-ref format; the three catalog/list command fields non-empty;
   `disciplines` a JSON array of valid catalog discipline ids that includes
   the five default cross-language disciplines.
4. The existing structured deviation entry (id `keep-local-uv-mirror` with its
   reason, owner, evidence, review_date) is PRESERVED unchanged in
   `engineering_core.deviations`.
5. `docs/engineering.local.md` is rewritten to structured form: YAML front
   matter with `summary` and at least one `read_when`; selected lane; selected
   disciplines; validation-evidence expectation; a deliberate-deviations
   section that lists the preserved deviation by its id.
6. The legacy tech-stack files remain ABSENT; every other repository file
   remains byte-identical.
"""


def spec_ta3(inst: str) -> str:
    pkg = {"a": "ledger_service", "b": "notifier_service", "c": "authz_service"}[inst]
    return COMMON_PREAMBLE + f"""
TASK (TA3-{inst}): Execute the full adoption->rollback lifecycle on this legacy
repository ({pkg}) BY HAND (the engineering-core CLI is not available to you) and prove
it with a transaction record.

Phase 1 (apply): author the v1 adoption contract for this repository —
create `policy/engineering-lane.json` (engineering_core with tool
"engineering-core", lanes ["py"], ref = current released catalog version in the
exact released-ref format, the three catalog/list command fields non-empty,
disciplines = a JSON array of valid catalog discipline ids including the five
default cross-language disciplines, deviations a list) and
`docs/engineering.local.md` (YAML front matter with summary and read_when;
selected lane and disciplines; validation-evidence expectation;
deliberate-deviations section), and REMOVE the legacy files
`policy/stack-lane.json` and `docs/tech-stack.local.md`.

Phase 2 (rollback): restore the repository to its EXACT pre-adoption bytes
(legacy files restored byte-for-byte, adoption files deleted) and leave no
adoption journal (no `.engineering-core/` directory).

Final tree requirements (frozen checker verifies digests):
- every original repository file byte-identical to its current content;
- `policy/engineering-lane.json`, `docs/engineering.local.md`, and
  `.engineering-core/` all ABSENT.

Transaction record (the proof that both phases really ran), directory
`.g3p3-transaction/`:

`apply.json` — the applied adoption plan:
  {{"mode": "migrate", "repo": "<abs repo path>", "lanes": ["py"],
   "disciplines": [<the discipline ids you selected>],
   "changes": [ four entries in apply order, each an object with keys
     path, action, before_sha256, after_sha256, before_b64, after_b64
     (sha256 = hex digest of the bytes; b64 = base64 of the bytes; null when
     absent):
     - policy/engineering-lane.json: action "create", before_* null,
       after_* = your created file's bytes;
     - docs/engineering.local.md: action "create", before_* null,
       after_* = your created file's bytes;
     - policy/stack-lane.json: action "delete", before_* = the file's
       ORIGINAL bytes, after_* null;
     - docs/tech-stack.local.md: action "delete", before_* = the file's
       ORIGINAL bytes, after_* null ],
   "safe_to_apply": true, "applied": true}}

`rollback.json` — the rollback receipt:
  {{"command": "rollback", "repo": "<abs repo path>", "status": "rolled_back",
   "restored": [{{"path": "policy/stack-lane.json", "action": "restored"}},
                {{"path": "docs/tech-stack.local.md", "action": "restored"}},
                {{"path": "policy/engineering-lane.json", "action": "removed"}},
                {{"path": "docs/engineering.local.md", "action": "removed"}}],
   "journal_removed": true}}

The checker decodes apply.json's base64 payloads and validates that the
created adoption files satisfied the v1 contract and that the recorded legacy
before-bytes equal the repository's original bytes.
"""


B_SPEC = COMMON_PREAMBLE + """
TASK ({tid}): Produce the advisory response the engineering advisor surface
expects for this repository.

The `engineering-advice-request-v1` JSON below was compiled for THIS repository
by `engineering-core advise` (digest-verified evidence, fixed budgets). The
request's compiled plan section is withheld from you (it is the answer key);
everything you need to bind a response is included: the request digest, the
captured evidence items (id, path, span), the allowed catalog id vocabulary,
and the prompt identity.

Produce ONE new file `g3p3-advice-response.json` in the repository root: a
valid `engineering-advice-response-v1` bound to this request. Do not modify any
existing repository file.

Envelope contract (mechanical):
- top-level keys EXACTLY: schema, request_sha256, provenance, status, summary,
  recommendations, critiques, patch_proposals
- schema: "engineering-advice-response-v1"; request_sha256: the request digest
  given below (copied exactly)
- provenance: object with keys EXACTLY provider, model, model_version, adapter,
  adapter_version, prompt_id, prompt_version (all non-empty strings; prompt_id
  and prompt_version must equal the request's prompt identity given below)
- status: "advice" (this task requires substantive advice; "abstain"/"unknown"
  would fail the substance requirements)
- summary: non-empty bounded text
- recommendations: array of 2..20 objects, each with keys EXACTLY id,
  catalog_ids, recommendation, confidence, unknowns, counterevidence,
  falsification, citations, competes_with
  - id: unique non-empty string; confidence: number in [0,1];
    catalog_ids: array of ids drawn ONLY from the allowed vocabulary below;
    recommendation/summary-like fields: non-empty text; unknowns,
    counterevidence, falsification, competes_with: arrays of strings
    (competes_with may only reference other recommendation ids you defined)
  - citations: array of objects with keys EXACTLY evidence_id, path, start,
    end — evidence_id and path must match one captured evidence item below,
    with integer spans 0 <= start < end <= that item's span end
- critiques: array of 0..20 objects with keys EXACTLY recommendation_id,
  critique, severity, falsification — recommendation_id must reference one of
    your recommendation ids; severity one of "low", "medium", "high"
- patch_proposals: [] (exactly empty in this task)
- all text fields bounded (<= 16000 bytes each)

Substance requirements (also checked):
- status == "advice" and at least 2 recommendations
- the UNION of catalog_ids across all recommendations EQUALS the set of lane
  and discipline ids the product's plan compiler selects (as requested
  selections) for this repository state — derive it from the repository, not
  from guesswork: which lane(s) the repository's manifests select (including
  any frontend addendum lane a frontend dependency triggers), plus the five
  default cross-language disciplines, or — when a v1 adoption policy is
  present — the selections that policy declares
- every recommendation carries at least one valid citation into the captured
  evidence (citing the file that justifies the recommendation)
- at least one critique referencing an existing recommendation id

NOTE on spans: citations are validated against the request's captured evidence
representations. If a captured file was redacted during capture, valid spans
are bounds on the REDACTED representation, and the redacted placeholders are
what the advisor may quote.

ACCEPTANCE REQUEST MATERIALS:
{request_materials}
"""


def spec_tb1(_inst: str) -> str:
    return B_SPEC.replace("{request_materials}", "{request_materials}").format(tid="TB1", request_materials="{request_materials}") + "\n"


def spec_tb2(_inst: str) -> str:
    return B_SPEC.format(tid="TB2", request_materials="{request_materials}") + "\n"


def spec_tb3(_inst: str) -> str:
    return B_SPEC.format(tid="TB3", request_materials="{request_materials}") + "\n"


def spec_tc1(inst: str) -> str:
    fn = {"a": ("g3ps-changelog-audit", "auditChangelogEntries", "summarizeChangelogAudit",
                "`entries` is an array of objects {file, text}. `auditChangelogEntries` "
                "returns one entry per input, in input order: {file, hasHeader, summary, "
                "readWhen} where hasHeader is true iff text contains a changelog-header "
                "block (a `<!-- changelog -->` HTML comment followed by a `## ` heading "
                "line), summary is the heading text after `## ` (or null when absent), "
                "readWhen is the array of quoted strings on `read_when:` trigger lines "
                "inside the block (empty when none, null when hasHeader is false). "
                "`summarizeChangelogAudit` returns {total, withHeader, missingHeader}."),
          "b": ("g3ps-todo-audit", "auditTodoMarkers", "summarizeTodoAudit",
                "`sources` is an array of objects {file, text}. `auditTodoMarkers` returns "
                "one entry per input, in input order: {file, hasTodos, count, firstLine} "
                "where hasTodos is true iff text contains at least one TODO marker (a line "
                "matching `// TODO:` or `# TODO:`), count is the number of such lines, "
                "firstLine is the 1-indexed line number of the first marker (or null). "
                "`summarizeTodoAudit` returns {total, withTodos, missingTodos}."),
          "c": ("g3ps-license-audit", "auditLicenseHeaders", "summarizeLicenseAudit",
                "`sources` is an array of objects {file, text}. `auditLicenseHeaders` "
                "returns one entry per input, in input order: {file, hasHeader, license, "
                "years} where hasHeader is true iff the first line of text starts with "
                "`// SPDX-License-Identifier:`, license is the identifier after that "
                "prefix (trimmed, or null when absent), years is the array of integers "
                "found in a `// Copyright (c) <years>` line that follows (empty when "
                "none, null when hasHeader is false). `summarizeLicenseAudit` returns "
                "{total, withHeader, missingHeader}."),
          }[inst]
    return COMMON_PREAMBLE + f"""
TASK (TC1-{inst}): Add an audit module with conforming tests to the
`packages/pi-context-packer` package area of this repository replica.

Repository context: the package is a pi extension package (Node + npm, ESM).
Its sources follow ESM JavaScript, `node:` builtins only, doc-header comments,
and Node's built-in test runner. The package's biome configuration is the
formatting/linting gate: 2-space indent, line width 100, double quotes,
semicolons.

Create exactly two new files at the package root (nothing else may change):

1. `{fn[0]}.js` — pure ESM module, `node:` builtins only, exporting:

       export function {fn[1]}(sources)
       export function {fn[2]}(sources)

   {fn[3]} No filesystem or network access; deterministic; no external
   dependencies.

2. `{fn[0]}.test.js` — tests for the Node built-in test runner
   (node:test + node:assert/strict), importing the module by relative path,
   with a doc-header comment of its own, containing at least 3 distinct tests:
   a parsing case, a missing/degenerate case, and a summary/aggregation case
   over at least 8 fixture inputs (deterministic, no unseeded randomness).

Constraints (checked): both files pass `node --check`; the test file passes
`node --test` (all tests pass, at least 3); both files respect 2-space
indent, width 100, double quotes, semicolons (hand-satisfied); each file
stays within 500 lines and 50 KiB.
"""


def spec_tc2(inst: str) -> str:
    tgt = {"a": "release:contracts:validate", "b": "lint:docs", "c": "typecheck:web"}[inst]
    return COMMON_PREAMBLE + f"""
TASK (TC2-{inst}): Expose a new quick validation command on this repository's
standardized command surface as a thin alias pair, exactly per the repo's
command-surface rule for this kind of repository.

The rule: the Justfile surface standardizes operator-facing command names
while each recipe stays a THIN ALIAS delegating to a package script — prefer
existing package scripts and wrappers, do not bury logic inside ad-hoc
Justfile shell blocks, do not invent fake targets.

Deliverables (exactly two changes; nothing else may change):

1. In the ROOT `package.json`, add script key `g3ps-quick-check` whose value
   is a thin delegation to the repository's EXISTING script `{tgt}` — i.e.
   the value must be exactly `npm run {tgt}` (no new logic, no new wrapper
   files).

2. In the ROOT `Justfile`, add a recipe that exposes the same command name as
   a thin alias over that package script:

       # G3PS quick check (thin alias over the package script)
       g3ps-quick-check:
           npm run g3ps-quick-check

   The recipe body must be exactly the thin alias invocation (a single
   `npm run g3ps-quick-check` line, optionally `@`-prefixed), must not cd,
   must not inline node/bash logic, and must not duplicate what the package
   script already expresses. Keep the existing `#`-comment style. Do not
   alter any existing recipe.

Checks (frozen): `just --list` still parses and lists the new recipe;
`just --dry-run g3ps-quick-check` exits 0 and prints the aliased command;
package.json parses as JSON with the exact script value; the Justfile recipe
body is exactly the thin alias; no other file changes.
"""


def spec_tc3(inst: str) -> str:
    fn = {"a": ("split_seat_budget", "total seats across departments by largest-remainder "
                "rounding: exact share_i = total * w_i / W; base_i = floor(exact share); "
                "distribute remaining units one each to keys with the LARGEST fractional "
                "parts; ties on fractional part broken by key in ascending lexicographic "
                "order; invariant: allocations sum to total, every allocation >= 0, keys "
                "exactly the input keys"),
          "b": ("compute_quorum_round", "the smallest round number r such that the sum of "
                "votes cast in the first r rounds reaches the quorum q; votes is a list of "
                "non-negative ints; raise ValueError if q < 0 or if the total votes never "
                "reach q (return len(votes)+1 is WRONG — raising is required); r is "
                "1-indexed; invariant: sum(votes[:r]) >= q and sum(votes[:r-1]) < q"),
          "c": ("backoff_schedule", "the list of the first n retry delays in milliseconds: "
                "delay_i = base * 2**min(i, cap) for i in 0..n-1, floored to an int; raise "
                "ValueError if n < 0, base <= 0, or cap < 0; invariant: len == n, "
                "delays[0] == int(base), delays non-decreasing"),
          }[inst]
    sig = {"a": "def split_seat_budget(total: int, weights: Mapping[str, float]) -> dict[str, int]",
           "b": "def compute_quorum_round(votes: Sequence[int], quorum: int) -> int",
           "c": "def backoff_schedule(n: int, base: float, cap: int) -> list[int]"}[inst]
    return COMMON_PREAMBLE + f"""
TASK (TC3-{inst}): Add a service function with conforming tests to this Python
monorepo replica (add NEW files only).

Repository context: Python 3.13 + uv; package sources live under
`packages/dspx-core/src/dspx/`; tests live in the root `tests/` directory
(pytest, with the package sources on sys.path via the repo's conftest). The
repo's quality gates are ruff (lint, default rules, 88-col lines) and pytest.
The testing discipline expects a property-style test (clear invariant over
many generated cases) beside behavior tests when the function has a strong
invariant. The environment has pytest and the standard library only — do not
import packages that are not present (no hypothesis; use plain pytest with
deterministic generated cases).

Create exactly two new files (nothing else may change):

1. `packages/dspx-core/src/dspx/g3ps_{ {"a": "seat_budget", "b": "quorum", "c": "backoff"}[inst] }.py` —
   module docstring, fully typed, exporting exactly:

       {sig}

   Semantics (must match exactly): {fn[1]}.

2. `tests/test_g3ps_{ {"a": "seat_budget", "b": "quorum", "c": "backoff"}[inst] }.py` —
   pytest tests: at least 3 distinct tests covering a basic case, the
   ValueError cases, and a property-style test asserting the stated invariant
   over at least 8 deterministic generated cases (fixed literal list or a
   fixed-seed random.Random — no unseeded randomness).

Checks (frozen): ruff check passes on both new files; the new test file
passes targeted pytest (`python -m pytest tests/test_g3ps_... -q`, at least 3
passed); both files within 500 lines / 50 KiB; ruff default line length (88)
respected.
"""


def spec_tc4(inst: str) -> str:
    shape = {"a": "Justfile with check/test/lint recipes",
             "b": "Justfile with check/test/lint/ci recipes",
             "c": "Justfile with check/test/lint recipes and a doctor script"}[inst]
    return COMMON_PREAMBLE + f"""
TASK (TC4-{inst}): Tier this repository's checks into a validation-tier-map
artifact in the exact frozen shape this repo family's validation discipline
defines.

Create exactly one new file `docs/validation-tier-map.md` (nothing else may
change). This repository's command surface: {shape}. The artifact must follow
the validation-tier-map template shape:

1. YAML front matter with `summary` (one sentence) and `read_when` (at least
   one trigger condition).
2. H1 title `# Validation Tier Map`, then a `Repo:` line and an owner-surface
   line naming `docs/engineering.local.md`.
3. Section `## Commands` containing a markdown table with header row EXACTLY:
   `| Tier | Command | Scope | Target runtime | Required before |`
   and exactly one row for each of the six tiers, in order:
   `editor/save`, `pre-commit`, `task-scope`, `pre-push`, `CI`, `release`
   — each row's Command cell non-empty and mapping a REAL command of this
   repository (a real Justfile recipe, script, or documented command); the
   Scope/Target-runtime/Required-before cells filled per the tier model
   (file-local+instant / staged slice+p95<10s / changed behavior+minutes /
   repo full gate / authoritative matrix+complete / shipped artifact+strongest).
4. Section `## Standard surface` mapping the standard commands of this
   repository's Justfile to what they actually run here, one bullet per key in
   this order: `just check`, `just test`, `just build`, `just ci`,
   `just doctor` — each bullet of the form "- `just X`: `<maps to>`". The
   mappings must be TRUE for this repository (reference the real recipe or
   script each standard command maps to). If a standard target is
   intentionally unavailable in this repository, say `n/a` and why — do not
   invent a fake target.
5. Section `## Evidence rule` stating the handoff evidence contract: every
   handoff records command, scope, result, warning acceptance (if any), and
   artifact path (if any).

Checks (frozen): template-shape assertions (front matter, headings, exact
table header, all six tier rows in order, five standard-surface bullets in
order, evidence-rule items) plus semantic truth: the `just check`, `just
test`, `just build`, `just ci`, `just doctor` mappings must reference
recipes/scripts that actually exist in this repository's Justfile (or be
marked n/a with a reason where genuinely absent).
"""


def spec_th1(inst: str) -> str:
    pkg = {"a": "ledger_service", "b": "notifier_service", "c": "authz_service"}[inst]
    return COMMON_PREAMBLE + f"""
TASK (TH1-{inst}): Perform a COMPOUND adoption change on this legacy repository
({pkg}): migrate it to the v1 engineering adoption contract AND tier its
validation surface, in one change.

Part 1 (migration): exactly the v1 adoption migration — create
`policy/engineering-lane.json` (engineering_core with tool "engineering-core",
lanes ["py"], ref = current released catalog version in the exact
released-ref format, the three catalog/list command fields non-empty,
disciplines = a JSON array of valid catalog discipline ids including the five
default cross-language disciplines, deviations a list) and
`docs/engineering.local.md` (YAML front matter with summary and read_when;
selected lane and disciplines; validation-evidence expectation;
deliberate-deviations section); REMOVE the legacy files
`policy/stack-lane.json` and `docs/tech-stack.local.md`.

Part 2 (tier map): create `docs/validation-tier-map.md` in the exact frozen
shape: YAML front matter with summary and read_when; H1 `# Validation Tier
Map`, a `Repo:` line, an owner-surface line naming `docs/engineering.local.md`;
section `## Commands` with header row EXACTLY
`| Tier | Command | Scope | Target runtime | Required before |` and one row
for each tier in order `editor/save`, `pre-commit`, `task-scope`, `pre-push`,
`CI`, `release`, each Command cell mapping a REAL recipe of this repository's
Justfile; section `## Standard surface` with bullets in order for `just
check`, `just test`, `just build`, `just ci`, `just doctor` (each either a
true mapping or `n/a` with a reason — never a fake target); section
`## Evidence rule` stating command, scope, result, warning acceptance, and
artifact path are recorded at every handoff.

Checks (frozen): the engineering-core 0.10.0 CLI gate (doctor all-pass,
released-match; scan completeness "complete", structural status "adopted",
no legacy flags, no unknown-id notes), the tier-map template-shape and
semantic-truth assertions, and byte-identity of every unrelated file.
"""


def spec_th2(inst: str) -> str:
    defect = {
        "a": "disciplines is a comma string",
        "b": "lanes contains the unknown id 'python'",
        "c": "the three catalog/list command fields are empty",
    }[inst]
    return B_SPEC.format(tid=f"TH2-{inst}", request_materials="{request_materials}") + f"""
ADDITIONALLY (compound deliverable): this repository's
`policy/engineering-lane.json` is DEFECTIVE ({defect}; ref pinned to an old
release). In the SAME change, repair the policy to full v1 conformance
(`tool` == "engineering-core"; `lanes` == ["py"]; `ref` == current released
catalog version in the exact released-ref format; the three catalog/list
command fields non-empty; `disciplines` a JSON array of valid ids including
the five default cross-language disciplines), PRESERVING the existing
deviation entry (id `keep-local-uv-mirror`) unchanged, and rewrite
`docs/engineering.local.md` to structured form (front matter summary +
read_when; selected lane; selected disciplines; validation-evidence
expectation; deliberate-deviations section listing the preserved deviation
id). The frozen checker grades BOTH the response envelope and the repaired
adoption surfaces.
"""


# ------------------------------------------------------------------ assembly

TEMPLATES = {
    "TA1": {"cls": "A", "fixture": "FIX_LEGACY_PY", "spec": spec_ta1},
    "TA2": {"cls": "A", "fixture": "FIX_DEGRADED_PY", "spec": spec_ta2},
    "TA3": {"cls": "A", "fixture": "FIX_LEGACY_PY", "spec": spec_ta3},
    "TB1": {"cls": "B", "fixture": "FIX_LEGACY_PY", "spec": spec_tb1},
    "TB2": {"cls": "B", "fixture": "FIX_TS_WEB", "spec": spec_tb2},
    "TB3": {"cls": "B", "fixture": "FIX_ADOPTED_REDACT_PY", "spec": spec_tb3},
    "TC1": {"cls": "C", "fixture": "FIX_PIEXT", "spec": spec_tc1},
    "TC2": {"cls": "C", "fixture": "FIX_PIEXT", "spec": spec_tc2},
    "TC3": {"cls": "C", "fixture": "FIX_DSPX", "spec": spec_tc3},
    "TC4": {"cls": "C", "fixture": "FIX_DSPX", "spec": spec_tc4},
    "TH1": {"cls": "H", "fixture": "FIX_LEGACY_PY", "spec": spec_th1},
    "TH2": {"cls": "H", "fixture": "FIX_DEGRADED_PY", "spec": spec_th2},
}

INSTANCES = ["a", "b", "c"]


def build_corpus() -> dict:
    """Enumerate the 36-instance corpus deterministically."""
    templates = {}
    for tid, t in sorted(TEMPLATES.items()):
        instances = []
        for inst in INSTANCES:
            fx = FIXTURE_BUILDERS[t["fixture"]](inst)
            instances.append({
                "instance_id": f"{tid}-{inst}",
                "template": tid,
                "instance": inst,
                "task_class": t["cls"],
                "fixture_key": t["fixture"],
                "fixture_files": sorted(fx),
                "fixture_digest": hashlib.sha256(
                    json.dumps(fx, sort_keys=True).encode()).hexdigest(),
                "spec": t["spec"](inst),
            })
        templates[tid] = {"task_class": t["cls"], "fixture": t["fixture"], "instances": instances}

    order = []
    for inst in INSTANCES:  # interleave templates per instance-round
        for tid in sorted(TEMPLATES):
            order.append(f"{tid}-{inst}")
    return {
        "schema": "dspx.g3ps-corpus/1",
        "release_ref": RELEASE_REF,
        "wheel_sha256": WHEEL_SHA256,
        "templates": templates,
        "instance_order": order,
        "design": {
            "n_templates": len(TEMPLATES),
            "n_instances": len(order),
            "families": FAMILIES,
            "pairs": len(order) * len(FAMILIES),
            "reps_note": "3 DISTINCT derived instances per template (not repeats)",
        },
    }


def digest(corpus: dict) -> str:
    blob = json.dumps(corpus, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


if __name__ == "__main__":
    c = build_corpus()
    print(digest(c), len(c["instance_order"]))
