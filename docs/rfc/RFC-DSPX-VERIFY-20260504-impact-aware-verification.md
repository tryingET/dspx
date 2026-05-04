---
summary: "RFC draft for deterministic impact-aware verification planning in DSPx."
read_when:
  - "You are changing DSPx CI, Justfile verification targets, pytest selection, or developer validation workflow."
  - "You need to decide whether a local change can use a narrower verification slice than just verify-full."
  - "You are implementing or reviewing impact-aware verification tooling."
---

# RFC: Impact-Aware Verification for DSPx

## 0) Metadata

- RFC ID: `RFC-DSPX-VERIFY-20260504-impact-aware-verification`
- Status: `review`
- Owner: `DSPx maintainers`
- Reviewers: `DSPx core reviewers`, `CI/runtime maintainers`
- Created: `2026-05-04`
- Target milestone: `local validation ergonomics wave`
- AK decision: `#26 Adopt deterministic impact-aware verification planning for DSPx`
- Related files:
  - `docs/adr/20260504-impact-aware-verification.md`
  - `Justfile`
  - `scripts/ci/verify-full.sh`
  - `scripts/check_task_scope.py`
  - `scripts/check_workflow_contracts.py`
  - `docs/project/developer_workflow.md`

## 1) Problem statement

`just verify-full` is the right final confidence gate, but it is too expensive as the default answer to every local change. Recent product-aligned slices routinely needed high-confidence validation over a small surface, while full verification exceeded interactive tool timeouts even after the relevant targeted checks had already passed.

The current workflow creates three problems:

- **Slow feedback**: local iteration waits on unrelated tests, full pre-commit scans, and runtime checks even when the change touches a narrow service and its tests.
- **Ad-hoc judgment**: agents and humans manually choose targeted tests from memory. This can be good when the maintainer knows the code, but it is not reproducible or auditable.
- **False binary**: the repo effectively offers either narrow hand-picked checks or full verification. It lacks a first-class middle tier that is deterministic, conservative, and explainable.

The desired outcome is a verification planner that produces the smallest truthful validation set for the current change while making risk explicit and preserving `just verify-full` as the final/wide gate.

## 2) Goals and non-goals

### Goals

- Add a deterministic impact-aware verification surface for local development.
- Select checks from changed files, committed ranges, or staged changes.
- Print a machine-readable and human-readable plan before execution.
- Run mapped targeted tests and required invariant checks without relying on model inference.
- Fail wide when changes are unknown, cross-cutting, or safety-critical.
- Preserve existing full verification semantics.
- Make the planner auditable through a checked-in impact map and tests for the planner itself.

### Non-goals

- Replacing `just verify-full` as the release/merge confidence gate.
- Using AI, embeddings, coverage guessing, or dynamic heuristics to decide what can be skipped.
- Guaranteeing complete regression detection from partial tests.
- Mutating AK, governance, Oracle indexes, generated artifacts, or external authority as part of verification planning.
- Automatically editing task scopes or work-item projections.

## 3) Current state

Existing verification targets are useful but coarse:

- `just verify-fast` checks workflow contracts, direction contracts, governance projection, task scope, and pre-commit over all files.
- `just verify-runtime` runs replay provenance, monorepo boundaries, module synthesis quality, boundary contract tests, and docs strict mode.
- `just verify-tests` runs typecheck and the full pytest suite.
- `just verify-full` runs `verify-fast`, then `verify-runtime` and `verify-tests` in parallel.

This design maximizes confidence but does not distinguish between:

- docs-only edits,
- a single service implementation plus one test file,
- a CI/Justfile change,
- dependency changes,
- cross-cutting runtime changes,
- task-scope/governance projection updates.

## 4) Decision

Introduce a conservative deterministic verification planner with two user-facing targets:

```bash
just verify-impact-plan
just verify-impact
```

`verify-impact-plan` prints the selected verification plan and exits without running it. `verify-impact` prints the same plan, executes it in deterministic order, and exits non-zero if any selected command fails or if the change requires full verification and `--allow-wide` was not supplied.

Keep `just verify-full` unchanged. The impact-aware path is a local development accelerator and evidence generator, not a replacement for the full gate.

## 5) Design principles

### 5.1 Deterministic, not clever

The planner must be table-driven. Given the same repo state and options, it must select the same checks. It must not ask a language model, infer semantic intent from code, or silently skip an unmapped change.

### 5.2 Conservative by default

