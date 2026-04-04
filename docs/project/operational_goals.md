---
summary: "Active operating-plan layer for the current tactical goal."
read_when:
  - "When choosing the next one-context-window slice"
  - "When mapping the active tactical goal to authoritative AK tasks"
---

# Operational Goals

Active tactical goal: `TG25`

Authoritative live execution: Agent Kernel tasks for repo `/home/tryinget/ai-society/softwareco/owned/dspx`

## Active operating slices

- no repo-scoped implementation slice is currently ready; wait for operator direction or the first truthful `TG25` contract/materialization step.

## Recently completed in this wave

- `AK-729` — landed the operator-directed adversarial TG24 follow-on by making exact-match SG2 receipt validation type-strict, allowing compatible partial/nested local MLflow artifact linkage, moving sync-provider `cwd` isolation into worker-local scope, centralizing OpenAPI numeric `multipleOf` enforcement across params/body/items, preferring PATH `ak` over the broken workspace-core cargo launcher in `./scripts/ak.sh`, exporting `governance/task-scopes/AK-729.snapshot.json`, and extending regressions.
- `AK-709` — tightened SG2 exact-match receipt parsing so malformed historical/governed-policy surfaces fail closed, tightened MLflow explain linkage by requiring same-artifact local runs to match expected correlation tags, hardened OpenAPI numeric validation against bool/float/string-integer/non-finite drift, rejected fractional/zero/negative server rate-limit counts, exported `governance/task-scopes/AK-709.snapshot.json`, and extended regressions.
- `AK-708` — hardened multi-provider orchestration by materializing runtime capability aggregation in the CLI/runtime surfaces, preserving request message history across fan-out and DTO-only providers, restoring temporary policy overrides after each run, falling back to mirror isolation when git worktrees would miss dirty changes, force-cleaning hung async losers before isolated workspace cleanup, exporting `governance/task-scopes/AK-708.snapshot.json`, and extending regressions for the new boundary behavior.
- `AK-707` — persisted server-generated signature/module/mermaid artifacts and receipts, enforced confirmation gates across all mutating server endpoints, returned stable artifact references/manifest paths, exported `governance/task-scopes/AK-707.snapshot.json`, and covered graceful persistence boundaries with server regressions plus `docs/SERVER.md` updates.
- `AK-646` — closed the remaining standardized-Justfile rollout gaps by moving the read-only verification recipes onto `uv run --no-sync`, making `just test`/`just replay-provenance-check`/`just monorepo-check`/`just verify-full` keep `uv.lock` clean again, and aligning the repo docs/checker/tests with the standardized outer surface.
- `AK-645` — hardened the standardized Justfile rollout by making `just doctor` and `just run` side-effect-free via `uv run --no-sync`, adding a zero-arg `just run` help fallback, and upgrading the workflow-contract checker/tests to validate target bodies plus clean-runtime behavior instead of raw substring presence.
- `AK-615` — audited DSPx's existing `Justfile` against the standardized owned-lane contract, added the missing `help`/`check`/`ci`/`doctor`/`run` surface as thin wrappers around existing DSPx behavior, documented the intentional no-`dev` omission, and locked the standardized surface into workflow-contract checks.
- `AK-600` — reconfirmed the repo-scoped AK ready queue was still empty after `AK-593`, refreshed the idle-state handoff/operating-plan artifacts at the current branch `HEAD`, and returned the repo to a no-ready-slice state.
- `AK-593` — emitted the first governance-only ranking/promotion evaluation receipts under `synthesis_diagnostics.governed_policy_evaluations`, keeping live V7 ranking, tie-breaking, pruning, and promotion behavior unchanged while extending persisted diagnostics parsing and regression coverage for the new receipt seam.

## Notes

- `TG24` is complete; `TG25` is now the active post-hardening SG2 tactical wave, but no repo-scoped `TG25` implementation slice is pinned yet.
- `AK-729` was an operator-directed adversarial follow-on that repaired hidden TG24 regressions without reopening the broader tactical-wave selection.
- Keep the `AK-707`/`AK-708`/`AK-709` runtime-boundary hardening wave closed unless a surfaced regression or a smaller `TG25` prerequisite explicitly reopens one seam.
- Do not guess the first `TG25` contract/materialization slice just to keep the queue non-empty; wait for operator direction or a truthful AK-ready task.
- Do not start live predictive ranking, candidate pruning, promotion blocking, or strategy/policy mutation now that `TG24` has closed; wait until a later tactical wave explicitly widens authority beyond governance-only receipts.
- Older deferred/provider/runtime follow-ons (`AK-224`, `AK-235`–`AK-239`) remain non-active backlog and were intentionally not resumed in this wave.
- The repo-local AK wrapper now prefers a working PATH `ak` before the broken workspace-core cargo launcher when no override or vendored CLI exists, so default `./scripts/ci/smoke.sh` / `just verify-full` validation should work again on stable-Rust machines without the temporary `AK_BIN=ak` workaround.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Tasks that opt into explicit AK task scope now validate against frozen exports under `governance/task-scopes/AK-<id>.snapshot.json`; brownfield `governance/task-scopes/AK-*.json` files remain validation-only fallback scaffolding, while workflow/handoff binding now relies only on explicit task IDs, AK claims, or changed task-scope artifacts.
- Current-slice working-tree validation should still run explicitly via `just task-scope-check <AK-ID> working-tree auto` before commit.
