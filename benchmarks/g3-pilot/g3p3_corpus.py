#!/usr/bin/env python3
"""G3 v3 pilot corpus (DIAGNOSTIC ONLY; DSPx AK task 5081).

CONTRACT-CONFORMANCE corpus. v2 closed null (20/20 ceiling, zero splits) because
generic coding tasks never required the guidance. v3's fix: every task's correct
answer lives in CONVENTION SPACE that the engineering-core candidate-4 guidance
encodes and a model without it must guess. Not "harder code" — models at :high
already code well. The measured question: does having the contract change
conformance?

Reshape (operator directive, pre-execution): 10 tasks total, 5 per family
(sol:high / glm:high), each task static+evidence ONCE within its assigned
family = 20 executions. Classes: 3xA adoption surgery, 3xB advise-loop, 4xC
lane-conformance builds. All classes represented.

This is NOT Gate G3, NOT protocol evidence, and claims no gate authority.
"""

from __future__ import annotations

import hashlib
import json

SCHEMA = "dspx.g3pilot-v3-corpus/1"
PILOT_SEED = 20260826

REPOS = {
    "dspx": {
        "repo_identity": "softwareco/owned/dspx",
        "local_path": "/home/tryinget/ai-society/softwareco/owned/dspx",
        "pin": "e74309284972236b996da3cf6dc3f11c8ab3c525",
        "kind": "python",
    },
    "piext": {
        "repo_identity": "softwareco/owned/pi-extensions",
        "local_path": "/home/tryinget/ai-society/softwareco/owned/pi-extensions",
        "pin": "e855d07799f7984770d8a7ce25fc8ebabe1b7e64",
        "kind": "ts",
    },
}

FAMILIES = {
    "fam-gpt": "openai-codex/gpt-5.6-sol:high",
    "fam-glm": "zai/glm-5.3:high",
}

# ---------------------------------------------------------------- fixtures
# Fixture repos are assembled in scratch from REAL repo shapes:
#  - legacy tech-stack surfaces transcribed from softwareco/owned/email-triage
#    (policy/stack-lane.json + docs/tech-stack.local.md, adapted only in names).
#  - a small py service skeleton (pyproject + src package + Justfile shape used
#    across softwareco/owned py repos).
#  - a small ts web-app shape (package.json + react dep, the inference trigger
#    documented in the engineering-ts lane) for advise-loop lane inference.

PYPROJECT_TXT = """[project]
name = "hello-service"
version = "0.3.0"
description = "Small internal greeting service"
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/hello_service"]
"""

INIT_PY = '"""Hello service package."""\n'

GREETER_PY = '"""Greeting helpers used by the service entrypoint."""\n\n\ndef greet(name: str) -> str:\n    """Return the canonical greeting for *name*."""\n    if not name.strip():\n        raise ValueError("name must not be blank")\n    return f"hello, {name.strip()}"\n'

README_TXT = """# hello-service

Small internal greeting service.

## Commands

- install: `uv sync`
- test: `uv run python -m pytest tests/`
- lint: `uv run ruff check .`
"""

JUSTFILE_TXT = """# hello-service — local command surface
set shell := ["bash", "-uc"]

# List available tasks
help:
    @just --list

default:
    @just --list

install:
    uv sync

test:
    uv run python -m pytest tests/ -v --tb=short

lint:
    uv run ruff check .

fmt:
    uv run ruff format .
"""

LEGACY_POLICY_TXT = """{
  "lane": "py",
  "tech_stack_core": {
    "tool": "tech-stack-core",
    "lane": "py",
    "repository": "https://github.com/lightningralf/tech-stack-core",
    "ref": "local-path",
    "command": "uv tool run --from ~/ai-society/core/tech-stack-core tech-stack-core show py --prefer-repo"
  }
}"""