Unknown files, dependency files, CI files, broad shared services, and large multi-domain diffs should escalate to broader verification. Narrow verification is allowed only when the mapping is explicit.

### 5.3 Plan before execution

Every run should first produce a plan containing:

- changed files,
- classifications,
- selected checks,
- selected tests,
- risk level,
- whether full verification is required,
- reasons for each selection.

### 5.4 Keep final confidence separate

`verify-impact` answers: "What should I run for this local change now?"

`verify-full` answers: "Is the repo broadly healthy enough for final integration confidence?"

The two commands should not be conflated.

## 6) Proposed command surface

### 6.1 Just targets

```make
verify-impact-plan base="auto":
  uv run --no-sync python scripts/ci/verify_changed.py --base {{base}} --plan-only

verify-impact base="auto":
  uv run --no-sync python scripts/ci/verify_changed.py --base {{base}} --run
```

Optional future flags can be exposed directly or through environment variables:

```bash
just verify-impact-plan base=HEAD~1
just verify-impact base=origin/main
DSPX_VERIFY_CHANGED_STAGED=1 just verify-impact-plan
DSPX_VERIFY_CHANGED_ALLOW_WIDE=1 just verify-impact
```

### 6.2 Script

Add:

```text
scripts/ci/verify_changed.py
scripts/ci/verification-impact.yml
tests/test_verify_changed.py
```

The script should support:

```bash
uv run --no-sync python scripts/ci/verify_changed.py --base auto --plan-only
uv run --no-sync python scripts/ci/verify_changed.py --base HEAD~1 --run
uv run --no-sync python scripts/ci/verify_changed.py --staged --plan-only
uv run --no-sync python scripts/ci/verify_changed.py --files path/a.py path/b.md --plan-only
```

## 7) Base selection

`--base auto` should use this precedence:

1. If there are staged changes and `--staged` is supplied, compare staged changes.
2. If the working tree has changes, use working-tree changes against `HEAD`.
3. If no working-tree changes exist, compare `HEAD~1..HEAD`.
4. If the repo has no parent commit, treat all tracked files as changed and require wide verification.

The chosen base mode must be present in the plan.

## 8) Plan schema

The planner should emit JSON with a stable schema, plus an optional text summary.

```json
{
  "schema_version": "dspx-verification-impact-plan-v1",
  "base_mode": "working_tree",
  "base_ref": "HEAD",
  "changed_files": ["packages/dspx-core/src/dspx/services/program_refinement.py"],
  "classifications": [
    {
      "path": "packages/dspx-core/src/dspx/services/program_refinement.py",
      "category": "python_service",
      "impact_group": "program_refinement",
      "risk": "bounded",
      "reasons": ["explicit impact map entry"]
    }
  ],
  "commands": [
    {
      "id": "ruff_touched",
      "command": ["uvx", "ruff", "check", "packages/dspx-core/src/dspx/services/program_refinement.py"],
      "reason": "python file changed"
    },
    {
      "id": "typecheck_core",
      "command": ["uvx", "ty", "check", "packages/dspx-core/src"],
      "reason": "core service changed"
    },
    {
      "id": "pytest_program_refinement",
      "command": ["uv", "run", "--no-sync", "-m", "pytest", "-q", "tests/test_program_refinement.py", "tests/test_program_refinement_candidate.py"],
      "reason": "program_refinement impact group"
    }
  ],
  "risk": "bounded",
  "full_verification_required": false,
  "wide_reason": null
}
```

Risk levels:

- `docs_only`: documentation checks only.
- `bounded`: explicit impact mapping covers all changed files.
- `expanded`: mapped change requires broader targeted checks, but not full verification.
- `wide`: full verification is required or strongly recommended.

## 9) Impact map

The impact map should be checked in as data, not embedded as scattered code.

Example shape:

```yaml
schema_version: dspx-verification-impact-map-v1

rules:
  - match: "docs/**/*.md"
    category: docs
    risk: docs_only
    commands:
      - docs_strict

  - match: "governance/work-items.json"
    category: governance_projection
    risk: bounded
    commands:
      - governance_check
      - task_scope_check

  - match: "packages/dspx-core/src/dspx/services/program_refinement_comparison.py"
    category: python_service
    impact_group: program_refinement_comparison
    risk: bounded
    commands:
      - ruff_touched
      - typecheck_core
      - pytest_program_refinement_comparison
      - pytest_refinement_adjacent

  - match: "packages/dspx-core/src/dspx/services/program_service.py"
    category: python_service
    impact_group: program_generation_spine
    risk: expanded
    commands:
      - ruff_touched
      - typecheck_core
      - pytest_program_generation_spine
      - boundary_contract_check
      - docs_strict

  - match: "Justfile"
    category: ci_contract
    risk: wide
    commands:
      - verify_fast
    requires_full_verification: true
```

