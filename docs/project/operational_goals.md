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

1. `AK-251` — **Module-gen: route through the synthesis runtime single-candidate path with static/smoke validation and receipts**
   - Status: ready
   - Deliverable: existing `module-gen` CLI/service enters the synthesis runtime, preserves current UX, and records candidate/evaluation/promotion evidence for the MVP path.

## Recently completed in this wave

- `AK-250` — added the module synthesis runtime shell on top of `dspx.synthesis`: persisted strategy metadata, materialized per-candidate scratch workspaces/manifests, and introduced an explicit promotion shell that only promotes the selected output.
- `AK-249` — landed `packages/dspx-core/src/dspx/synthesis/` with `SynthesisRequest`, structured module spec IR, `CandidateRecord`, `EvaluationRecord`, `SelectionPolicy`, and `PromotionDecision`, then wired `module_service` to emit the contract bundle without changing the current `module-gen` surface.

## Notes

- This file is the operating-plan layer for the current tactical goal; it should stay focused on `TG2` only.
- `AK-224` and `AK-235` were manually deferred because they belong to older/non-active waves and would otherwise leave the ready queue pointing away from the current architecture slice.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Promote `TG3` only after `AK-249` through `AK-251` are materially complete.
