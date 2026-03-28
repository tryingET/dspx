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

1. `AK-317` — **Remove repo-local `rocs_cli` GitLab baseline-resolution compatibility path**
   - Status: ready
   - Deliverable: remove the repo-local compatibility path now that the SG2 counterfactual-advisory slice is complete and no next SG2 contract is pinned yet.

## Recently completed in this wave

- `AK-473` — materialized the ADR-backed read-only candidate-prior counterfactual advisory on live module metadata and persisted receipts using already-emitted SG2 surfaces plus trusted current-run comparison metadata, while leaving V7 ranking/promotion behavior unchanged.
- `AK-466` — froze the next SG2 contract after the read-only candidate-prior readiness advisory as a read-only counterfactual advisory and aligned the next implementation slice to `AK-473`.
- `AK-462` — materialized the ADR-backed read-only candidate-prior readiness advisory on live module metadata and persisted receipts by rolling up persisted exact-match candidate-prior audit/divergence-explanation outcomes, while leaving V7 ranking/promotion behavior unchanged.
- `AK-459` — froze the next SG2 contract after the read-only candidate-prior divergence explanation as a receipt-backed readiness advisory and aligned the next implementation slice to `AK-462`.
- `AK-441` — materialized the ADR-backed read-only candidate-prior divergence explanation on live module metadata and persisted receipts using trusted current ranked/evaluation metadata, while leaving V7 ranking/promotion behavior unchanged.

- `AK-386` — froze the next SG2 contract after the post-selection candidate-prior audit as a read-only divergence explanation, explicitly reusing fail-closed rank truth from `AK-388`/`AK-431`, and aligned the next implementation slice to `AK-441`.
- `AK-436` — hardened generated-code validation and server trust boundaries by isolating smoke checks, failing closed on auth token-file misconfiguration, hashing/bounding rate-limit token identity, and preventing promotion of non-selected candidates without widening SG2 evidence authority.
- `AK-431` — made candidate-prior audit rank reporting fail closed when ranked metadata only partially covers audited candidates, so DSPx now omits rank context rather than mixing real and missing order inside the same audit.
- `AK-388` — made candidate-prior audit rank reporting fail closed under metadata drift so DSPx now reports rank only from explicit ranked-candidate metadata and falls back from empty decision-ranked data to valid shell-ranked data.
- `AK-379` — materialized the ADR-backed read-only candidate-prior audit on live module metadata and persisted receipts so DSPx now records how the V7-selected candidate relates to available positive prior support without changing ranking or promotion behavior.
- `AK-378` — froze the next SG2 contract for consuming `candidate_winner_priors` as a post-selection audit of selected-vs-available positive prior support, then aligned the next implementation slice to `AK-379`.
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

- `TG19` is complete; no next SG2 implementation slice is pinned until a later contract freezes the next evidence-authority question, so the repo-scoped ready queue currently falls back to `AK-317`.
- `AK-388`, `AK-431`, and `AK-436` were operator-directed guardrail fixes that hardened runtime trust boundaries without widening evidence authority; `AK-388` and `AK-431` now form part of the fail-closed rank-truth boundary that `AK-441` reused.
- `AK-224` and `AK-235` remain manually deferred because they belong to older/non-active waves and would otherwise leave the ready queue pointing away from the current architecture slice.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Claimed tasks that intend to pass `just verify-full` now need an attested scope manifest under `governance/task-scopes/AK-<id>.json`, and current-slice working-tree validation should run explicitly via `just task-scope-check task_id=<AK-ID> mode=working-tree` before commit.
- Do not start predictive ranking, candidate pruning, promotion blocking, or governed self-evolution implementation until a later contract explicitly widens evidence authority beyond the read-only candidate-prior payload, audit, divergence-explanation, readiness-advisory, and counterfactual-advisory surfaces now attached to runtime metadata and receipts.
