---
summary: "Tactical goals for the single active strategic goal."
read_when:
  - "When planning sprints/weeks"
  - "When selecting the current active execution wave"
---

# Tactical Goals

Active strategic goal: `SG2` — turn receipts, replay, and Oracle evidence into the predictive/governance substrate for V8 and V9.

Active tactical goal: `TG10`
Next tactical goal: `TBD`

## Recently completed tactical goals for `SG1`

### `TG1` — Freeze the synthesis target architecture in dated, referenceable docs
- Status: complete
- Definition of done: `docs/project/vision.md`, `docs/VISION.md`, strategic/tactical docs, and a dated ADR all agree on the V7/V8/V9 architecture horizon and the "V9-compatible core, V7-first implementation" posture.

### `TG2` — Land a V9-compatible module synthesis runtime MVP inside the existing `module-gen` surface
- Status: complete
- Definition of done: DSPx has explicit synthesis contracts (request/IR/candidate/evaluation/policy/promotion), a runtime shell/workspace boundary, and a feature-preserving one-candidate module synthesis path that can become the base for V7 selection later.

### `TG3` — Extend the MVP to true V7 candidate selection and evidence-backed promotion
- Status: complete
- Definition of done: `module-gen` can generate multiple candidates, run the agreed evaluation stack, rank them through a named policy, and promote the winning artifact with receipts explaining the choice.

### `TG4` — Harden the module synthesis pipeline with quality gates and corpus coverage
- Status: complete
- Definition of done: module synthesis has deterministic regression tests, validation/quality telemetry, and CI gates analogous to the native signature pipeline.

## Tactical goals for `SG2`

### `TG5` — Freeze the first evidence-substrate contract for ranked synthesis
- Status: complete
- Definition of done: DSPx has a dated, referenceable contract for which receipts, replay outputs, and Oracle surfaces ranked synthesis will retrieve first, and the first AK-backed execution slice is aligned to that contract.
- Reference: `docs/adr/20260323-synthesis-evidence-retrieval-v1.md`

### `TG6` — Materialize the v1 evidence retrieval bundle for ranked module synthesis
- Status: complete
- Definition of done: DSPx can retrieve contract-shaped evidence bundles for `module-gen` requests by combining exact-match synthesis receipts, replay-health facts, and constrained Oracle neighbors without changing selection behavior yet.
- Implementation reference: `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`

### `TG7` — Thread the v1 evidence bundle into module-synthesis diagnostics before ranking changes
- Status: complete
- Definition of done: `module-gen` can surface the retrieved evidence bundle through bounded runtime diagnostics/receipts so later V8 work consumes explicit evidence artifacts instead of rediscovering history ad hoc.
- Implementation reference: `packages/dspx-core/src/dspx/services/module_service.py`, `packages/dspx-core/src/dspx/cli/commands/module.py`

### `TG8` — Freeze the first post-diagnostics SG2 contract before predictive ranking begins
- Status: complete
- Definition of done: DSPx has a dated, referenceable contract for the first evidence-consuming behavior after `TG7`, plus an AK-aligned next execution slice, while keeping predictive ranking and policy mutation out of implementation scope until that contract exists.
- Reference: `docs/adr/20260324-synthesis-evidence-history-advisory-v1.md`

### `TG9` — Materialize a read-only historical convergence advisory from SG2 evidence
- Status: complete
- Definition of done: `module-gen` emits a stable advisory that classifies the selected artifact against healthy exact-match history (`no_history`, `degraded_history_only`, `convergent_with_positive_history`, or `divergent_from_positive_history`) on both runtime metadata and persisted receipts, while leaving ranking/promotion behavior unchanged.
- Contract reference: `docs/adr/20260324-synthesis-evidence-history-advisory-v1.md`
- Implementation reference: `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`, `packages/dspx-core/src/dspx/services/module_service.py`

### `TG10` — Freeze the first evidence-backed candidate-prior contract before predictive ranking
- Status: active
- Definition of done: DSPx has a dated, referenceable contract for how SG2 evidence may inform future candidate priors or pruning after `TG9`, including authority order, replay-health boundaries, explicit non-goals, and the next AK-aligned implementation slice, while leaving runtime ranking behavior unchanged until that contract exists.
- Next slice reference: `AK-356`

## Defer/until-later notes

The following are intentionally not tactical goals for the current strategic wave:
- V8 predictive ranking from Oracle priors,
- V9 governed strategy/policy evolution,
- further provider-runtime expansion beyond what the synthesis MVP needs,
- exact-fidelity template-adapter work in the critical path.
