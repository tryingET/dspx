---
summary: "Upstream DSPy RFC draft for additive callback metadata, lifecycle hooks, and context propagation guarantees."
read_when:
  - "You are preparing DSPy upstream work for callback contract and concurrency-safe context propagation."
  - "You need contract-level metadata semantics for downstream observability consumers."
---

# RFC: Upstream DSPy Callback Contract Evolution

## 0) Metadata

- RFC ID: `RFC-DSPY-CALLBACK-20260207-lifecycle-contract-v1`
- Status: `draft`
- Owner: `lightningralf (DSPx upstream liaison)`
- Reviewers: `DSPy maintainers`, `DSPx observability reviewers`
- Created: `2026-02-07`
- Target upstream release: `dspy-ai >= 3.2.0` (candidate)
- Related docs:
  - `docs/ARCH_DRAFT_UPSTREAM_DSPY.md`
  - `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`

## 1) Problem statement

Downstream observability consumers need richer, stable callback semantics than current baseline provides.

Current gaps:
- limited canonical metadata for phase/optimizer/dataset identity
- compile lifecycle boundaries are not explicit enough for robust correlation
- context propagation expectations under parallel execution are not explicit enough
- compatibility/version interpretation is not explicit enough for mixed old/new consumers

## 2) Scope / non-goals

### In scope
- callback metadata contract
- compile/eval/infer lifecycle semantics
- context propagation guarantees in parallel execution

### Out of scope
- adding backend-specific observability systems
- changing DSPy model semantics unrelated to callback contract
- redesigning DSPy runtime concurrency architecture

## 3) Current state evidence

- current callback hooks and payload shape:
  - useful generic callbacks, but metadata envelope is not standardized
- ambiguity points (phase, optimizer step, split, identity):
  - downstream callbacks infer semantics ad hoc
- parallel propagation gaps:
  - parent/child correlation can be unclear for consumers in concurrent paths

## 4) Option analysis (A/B/C)

### Option A: Enrich existing hooks only
- Design:
  - inject additional metadata keys into current hook payloads; no new lifecycle hooks
- Pros:
  - minimal compatibility risk
  - smallest implementation footprint
- Cons:
  - compile lifecycle still inferred indirectly
  - weaker long-term contract clarity
- Risks:
  - semantic drift across call sites over time

### Option B: Add explicit lifecycle hooks + canonical metadata (additive)
- Design:
  - define canonical metadata key set (v1)
  - add optional compile lifecycle hooks (`on_compile_start`, `on_compile_end`)
  - document context propagation guarantees
- Pros:
  - practical clarity without breaking existing callbacks
  - gives downstream consumers stable phase boundaries
- Cons:
  - requires carefully staged updates across runtime paths
- Risks:
  - partial rollout can create temporary inconsistencies

### Option C: Introduce callback context object contract
- Design:
  - add formal callback context object and migrate hooks around it
- Pros:
  - strongest long-term explicitness and extension path
- Cons:
  - larger API/migration surface
  - likely excessive for immediate release window
- Risks:
  - prolonged review and adoption cycle

## 5) Decision

- Chosen option: `B`
- Rationale:
  - best balance of semantic clarity and additive compatibility
  - enables deterministic downstream observability mapping now
- Deferred/phase-2 items:
  - possible future context object (`C`) only if additive metadata/hooks prove insufficient

## 6) Target contract

### 6.1 Canonical metadata keys (v1)

For additive rollout, producers may initially emit only a subset of keys. Once a producer emits `callback_contract_version="1"`, it is asserting v1 completeness rules below.

