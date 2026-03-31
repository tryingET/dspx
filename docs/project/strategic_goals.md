---
summary: "Top strategic goals selected from the vision."
read_when:
  - "When planning quarters"
  - "When deciding which major bet is active now versus next"
---

# Strategic Goals

Active strategic goal: `SG2`
Next strategic goal: `unmaterialized`

## Strategic ranking (Eisenhower-3D)

| ID | Status | Goal | Importance | Urgency | Difficulty | Why this is the right wave now |
| --- | --- | --- | --- | --- | --- | --- |
| `SG2` | active | Turn receipts, replay, and Oracle evidence into the predictive/governance substrate for V8 and V9. | 5 | 5 | 4 | DSPx now emits the first bounded governance-only ranking/promotion evaluation receipts from shadow predictive-ranking evidence, but it still lacks the next explicit contract for how any named variant could ever move from governance-only evaluation into future live-authorized policy under human control. |
| `SG3` | complete | Replace hand-authored task-scope manifests with AK-native scope snapshots across validation and handoff. | 4 | 4 | 3 | Cross-repo fixture work `AK-548` plus repo-local validation, workflow/handoff cleanup, and regression slices `AK-549`–`AK-551` have all landed, so DSPx now validates task scope from AK-native snapshots, keeps legacy scope files as brownfield fallback only, and covers the cleaned-up authority story with broader regressions. |

## Strategic definitions of done

### `SG2` — Evidence substrate for V8/V9
Done when:
- DSPx can retrieve and consume structured receipt/replay/Oracle evidence through bounded shadow predictive-ranking or equivalent evidence-aware comparisons without mutating live V7 behavior by accident,
- evidence-backed candidate priors and named governance-only ranking/promotion variants can be evaluated under explicit contracts before any live pre-ranking/pruning is authorized,
- future movement from governance-only evaluation into live-authorized policy requires an explicit human-governed contract rather than silent prompt or policy drift.

### `SG3` — AK-native scope snapshots for repo validation/handoff
Done when:
- repo validation derives task scope from AK-native snapshots instead of hand-authored manifest bookkeeping,
- `next_session_prompt.md`, workflow docs, and verification commands no longer depend on manual task-scope manifest coupling,
- regression coverage proves the AK-native scope flow across dirty working-tree and committed `HEAD` modes.

## Recently completed strategic goals

### `SG3` — AK-native scope snapshots for repo validation/handoff
Status: complete

Completed via:
- `AK-548` cross-repo fixture alignment,
- `AK-549` snapshot-first task-scope validation,
- `AK-550` workflow/handoff cleanup that removed `next_session_prompt.md` from task binding,
- `AK-551` broader regression coverage for claim-based binding, explicit scope-artifact CLI paths, snapshot preference, and workflow-contract surfaces.

### `SG1` — V9-compatible synthesis core, V7-first delivery
Status: complete

Done when:
- `module-gen` runs through a synthesis runtime rather than an ad-hoc template-only service path,
- synthesis requests, candidate records, evaluation results, and promotion decisions are explicit/versioned,
- the first V7 path can generate, validate, and promote a module artifact while preserving the current CLI contract.

## Explicit exclusions for the active wave

These remain important but are not the active strategic wave:
- live predictive ranking, candidate pruning, or promotion blocking until a later contract explicitly widens authority beyond governance-only evaluation receipts,
- treating repeated governance-only receipt outcomes as de facto live policy authority before an explicit human-governed promotion step exists,
- reopening the completed SG3 scope-snapshot chain without a new contract, surfaced regression, or operator-directed follow-on,
- older provider/runtime and Oracle follow-ons (`AK-224`, `AK-235`–`AK-239`) that are not selected by the current strategic ranking.
