---
summary: "Active operating-plan layer for the current tactical goal."
read_when:
  - "When choosing the next one-context-window slice"
  - "When mapping the active tactical goal to authoritative AK tasks"
---

# Operational Goals

Active tactical goal: `TG21`

Authoritative live execution: Agent Kernel tasks for repo `/home/tryinget/ai-society/softwareco/owned/dspx`

## Active operating slices

1. `AK-562` — emit the ADR-backed read-only shadow predictive-ranking advisory on live module metadata and persisted receipts, using already-emitted SG2 surfaces plus trusted current ranked/evaluation metadata while leaving live V7 ranking, tie-breaking, pruning, and promotion unchanged.
   - Status: ready after `AK-561`
   - Deliverables: contract-shaped advisory payload, attachment on live `synthesis_diagnostics` + persisted receipt metadata, and focused tests/docs aligned to the new ADR.

## Recently completed in this wave

- `AK-561` — froze the next SG2 contract after the read-only candidate-prior counterfactual advisory as a bounded offline/shadow predictive-ranking advisory and aligned the next implementation slice to `AK-562`.
- `AK-559` — fixed repeated local OpenAPI schema ref resolution so reused sibling properties and combinator branches no longer collapse into unconstrained schemas, added regressions for the surfaced false-pass cases, and refreshed the aligned docs/handoff artifacts.
- `AK-558` — made task-scope mode selection deterministic for dirty vs clean repos so `verify-fast`/`verify-full` cover active working-tree slices, hardened OpenAPI `oneOf|anyOf` ref resolution plus exclusivity semantics, and refreshed the aligned docs/handoff artifacts.
- `AK-556` — reconfirmed the repo-scoped AK ready queue was still empty after `AK-534`, refreshed the idle-state handoff/operating-plan artifacts at the current branch `HEAD`, and returned the repo to a no-ready-slice state.
- `AK-487` / `AK-493` — hardened the candidate-prior counterfactual advisory so SG2 surface drift now fails closed without widening evidence authority or changing V7 behavior.

## Notes

- `TG20` is complete, `TG21` is active, and `AK-562` now gives the active tactical goal live backlog coverage.
- Do not start live predictive ranking, candidate pruning, promotion blocking, or strategy/policy mutation until a later contract explicitly widens authority beyond the new shadow predictive-ranking advisory.
- `AK-549`–`AK-551` remain the next strategic-wave AK-native task-scope migration, but they stay out of the active operating plan because `AK-549` is blocked on cross-repo `AK-548`.
- Older deferred/provider/runtime follow-ons (`AK-224`, `AK-235`–`AK-239`) remain non-active backlog and were intentionally not resumed in this SG2 wave.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Claimed tasks that intend to pass `just verify-full` still need an attested scope manifest under `governance/task-scopes/AK-<id>.json`, and current-slice working-tree validation should run explicitly via `just task-scope-check task_id=<AK-ID> mode=working-tree` before commit.
