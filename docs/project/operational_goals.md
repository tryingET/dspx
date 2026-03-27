---
summary: "Active operating-plan layer for the current tactical goal."
read_when:
  - "When choosing the next one-context-window slice"
  - "When mapping the active tactical goal to authoritative AK tasks"
---

# Operational Goals

Active tactical goal: `TBD`

Authoritative live execution: Agent Kernel tasks for repo `/home/tryinget/ai-society/softwareco/owned/dspx`

## Active operating slices

1. `AK-378` — **Synthesis evidence substrate: define the next SG2 contract for candidate-prior consumption after TG11**
   - Status: ready
   - Deliverable: freeze the next dated SG2 contract / execution slice for how DSPx may inspect or consume the new read-only candidate-prior payload without silently widening authority.

## Recently completed in this wave

- `AK-377` — materialized the ADR-backed read-only candidate winner-prior payload for the current deterministic `module-gen` variants on live metadata and persisted receipts while preserving V7 ranking/promotion behavior.

- `AK-356` — froze the first evidence-backed candidate-prior contract in a dated ADR, limited positive authority to replay-healthy exact-match historical winners, and aligned the next implementation slice to `AK-377`.
- `AK-366` — scoped advisory degradation to exact-match receipt failures so unrelated corrupt receipts no longer downgrade request-local history posture while retrieval diagnostics still surface broader scan damage.
- `AK-357` — hardened advisory evidence resolution so malformed/unavailable history no longer silently collapses into `no_history`, kept diagnostics shape stable on retrieval failure, and aligned default Oracle provenance roots with receipt roots.
- `AK-341` — emitted the ADR-backed historical convergence advisory on live module metadata and persisted receipts while keeping V7 ranking/promotion behavior unchanged.
- `AK-337` — froze the first post-diagnostics SG2 contract in a dated ADR, defined the historical-convergence advisory as the first evidence consumer, and aligned the next implementation slice to `AK-341`.
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

- `TG11` is complete; `AK-378` is now the pinned SG2 planning slice that should freeze the next contract/execution wave for candidate-prior consumption without silently widening authority.
- `AK-224` and `AK-235` remain manually deferred because they belong to older/non-active waves and would otherwise leave the ready queue pointing away from the current architecture slice.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Claimed tasks that intend to pass `just verify-full` now need an attested scope manifest under `governance/task-scopes/AK-<id>.json`.
- Do not start predictive ranking, candidate pruning, or governed self-evolution implementation until a later contract explicitly widens evidence authority beyond the read-only candidate-prior payload now attached to runtime metadata and receipts.
