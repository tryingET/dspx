---
summary: "Fill-in RFC template for DSPx-owned observability architecture changes."
read_when:
  - "You are drafting the DSPx next architecture RFC from the observability handoff packet."
  - "You need a decision-log skeleton with options and rollout phases for DSPx scope."
---

# RFC: DSPx Observability Next

## 0) Metadata

- RFC ID: `RFC-DSPX-OBS-<YYYYMMDD>-<slug>`
- Status: `draft | review | accepted | rejected | superseded`
- Owner: `<name>`
- Reviewers: `<names>`
- Created: `<date>`
- Target milestone: `<milestone>`
- Related docs:
  - `docs/ARCH_DRAFT_DSPX_NEXT.md`
  - `docs/MLFLOW_OBSERVABILITY_PLAN.md`
  - `docs/RUN_REPLAY_EXPLAIN.md`

## 1) Problem statement

What is failing or too weak today? Add concrete examples and impact.

## 2) Scope / non-goals

### In scope
- <item>

### Out of scope
- <item>

### Invariants (must not break)
- replay/explain local-first baseline remains source of truth
- MLflow enrichment never blocks explain baseline
- boundary invariant: no `core -> apps/*` imports

## 3) Current state evidence

- existing behavior:
  - <fact>
- metrics/logs/tests proving gap:
  - <evidence>

## 4) Option analysis (A/B/C)

### Option A: <name>
- Design:
- Pros:
- Cons:
- Risks:

### Option B: <name>
- Design:
- Pros:
- Cons:
- Risks:

### Option C: <name>
- Design:
- Pros:
- Cons:
- Risks:

## 5) Decision

- Chosen option: `<A|B|C>`
- Rationale:
- Rejected alternatives and why:

## 6) Target architecture

### 6.1 Interfaces/contracts

Specify exact contract deltas (examples):
- run tags schema
- receipt hint keys
- `mlflow_context` JSON fields
- reason-code taxonomy

### 6.2 Data model / payload examples

Provide before/after JSON snippets.

## 7) Rollout plan

### Phase 1
- implementation:
- tests:
- docs:

### Phase 2
- implementation:
- tests:
- docs:

### Phase 3
- implementation:
- tests:
- docs:

## 8) Compatibility and migration

- backward compatibility strategy:
- feature flags / defaults:
- deprecation plan (if any):

## 9) Validation plan

Required checks:
- `pre-commit run --all-files`
- `just monorepo-check`
- `just test`

Add focused tests:
- <test file + scenario>

## 10) Operational impact

- expected runtime/storage cost impact:
- failure/degraded modes:
- operator diagnostics (what to inspect first):

## 11) Risk register

| Risk | Trigger | Mitigation | Rollback |
|---|---|---|---|
| <risk> | <trigger> | <mitigation> | <rollback> |

## 12) Cross-team dependencies

- Upstream MLflow dependency:
- Upstream DSPy dependency:
- Sequencing constraints:

## 13) Open questions / decisions needed

- Q1:
- Q2:

## 14) Execution checklist

- [ ] implementation PRs scoped
- [ ] tests added/updated
- [ ] docs synced (`README`, `PROJECT_STATUS`, `docs/project/*`, domain docs)
- [ ] rollout owner assigned
