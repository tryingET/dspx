---
summary: "Active operating-plan layer for the current tactical goal."
read_when:
  - "When choosing the next one-context-window slice"
  - "When mapping the active tactical goal to authoritative AK tasks"
---

# Operational Goals

Active tactical goal: `TG24`

Authoritative live execution: Agent Kernel tasks for repo `/home/tryinget/ai-society/softwareco/owned/dspx`

## Active operating slices

- `AK-708` (ready) — harden multi-provider orchestration with dynamic capability aggregation, request-message preservation, policy override restoration, dirty-worktree-safe git-worktree isolation, and hung-loser cleanup.
- `AK-709` (blocked on `AK-708`) — tighten SG2 receipt parsing, MLflow explain artifact matching, OpenAPI numeric strictness, rate-limit token parsing, and adjacent regression coverage.

## Recently completed in this wave

- `AK-707` — persisted server-generated signature/module/mermaid artifacts and receipts, enforced confirmation gates across all mutating server endpoints, returned stable artifact references/manifest paths, exported `governance/task-scopes/AK-707.snapshot.json`, and covered graceful persistence boundaries with server regressions plus `docs/SERVER.md` updates.
- `AK-646` — closed the remaining standardized-Justfile rollout gaps by moving the read-only verification recipes onto `uv run --no-sync`, making `just test`/`just replay-provenance-check`/`just monorepo-check`/`just verify-full` keep `uv.lock` clean again, and aligning the repo docs/checker/tests with the standardized outer surface.
- `AK-645` — hardened the standardized Justfile rollout by making `just doctor` and `just run` side-effect-free via `uv run --no-sync`, adding a zero-arg `just run` help fallback, and upgrading the workflow-contract checker/tests to validate target bodies plus clean-runtime behavior instead of raw substring presence.
- `AK-615` — audited DSPx's existing `Justfile` against the standardized owned-lane contract, added the missing `help`/`check`/`ci`/`doctor`/`run` surface as thin wrappers around existing DSPx behavior, documented the intentional no-`dev` omission, and locked the standardized surface into workflow-contract checks.
- `AK-600` — reconfirmed the repo-scoped AK ready queue was still empty after `AK-593`, refreshed the idle-state handoff/operating-plan artifacts at the current branch `HEAD`, and returned the repo to a no-ready-slice state.
- `AK-593` — emitted the first governance-only ranking/promotion evaluation receipts under `synthesis_diagnostics.governed_policy_evaluations`, keeping live V7 ranking, tie-breaking, pruning, and promotion behavior unchanged while extending persisted diagnostics parsing and regression coverage for the new receipt seam.

## Notes

- `TG24` remains the active post-`TG23` tactical wave until the multi-provider/runtime and boundary-invariant follow-ons land.
- `AK-708` is the single current ready slice; claim it before editing docs or code.
- Keep `AK-708` bounded to multi-provider orchestration, dynamic capability aggregation, request/policy isolation, dirty-worktree-safe isolation, and loser cleanup; leave parser/strictness work to `AK-709` unless strict dependency pressure forces a narrower shared fix.
- `AK-707` exported a repo-default AK snapshot at `governance/task-scopes/AK-707.snapshot.json`, so `just verify-full` can bind deterministically without reintroducing hand-authored manifest coupling.
- `TG25` remains next; do not jump to the governance-to-live promotion contract until `TG24` is materially complete.
- Do not start live predictive ranking, candidate pruning, promotion blocking, or strategy/policy mutation now that `AK-593` has landed; wait until a later tactical wave explicitly widens authority beyond governance-only receipts.
- Older deferred/provider/runtime follow-ons (`AK-224`, `AK-235`–`AK-239`) remain non-active backlog and were intentionally not resumed in this wave.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Tasks that opt into explicit AK task scope now validate against frozen exports under `governance/task-scopes/AK-<id>.snapshot.json`; brownfield `governance/task-scopes/AK-*.json` files remain validation-only fallback scaffolding, while workflow/handoff binding now relies only on explicit task IDs, AK claims, or changed task-scope artifacts.
- Current-slice working-tree validation should still run explicitly via `just task-scope-check task_id=<AK-ID> mode=working-tree` before commit.
