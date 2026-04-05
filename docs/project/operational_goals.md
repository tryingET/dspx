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

- `AK-800` — add request body size limits middleware to the DSPx server.

## Recently completed in this wave

- `AK-799` — flipped DSPx server auth to required-by-default startup semantics, added the explicit local-only `DSPX_AUTH_SKIP_FOR_DEV=1` bypass, updated server docs plus server-facing tests to opt into the bypass only when intended, exported `governance/task-scopes/AK-799.snapshot.json`, and refreshed the checked-in AK projection after completion.
- `AK-798` — replaced contract-expression `eval()` with a tiny AST interpreter over a narrowed helper namespace plus a read-only embedding view, rejected arbitrary method calls / non-allowlisted helpers / arbitrary attribute traversal, added regressions in `tests/test_coordinates_phase_b.py`, exported `governance/task-scopes/AK-798.snapshot.json`, and refreshed the checked-in AK projection after completion.
- `AK-797` — confined `optimize_service._import_program_module()` to trusted program roots (`cwd`, the system temp root, plus `DSPX_TRUSTED_PROGRAM_ROOTS` overrides), added rejection/allowlist regressions in `tests/test_optimize_gepa_stub.py`, exported `governance/task-scopes/AK-797.snapshot.json`, and refreshed the checked-in AK projection after completion.
- `AK-734` — surfaced `mlflow_tag_contract_violation` for contradictory MLflow correlation tags during explain candidate filtering, reconfirmed the existing assignment-style `just task-scope-check task_id=<AK-ID> mode=working-tree` contract without unnecessary doc churn, recorded the completed slice in `governance/task-scopes/AK-734.snapshot.json` + diary/handoff artifacts, and then closed the task after repairing the live AK task-mutation foreign-key blocker.
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

- `TG24` is complete; `TG25` is now an active repo-scoped security hardening queue rather than an empty waiting state.
- `AK-799` is closed; the truthful ready queue now starts at `AK-800`.
- Keep the `AK-799` required-by-default server auth boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-797` trusted-program-root boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-798` narrowed contract-expression boundary closed unless a smaller follow-up explicitly widens the helper/attribute contract.
- `AK-729` was an operator-directed adversarial follow-on that repaired hidden TG24 regressions without reopening the broader tactical-wave selection.
- Keep the `AK-707`/`AK-708`/`AK-709` runtime-boundary hardening wave closed unless a surfaced regression or a smaller `TG25` prerequisite explicitly reopens one seam.
- Do not start live predictive ranking, candidate pruning, promotion blocking, or strategy/policy mutation now that `TG24` has closed; wait until a later tactical wave explicitly widens authority beyond governance-only receipts.
- Older deferred/provider/runtime follow-ons (`AK-224`, `AK-235`–`AK-239`) remain non-active backlog and were intentionally not resumed in this wave.
- The repo-local AK wrapper now prefers a working PATH `ak` before the broken workspace-core cargo launcher when no override or vendored CLI exists, so default `./scripts/ci/smoke.sh` / `just verify-full` validation should work again on stable-Rust machines without the temporary `AK_BIN=ak` workaround.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Tasks that opt into explicit AK task scope now validate against frozen exports under `governance/task-scopes/AK-<id>.snapshot.json`; brownfield `governance/task-scopes/AK-*.json` files remain validation-only fallback scaffolding, while workflow/handoff binding now relies only on explicit task IDs, AK claims, or changed task-scope artifacts.
- Current-slice working-tree validation should still run explicitly via `just task-scope-check <AK-ID> working-tree auto` before commit.
