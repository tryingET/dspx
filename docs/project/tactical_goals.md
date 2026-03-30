---
summary: "Tactical goals for the single active strategic goal."
read_when:
  - "When planning sprints/weeks"
  - "When selecting the current active execution wave"
---

# Tactical Goals

Active strategic goal: `SG2` — turn receipts, replay, and Oracle evidence into the predictive/governance substrate for V8 and V9.

Active tactical goal: `TG21`
Next tactical goal: `TG22`

## Active and upcoming tactical goals for `SG2`

### `TG20` — Freeze the first offline/shadow predictive-ranking contract after the read-only counterfactual advisory
- Status: complete
- Definition of done: DSPx has a dated ADR defining the first read-only shadow predictive-ranking surface, the authority order it may use, and the next AK-backed implementation slice while keeping live V7 ranking, tie-breaking, pruning, and promotion unchanged.
- Reference: `docs/adr/20260329-synthesis-evidence-shadow-predictive-ranking-advisory-v1.md`
- Execution reference: `AK-561`

### `TG21` — Materialize a read-only shadow predictive-ranking advisory for module-gen outcomes
- Status: active
- Definition of done: `module-gen` emits a contract-shaped shadow predictive-ranking advisory on live metadata and persisted receipts that compares a bounded prior-aware shadow preference against the trusted V7 winner without changing live ranking, tie-breaking, pruning, or promotion behavior.
- Contract reference: `docs/adr/20260329-synthesis-evidence-shadow-predictive-ranking-advisory-v1.md`
- Execution reference: `AK-562`

### `TG22` — Freeze the first governed policy-evaluation contract that consumes shadow predictive-ranking evidence
- Status: next
- Definition of done: DSPx has a dated, referenceable contract for evaluating candidate-ranking or promotion-policy variants against receipt-backed shadow predictive-ranking evidence under governance, without mutating the live default policy yet.

### `TG23` — Materialize governed policy-evaluation receipts for evidence-aware synthesis variants
- Status: queued
- Definition of done: DSPx can run named strategy/policy variants against bounded shadow/evidence surfaces and emit governance receipts that support explicit promotion or rejection, while the default live policy remains stable until governance approves change.

## Recently completed tactical goals for `SG2`

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

The following remain intentionally out of the active tactical wave until `TG21` and `TG22` advance:
- live predictive ranking from Oracle priors,
- live candidate pruning or promotion blocking from prior-backed signals,
- strategy/policy mutation without explicit governed evaluation receipts,
- SG3 AK-native scope-snapshot execution while `AK-548` still blocks `AK-549`.
