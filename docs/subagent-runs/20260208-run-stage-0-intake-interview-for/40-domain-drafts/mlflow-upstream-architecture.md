# MLflow upstream architecture draft (Stage 4)

## Problem framing

### Container
- **Boundary:** Upstream MLflow changes for DSPy tracing/autolog reliability; no DSPx-local workaround proposals as primary solution.
- **Constraint:** Additive, backward-compatible surface by default; no mandatory behavior breaks.
- **Edge:** `mlflow/dspy/callback.py`, `mlflow/tracing/fluent.py`, `mlflow/dspy/autolog.py`.
- **Dependency:** DSPy callback semantics and downstream validation loops.
- **Anti-Goal:** Fixing downstream symptoms only in DSPx while upstream fragility remains.

### Compass
- **Driver:** Reduce warning-noise and concurrency fragility that degrade trust in observability.
- **Outcome:** Upstream-safe incremental changes that downstreams can adopt without local forks.
- **Trade-off:** Smaller PRs and slower breadth vs one-shot redesign.

### Engine
- **Trigger:** Recurrent no-op span warning patterns + callback linkage ambiguity under parallel optimize/eval.
- **State:** `problem taxonomy -> option selection -> issue/PR slicing -> rollout gates -> downstream reconciliation`.
- **Invariant:** Tracing failures must degrade gracefully; business logic should not crash from tracing internals.
- **Lifecycle:** Merge PR1 safety first, then PR2 correctness, then optional PR3 controls.

### Fog
- **Assumption:** Maintainers accept Option-B style scope (hardening + context-safe state + additive controls).
- **Risk:** Maintainers trim scope to warning-only patch.
- **Exception:** If PR3 control-surface scope is rejected, PR1/PR2 should still proceed.
- **Debt:** Placeholder issue IDs still need final pinning.

---

## Option matrix + trade-offs

### Option A — warning suppression only

#### Container
- Narrow to no-op warning classification/suppression.

#### Compass
- Quick relief for operator noise.

#### Engine
- Small patch, low review friction.

#### Fog
- Leaves concurrency correctness unresolved.

---

### Option B — no-op safety + context-scoped callback state + minimal controls (**recommended**)

#### Container
- PR1/PR2/PR3 slices with clear ownership and acceptance tests.

#### Compass
- Best balance between risk reduction and upstream reviewability.

#### Engine
- Ordered increments reduce blast radius:
  - PR1 taxonomy/rate-limit safety,
  - PR2 context isolation correctness,
  - PR3 additive controls.

#### Fog
- Needs strong stress + compatibility evidence to avoid partial/fragile merges.

---

### Option C — full callback architecture redesign

#### Container
- New broad callback context model and larger API reshaping.

#### Compass
- Long-term clean slate potential.

#### Engine
- High coupling and extended review cycles.

#### Fog
- Too large for near-term release cadence.

---

## Recommended issue/PR sequence (smallest-safe order)

### Container
- **Issue 0 (umbrella):** define taxonomy (`N0/N1/N2/E1/E2`), warning rate-limit policy, and acceptance gates.
- **Issue 1:** span no-op safety + warning policy in callback/fluent.
- **Issue 2:** callback concurrency state isolation (`ContextVar`-scoped state) and invariant recovery.
- **Issue 3 (optional/independent):** additive `autolog()` controls for naming/tags/correlation.

### Compass
- Sequence prioritizes user pain first (noise), then correctness, then ergonomics.

### Engine
1. **PR1 (Issue 1):** expected no-op = silent/debug only, unexpected tracing failures = rate-limited warnings.
2. **PR2 (Issue 2):** remove global mutable linkage state; enforce try/finally balance + cross-context isolation tests.
3. **PR3 (Issue 3):** optional controls with defaults unchanged.
4. Release candidate verification with downstream DSPx regression matrix.

### Fog
- Keep PR3 optional to prevent scope deadlock.

---

## Compatibility + migration notes

### Container
- No default behavior break accepted.
- New controls must be optional; existing `autolog()` usage remains valid.

### Compass
- Preserve adoption simplicity for current users while enabling structured downstream semantics.

### Engine
- Rollout gates:
  - **Gate A (PR1):** expected no-op scenarios emit zero warning flood.
  - **Gate B (PR2):** concurrent stress shows zero parent/child contamination.
  - **Gate C (PR3):** defaults unchanged when args unset; configured metadata appears when set.
- Migration:
  - downstreams can adopt PR1/PR2 immediately without callsite changes.
  - PR3 adoption opt-in by explicit argument usage.

### Fog
- If maintainers require narrower scope, defer PR3 without blocking PR1/PR2 release.

---

## Validation plan (unit/integration/behavioral signals)

### Container
- Validate at MLflow unit/integration/stress layers plus downstream RC canary.

### Compass
- Target confidence: no warning floods in no-op states, deterministic linkage under concurrency.

### Engine
- Unit:
  - no-op taxonomy classification,
  - warning limiter dedupe/window behavior,
  - callback state reset on exceptions.
- Integration:
  - DSPy optimize/eval sequential + concurrent linkage,
  - thread + async context-boundary checks,
  - additive autolog controls (if PR3).
- Behavioral signals:
  - warning-count metrics per dedupe key,
  - linkage mismatch count (must remain 0),
  - regression replay for prior `NonRecordingSpan` flood pattern.

### Fog
- Unknown until upstream CI runs: long-tail concurrency flakes under varied schedulers.

---

## Risks / mitigations

### Container
- **Risk:** Over-broad no-op classification hides true failures.
- **Mitigation:** enforce strict `N*` vs `E*` taxonomy tests.

### Compass
- **Risk:** Concurrency refactor destabilizes nested linkage semantics.
- **Mitigation:** PR2 stress matrix + rollback-ready isolation.

### Engine
- **Risk:** Warning limiter key cardinality grows under fault storms.
- **Mitigation:** normalized keys + bounded LRU key cache.

### Fog
- **Risk:** upstream review bandwidth delays PR2.
- **Mitigation:** keep PR1 independently mergeable and beneficial.

---

## Open maintainer questions

### Container
- Is `ContextVar` the preferred default for callback state isolation?

### Compass
- Should expected no-op paths be fully silent or retain optional debug breadcrumbs?

### Engine
- Minimal accepted additive `autolog()` controls: name only, or name+tags+correlation factory?

### Fog
- Is `300s` suppression window a reasonable initial default, or should it be configurable first?

---

## Evidence
- `docs/rfc/RFC-MLFLOW-OBS-20260207-dspy-tracing-hardening.md`
- `docs/rfc/RFC-DSPX-OBS-20260207-mlflow-explain-correlation-v11.md`
- `docs/MLFLOW_OBSERVABILITY_PLAN.md`
- `20-synthesis/technical-writer.md`
- `30-prompt-factory/system-prompts/mlflow-architect-system.md`
- `30-prompt-factory/task-prompts/mlflow-architect-task.md`