Command definitions should also live in the map or in a small fixed registry inside the script.

## 10) Initial impact groups

The first implementation should cover only high-signal groups already exercised frequently by current work.

### 10.1 Documentation

Changed files:

```text
docs/**/*.md
AGENTS.md
README.md
```

Run:

```bash
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict
```

If `AGENTS.md` or `CLAUDE.md` changes, require wide verification or a dedicated loader-behavior check because those files alter agent runtime context.

### 10.2 Governance/task-scope projections

Changed files:

```text
governance/work-items.json
governance/task-scopes/*.snapshot.json
```

Run:

```bash
just governance-check
just task-scope-check
```

If task-scope snapshots change without any implementation/doc changes, the plan should still explain why governance checks are selected.

### 10.3 Program generation spine

Changed files:

```text
packages/dspx-core/src/dspx/services/program_service.py
packages/dspx-core/src/dspx/services/program_surfaces.py
packages/dspx-core/src/dspx/services/program_dataset.py
```

Run targeted tests such as:

```bash
uv run --no-sync -m pytest -q \
  tests/test_program_service.py \
  tests/test_program_dataset_splits.py \
  tests/test_program_topology_intent.py
```

Also run:

```bash
uvx ty check packages/dspx-core/src
just boundary-contract-check
```

Risk: `expanded`, because these files affect many generated artifacts and receipt surfaces.

### 10.4 Oracle evidence/report/refinement seam

Changed files:

```text
packages/dspx-core/src/dspx/services/program_oracle_index.py
packages/dspx-core/src/dspx/services/program_oracle_report.py
packages/dspx-core/src/dspx/services/program_refinement.py
```

Run:

```bash
uv run --no-sync -m pytest -q \
  tests/test_program_oracle_index.py \
  tests/test_program_oracle_report.py \
  tests/test_program_refinement.py
```

Add adjacent tests when refinement outputs feed promotion or candidate-state surfaces.

### 10.5 Refinement candidate/comparison/promotion seam

Changed files:

```text
packages/dspx-core/src/dspx/services/program_refinement_candidate.py
packages/dspx-core/src/dspx/services/program_refinement_comparison.py
packages/dspx-core/src/dspx/services/program_refinement_workflow.py
packages/dspx-core/src/dspx/services/program_promotion_plan.py
```

Run:

```bash
uv run --no-sync -m pytest -q \
  tests/test_program_refinement_candidate.py \
  tests/test_program_refinement_comparison.py \
  tests/test_program_promotion_plan.py
```

Risk: `bounded` or `expanded` depending on whether promotion/candidate-state files are touched.

### 10.6 Boundary-sensitive files

Changed files include:

```text
packages/dspx-core/src/dspx/services/program_external_authority_export.py
packages/dspx-core/src/dspx/services/program_candidate_state.py
packages/dspx-core/src/dspx/services/run_replay_service.py
scripts/check_task_scope.py
scripts/check_workflow_contracts.py
```

Run:

```bash
just boundary-contract-check
just verify-runtime
```

Risk: at least `expanded`; CI/workflow contract scripts may be `wide`.

### 10.7 Dependency and CI files

Changed files:

```text
pyproject.toml
uv.lock
Justfile
scripts/ci/**
.github/**
```

Default to `wide` unless a more precise rule is deliberately added.

## 11) Execution ordering

When running selected commands, execute in this order:

1. cheap deterministic contract checks,
2. lint/format checks for touched files,
3. typecheck,
4. targeted tests,
5. runtime/boundary/docs checks,
6. wide/full verification if explicitly allowed and required.

The command should stop on first failure by default. A later `--keep-going` mode can collect all failures, but that is not required for the first slice.

## 12) Failure and escalation behavior

The planner must fail closed when:

- a changed file has no rule,
- a file matches conflicting rules without a deterministic merge policy,
- the impact map schema is invalid,
- a command id referenced by a rule is unknown,
- a change touches CI/dependency files and `--allow-wide` is not provided,
- a change crosses a configured file-count or impact-group threshold.

Recommended thresholds for the first implementation:

