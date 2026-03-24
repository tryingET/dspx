---
summary: "Active operating-plan layer for the current tactical goal."
read_when:
  - "When choosing the next one-context-window slice"
  - "When mapping the active tactical goal to authoritative AK tasks"
---

# Operational Goals

Active tactical goal: `TG8` — freeze the first post-diagnostics SG2 contract before predictive ranking begins.

Authoritative live execution: Agent Kernel tasks for repo `/home/tryinget/ai-society/softwareco/owned/dspx`

## Active operating slices

1. `AK-337` — **Synthesis evidence substrate: define the first post-diagnostics SG2 contract and next execution slice**
   - Status: ready
   - Deliverable: a dated tactical/ADR-level contract that defines the first evidence-consuming behavior after `TG7`, explicitly names non-goals, and aligns the next implementation task without starting predictive ranking yet.

## Recently completed in this wave

- `AK-278` — threaded the v1 module-synthesis evidence bundle into runtime diagnostics and `module-gen` receipts without changing ranked selection behavior.
- `AK-274` — implemented `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`, which retrieves exact-match `module-gen` synthesis receipts, replay-health facts, and constrained Oracle neighbors as the first SG2 evidence bundle.
- `AK-263` — froze the first SG2 evidence contract in a dated ADR, aligned the next implementation slice to that contract, and moved the repo from SG2 planning into the first execution-ready evidence-bundle task.
- `AK-271` — bound runtime module-quality events to the selected candidate artifact hash so receipt integrity now covers the user-visible artifact payload as well as ranking/promotion metadata.
- `AK-266` — added task-scope attestation for claimed slices in `just verify-full`, hardened semantic receipt invariants for module-synthesis quality checks, and connected runtime `module-gen` runs to quality-event logging.
- `AK-260` — hardened the ranked module synthesis runtime with a deterministic regression corpus, module-synthesis quality telemetry, and explicit `just verify-full` CI gating via `module-synthesis-quality-check`.
- `AK-256` — extended `module-gen` from the runtime MVP to true multi-candidate fan-out, ranked evaluation/selection receipts, and explicit winner handoff into the promotion shell.
- `AK-251` — routed `module-gen` through the synthesis runtime single-candidate path, added runtime static/smoke validation, and wrote receipt-linked synthesis evidence for the promoted artifact path.
- `AK-250` — added the module synthesis runtime shell on top of `dspx.synthesis`: persisted strategy metadata, materialized per-candidate scratch workspaces/manifests, and introduced an explicit promotion shell that only promotes the selected output.
- `AK-249` — landed `packages/dspx-core/src/dspx/synthesis/` with `SynthesisRequest`, structured module spec IR, `CandidateRecord`, `EvaluationRecord`, `SelectionPolicy`, and `PromotionDecision`, then wired `module_service` to emit the contract bundle without changing the current `module-gen` surface.

## Notes

- `TG6` and `TG7` are complete; this file now tracks the planning/contract-setting follow-up slice for `TG8`.
- `AK-224` and `AK-235` remain manually deferred because they belong to older/non-active waves and would otherwise leave the ready queue pointing away from the current architecture slice.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Claimed tasks that intend to pass `just verify-full` now need an attested scope manifest under `governance/task-scopes/AK-<id>.json`.
- Do not start predictive ranking or governed self-evolution implementation until `AK-337` (or its successor contract slice) explicitly freezes the next evidence-consuming behavior and keeps the evidence bundle read-only where required.