LEGACY_DOC_TXT = """---
summary: "Repo-local override notes for the shared tech-stack-core lane used by this repo."
read_when:
  - "Aligning implementation decisions with the stack baseline for this project repo."
  - "Reconciling local workflow differences with shared lane guidance."
system4d:
  container: "Repo-local deltas on top of shared lane guidance."
  compass: "Keep project work reproducible while preserving local constraints."
  engine: "Use shared lane -> apply local override -> validate with repo scripts."
  fog: "Upstream lane guidance may evolve independently of this repo."
---

# tech-stack.local (project repo)

Primary lane:

- `tech-stack-core show py --prefer-repo`
- `uv tool run --from ~/ai-society/core/tech-stack-core tech-stack-core show py --prefer-repo`

Executable contract surface:

- `policy/stack-lane.json` pins the upstream lane and retrieval command.
- `docs/tech-stack.local.md` records repo-local deltas.
- Repo validation should at least verify the pinned lane metadata.

Repo-local emphasis:

- Keep workflow scripts and docs aligned with the pinned lane.
- Prefer local deterministic wrappers before ad-hoc commands.
- Update this file when local practice intentionally diverges from the upstream lane.
"""

TESTS_INIT = '"""Tests for greeting helpers."""\n'
TEST_GREETER = '''"""Behavior tests for hello_service.greeter."""

from hello_service.greeter import greet


def test_greet_plain() -> None:
    assert greet("world") == "hello, world"


def test_greet_strips_whitespace() -> None:
    assert greet("  ada  ") == "hello, ada"


def test_greet_blank_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        greet("   ")
'''

FIX_BASE_PY = {
    "pyproject.toml": PYPROJECT_TXT,
    "README.md": README_TXT,
    "Justfile": JUSTFILE_TXT,
    "src/hello_service/__init__.py": INIT_PY,
    "src/hello_service/greeter.py": GREETER_PY,
    "tests/__init__.py": TESTS_INIT,
    "tests/test_greeter.py": TEST_GREETER,
}

# FIX_LEGACY_PY: legacy tech-stack adoption (real email-triage shape).
FIX_LEGACY_PY = dict(FIX_BASE_PY)
FIX_LEGACY_PY["policy/stack-lane.json"] = LEGACY_POLICY_TXT
FIX_LEGACY_PY["docs/tech-stack.local.md"] = LEGACY_DOC_TXT

# FIX_DEGRADED_PY: v1 adoption present with deliberate defects:
#   (1) stale ref pin v0.9.0 (catalog is 1.0.0 -> released-mismatch),
#   (2) schema violations: disciplines is a comma STRING (must be an array),
#       and lanes contains the unknown id "python" (valid id is "py"),
#   (3) unstructured local doc: no front matter, no managed shape.
FIX_DEGRADED_POLICY = """{
  "engineering_core": {
    "schema_version": "1",
    "tool": "engineering-core",
    "lanes": ["py", "python"],
    "disciplines": "validation, testing, security-privacy, documentation",
    "ref": "v0.9.0",
    "catalog_command": "engineering-core catalog --pretty",
    "list_disciplines_command": "engineering-core list-disciplines",
    "list_templates_command": "engineering-core list-templates",
    "deviations": [
      {
        "id": "keep-local-uv-mirror",
        "reason": "CI mirrors PyPI through a local uv cache; upstream freshness gates do not apply",
        "owner": "platform-team",
        "evidence": ["gitlab/ci/uv-config.toml"],
        "review_date": "2026-09-30"
      }
    ]
  }
}"""

FIX_DEGRADED_DOC = """# engineering notes

We adopted the engineering thing. Lanes: python. See policy file for details.
Validation: run the tests before handoff. Deviations: we keep the local uv mirror.
"""

FIX_DEGRADED_PY = dict(FIX_BASE_PY)
FIX_DEGRADED_PY["policy/engineering-lane.json"] = FIX_DEGRADED_POLICY
FIX_DEGRADED_PY["docs/engineering.local.md"] = FIX_DEGRADED_DOC

# FIX_ADOPTED_REDACT_PY (B3): valid v1 adoption + a local doc that carries a
# secret-like token and an email, so the advise request redacts them and any
# citation must span the REDACTED representation, not the on-disk bytes.
FIX_ADOPTED_POLICY = """{
  "engineering_core": {
    "schema_version": "1",
    "tool": "engineering-core",
    "lanes": ["py"],
    "disciplines": [
      "validation",
      "testing",
      "security-privacy",
      "documentation",
      "dependency-governance",
      "data-governance",
      "domain-modeling"
    ],
    "ref": "v1.0.0",
    "catalog_command": "engineering-core catalog --pretty",
    "list_disciplines_command": "engineering-core list-disciplines",
    "list_templates_command": "engineering-core list-templates",
    "deviations": []
  }
}"""

