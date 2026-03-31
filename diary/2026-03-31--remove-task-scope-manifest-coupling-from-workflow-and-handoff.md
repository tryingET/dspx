---
summary: "Removed manifest-centric workflow/handoff coupling after AK-549 by making task-scope binding depend only on explicit task IDs, AK claims, or changed scope artifacts while keeping brownfield legacy-file fallback for validation."
read_when:
  - "You are resuming after AK-550 and need the exact workflow/handoff cleanup seam."
  - "You need to know how DSPx now binds task-scope validation after the AK snapshot migration."
---

# 2026-03-31 — Remove Task-Scope Manifest Coupling from Workflow and Handoff

## What I Did
- Claimed `AK-550`, authored explicit AK task scope for the slice, and exported `governance/task-scopes/AK-550.snapshot.json`.
- Updated `packages/dspx-core/src/dspx/task_scope.py` so task-scope resolution no longer uses the committed `next_session_prompt.md` checkpoint as a control-plane fallback.
- Kept validation binding explicit and deterministic: `check_task_scope()` now binds only from an explicit `task_id`, an active AK claim, or changed task-scope artifacts in the working tree / `HEAD`.
- Preserved brownfield validation fallback for legacy `governance/task-scopes/AK-*.json` files, but removed manifest-centric wording from the operator-facing workflow/help surface.
- Renamed the explicit CLI path surface to `--scope-artifact` while keeping `--manifest` as a compatibility alias.
- Refreshed `Justfile`, `README.md`, `docs/project/developer_workflow.md`, and the workflow contract checker so docs now describe snapshots as authoritative and `next_session_prompt.md` as handoff context only.
- Replaced the old checkpoint-coupled regressions in `tests/test_task_scope.py` with fail-closed head-mode cases plus an explicit-task-id success case, and extended workflow contract fixtures for the new wording.

## Why It Mattered
- AK-native scope snapshots are now the authoritative operator story end to end, not just the internal validator preference.
- `next_session_prompt.md` stays useful as handoff context, but it no longer has hidden task-binding authority.
- Brownfield history remains readable because legacy scope files still work as validation fallback when no snapshot exists.

## Validation
- `uv run -m pytest -q tests/test_task_scope.py tests/test_workflow_contracts.py` ✅
- `just task-scope-check task_id=550 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 550 --result '{...}'` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Claim `AK-551`.
- Add the broader regression coverage for the AK-native task-scope workflow across the cleaned-up binding/handoff contract.
