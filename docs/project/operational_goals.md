---
summary: "Active operating-plan layer for the current tactical goal."
read_when:
  - "When choosing the next one-context-window slice"
  - "When mapping the active tactical goal to authoritative AK tasks"
---

# Operational Goals

Active tactical goal: `TG3` — extend the MVP to true V7 candidate selection and evidence-backed promotion.

Authoritative live execution: Agent Kernel tasks for repo `/home/tryinget/ai-society/softwareco/owned/dspx`

## Active operating slices

1. `AK-256` — **Module synthesis: add multi-candidate fan-out and ranked selection receipts on top of the runtime MVP**
   - Status: ready
   - Deliverable: the synthesis runtime can materialize more than one module candidate, record ranked evaluation/selection receipts under a named policy, and hand the winning candidate to the existing explicit promotion shell.

## Recently completed in this wave

- `AK-251` — routed `module-gen` through the synthesis runtime single-candidate path, added runtime static/smoke validation, and wrote receipt-linked synthesis evidence for the promoted artifact path.
- `AK-250` — added the module synthesis runtime shell on top of `dspx.synthesis`: persisted strategy metadata, materialized per-candidate scratch workspaces/manifests, and introduced an explicit promotion shell that only promotes the selected output.
- `AK-249` — landed `packages/dspx-core/src/dspx/synthesis/` with `SynthesisRequest`, structured module spec IR, `CandidateRecord`, `EvaluationRecord`, `SelectionPolicy`, and `PromotionDecision`, then wired `module_service` to emit the contract bundle without changing the current `module-gen` surface.

## Notes

- `TG2` is materially complete; keep this file focused on `TG3` follow-on work only.
- `AK-224` and `AK-235` were manually deferred because they belong to older/non-active waves and would otherwise leave the ready queue pointing away from the current architecture slice.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Promote `TG4` only after the multi-candidate selection/promotion path under `TG3` is materially complete.
