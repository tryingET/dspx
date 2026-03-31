---
summary: "Broadened AK-native task-scope workflow regression coverage after AK-550 by locking in claim-based binding, explicit scope-artifact CLI use, snapshot preference, and repo-level workflow contract alignment."
read_when:
  - "You are resuming after AK-551 and need the exact regression seam for the cleaned-up task-scope workflow."
  - "You need to know which broader task-scope regressions now protect the AK-native authority story end to end."
---

# 2026-03-31 — Add Regression Coverage for AK-Native Task-Scope Workflow

## What I Did
- Claimed `AK-551`, authored explicit AK task scope for the slice, and exported `governance/task-scopes/AK-551.snapshot.json`.
- Extended `tests/test_task_scope.py` with broader regression coverage for:
  - repo-scoped AK claim resolution,
  - rejection of multiple simultaneous repo claims,
  - snapshot-over-legacy scope-artifact preference,
  - claim-bound `head` validation when the latest commit no longer changes a scope artifact,
  - claim-bound `working-tree` validation when neither the dirty tree nor `HEAD` exposes a binding artifact,
  - explicit `--scope-artifact` CLI binding for snapshots,
  - and the `--manifest` compatibility alias against the same snapshot path.
- Extended `tests/test_workflow_contracts.py` with a repo-level integration check so the live DSPx workflow docs/Justfile surfaces must continue to satisfy the cleaned-up contract rather than only fixture copies.
- Refreshed the SG3 direction stack/docs so `AK-551` moves from active follow-on slice to completed work and the handoff now points at the remaining ready slice.

## Why It Mattered
- The AK-native task-scope workflow is now protected at the actual seams that were still most regression-prone after `AK-550`: claim-based binding, explicit operator artifact binding, and snapshot-first precedence over brownfield legacy files.
- The workflow-contract checker now guards the real repo surface as well as synthetic fixtures, reducing the chance that docs/help/Justfile drift reintroduces the old authority story.
- `SG3` is now complete as a bounded wave rather than an almost-done side chain with one untested gap left open.

## Validation
- `uv run -m pytest -q tests/test_task_scope.py tests/test_workflow_contracts.py` ✅
- `just task-scope-check task_id=551 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 551 --result '{...}'` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ after completion (`AK-615`)

## Next
- Claim `AK-615`.
- Audit DSPx's `Justfile` against the standardized contract control case unless operator direction selects a different ready slice.
