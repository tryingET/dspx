---
summary: "Top strategic goals selected from the vision."
read_when:
  - "When planning quarters"
  - "When deciding which major bet is active now versus next"
---

# Strategic Goals

Active strategic goal: `SG1`
Next strategic goal: `SG2`

## Strategic ranking (Eisenhower-3D)

| ID | Status | Goal | Importance | Urgency | Difficulty | Why this is the right wave now |
| --- | --- | --- | --- | --- | --- | --- |
| `SG1` | active | Deliver a V9-compatible synthesis core and ship V7 module synthesis through the existing `module-gen` surface. | 5 | 5 | 4 | The repo now has provider/runtime proof, replay discipline, and Oracle foundations, but its next architecture step is still implicit. Module generation remains template-first, so the highest-leverage move is to establish the synthesis runtime seam that V7 can ship on and V8/V9 can grow from. |
| `SG2` | next | Turn receipts, replay, and Oracle evidence into the predictive/governance substrate for V8 and V9. | 5 | 3 | 4 | DSPx's unique moat is not generic generation; it is evidence-backed generation. Oracle Phase A/B are already complete and Phase C foundations exist, but predictive ranking and governed self-evolution should land only after the V7 synthesis contracts, evaluation surfaces, and promotion boundaries are real. |

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
