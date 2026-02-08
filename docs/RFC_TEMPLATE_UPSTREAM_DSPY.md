---
summary: "Fill-in RFC template for upstream DSPy callback/lifecycle/context-propagation contract improvements."
read_when:
  - "You are drafting upstream DSPy architecture changes for callback metadata and lifecycle semantics."
  - "You need an additive, backend-agnostic contract RFC skeleton."
---

# RFC: Upstream DSPy Callback Contract Evolution

## 0) Metadata

- RFC ID: `RFC-DSPY-CALLBACK-<YYYYMMDD>-<slug>`
- Status: `draft | review | accepted | rejected | superseded`
- Owner: `<name>`
- Reviewers: `<names>`
- Created: `<date>`
- Target upstream release: `<version target>`
- Related docs:
  - `docs/ARCH_DRAFT_UPSTREAM_DSPY.md`
  - `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`

## 1) Problem statement

What callback/lifecycle gaps block reliable downstream observability consumers?

## 2) Scope / non-goals

### In scope
- callback metadata contract
- compile/eval/infer lifecycle semantics
- context propagation guarantees in parallel execution

### Out of scope
- adding backend-specific observability systems
- changing DSPy model semantics unrelated to callback contract

## 3) Current state evidence

- current callback hooks and payload shape:
  - <evidence>
- ambiguity points (phase, optimizer step, split, identity):
  - <evidence>
- parallel propagation gaps:
  - <evidence>

## 4) Option analysis (A/B/C)

### Option A: Enrich existing hooks only
- Design:
- Pros:
- Cons:
- Risks:

### Option B: Add explicit lifecycle hooks + metadata
- Design:
- Pros:
- Cons:
- Risks:

### Option C: Introduce callback context object contract
- Design:
- Pros:
- Cons:
- Risks:

## 5) Decision

- Chosen option: `<A|B|C>`
- Rationale:
- Deferred/phase-2 items:

## 6) Target contract

### 6.1 Canonical metadata keys (v1)

List key + type + semantics:
- `phase`
- `optimizer_id`
- `optimizer_step`
- `dataset_name`
- `dataset_split`
- `predictor_name`
- `parent_call_id`

### 6.2 Lifecycle hook additions (if any)

Specify hook signatures and when emitted.

### 6.3 Context propagation guarantees

Define guarantees for:
- thread pools
- async tasks
- nested execution

## 7) Backward compatibility

- additive strategy:
- behavior preserved for existing callbacks:
- contract version marker strategy (if any):

## 8) PR slicing plan

### PR1: metadata envelope
- files touched:
- tests:

### PR2: lifecycle hooks
- files touched:
- tests:

### PR3: propagation semantics
- files touched:
- tests:

## 9) Validation plan

- callback compatibility tests with legacy callbacks
- deterministic ordering/correlation tests under concurrency
- docs/examples updated for new keys/hooks

## 10) Risks

| Risk | Trigger | Mitigation | Rollback |
|---|---|---|---|
| <risk> | <trigger> | <mitigation> | <rollback> |

## 11) Open questions for maintainers

- Q1:
- Q2:

## 12) Execution checklist

- [ ] upstream issue(s) filed
- [ ] metadata key set agreed
- [ ] hook semantics agreed
- [ ] compatibility tests merged
- [ ] downstream DSPx validation completed