FIX_ADOPTED_DOC = """---
summary: "Repository-local engineering-core selections, commands, and deviations."
read_when:
  - "Before changing repository engineering conventions or validation commands."
type: "policy"
---

# Repository engineering contract

## Selected lanes and addenda

- `py`

## Selected disciplines

- `validation`
- `testing`
- `security-privacy`
- `documentation`
- `dependency-governance`
- `data-governance`
- `domain-modeling`

## Canonical local commands

- Catalog: `engineering-core catalog --pretty`
- Diagnose adoption: `engineering-core doctor --repo .`

## Validation evidence before handoff

Run the repository-local test and lint commands, then report commands and outcomes.

## Deliberate deviations

- None recorded.

## Operational contact

Owner: ops@example.com — rotate the deploy hook token=sk_live_9f3aab71c2 when
this document changes.
"""

FIX_ADOPTED_REDACT_PY = dict(FIX_BASE_PY)
FIX_ADOPTED_REDACT_PY["policy/engineering-lane.json"] = FIX_ADOPTED_POLICY
FIX_ADOPTED_REDACT_PY["docs/engineering.local.md"] = FIX_ADOPTED_DOC

# FIX_TS_WEB (B2): ts web-app shape. package.json carries the react dependency
# that the lane documents as the frontend addendum trigger.
FIX_TS_PACKAGE = """{
  "name": "tiny-web-app",
  "version": "0.2.0",
  "type": "module",
  "description": "Tiny internal web app",
  "dependencies": {
    "react": "^19.0.0"
  }
}
"""

FIX_TS_INDEX = """/**
summary: "App entry: mounts the root component."
read_when:
  - "You change application bootstrap or root rendering."
*/

export function mount(root) {
  root.textContent = "tiny web app";
  return root;
}
"""

FIX_TS_WEB = {
    "package.json": FIX_TS_PACKAGE,
    "src/index.js": FIX_TS_INDEX,
    "README.md": "# tiny-web-app\n\nTiny internal web app.\n",
}

FIXTURES = {
    "FIX_LEGACY_PY": FIX_LEGACY_PY,
    "FIX_DEGRADED_PY": FIX_DEGRADED_PY,
    "FIX_ADOPTED_REDACT_PY": FIX_ADOPTED_REDACT_PY,
    "FIX_TS_WEB": FIX_TS_WEB,
}

# ---------------------------------------------------------------- specs

COMMON_HEAD = """You are executing a bounded work task in a disposable scratch repository.
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

A1_SPEC = COMMON_HEAD + """
TASK (A1): Complete this repository's migration from the legacy tech-stack
adoption surfaces to the v1 engineering adoption contract.

Current state: this repository still carries the LEGACY surfaces
`policy/stack-lane.json` and `docs/tech-stack.local.md`, and has NO v1
adoption surfaces.

Required end state (verification is objective, deterministic, and automated;
the frozen checker runs the engineering-core 1.0.0 CLI against your tree):

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

A2_SPEC = COMMON_HEAD + """
TASK (A2): Repair this repository's degraded v1 engineering adoption.

Current state: v1 adoption surfaces exist but are DEFECTIVE:
- the policy `ref` is pinned to an old release (the catalog release current at
  verification time is newer);
- `engineering_core.disciplines` violates the schema (it is not a JSON array
  of ids);
- `engineering_core.lanes` contains an id that is not in the catalog;
- `docs/engineering.local.md` is unstructured: no front matter, no sections.

Required end state (frozen checker runs the engineering-core 1.0.0 CLI):

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

A3_SPEC = COMMON_HEAD + """
TASK (A3): Execute the full adoption->rollback lifecycle on this legacy
repository BY HAND (the engineering-core CLI is not available to you) and prove
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
  {"mode": "migrate", "repo": "<abs repo path>", "lanes": ["py"],
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
   "safe_to_apply": true, "applied": true}

