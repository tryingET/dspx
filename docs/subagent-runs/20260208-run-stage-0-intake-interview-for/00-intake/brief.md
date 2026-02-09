# Intake brief

## Task
- Run: `20260208-run-stage-0-intake-interview-for`
- Title: `Run Stage-0 intake interview for:`
- Goal now: recover after timeout, complete Stage-0 packet, then execute workflow stages through prompt-factory.

## System4D normalization

### Container
- Boundary (in):
  - Stage-0 artifacts (`questions`, `responses`, `brief`, `gate`).
  - Kickoff-readiness prep from recovered interview.
  - Workflow execution artifacts for explorers + synthesis + prompt-factory.
- Boundary (out):
  - Feature implementation/code changes.
  - Destructive git/file operations.
- Constraints (hard):
  - No DB mutation.
  - Security/policy gates enforced.
  - Keep docs/tests/contracts in sync.
  - Dirty working tree is expected (do not clean destructively).
  - Canonical contract: `docs/subagent-runs/schema/system4d-attrs.schema.json`.
- Constraints (preferences):
  - Prioritize strictness over compatibility when ambiguous.
  - Resume from baseline handoff, edit only where needed.
- Edges:
  - `docs/subagent-runs/*` stage artifacts.
  - `.pi/prompts/*` + `.pi/extensions/4d-intake-router.ts`.
  - quality-gate and test surfaces.
  - DB-path handoff to DB explorer.
- Dependencies:
  - Required intake fields fully answered (done).
  - Focus-area confirmation (done, broad scope).
  - DB canonicalization clarified: `mlflow.db` is canonical MLflow DB for this repo context.
  - Domain-expert takes source confirmed: `docs/rfc/*` packet files.
- Anti-Goals:
  - No premature implementation.
  - No unrelated tooling rewrites.

### Compass
- Driver:
  - Workflow recovery after timeout.
- Outcome:
  - Kickoff-ready intake packet with required fields complete.
- Trade-offs:
  - Strictness vs compatibility (selected priority).

### Engine
- Trigger:
  - Session recovery command `/interview-4d-intake ...`.
- States:
  - `intake_started -> interview_running -> interview_completed -> gate_pass|gate_fail`.
- Invariants:
  - Canonical schema is source of truth.
  - No kickoff proposal when interview incomplete.
  - Required kickoff fields must be non-empty.
  - No DB mutation during intake/exploration.
- Lifecycle:
  - Retry interview until complete, evaluate gate, proceed stage-by-stage.

### Fog
- Assumptions:
  - Branch remains `main`.
  - Dirty tree is expected/acceptable.
  - Existing domain-expert takes for MLflow/DSPy are in `docs/rfc/*` and reusable.
- Risks (top 3 + mitigations):
  1. Scope still broad (`complete workflow + existing domain takes`) and may dilute explorer focus.
     - Mitigation: enforce ranked issue/PR priority set before domain-architect drafting.
  2. `mlflow.db` is canonical but not present locally at runtime.
     - Mitigation: provide actual path/file before DB-heavy downstream tasks, or skip DB explorer stage explicitly.
  3. Documentation discoverability drift (`qmd` collection misses subagent-workflow docs).
     - Mitigation: qmd-first + direct-file fallback; capture drift and update collection scope later.
- Exceptions:
  - Interview timeout/cancel/skipped paths (already exercised and recovered).
- Debt:
  - `No debt allowed` selected; avoid carrying placeholders into downstream prompts.

## Success criteria
- Required kickoff fields captured from answers.
- Hard constraints vs preferences separated.
- Invariants captured.
- Top 3 risks + mitigations captured.
- Open questions for explorers captured.
- Gate checklist updated with explicit PASS/FAIL.

## Inputs
- `RUN_ID`: `20260208-run-stage-0-intake-interview-for`
- `TASK_TITLE`: `Run Stage-0 intake interview for:`
- `DRIVER`: `Workflow recovery after timeout`
- `OUTCOME`: `Kickoff-ready intake packet with required fields complete`
- `CONSTRAINTS`: `No DB mutation; Security/policy gates; Keep docs/tests/contracts in sync; Dirty working tree is expected`
- `BOUNDARY`: `in: Stage-0 intake artifacts only (questions/responses/brief/gate), Recovery from previous timeout, Kickoff-readiness prep (without launching kickoff) | out: Feature implementation/code changes, Destructive git/file operations`
- `EDGES_DEPENDENCIES`: `edges: docs/subagent-runs artifacts, .pi prompts/extensions (interview/router), Tests + quality gates, DB path resolution for later DB explorer | dependencies: Stakeholder answers for required fields, Explicit focus-area confirmation, DB path confirmation`
- `DB_PATH_OR_NONE` (canonical): `mlflow.db`

## Open questions for explorers
- Which exact MLflow/DSPy issue+PR set from `docs/rfc/*` is priority order 1..N?
- Should DB explorer be deferred until `mlflow.db` is present locally?
- If a downstream command uses a different RUN_ID (`20260208-dspx-development-session-kickoff`), should it be treated as a separate new run with explicit handoff linkage?
