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

- No repo-scoped implementation slice is currently pinned. The repo-scoped ready queue is empty again until the next truthful post-`TG23` contract/materialization step is created.

## Recently completed in this wave

- `AK-593` — emitted the first governance-only ranking/promotion evaluation receipts under `synthesis_diagnostics.governed_policy_evaluations`, keeping live V7 ranking, tie-breaking, pruning, and promotion behavior unchanged while extending persisted diagnostics parsing and regression coverage for the new receipt seam.
- `AK-578` — froze the ADR-backed first governed policy-evaluation contract after the read-only shadow predictive-ranking advisory, created `AK-593` as the next truthful repo-local implementation slice, and refreshed the aligned docs/handoff artifacts without widening live V7 authority.
- `AK-577` — refreshed the SG2 direction stack after `AK-562`, promoted `TG22` to the active tactical goal, and materialized `AK-578` as the next ready repo-local slice instead of treating the empty ready queue as repo completion.
- `AK-562` — materialized the ADR-backed read-only shadow predictive-ranking advisory on live module metadata and persisted receipts, using already-emitted SG2 surfaces plus trusted current ranked/evaluation metadata while leaving live V7 ranking, tie-breaking, pruning, and promotion unchanged.
- `AK-570` — added `just show-dspy-lm-auth-route` so operators can prove the active import path plus the auth-backed resolve/health route in one command, and documented that helper without displacing active slice `AK-562`.
- `AK-567` — documented how to verify that DSPx is actually using the Pi auth-backed `dspy-lm-auth` route, including the default `~/.pi/agent/auth.json` path, the resolve/health probe checks, and the local-vs-auth-backed split in mixed-provider runs, without displacing active slice `AK-562`.
- `AK-564` — added a repo-local `just link-dspy-lm-auth` helper, documented the workspace contrib checkout as the canonical editable `dspy-lm-auth` source, tightened the provider import guidance, and verified DSPx now resolves `dspy_lm_auth` from `~/ai-society/softwareco/contrib/dspy-lm-auth` without displacing active slice `AK-562`.
- `AK-561` — froze the next SG2 contract after the read-only candidate-prior counterfactual advisory as a bounded offline/shadow predictive-ranking advisory and aligned the next implementation slice to `AK-562`.
- `AK-559` — fixed repeated local OpenAPI schema ref resolution so reused sibling properties and combinator branches no longer collapse into unconstrained schemas, added regressions for the surfaced false-pass cases, and refreshed the aligned docs/handoff artifacts.
- `AK-558` — made task-scope mode selection deterministic for dirty vs clean repos so `verify-fast`/`verify-full` cover active working-tree slices, hardened OpenAPI `oneOf|anyOf` ref resolution plus exclusivity semantics, and refreshed the aligned docs/handoff artifacts.
- `AK-556` — reconfirmed the repo-scoped AK ready queue was still empty after `AK-534`, refreshed the idle-state handoff/operating-plan artifacts at the current branch `HEAD`, and returned the repo to a no-ready-slice state.
- `AK-487` / `AK-493` — hardened the candidate-prior counterfactual advisory so SG2 surface drift now fails closed without widening evidence authority or changing V7 behavior.

## Notes

- `TG23` is complete; no next SG2 implementation slice is pinned yet, so the repo-scoped ready queue is empty again until the next truthful post-`TG23` contract/materialization step is created.
- `TG22` is complete; do not materialize the post-`TG23` tactical wave until the first governed receipt seam reveals the truthful next contract or follow-on slice.
- `TG21` is complete; the empty post-`AK-562` ready queue was a decomposition gap rather than evidence that SG2 repo-local work was finished.
- `AK-570` was an operator-directed provider-runtime helper/documentation slice; it collapsed the route proof into one stable command without replacing the active SG2 implementation slice.
- `AK-567` was an operator-directed provider-runtime documentation slice; it made the auth-store routing proof explicit for operators without replacing the active SG2 implementation slice.
- `AK-564` was an operator-directed provider-runtime/workflow slice; it fixed local editable import resolution for `dspy-lm-auth` but did not replace the active SG2 implementation slice.
- Do not start live predictive ranking, candidate pruning, promotion blocking, or strategy/policy mutation now that `AK-593` has landed; wait until a later tactical wave explicitly widens authority beyond governance-only receipts.
- `AK-549`–`AK-551` remain the next strategic-wave AK-native task-scope migration, but they stay out of the active operating plan because `AK-549` is blocked on cross-repo `AK-548`.
- Older deferred/provider/runtime follow-ons (`AK-224`, `AK-235`–`AK-239`) remain non-active backlog and were intentionally not resumed in this SG2 wave.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Claimed tasks that intend to pass `just verify-full` still need an attested scope manifest under `governance/task-scopes/AK-<id>.json`, and current-slice working-tree validation should run explicitly via `just task-scope-check task_id=<AK-ID> mode=working-tree` before commit.
