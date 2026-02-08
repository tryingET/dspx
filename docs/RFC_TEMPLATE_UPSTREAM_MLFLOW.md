---
summary: "Fill-in RFC template for upstream MLflow observability hardening (DSPy integration + tracing internals)."
read_when:
  - "You are drafting upstream MLflow architecture/PR plan from the DSPx handoff packet."
  - "You need a structured decision template for span safety, concurrency, and autolog controls."
---

# RFC: Upstream MLflow DSPy/Tracing Hardening

## 0) Metadata

- RFC ID: `RFC-MLFLOW-OBS-<YYYYMMDD>-<slug>`
- Status: `draft | review | accepted | rejected | superseded`
- Owner: `<name>`
- Reviewers: `<names>`
- Created: `<date>`
- Target upstream release: `<version target>`
- Related docs:
  - `docs/ARCH_DRAFT_UPSTREAM_MLFLOW.md`
  - `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`

## 1) Problem statement

Describe observed failures with reproducible conditions.

Priority gaps (typical):
- span-start warning floods in expected no-op states
- callback state not parallel-safe
- missing autolog controls for naming/tagging/correlation

## 2) Scope / non-goals

### In scope
- <item>

### Out of scope
- <item>

### Compatibility constraints
- no breaking default behavior for existing users
- additive config/API where possible

## 3) Current state evidence

- source locations involved:
  - `mlflow/dspy/autolog.py`
  - `mlflow/dspy/callback.py`
  - `mlflow/tracing/fluent.py`
- failing logs/traces:
  - <evidence>
- concurrency failure scenarios:
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
- Deferred items:

## 6) Target architecture

### 6.1 Span safety behavior

Define expected behavior for:
- disabled tracing
- non-recording spans
- unexpected tracing exceptions

Include log-level policy (silent/debug/warn) and rate-limiting policy.

### 6.2 Parallel-safe callback state model

Define state container choice:
- contextvars / thread-local / explicit context object

Define guarantees under concurrent optimize/eval.

### 6.3 Autolog control surface (if changed)

List proposed optional args and defaults.

## 7) PR slicing plan

### PR1: <name>
- files touched:
- tests:
- expected user-visible impact:

### PR2: <name>
- files touched:
- tests:
- expected user-visible impact:

### PR3: <name>
- files touched:
- tests:
- expected user-visible impact:

## 8) Test strategy

- unit tests:
- integration tests:
- concurrency stress tests:
- warning-noise regression tests:

## 9) Rollout and release

- release sequencing:
- docs/changelog requirements:
- downstream verification in DSPx after release:

## 10) Risks

| Risk | Trigger | Mitigation | Rollback |
|---|---|---|---|
| <risk> | <trigger> | <mitigation> | <rollback> |

## 11) Open questions for maintainers

- Q1:
- Q2:

## 12) Execution checklist

- [ ] upstream issue(s) filed
- [ ] PR plan agreed with maintainers
- [ ] tests merged
- [ ] release version confirmed
- [ ] DSPx follow-up compatibility validation done