| Key | Type | Required in v1-marked payload | Nullable | Semantics / constraints |
|---|---|---|---|---|
| `phase` | `str` | yes | no | one of `compile`, `eval`, `infer` |
| `optimizer_id` | `str \| None` | yes | yes | optimizer identity; `None` when not optimizer-driven |
| `optimizer_step` | `int \| None` | yes | yes | non-negative index when present; `None` when outside optimizer step scope |
| `dataset_name` | `str \| None` | yes | yes | logical dataset identifier; `None` when not dataset-backed |
| `dataset_split` | `str \| None` | yes | yes | split label (`train`, `dev`, `test`, etc.); `None` when not applicable |
| `predictor_name` | `str \| None` | yes | yes | predictor/module identity; `None` for root/global events |
| `parent_call_id` | `str \| None` | yes | yes | linkage id to logical parent callback; `None` for root callback events |
| `callback_contract_version` | `str` | no (recommended) | no | if present in v1 rollout, value MUST be `"1"` |

Presence/nullability interpretation:
- Missing key: producer did not assert v1 completeness for that payload path (legacy/partial rollout).
- Present key with `null`: producer asserts key is known but not applicable/unknown for that event.
- Consumers MUST treat missing and `null` as semantically non-breaking equivalents for control flow.
- Producers MUST NOT encode null-like sentinels (e.g., empty string, `"none"`) in place of `null`.

### 6.2 Lifecycle hook additions

Candidate additive hooks:
- `on_compile_start(context, **kwargs) -> None`
- `on_compile_end(context, result=None, error=None, **kwargs) -> None`

Semantics (normative):
- compile root definition:
  - a compile root is the outermost compile invocation with no active compile lifecycle context
- ordering:
  - `on_compile_start` MUST fire before any descendant compile/eval/infer callback for that root
  - `on_compile_end` MUST fire after all descendant callbacks for that root have completed dispatch
  - per-root ordering is deterministic; no global total ordering is guaranteed across different roots executing concurrently
- once semantics:
  - in non-fatal in-process execution, `on_compile_start` and `on_compile_end` MUST each emit exactly once per compile root
  - `on_compile_end` MUST be emitted from a `finally`-equivalent path with exactly one of `{result, error}` populated
  - if process/interpreter terminates abruptly (SIGKILL, hard crash), `on_compile_end` is at-most-once (may be absent)
  - `on_compile_end` MUST NOT emit if corresponding `on_compile_start` did not emit
- nested compile behavior:
  - nested compile activity inside an active compile root does not create a second root lifecycle pair by default
  - nested work remains observable through existing hooks + metadata lineage

### 6.3 Context propagation guarantees

Guarantees (backend-agnostic, runtime-internal concurrency only):
- propagation scope:
  - context propagation applies to thread/async tasks created by DSPy runtime internals during callback-producing execution
- snapshot semantics:
  - child tasks capture callback context at scheduling/submission time; later parent mutation does not retroactively alter already-scheduled children
- lineage invariants:
  - `phase` remains stable within a callback subtree unless explicit phase transition occurs at the runtime boundary
  - `parent_call_id` in child callbacks refers to the logical parent callback lineage for that subtree
- isolation invariants:
  - no cross-root context leakage: concurrent roots MUST NOT reuse each other’s lineage metadata

Non-guarantees:
- no guarantee for user-managed executors/tasks outside DSPy-internal scheduling points
- no guarantee across process boundaries (`multiprocessing`, remote workers, RPC boundaries) unless separately instrumented
- no global deterministic interleaving order across parallel siblings (only per-root/per-branch ordering invariants)
- no exactly-once end-of-lifecycle emission under hard process termination

## 7) Backward compatibility

- additive strategy:
  - all new keys/hooks remain additive; existing callbacks keep working without source changes
- compatibility modes:
  - legacy/unmarked payload (`callback_contract_version` absent): consumers MUST parse defensively and assume partial metadata
  - v1-marked payload (`callback_contract_version="1"`): consumers MAY enforce v1 key semantics from Section 6.1
- consumer guidance:
  - treat unknown keys/hooks as ignorable extensions
  - do not fail closed on missing optional lifecycle hooks
  - prefer feature detection (`hasattr`/capability checks) over version pinning for hook registration