`rollback.json` — the rollback receipt:
  {"command": "rollback", "repo": "<abs repo path>", "status": "rolled_back",
   "restored": [{"path": "policy/stack-lane.json", "action": "restored"},
                {"path": "docs/tech-stack.local.md", "action": "restored"},
                {"path": "policy/engineering-lane.json", "action": "removed"},
                {"path": "docs/engineering.local.md", "action": "removed"}],
   "journal_removed": true}

The checker decodes apply.json's base64 payloads and validates that the
created adoption files satisfied the v1 contract and that the recorded legacy
before-bytes equal the repository's original bytes.
"""

B_COMMON_TAIL = """
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

B1_SPEC = COMMON_HEAD + """
TASK (B1): Produce the advisory response the engineering advisor surface
expects for this repository.
""" + B_COMMON_TAIL

B2_SPEC = COMMON_HEAD + """
TASK (B2): Produce the advisory response the engineering advisor surface
expects for this repository.
""" + B_COMMON_TAIL

B3_SPEC = COMMON_HEAD + """
TASK (B3): Produce the advisory response the engineering advisor surface
expects for this repository (it carries a valid v1 adoption policy).
""" + B_COMMON_TAIL

C1_SPEC = COMMON_HEAD + """TASK (C1): Add a documentation-header audit module with conforming tests to
the `packages/pi-context-packer` package of this repository replica.

Repository context: `packages/pi-context-packer` is a pi extension package
(Node + npm, ESM). Its sources under `src/` and tests under `tests/` follow the
package's conventions: ESM JavaScript, `node:` builtins only, doc-header
comments of the form

    /**
    summary: "One sentence."
    read_when:
      - "Trigger condition."
    */

and tests written for Node's built-in test runner. The package's biome
configuration (biome.jsonc) is the formatting/linting gate: 2-space indent,
line width 100, double quotes, semicolons, recommended lint rules including
enforced template literals where interpolation is used.

Create exactly two new files (nothing else may change):

1. `packages/pi-context-packer/src/g3p3-header-audit.js` — pure ESM module,
   `node:` builtins only, exporting:

       export function auditDocHeaders(sources)
       export function summarizeHeaderAudit(sources)

   `sources` is an array of objects {file, text}. `auditDocHeaders` returns an
   array with one entry per input, in input order: {file, hasHeader, summary,
   readWhen} where hasHeader is true iff text contains a doc-header block (a
   `/**` ... `*/` block whose content contains a `summary:` line), summary is
   the quoted string after `summary:` (without quotes) or null, readWhen is an
   array of the quoted strings after `read_when:` trigger lines (empty array if
   none, null when hasHeader is false). `summarizeHeaderAudit` returns
   {total, withHeader, missingHeader} computed over the same input (total =
   number of entries; withHeader/missingHeader = counts). No filesystem or
   network access; deterministic; no external dependencies.

2. `packages/pi-context-packer/tests/g3p3-header-audit.test.js` — tests for the
   Node built-in test runner (node:test + node:assert/strict), importing the
   module by relative path, with a doc-header comment of its own, containing at
   least 3 distinct tests: header parsing (summary + read_when extraction), a
   missing-header case, and a summary/aggregation case over a set of at least 8
   fixture inputs (deterministic, no randomness beyond a fixed seed).

Constraints (checked): both files pass `node --check`; the test file passes
`node --test` (all tests pass, at least 3); both files pass the package's biome
check (format + lint) — hand-format to the settings above (you cannot run biome
here); each file stays within 500 lines and 50 KiB.
"""

