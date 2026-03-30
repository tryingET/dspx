---
summary: "Top strategic goals selected from the vision."
read_when:
  - "When planning quarters"
  - "When deciding which major bet is active now versus next"
---

# Strategic Goals

Active strategic goal: `SG2`
Next strategic goal: `SG3`

## Strategic ranking (Eisenhower-3D)

| ID | Status | Goal | Importance | Urgency | Difficulty | Why this is the right wave now |
| --- | --- | --- | --- | --- | --- | --- |
| `SG2` | active | Turn receipts, replay, and Oracle evidence into the predictive/governance substrate for V8 and V9. | 5 | 5 | 4 | DSPx has completed the read-only SG2 evidence chain through candidate-prior counterfactual advisories, but it still lacks the next bounded step: a shadow predictive-ranking contract that can test evidence-aware behavior without changing live V7 ranking or promotion. |
| `SG3` | next | Replace hand-authored task-scope manifests with AK-native scope snapshots across validation and handoff. | 4 | 4 | 3 | Repo-local tasks `AK-549`–`AK-551` already capture this work and it directly strengthens reproducibility/governance, but the first repo-local slice is blocked on cross-repo fixture work `AK-548`, so it stays next rather than active. |

## Strategic definitions of done

### `SG2` — Evidence substrate for V8/V9
Done when:
- DSPx can retrieve and consume structured receipt/replay/Oracle evidence through bounded shadow predictive-ranking or equivalent evidence-aware comparisons without mutating live V7 behavior by accident,
- evidence-backed candidate priors can be evaluated under explicit contracts before any live pre-ranking/pruning is authorized,
- strategy/policy variants can be evaluated and governed with explicit receipts instead of silent prompt or policy drift.

### `SG3` — AK-native scope snapshots for repo validation/handoff
Done when:
- repo validation derives task scope from AK-native snapshots instead of hand-authored manifest bookkeeping,
- `next_session_prompt.md`, workflow docs, and verification commands no longer depend on manual task-scope manifest coupling,
- regression coverage proves the AK-native scope flow across dirty working-tree and committed `HEAD` modes.

## Recently completed strategic goal

### `SG1` — V9-compatible synthesis core, V7-first delivery
Status: complete

Done when:
- `module-gen` runs through a synthesis runtime rather than an ad-hoc template-only service path,
- synthesis requests, candidate records, evaluation results, and promotion decisions are explicit/versioned,
- the first V7 path can generate, validate, and promote a module artifact while preserving the current CLI contract.

## Explicit exclusions for the active wave

These remain important but are not the active strategic wave:
- live predictive ranking, candidate pruning, or promotion blocking before the shadow predictive-ranking contract is frozen and materialized,
- resuming blocked SG3 scope-snapshot tasks before `AK-548` unblocks the repo-local chain,
- older provider/runtime and Oracle follow-ons (`AK-224`, `AK-235`–`AK-239`) that are not selected by the current strategic ranking.
