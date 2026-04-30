---
summary: "Archived subagent-run artifact: Stage 6 implementation plan — full-sweep."
read_when:
  - "You are auditing the archived subagent-run workflow output."
  - "You need the recorded artifact for Stage 6 implementation plan — full-sweep."
type: "reference"
---

# Stage 6 implementation plan — full-sweep

Run: `20260208-run-stage-0-intake-interview-for`
Execution mode: `full-sweep`

## Scope
- Implement all agreed work items from Stage-4 drafts and Stage-5 consensus.
- Keep ordered waves; avoid unordered parallel churn.

## Wave plan

### Wave 1 — DSPx-owned changes (foundation)
1. Correlation contract v1.1 in DSPx (`dspx.*` tags + optional receipt hints).
2. Deterministic explain diagnostics taxonomy (`mlflow_context` reason codes/version).
3. Optional bounded remote lookup path (`--mlflow-remote-lookup`, default off).
4. Docs + tests updated (`README`, `PROJECT_STATUS`, `NEXT_STEPS`, observability docs).

Acceptance gate:
- local-first replay/explain unchanged.
- deterministic diagnostics tests green.
- no DB mutation in workflow artifacts.

### Wave 2 — Upstream MLflow sweep
1. Umbrella issue with taxonomy/scope.
2. PR1: no-op span safety + warning policy.
3. PR2: callback concurrency safety/state isolation.
4. PR3 (optional but in-scope): additive autolog controls.

Acceptance gate:
- no warning flood in expected no-op paths.
- concurrency stress invariants pass.
- default behavior backward compatible.

### Wave 3 — Upstream DSPy sweep
1. Umbrella issue locking metadata/lifecycle semantics.
2. PR1: additive metadata envelope + version marker strategy.
3. PR2: compile lifecycle hooks (`on_compile_start/end`).
4. PR3: propagation guarantees + thread/async stress tests.

Acceptance gate:
- legacy callbacks keep working.
- compile lifecycle ordering/once semantics verified.
- no cross-root lineage leakage.

### Wave 4 — Downstream reconciliation
1. Bump dependency floors when upstream releases land.
2. Remove superseded local mitigations.
3. Full quality gates (`just fmt && just lint && just typecheck && just test`).
4. Replay/explain + MLflow behavior validation on upgraded stack.

Acceptance gate:
- no regressions in DSPx CLI flows.
- docs/contracts synced.

## Task contract format (for each work item)
- goal
- files/areas touched
- tests added/updated
- docs updates
- risks/rollback
- evidence links

## Evidence baseline for Stage 6 start
- consensus: `50-consensus/full-sweep-consensus.md`
- domain drafts:
  - `40-domain-drafts/dspx-workflow-architecture.md`
  - `40-domain-drafts/mlflow-upstream-architecture.md`
  - `40-domain-drafts/dspy-upstream-architecture.md`
- canonical DB available: `mlflow.db`