C2_SPEC = COMMON_HEAD + """TASK (C2): Expose a new quick contract-validation command on this repository's
standardized command surface as a thin alias pair, exactly per the repo's
command-surface rule for this kind of repository.

The rule (as this repo family's engineering lane states it): the Justfile
surface standardizes operator-facing command names while each recipe stays a
THIN ALIAS delegating to a package script — prefer existing package scripts and
wrappers, do not bury logic inside ad-hoc Justfile shell blocks, do not invent
fake targets.

Deliverables (exactly two changes; nothing else may change):

1. In the ROOT `package.json`, add script key `g3p3-contracts-quick` whose
   value is a thin delegation to the repository's EXISTING contract-validation
   script `release:contracts:validate` — i.e. the value must be exactly
   `npm run release:contracts:validate` (no new logic, no new wrapper files).

2. In the ROOT `Justfile`, add a recipe that exposes the same command name as a
   thin alias over that package script:

       # G3P3 quick contract validation (thin alias over the package script)
       g3p3-contracts-quick:
           npm run g3p3-contracts-quick

   The recipe body must be exactly the thin alias invocation (a single
   `npm run g3p3-contracts-quick` line, optionally `@`-prefixed), must not cd,
   must not inline node/bash logic, and must not duplicate what the package
   script already expresses. Keep the existing `#`-comment style. Do not alter
   any existing recipe.

Checks (frozen): `just --list` still parses and lists the new recipe;
`just --dry-run g3p3-contracts-quick` exits 0 and prints the aliased command;
package.json parses as JSON with the exact script value; the Justfile recipe
body is exactly the thin alias; no other file changes.
"""

C3_SPEC = COMMON_HEAD + """TASK (C3): Add a service function with conforming tests to this Python
monorepo replica (soomfon-free area; add NEW files only).

Repository context: Python 3.13 + uv; the dspx-core package lives at
`packages/dspx-core/src/dspx/`; tests live in the root `tests/` directory
(pytest, with the package sources on sys.path via the repo's conftest). The
repo's quality gates are ruff (lint, default rules, 88-col lines) and pytest.
The testing discipline for this repo family expects a property-style test
(clear invariant over many generated cases) next to behavior tests when the
function has a strong invariant. The environment has pytest and the standard
library only — do not import packages that are not present (no hypothesis; use
plain pytest with deterministic generated cases).

Create exactly two new files (nothing else may change):

1. `packages/dspx-core/src/dspx/g3p3_token_budget.py` — module docstring,
   fully typed, exporting exactly:

       def split_token_budget(total: int, weights: Mapping[str, float]) -> dict[str, int]

   Semantics (must match exactly):
   - weights maps consumer key -> non-negative float weight; total >= 0.
   - Raise ValueError if total < 0, if weights is empty, if any weight is
     negative, or if the weight sum is 0 (or not > 0).
   - Allocate `total` whole units across keys by largest-remainder rounding:
     exact share_i = total * w_i / W (W = sum of weights); base_i = floor of
     exact share; distribute the remaining units one each to the keys with the
     LARGEST fractional parts; ties on fractional part are broken by key in
     ascending lexicographic order.
   - Return {key: allocated units}; invariant: allocations sum to `total`,
     every allocation >= 0, keys exactly the input keys.

2. `tests/test_g3p3_token_budget.py` — pytest tests: at least 3 distinct
   tests covering (a) an exact split with no remainder, (b) largest-remainder
   distribution with a tie broken by key order, (c) the ValueError cases, and
   (d) a property-style test asserting the sum-invariant and key-preservation
   over at least 8 deterministic generated cases (fixed literal list or a
   fixed-seed random.Random — no unseeded randomness).

Checks (frozen): ruff check passes on both new files; the new test file passes
targeted pytest (`python -m pytest tests/test_g3p3_token_budget.py -q`, at
least 3 passed); both files within 500 lines / 50 KiB; ruff default line
length (88) respected.
"""

C4_SPEC = COMMON_HEAD + """TASK (C4): Tier this repository's checks into a validation-tier-map artifact
in the exact frozen shape this repo family's validation discipline defines.

Create exactly one new file `docs/validation-tier-map.md` (nothing else may
change). The artifact must follow the validation-tier-map template shape:

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
   script each standard command maps to). If a standard target is intentionally
   unavailable in this repository, say `n/a` and why — do not invent a fake
   target.
5. Section `## Evidence rule` stating the handoff evidence contract: every
   handoff records command, scope, result, warning acceptance (if any), and
   artifact path (if any).

Checks (frozen): template-shape assertions (front matter, headings, exact
table header, all six tier rows in order, five standard-surface bullets in
order, evidence-rule items) plus semantic truth: the `just check`, `just test`,
`just build`, `just ci`, `just doctor` mappings must reference recipes/scripts
that actually exist in this repository's Justfile (or be marked n/a with a
reason where genuinely absent).
"""

