---
summary: "Active operating-plan layer for the current tactical goal."
read_when:
  - "When choosing the next one-context-window slice"
  - "When mapping the active tactical goal to authoritative AK tasks"
---

# Operational Goals

Active tactical goal: `TG2` — land a V9-compatible module synthesis runtime MVP inside the existing `module-gen` surface.

Authoritative live execution: Agent Kernel tasks for repo `/home/tryinget/ai-society/softwareco/owned/dspx`

## Active operating slices

1. `AK-249` — **Synthesis core: add V9-compatible request/IR/candidate/evaluation/policy/promotion contracts for module generation**
   - Status: ready
   - Deliverable: first synthesis package/contracts for `SynthesisRequest`, structured module spec IR, `CandidateRecord`, `EvaluationRecord`, `SelectionPolicy`, and `PromotionDecision`.

2. `AK-250` — **Module synthesis runtime: add strategy metadata, candidate workspace, and promotion shell**
   - Status: pending after `AK-249`
   - Deliverable: runtime/workspace boundary that materializes candidates in scratch space, preserves strategy/version metadata, and promotes only selected output.

3. `AK-251` — **Module-gen: route through the synthesis runtime single-candidate path with static/smoke validation and receipts**
   - Status: pending after `AK-250`
   - Deliverable: existing `module-gen` CLI/service enters the synthesis runtime, preserves current UX, and records candidate/evaluation/promotion evidence for the MVP path.

## Notes

- This file is the operating-plan layer for the current tactical goal; it should stay focused on `TG2` only.
- `AK-224` and `AK-235` were manually deferred because they belong to older/non-active waves and would otherwise leave the ready queue pointing away from the current architecture slice.
- Promote `TG3` only after `AK-249` through `AK-251` are materially complete.
