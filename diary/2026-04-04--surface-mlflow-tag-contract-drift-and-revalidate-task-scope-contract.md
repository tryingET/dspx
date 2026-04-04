---
summary: "Implement AK-734 by surfacing MLflow tag-contract drift in explain reason codes and confirming the existing task-scope invocation contract does not need churn."
read_when:
  - "You are resuming after AK-734 implementation."
  - "You need the rationale and validation story for the post-AK-729 cleanup slice."
---

# 2026-04-04 — Surface MLflow Tag-Contract Drift and Revalidate Task-Scope Contract

## What I Did
- Materialized and claimed `AK-734` as an operator-directed cleanup slice after the atomic-completion pass surfaced one real gap and one suspected workflow-contract mismatch.
- Added MLflow explain observability for contradictory correlation tags so local and remote candidate filtering now records `mlflow_tag_contract_violation` whenever a candidate is dropped because its overlapping tag values disagree with the expected receipt tags.
- Extended the run-explain regressions so the reason code appears when contradictory tags are filtered, but stays absent for compatible partial-tag and nested-artifact local histories.
- Re-checked the task-scope invocation concern instead of blindly churning docs: `scripts/check_task_scope.py` already normalizes assignment-style values like `task_id=734` and `mode=working-tree`, and the existing `just task-scope-check task_id=<AK-ID> mode=working-tree` contract is therefore still truthful.
- Exported `governance/task-scopes/AK-734.snapshot.json` and refreshed the checked-in work-items projection.

## Why It Mattered
- `docs/rfc/RFC-DSPX-OBS-20260207-mlflow-explain-correlation-v11.md` already named `mlflow_tag_contract_violation` as part of the explain reason-code contract, but the runtime never emitted it; contradictory tags were silently filtered out.
- That meant the explain surface could hide a real reason for candidate exclusion even after the earlier TG24 and AK-729 hardening waves.
- The suspected task-scope contract bug could have triggered unnecessary doc/churn debt, so verifying the actual normalization path before editing preserved the real contract instead of rewriting around a false alarm.

## Risk Boundaries
- No live policy widening: the slice only improves explain observability around already-bounded candidate filtering.
- No task-scope contract churn without evidence: the docs/checkers stayed untouched because the underlying repo workflow already supported the documented invocation shape.
- No tactical-goal churn: `TG25` remains active and the queue returns to empty after this cleanup slice once the AK authority blocker is resolved.

## Validation
- `uv run --no-sync -m pytest -q tests/test_run_receipts.py` ✅
- `uvx ruff check packages/dspx-core/src/dspx/services/run_explain_service.py tests/test_run_receipts.py` ✅
- `uvx ty check packages/dspx-core/src/dspx/services/run_explain_service.py` ✅
- `just task-scope-check task_id=734 mode=working-tree` ✅ (repo-default snapshot skip; assignment-style contract reconfirmed)
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ after implementation (`[]`)

## Hard Blocker
- `./scripts/ak.sh task complete 734 --result '{...}'` ❌ → `Database error: engine error: FOREIGN KEY constraint failed`
- `./scripts/ak.sh task unclaim 734` ❌ → same foreign-key failure
- Result: the code and repo artifacts are ready, but the live AK task cannot currently be completed or released in this environment.

## Next
- Resolve or operator-direct around the claimed-`AK-734` AK foreign-key blocker before starting another repo-local slice.
- If the blocker clears, complete `AK-734`, export `governance/work-items.json` again, and refresh the handoff back to the normal empty-ready-queue `TG25` waiting state.
- Preserve the rule from this pass: verify suspected workflow-contract mismatches against the actual parser/normalization path before rewriting docs around them.