# ---------------------------------------------------------------- guidance map
# What the EVIDENCE arm receives beyond the identical spec: rendered guidance
# content from the candidate-4 wheel itself (no other source). Rendered at
# freeze time via the wheel's own CLI / shipped files; digests recorded.

GUIDANCE = {
    "A": {
        "readme": "wheel README.md (adoption, scanner, capability observation, CLI sections)",
        "skill": "shipped skill/SKILL.md (adopt/diagnose/validate procedure, deviation evidence shape)",
        "templates": ["engineering.local", "discipline-adoption-checklist"],
        "lanes": ["py"],
        "disciplines": ["validation", "testing", "security-privacy", "documentation", "dependency-governance"],
        "catalog": "catalog --pretty (version + valid lane/discipline id vocabulary)",
    },
    "B": {
        "readme": "wheel README.md (bounded advisory protocol, lane selection, typical combinations)",
        "lanes_by_task": {"B1": ["py"], "B2": ["ts", "ts-frontend"], "B3": ["py"]},
        "disciplines": ["validation", "testing"],
        "catalog": "catalog --pretty (the allowed id vocabulary)",
        "note": "advise request materials are already in the spec (both arms); no advisor model call for class B (it would fabricate the deliverable)",
    },
    "C1C2": {
        "readme": "wheel README.md",
        "lanes": ["pi-ts"],
        "addenda": ["pi-ts.justfile"],
        "disciplines": ["validation", "testing", "documentation"],
    },
    "C3": {
        "readme": "wheel README.md",
        "lanes": ["py"],
        "addenda": ["py.justfile"],
        "disciplines": ["validation", "testing", "documentation"],
    },
    "C4": {
        "readme": "wheel README.md",
        "lanes": ["py"],
        "addenda": ["py.justfile"],
        "disciplines": ["validation", "testing", "documentation"],
        "templates": ["validation-tier-map"],
    },
}

# ---------------------------------------------------------------- tasks

def _task(task_id, cls, family, repo, title, rationale, spec, new_files, symbols, **acc):
    return {
        "task_id": task_id,
        "task_class": cls,
        "family": family,
        "repo": repo,  # fixture key or repo key
        "title": title,
        "convention_rationale": rationale,
        "spec": spec,
        "new_files": new_files,
        "new_symbols": symbols,
        "acceptance": acc,
    }