- version evolution policy:
  - additive keys and hook kwargs: allowed in same major contract version
  - semantic change to existing key meaning or lifecycle ordering: requires new major contract version
  - deprecations: dual-emission/dual-parse window for at least one minor upstream release before removal

## 8) PR slicing plan

### PR1: metadata envelope
- files touched:
  - callback dispatch/runtime hook payload builders
- tests:
  - metadata presence/shape tests with legacy callback compatibility
  - missing-vs-null interpretation tests
  - optional marker (`callback_contract_version`) parse compatibility tests
- acceptance gate:
  - legacy callbacks unchanged; v1-marked payloads satisfy Section 6.1 key completeness

### PR2: lifecycle hooks
- files touched:
  - compile execution entry/exit paths
- tests:
  - compile start/end emission and ordering tests
  - success and error path tests (`result` xor `error`)
  - nested compile root/non-root behavior tests
- acceptance gate:
  - exactly one lifecycle pair per compile root in non-fatal runs

### PR3: propagation semantics
- files touched:
  - parallel executor/callback propagation paths
- tests:
  - deterministic parent linkage under thread/async concurrency
  - cross-root isolation tests under concurrent compile roots
  - repeated stress runs to detect race/flaky lineage behavior
- acceptance gate:
  - no lineage invariant violations across thread/async mixed stress matrix

## 9) Validation plan

Validation must pass both compatibility and concurrency criteria.

Core criteria:
- compatibility:
  - legacy callbacks pass unchanged behavioral tests
  - mixed old/new consumers parse metadata without exceptions
- lifecycle correctness:
  - per compile root in non-fatal runs: `count(start) == 1`, `count(end) == 1`
  - `on_compile_start` index < any descendant callback index < `on_compile_end` index
  - `on_compile_end` carries exactly one of `result` or `error`
- concurrency lineage correctness:
  - no cross-root `parent_call_id` contamination under parallel roots
  - per-branch parent lineage remains internally consistent under thread and async fan-out
  - no deterministic-order assertions across parallel siblings beyond defined invariants

Execution criteria:
- run concurrency matrix (`sync`, `threads`, `async`, `mixed`) with repeated runs and scheduler jitter
- require zero invariant violations across repeated CI stress runs before merge
- document any intentionally unsupported concurrency boundary as explicit non-goal (not silent failure)

## 10) Risks

| Risk | Trigger | Mitigation | Rollback |
|---|---|---|---|
| metadata interpretation drift during partial rollout | mixed marked/unmarked payload paths | strict docs for missing vs null + marker-aware tests | temporarily disable marker emission, keep additive keys only |
| duplicate or missing lifecycle hooks | incorrect root detection or non-finally exit | root guard + finally-path emission + invariant tests | disable `on_compile_*` emission behind flag while retaining PR1 |
| concurrency lineage leakage | context capture bug in thread/async paths | stress matrix + cross-root contamination assertions | revert PR3 only; keep PR1/PR2 merged |
| consumer breakage from strict parsing assumptions | downstream assumes full metadata always present | compatibility guidance + defensive parsing examples | revert to unmarked payload mode and publish migration note |

## 11) Open questions for maintainers

- Q1: Should `callback_contract_version="1"` be emitted immediately in first release, or enabled after one release of unmarked additive key rollout?
- Q2: For nested compile calls, is root-only lifecycle emission the preferred default, or should maintainers allow opt-in nested lifecycle pairs?
- Q3: Is one minor release of dual-parse/deprecation window sufficient for upstream policy, or does DSPy require longer?

## 12) Execution checklist

- [ ] upstream issue(s) filed
- [ ] metadata key set agreed
- [ ] hook semantics agreed
- [ ] compatibility tests merged
- [ ] concurrency stress matrix added to CI (or pre-merge gating)
- [ ] version marker rollout decision recorded (`immediate` vs `staged`)
- [ ] downstream DSPx validation completed
