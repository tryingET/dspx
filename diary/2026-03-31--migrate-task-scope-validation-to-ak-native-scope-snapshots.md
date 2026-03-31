---
summary: "Migrated DSPx task-scope validation to consume AK-native task-scope snapshots, keeping brownfield fallback explicit while making `AK-549` the first repo-local snapshot-backed slice."
read_when:
  - "You are resuming after AK-549 and need the exact AK-native task-scope migration seam."
  - "You need to know how DSPx now treats AK task-scope snapshots versus legacy manifests."
---

# 2026-03-31 — Migrate Task-Scope Validation to AK-Native Scope Snapshots

## What I Did
- Set explicit AK task scope on `AK-549` and exported the first repo-local frozen snapshot to `governance/task-scopes/AK-549.snapshot.json`.
- Updated `packages/dspx-core/src/dspx/task_scope.py` so task-scope validation now:
  - detects both `AK-<id>.snapshot.json` and legacy `AK-<id>.json` artifacts,
  - prefers AK-authored snapshots when present,
  - skips cleanly to repo-default scope when no explicit scope artifact exists,
  - treats snapshot `default_applies: true` as an explicit repo-default signal,
  - and still tolerates legacy manifests as transitional fallback while brownfield history remains in the repo.
- Updated `scripts/check_task_scope.py` and the `Justfile` task-scope recipe so the operator-facing validation surface matches the new snapshot-first contract and no longer dirties `uv.lock` just to run the scope checker.
- Extended `tests/test_task_scope.py` with focused coverage for AK snapshot loading, head/working-tree validation from snapshot artifacts, and repo-default skip semantics.
- Refreshed the SG3 direction stack/docs so `AK-548` is no longer treated as the blocker and `AK-550` becomes the selected next follow-on slice after `AK-549`.

## Why It Mattered
- This is the first DSPx repo-local slice that actually consumes AK-authored task-scope snapshots instead of requiring hand-authored task-scope manifests on the primary validation path.
- The brownfield fallback now matches the authority contract: missing explicit scope artifacts no longer fail closed as if hand-authored repo files were canonical.
- DSPx can keep historical manifest-backed slices readable while moving new scope-controlled work onto frozen AK exports.

## Validation
- `just task-scope-check task_id=549 mode=working-tree` ✅
- `uv run -m pytest -q tests/test_task_scope.py tests/test_workflow_contracts.py tests/test_direction_to_execution.py` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 549 --result '{...}'` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Claim `AK-550`.
- Remove the residual workflow and handoff coupling to hand-authored task-scope manifests now that validation itself is snapshot-first.
- Keep `AK-551` queued behind that cleanup slice for the broader regression pass.
