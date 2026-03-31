---
summary: "Tactical goals for the single active strategic goal."
read_when:
  - "When planning sprints/weeks"
  - "When selecting the current active execution wave"
---

# Tactical Goals

Active strategic goal: `SG2` — turn receipts, replay, and Oracle evidence into the predictive/governance substrate for V8 and V9.

Active tactical goal: `TBD`
Next tactical goal: `unmaterialized`

## Upcoming tactical goals for `SG2`

No next tactical goal is pinned yet.
`TG23` is complete, and the repo should not guess the post-receipt tactical wave until the truthful next contract or implementation slice exists. `AK-548` is now complete, so SG3 task-scope migration is unblocked as a separate next-wave chain when explicitly selected.

## Recently completed tactical goals for `SG2`

- `TG23` — materialized the first governance-only ranking/promotion evaluation receipts on `synthesis_diagnostics.governed_policy_evaluations`, evaluating named bounded variants against shadow predictive-ranking evidence plus trusted current metadata without changing live V7 ranking, tie-breaking, pruning, or promotion behavior.
- `TG22` — froze the first governed policy-evaluation contract that consumes shadow predictive-ranking evidence as `docs/adr/20260330-synthesis-evidence-governed-policy-evaluation-contract-v1.md`, defining the bounded evaluation inputs, variant surfaces, receipt payload, and promotion-authority limits before the first governed receipt wave.
- `TG21` — materialized the read-only shadow predictive-ranking advisory on live module metadata and persisted receipts, comparing a bounded prior-aware shadow preference against the trusted V7 winner without changing live ranking, tie-breaking, pruning, or promotion behavior.
- `TG20` — froze the first offline/shadow predictive-ranking contract after the read-only counterfactual advisory.
- `TG19` — materialized the read-only candidate-prior counterfactual advisory on live module metadata and persisted receipts before any predictive-ranking authority widened.
- `TG18` — froze the next post-readiness SG2 contract as the read-only candidate-prior counterfactual advisory contract.
- `TG17` — materialized the read-only candidate-prior readiness advisory on live metadata and persisted receipts.
- `TG16` — froze the next post-divergence SG2 contract as the read-only candidate-prior readiness advisory contract.
- `TG15` — materialized the read-only candidate-prior divergence explanation on live metadata and persisted receipts.
- `TG14` — froze the next post-audit SG2 contract as the read-only candidate-prior divergence-explanation contract.
- `TG13` — materialized the read-only post-selection candidate-prior audit on live metadata and persisted receipts.
- `TG12` — froze the first post-selection candidate-prior audit contract.
- `TG11` — materialized read-only candidate winner priors for the current deterministic `module-gen` variants.
- `TG10` — froze the first evidence-backed candidate-prior contract before predictive ranking.
- `TG9` — materialized the first read-only historical convergence advisory from SG2 evidence.
- `TG8` — froze the first post-diagnostics SG2 contract before predictive ranking began.
- `TG7` — threaded the v1 evidence bundle into module-synthesis diagnostics.
- `TG6` — materialized the v1 evidence retrieval bundle for ranked module synthesis.
- `TG5` — froze the first evidence-substrate contract for ranked synthesis.

## Recently completed tactical goals for `SG1`

- `TG1` — froze the synthesis target architecture in dated, referenceable docs.
- `TG2` — landed a V9-compatible module synthesis runtime MVP inside the existing `module-gen` surface.
- `TG3` — extended the MVP to true V7 candidate selection and evidence-backed promotion.
- `TG4` — hardened the module synthesis pipeline with quality gates and corpus coverage.

## Defer/until-later notes

The following remain intentionally out of the active tactical wave until the next SG2 tactical wave is truthfully materialized:
- live predictive ranking from Oracle priors,
- live candidate pruning or promotion blocking from prior-backed signals,
- strategy/policy mutation without explicit governed evaluation receipts,
- widening authority beyond governance-only receipt emission before a later contract explicitly promotes a named variant into live policy,
- decomposing the post-`TG23` tactical wave early just to keep the queue non-empty,
- auto-promoting the SG3 AK-native scope-snapshot chain just because `AK-548` landed, instead of selecting `AK-550`/`AK-551` explicitly when that wave is actually chosen.