def build_tasks() -> list[dict]:
    tasks: list[dict] = []

    tasks.append(_task(
        "A1", "A", "fam-gpt", "FIX_LEGACY_PY",
        "Legacy -> v1 adoption migration (contract conformance)",
        "Convention space a model without the guidance must guess: (1) release ref format "
        "'v<catalog-version>' (v1.0.0, not 1.0.0/workspace-local) for released-match pin posture; "
        "(2) valid catalog id spellings 'py' + the five default cross-language discipline ids "
        "(hyphenated forms security-privacy/dependency-governance); (3) the three required "
        "catalog/list command fields; (4) legacy surfaces must be REMOVED for structural status "
        "'adopted' (legacy-mixed otherwise); (5) both surfaces (policy JSON + structured local doc "
        "with front matter) are required — doc-only/policy-only are distinct degraded statuses.",
        A1_SPEC,
        ["policy/engineering-lane.json", "docs/engineering.local.md"], [],
        kind="adoption_migration", fixture="FIX_LEGACY_PY",
        required_absent=["policy/stack-lane.json", "docs/tech-stack.local.md"],
    ))

    tasks.append(_task(
        "A2", "A", "fam-glm", "FIX_DEGRADED_PY",
        "Degraded adoption repair (doctor + scanner conformance)",
        "Convention space: same id/ref/command-field vocabulary as A1 plus repair semantics: "
        "disciplines must be a JSON ARRAY of catalog ids (comma string is a schema violation that "
        "blocks doctor); unknown lane id 'python' must be dropped for 'py'; the deviation ledger "
        "structure (id/reason/owner/evidence/review_date) must be preserved through repair; the "
        "local doc must be restructured (front matter + sections), not patched in place.",
        A2_SPEC,
        ["policy/engineering-lane.json", "docs/engineering.local.md"], [],
        kind="adoption_repair", fixture="FIX_DEGRADED_PY",
        required_absent=["policy/stack-lane.json", "docs/tech-stack.local.md"],
        preserve_deviation="keep-local-uv-mirror",
    ))

    tasks.append(_task(
        "A3", "A", "fam-glm", "FIX_LEGACY_PY",
        "Adoption apply -> rollback lifecycle with byte-exact restore",
        "Convention space: the adoption transaction/journal semantics — apply records per-file "
        "before/after digests+bytes for creates AND legacy deletes; rollback restores exact "
        "pre-adoption bytes and removes the journal (.engineering-core/); the created adoption "
        "files must satisfy the full v1 contract even though they are then rolled back; "
        "restored/removed action vocabulary in the rollback receipt.",
        A3_SPEC,
        [".g3p3-transaction/apply.json", ".g3p3-transaction/rollback.json"], [],
        kind="adoption_rollback", fixture="FIX_LEGACY_PY",
        required_absent=["policy/engineering-lane.json", "docs/engineering.local.md",
                         ".engineering-core"],
        restore_exact=True,
    ))

    for tid, fixture in (("B1", "FIX_LEGACY_PY"), ("B2", "FIX_TS_WEB"), ("B3", "FIX_ADOPTED_REDACT_PY")):
        fam = "fam-gpt" if tid in ("B1", "B3") else "fam-glm"
        if tid == "B1":
            title = "Advise response for a plain legacy py repo (inference-selected ids)"
            rationale = ("Convention space: response envelope binding (request digest, prompt "
                         "identity provenance, citation spans within captured evidence) plus the "
                         "SELECTION vocabulary: the plan compiler selects lane 'py' from "
                         "pyproject.toml plus exactly the five default cross-language disciplines "
                         "— id spellings are catalog vocabulary, not guessable English.")
        elif tid == "B2":
            title = "Advise response for a ts web-app repo (frontend addendum lane)"
            rationale = ("Convention space: manifest->lane inference ('ts' from package.json) PLUS "
                         "the frontend addendum rule: a react dependency adds lane 'ts-frontend' "
                         "(and it is never used alone), still with the five default disciplines. "
                         "Without the lane-selection rules the union-of-catalog-ids equality "
                         "cannot be derived.")
        else:
            title = "Advise response for an adopted repo with redacted evidence"
            rationale = ("Convention space: when a v1 policy is present the plan selections are "
                         "the policy's declared lanes+disciplines (7 ids here); and citations are "
                         "validated against the REDACTED evidence representation (secret token and "
                         "email become placeholders), so spans computed from the on-disk file "
                         "bytes fail the product validator.")
        tasks.append(_task(
            tid, "B", fam, fixture, title, rationale,
            {"B1": B1_SPEC, "B2": B2_SPEC, "B3": B3_SPEC}[tid],
            ["g3p3-advice-response.json"], [],
            kind="advise_response", fixture=fixture,
        ))

    tasks.append(_task(
        "C1", "C", "fam-gpt", "piext",
        "pi-ts lane-conformance: extension module + built-in-runner tests",
        "Convention space: Node built-in test runner (node:test + assert/strict) as the default "
        "unit runner for this package family; doc-header comment convention (summary/read_when) "
        "on both source and test; biome as the single format+lint gate (2-space, width 100, "
        "double quotes, template literals) hand-satisfied without running it; node:-builtins-only "
        "dependency minimalism.",
        C1_SPEC,
        ["packages/pi-context-packer/src/g3p3-header-audit.js",
         "packages/pi-context-packer/tests/g3p3-header-audit.test.js"], ["auditDocHeaders", "summarizeHeaderAudit"],
        kind="lane_build_ts", repo_key="piext",
    ))

    tasks.append(_task(
        "C2", "C", "fam-gpt", "piext",
        "pi-ts lane-conformance: thin-alias command-surface pair",
        "Convention space: the standardized command surface rule for this family — Justfile "
        "recipes are THIN ALIASES over package scripts (no cd, no inlined node/bash logic, no "
        "duplicated release policy in ad-hoc shell blocks); the alias-pair shape (package.json "
        "script + same-named Justfile recipe); minimal churn against the existing surface.",
        C2_SPEC,
        ["Justfile", "package.json"], ["g3p3-contracts-quick"],
        kind="lane_alias_pair", repo_key="piext",
        allowed_modified=["Justfile", "package.json"],
    ))

    tasks.append(_task(
        "C3", "C", "fam-glm", "dspx",
        "py lane-conformance: service function + property test",
        "Convention space: the Python lane tooling contract — ruff default rule set with 88-col "
        "lines as the lint gate; pytest as the runner with tests in the root tests/ layout and "
        "package sources imported via the repo's conftest path setup; the exact invocation form; "
        "and the testing discipline's property-style test (clear invariant over many generated "
        "cases) beside behavior tests, expressed without unavailable dependencies.",
        C3_SPEC,
        ["packages/dspx-core/src/dspx/g3p3_token_budget.py", "tests/test_g3p3_token_budget.py"],
        ["split_token_budget"],
        kind="lane_build_py", repo_key="dspx",
    ))

    tasks.append(_task(
        "C4", "C", "fam-glm", "dspx",
        "validation-tier-map artifact in the discipline's frozen shape",
        "Convention space: the validation-tier-map template's exact shape — front matter, H1, "
        "owner-surface line, the six-tier table (editor/save, pre-commit, task-scope, pre-push, "
        "CI, release) with exact column set, the five-bullet standard surface in fixed order, and "
        "the evidence-rule items; plus the 'do not invent fake targets' rule (just build is "
        "intentionally absent here and must be marked n/a with a reason).",
        C4_SPEC,
        ["docs/validation-tier-map.md"], [],
        kind="tier_map", repo_key="dspx",
    ))

    return tasks


