---
summary: "Top strategic goals selected from the vision."
read_when:
  - "When planning quarters"
  - "When deciding which major bet is active now versus next"
---

# Strategic Goals

Active strategic goal: `SG2`
Next strategic goal: `TBD`

## Strategic ranking (Eisenhower-3D)

| ID | Status | Goal | Importance | Urgency | Difficulty | Why this is the right wave now |
| --- | --- | --- | --- | --- | --- | --- |
| `SG1` | complete | Deliver a V9-compatible synthesis core and ship V7 module synthesis through the existing `module-gen` surface. | 5 | 5 | 4 | This wave is now materially complete: `module-gen` runs through the synthesis runtime, ranked candidate selection/promotion receipts exist, and the ranked path is hardened with deterministic regression corpus + CI coverage. |
| `SG2` | active | Turn receipts, replay, and Oracle evidence into the predictive/governance substrate for V8 and V9. | 5 | 4 | 4 | With the V7-ranked runtime now explicit and guarded by regression gates, the next highest-leverage move is to define how synthesis retrieves structured evidence from receipts/replay/Oracle history before attempting predictive ranking or governed strategy evolution. |

## Strategic definitions of done

### `SG1` — V9-compatible synthesis core, V7-first delivery
Done when:
- `module-gen` runs through a synthesis runtime rather than an ad-hoc template-only service path,
- synthesis requests, candidate records, evaluation results, and promotion decisions are explicit/versioned,
- the first V7 path can generate, validate, and promote a module artifact while preserving the current CLI contract.

### `SG2` — Evidence substrate for V8/V9
Done when:
- receipts, replay outputs, and Oracle history can be retrieved as structured evidence for synthesis decisions,
- DSPx can pre-rank or prune candidate work with evidence-backed priors,
- strategy/policy changes can be evaluated and governed instead of silently changing via prompt drift.

## Explicit exclusions for this wave

These remain important but are not the active strategic wave:
- exact-fidelity `dspy-template-adapter` critical-path integration,
- more provider-family expansion for its own sake,
- app-first features that would weaken the core/app boundary,
- V9-style self-evolving behavior before V7 contracts and V8 evidence exist.
