---
summary: "Tactical goals for the single active strategic goal."
read_when:
  - "When planning sprints/weeks"
  - "When selecting the current active execution wave"
---

# Tactical Goals

Active strategic goal: `SG1` — deliver a V9-compatible synthesis core and ship V7 module synthesis through `module-gen`.

Active tactical goal: `TG2`
Next tactical goal: `TG3`

## Tactical goals for `SG1`

### `TG1` — Freeze the synthesis target architecture in dated, referenceable docs
- Status: complete
- Definition of done: `docs/project/vision.md`, `docs/VISION.md`, strategic/tactical docs, and a dated ADR all agree on the V7/V8/V9 architecture horizon and the "V9-compatible core, V7-first implementation" posture.

### `TG2` — Land a V9-compatible module synthesis runtime MVP inside the existing `module-gen` surface
- Status: active
- Definition of done: DSPx has explicit synthesis contracts (request/IR/candidate/evaluation/policy/promotion), a runtime shell/workspace boundary, and a feature-preserving one-candidate module synthesis path that can become the base for V7 selection later.

### `TG3` — Extend the MVP to true V7 candidate selection and evidence-backed promotion
- Status: next
- Definition of done: `module-gen` can generate multiple candidates, run the agreed evaluation stack, rank them through a named policy, and promote the winning artifact with receipts explaining the choice.

### `TG4` — Harden the module synthesis pipeline with quality gates and corpus coverage
- Status: queued
- Definition of done: module synthesis has deterministic regression tests, validation/quality telemetry, and CI gates analogous to the native signature pipeline.

## Defer/until-later notes

The following are intentionally not tactical goals for the current strategic wave:
- V8 predictive ranking from Oracle priors,
- V9 governed strategy/policy evolution,
- further provider-runtime expansion beyond what the synthesis MVP needs,
- exact-fidelity template-adapter work in the critical path.