def build_corpus() -> dict:
    tasks = build_tasks()
    pairs = []
    for task in tasks:
        family = task["family"]
        model = FAMILIES[family]
        repo_cfg = REPOS.get(task["repo"])
        pairs.append({
            "pair_id": f"PL3-{task['task_id']}-{family}",
            "task_id": task["task_id"],
            "task_class": task["task_class"],
            "family": family,
            "model_identity": model,
            "repo_key": task["repo"],
            "repo_identity": repo_cfg["repo_identity"] if repo_cfg else f"fixture:{task['repo']}",
            "repo_pin": repo_cfg["pin"] if repo_cfg else "frozen-fixture",
            "arm_order": ["static", "evidence"] if (hash_fn(task["task_id"] + family) % 2 == 0) else ["evidence", "static"],
            "task": task,
        })
    # Interleaved execution order: strict family alternation in authored order.
    order = [p["pair_id"] for p in pairs]
    return {
        "schema": SCHEMA,
        "pilot_seed": PILOT_SEED,
        "design": {
            "shape": "10 tasks x 1 family x 2 arms = 20 executions (operator reshape directive)",
            "operator_directive_quote": "please do only 10 tasks, 5 per model",
            "classes": {"A": 3, "B": 3, "C": 4},
            "families": {f: sorted(t["task_id"] for t in tasks if t["family"] == f) for f in FAMILIES},
        },
        "fixtures": {k: sorted(v) for k, v in FIXTURES.items()},
        "pairs": pairs,
        "execution_order": order,
    }


def hash_fn(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


if __name__ == "__main__":
    corpus = build_corpus()
    print(json.dumps({
        "schema": corpus["schema"],
        "n_pairs": len(corpus["pairs"]),
        "corpus_digest": digest(corpus),
        "design": corpus["design"],
        "tasks": [
            {"id": p["task_id"], "class": p["task_class"], "family": p["family"],
             "repo": p["repo_identity"], "arms": p["arm_order"]}
            for p in corpus["pairs"]
        ],
    }, indent=1))