- more than `20` changed files: risk `wide`, unless all are docs-only,
- more than `3` impact groups: risk `wide`,
- any deleted test file: risk `wide`,
- any changed test helper used by many suites: risk `expanded` or `wide`.

## 13) Output examples

### 13.1 Docs-only edit

```text
Plan risk: docs_only
Commands:
- docs_strict
Full verification required: false
```

### 13.2 Bounded service edit

```text
Plan risk: bounded
Commands:
- ruff_touched
- typecheck_core
- pytest_program_refinement_comparison
- pytest_refinement_adjacent
- task_scope_check, if governance/task-scope files changed
Full verification required: false
```

### 13.3 CI change

```text
Plan risk: wide
Commands:
- verify_fast
Full verification required: true
Reason: Justfile or scripts/ci changed
```

## 14) Validation plan for implementation

Targeted tests for the planner:

- docs-only change selects docs strict and no Python tests,
- known service file selects mapped tests and typecheck,
- service + matching test file deduplicates commands,
- governance projection selects governance and task-scope checks,
- unknown file escalates to wide,
- `Justfile`/CI changes require full verification,
- large multi-domain change escalates to wide,
- `--plan-only` never runs commands,
- `--run` runs commands in deterministic order,
- JSON schema remains stable.

Implementation validation should include:

```bash
uv run --no-sync -m pytest -q tests/test_verify_changed.py
uvx ruff check scripts/ci/verify_changed.py tests/test_verify_changed.py
uvx ty check packages/dspx-core/src
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict
just task-scope-check task_id=<AK-ID> mode=working-tree
```

If the implementation touches `Justfile`, `scripts/ci/**`, or workflow-contract checks, run `just verify-fast` and attempt `just verify-full` when tool time allows.

## 15) Rollout plan

### Phase 1: Plan-only deterministic mapper

- Add `scripts/ci/verify_changed.py` with `--plan-only`.
- Add `verification-impact.yml` for docs, governance, and 3-5 common program-gen/refinement groups.
- Add planner tests.
- Add `just verify-impact-plan`.

### Phase 2: Execute selected checks

- Add `--run` execution mode.
- Add `just verify-impact`.
- Record command results in a simple JSON result payload.
- Keep wide changes non-executing by default unless `--allow-wide` is supplied.

### Phase 3: Developer workflow adoption

- Update `docs/project/developer_workflow.md` to recommend:
  - `just verify-impact-plan` before implementation validation,
  - `just verify-impact` during local iteration,
  - `just verify-full` for final confidence, risky changes, or release prep.

### Phase 4: Expand map cautiously

- Add impact groups only when validated by repeated real work.
- Prefer over-selecting adjacent tests to under-selecting critical consumers.
- Treat each map expansion as a small reviewable change with planner tests.

## 16) Risks and mitigations

### Risk: false confidence from partial checks

Mitigation: plans must say whether full verification is required or merely recommended. Unknown and high-risk changes fail wide. Docs should describe `verify-impact` as a local development gate, not a replacement for full verification.

### Risk: stale impact map

Mitigation: keep the map small initially, test it, and require explicit updates when new service surfaces are introduced. Unknown files should not silently pass.

### Risk: planner complexity becomes its own CI system

Mitigation: the planner should only select existing commands/tests. It should not invent new coverage semantics, parse imports deeply, or become a build graph engine.

### Risk: too conservative to be useful

Mitigation: start with the high-frequency DSPx program-gen/refinement seams where targeted validation is already known and repeatedly used. Expand based on observed developer pain.

### Risk: local/CI divergence

Mitigation: keep `verify-full` unchanged and continue to use it for final confidence. If CI adopts `verify-impact`, it should be as a fast preflight job, not as the only required job.

## 17) Open questions

- Should `verify-impact` default to working-tree changes or staged changes when both exist?
- Should full verification be "required" or "recommended" for `Justfile` changes during local development?
- Should selected command results be written to a receipt file under `generated/ci/`, or printed only?
- Should task-scope mode default to `working-tree` when an active AK task is detected?
- Should the impact map include negative rules, such as "if this helper changes, never run less than expanded"?

## 18) Practical consequence

DSPx should keep `just verify-full` as the broad confidence gate while adding a deterministic middle tier that makes local validation faster, more reproducible, and less dependent on individual memory. The first implementation should be deliberately conservative: table-driven, plan-first, fail-wide on uncertainty, and useful for the program-gen/refinement surfaces where full verification is already too slow for every iteration.
