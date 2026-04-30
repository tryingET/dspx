---
summary: "Archived subagent-run artifact: DSPy upstream architecture draft (Stage 4)."
read_when:
  - "You are auditing the archived subagent-run workflow output."
  - "You need the recorded artifact for DSPy upstream architecture draft (Stage 4)."
type: "reference"
---

# DSPy upstream architecture draft (Stage 4)

## Problem framing

### Container
- **Boundary:** Upstream DSPy callback contract evolution only (metadata, lifecycle hooks, context propagation guarantees).
- **Constraint:** Additive evolution preferred; avoid breaking existing callback implementations.
- **Edge:** Callback payload builders, compile lifecycle dispatch, parallel callback propagation paths.
- **Dependency:** Maintainer acceptance of explicit contract semantics and rollout marker strategy.
- **Anti-Goal:** Encoding DSPx-only assumptions as universal DSPy behavior.

### Compass
- **Driver:** Current callback payloads are semantically thin/implicit for robust downstream observability.
- **Outcome:** Explicit, testable callback contract with deterministic lifecycle/correlation behavior.
- **Trade-off:** Staged additive rollout vs immediate strict contract enforcement.

### Engine
- **Trigger:** Need reliable compile/eval/infer lineage semantics under concurrency.
- **State:** `contract proposal -> metadata rollout -> lifecycle hooks -> propagation guarantees`.
- **Invariant:** Ambiguity surfaced as open questions, not hidden defaults.
- **Lifecycle:** PR1 metadata, PR2 hooks, PR3 propagation semantics.

### Fog
- **Assumption:** Upstream willing to accept versioned callback contract marker.
- **Risk:** Partial rollout creates mixed payload modes (missing vs null confusion).
- **Exception:** Hard process termination may violate exactly-once end-hook expectations.
- **Debt:** Final marker rollout strategy (`immediate` vs `staged`) unresolved.

---

## Contract delta map (current -> proposed)

### Container
| Surface | Current (baseline) | Proposed (additive) |
|---|---|---|
| Metadata envelope | ad-hoc keys, inconsistent presence | canonical key set (`phase`, `optimizer_id`, `optimizer_step`, `dataset_name`, `dataset_split`, `predictor_name`, `parent_call_id`) |
| Contract marker | none/implicit | optional `callback_contract_version="1"` |
| Compile lifecycle | inferred from generic hooks | explicit `on_compile_start` / `on_compile_end` hooks |
| Concurrency semantics | largely undocumented | explicit propagation/isolation guarantees and non-guarantees |
| Consumer expectations | defensive parsing by convention | documented missing-vs-null compatibility semantics |

### Compass
- Delta intent: increase semantic clarity without invalidating existing callbacks.

### Engine
- Producer behavior:
  - unmarked payloads allowed during rollout,
  - marked payloads must meet v1 completeness semantics.
- Hook behavior:
  - root compile lifecycle pair exactly-once in non-fatal runs,
  - `on_compile_end` from finally path with `result xor error`.

### Fog
- Requires strict docs/tests to prevent interpretation drift during transition.

---

## Option matrix + trade-offs

### Option A — metadata enrichment only

#### Container
- Add canonical keys into existing callbacks only.

#### Compass
- Lowest compatibility risk and fastest merge path.

#### Engine
- No new lifecycle hooks; compile boundaries still inferred.

#### Fog
- Leaves major lifecycle ambiguity unresolved.

---

### Option B — metadata + explicit compile hooks + propagation contract (**recommended**)

#### Container
- Full additive v1 contract package in three PR slices.

#### Compass
- Best balance between practicality and long-term reliability.

#### Engine
- Staged rollout:
  - PR1 metadata,
  - PR2 compile hooks,
  - PR3 propagation semantics + stress tests.

#### Fog
- Medium complexity; needs careful mixed-mode compatibility handling.

---

### Option C — new callback context object API

#### Container
- Larger API redesign centered on context object abstraction.

#### Compass
- Strong long-term extensibility.

#### Engine
- Wide migration burden for maintainers/users.

