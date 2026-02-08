---
summary: "Upstream DSPy architecture draft for callback contract and context propagation (backend-agnostic)."
read_when:
  - "You are preparing upstream DSPy issues/PRs for observability callback metadata/lifecycle."
  - "You need DSPy-owned changes without adding new observability backends."
---

# Upstream DSPy Architecture Draft

RFC skeleton to fill:
- `docs/RFC_TEMPLATE_UPSTREAM_DSPY.md`

## Ownership (DSPy)

Own in DSPy core runtime:
- callback contract richness and stability
- lifecycle semantics for compile/eval/infer phases
- context propagation guarantees under parallel executors

Do not require DSPy to ship new observability backends.

## Problem statement

Current callback API is useful but thin for higher-order observability and
cross-phase correlation.

Downstream impact:
- harder to attach stable semantics to compile/eval/infer boundaries
- limited standard metadata for dataset split, optimizer step, predictor identity
- parallel execution can lose correlation clarity for callback consumers

## Scope constraints

- no requirement to add any backend-specific instrumentation
- changes must remain backend-agnostic callback/runtime contract improvements
- preserve compatibility for existing callback implementations

## Proposed target architecture

### A) Standard callback metadata envelope

Provide standard metadata keys (where available) to callback handlers, e.g.:
- `phase`: `compile | eval | infer`
- `optimizer_id`
- `optimizer_step`
- `dataset_name`
- `dataset_split`
- `predictor_name` / module identity
- `parent_call_id` (when nested)

Backend consumers (MLflow or others) can use these keys without ad-hoc parsing.

### B) Explicit lifecycle hooks for compile roots

Add optional callback hooks (default no-op):
- `on_compile_start(...)`
- `on_compile_end(...)`

Rationale:
- avoids overloading generic module callbacks for compile lifecycle boundaries
- improves parent-child grouping consistency for downstream loggers

### C) Context propagation contract for parallelism

Define explicit guarantees for callback context propagation across:
- thread pools
- async tasks
- internal parallel executors

At minimum:
- preserve parent correlation (`parent_call_id`)
- deterministic callback ordering semantics per call subtree

## Compatibility strategy

- additive fields/hooks only
- existing callbacks continue to work unchanged
- clear docs for new optional metadata keys

## Suggested PR slices

### PR1: Metadata envelope (additive)
- introduce standard metadata keys where already available
- no behavioral changes to existing callbacks

### PR2: Compile lifecycle hooks
- add optional compile root start/end hooks
- integrate in relevant compile execution paths

### PR3: Context propagation semantics + tests
- codify parent/child correlation behavior under parallel execution
- stress tests for deterministic callback linkage

## Acceptance criteria

- downstream callback consumers can distinguish compile/eval/infer reliably
- optimizer/eval context can be correlated without global mutable state hacks
- no regression for existing callback classes

## Risks

- metadata key explosion
  - mitigate: keep minimal canonical key set + clear docs
- rollout complexity across DSPy internals
  - mitigate: additive staged rollout, comprehensive tests

## Open questions for DSPy domain expert

1. minimal canonical metadata key set for v1?
2. compile hook shape: dedicated hooks vs enriched existing hooks?
3. required guarantees for callback ordering under concurrency?
4. should DSPy publish a callback contract version marker?
