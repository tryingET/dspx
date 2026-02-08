---
summary: "Upstream MLflow architecture draft for DSPy integration hardening (span safety, concurrency, control surfaces)."
read_when:
  - "You are preparing upstream MLflow issues/PRs related to DSPy autolog/tracing behavior."
  - "You need clear MLflow-owned responsibilities vs DSPx local mitigations."
---

# Upstream MLflow Architecture Draft

RFC skeleton to fill:
- `docs/RFC_TEMPLATE_UPSTREAM_MLFLOW.md`

## Ownership (MLflow)

Primary ownership in MLflow integration layer:
- `mlflow/dspy/autolog.py`
- `mlflow/dspy/callback.py`
- `mlflow/tracing/fluent.py`

DSPx should not carry long-term forks/monkeypatches for these behaviors.

## Problem statement

### 1) Span-start warning flood risk in opt-in trace mode

Observed class of issue:
- repeated warnings like `Failed to start span ... NonRecordingSpan ...`
- can reappear when tracing toggles/context states diverge
- creates operator noise; leads to disabling observability

### 2) Callback optimization/eval state not parallel-safe

Current callback includes explicit note about parallel optimization state safety.
Global mutable structures can mis-link runs/metrics under concurrency.

### 3) Control surfaces not rich enough for structured run semantics

Need stronger first-class controls for run naming/tagging in DSPy autolog flows,
without downstream wrappers reimplementing semantics.

## Proposed target architecture

### A) Span lifecycle hardening (no warning flood on expected no-op states)

Candidate design:
- in `MlflowCallback._start_span`, guard known no-op tracing states early
- when no real recording span can be created, return no-op silently (debug only)
- avoid warning-level logs for expected disabled/non-recording paths
- ensure `_end_span` treats missing/no-op span as debug, not noisy warning

### B) `start_span_no_context` hardening

In `mlflow/tracing/fluent.py`:
- treat expected non-recording tracer states as no-op without warning flood
- reserve warnings for unexpected exceptional failures only
- optional rate-limited/once-per-session warning behavior for repeated same cause

### C) Parallel-safe callback state model

Refactor callback optimization/eval state:
- remove reliance on process-global mutable counters/sets
- use context-scoped state (thread/task-local or contextvars)
- preserve deterministic parent-child run linkage under concurrent optimize/eval

### D) Autolog control surface extensions

Consider adding optional args in `mlflow.dspy.autolog(...)`:
- eval run naming template (or callback)
- run tag injection hook/static dict
- compile/eval correlation-id hook

Goal: avoid downstream projects hand-rolling run semantics repeatedly.

## Backward compatibility constraints

- keep default behavior stable for existing users
- new controls optional; no required migration
- no regressions in managed-run semantics for existing autolog users

## Suggested PR slices (small, reviewable)

### PR1: Warning/safety hardening
- callback + fluent no-op handling
- tests: no warning flood in disabled/non-recording states

### PR2: Parallel state safety
- callback state refactor
- tests: concurrent compile/eval linkage correctness

### PR3: Optional control surface
- new autolog optional args
- tests + docs for naming/tag hooks

## Acceptance criteria

- opt-in trace mode does not flood warnings on expected no-op paths
- concurrent optimization/eval does not corrupt run linkage
- downstream integrators can apply stable naming/tagging without invasive patching

## Risks

- behavior changes in warning policy may hide real failures
  - mitigate: classify expected vs unexpected paths explicitly
- concurrency refactor complexity
  - mitigate: incremental PR + targeted stress tests

## Open questions for MLflow domain expert

1. preferred no-op logging policy: fully silent vs debug-level breadcrumbs?
2. should parallel-safe state use contextvars, thread-local, or explicit run-context object?
3. what minimal new autolog controls are acceptable without API bloat?
4. should correlation IDs be standardized across integrations, not only DSPy?