#### Fog
- High review/adoption risk for near-term release windows.

---

## Recommended sequencing (issues/PR decomposition)

### Container
- **Issue 0 (umbrella):** lock v1 key set, missing-vs-null semantics, and lifecycle ordering rules.
- **Issue 1 / PR1:** metadata envelope + optional version marker.
- **Issue 2 / PR2:** compile root lifecycle hooks and ordering guarantees.
- **Issue 3 / PR3:** context propagation guarantees with thread/async stress matrix.

### Compass
- Sequence maximizes early value while preserving rollback boundaries.

### Engine
1. **PR1 gate:** legacy callbacks unchanged; marked v1 payload completeness tests pass.
2. **PR2 gate:** exactly one compile root start/end pair in non-fatal runs; `result xor error` enforced.
3. **PR3 gate:** zero cross-root lineage leakage across sync/thread/async/mixed stress runs.
4. Post-merge adoption note for downstream consumers (feature detection over strict version pinning).

### Fog
- If PR3 slips, PR1+PR2 still provide meaningful contract clarity.

---

## Backward-compatibility guardrails + adoption strategy

### Container
- Additive-only changes in v1 cycle.
- Existing callbacks remain operational without source updates.

### Compass
- Encourage safe incremental adoption for mixed old/new ecosystems.

### Engine
- Guardrails:
  - missing key and null treated as non-breaking equivalents for control flow,
  - unknown future keys/hooks ignored safely,
  - feature detection preferred for hook usage.
- Adoption strategy:
  - phase 1: emit keys unmarked in partial paths,
  - phase 2: enable `callback_contract_version="1"` when coverage complete,
  - phase 3: enforce stronger downstream assertions only for marked payloads.

### Fog
- Final decision needed: immediate marker emission vs one-release staged marker rollout.

---

## Testability implications / validation plan

### Container
- Must prove lifecycle correctness + propagation isolation + compatibility behavior.

### Compass
- Desired confidence: deterministic lineage under concurrency, no legacy regression.

### Engine
- Unit tests:
  - key presence/shape checks,
  - missing-vs-null semantics,
  - marker parse behavior.
- Lifecycle tests:
  - compile start before descendants,
  - compile end after descendants,
  - exactly-one pair/root in non-fatal runs.
- Concurrency tests:
  - sync/thread/async/mixed matrix,
  - cross-root contamination assertions,
  - repeated stress with scheduler jitter.

### Fog
- Non-goal reminder in tests: no global deterministic order across parallel siblings.

---

## Risks / mitigations

### Container
- **Risk:** Metadata key sprawl.
- **Mitigation:** minimal canonical v1 set, explicit extension policy.

### Compass
- **Risk:** Lifecycle hooks duplicated/missed in nested compile scenarios.
- **Mitigation:** root-detection invariants + finally-path enforcement tests.

### Engine
- **Risk:** Context leakage across thread/async boundaries.
- **Mitigation:** PR3 stress matrix and explicit non-guarantee docs for user-managed executors.

### Fog
- **Risk:** Downstreams assume marked semantics too early.
- **Mitigation:** staged marker rollout and migration guidance.

---

## Open maintainer questions

### Container
- Should `callback_contract_version="1"` ship immediately or after one release of unmarked additive key rollout?

### Compass
- Is root-only compile lifecycle emission the preferred default, or should nested roots support opt-in lifecycle pairs?

### Engine
- What minimum concurrency guarantee set is acceptable for first upstream release (thread+async both required)?

### Fog
- How long should dual-parse/deprecation windows be for future major contract version changes?

---

## Evidence
- `docs/rfc/RFC-DSPY-CALLBACK-20260207-lifecycle-contract-v1.md`
- `docs/rfc/OBSERVABILITY_KICKOFF_20260207.md`
- `docs/ARCH_DRAFT_UPSTREAM_DSPY.md`
- `20-synthesis/technical-writer.md`
- `30-prompt-factory/system-prompts/dspy-architect-system.md`
- `30-prompt-factory/task-prompts/dspy-architect-task.md`
