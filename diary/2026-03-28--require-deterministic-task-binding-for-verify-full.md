---
summary: "Complete AK-474 by making verify-full task-scope resolution deterministic and fail-closed again."
read_when:
  - "You are resuming workflow-guardrail work after AK-474."
  - "You need the rationale behind deterministic task binding for task-scope validation."
---

# 2026-03-28 — Require Deterministic Task Binding for Verify-Full

## What I Did
- Claimed `AK-474` and hardened `packages/dspx-core/src/dspx/task_scope.py` so unresolved task binding fails closed again.
- Added deterministic head-mode fallback to the committed `next_session_prompt.md` checkpoint (`Slice executed: AK-...`) so multi-commit slices no longer depend on the last commit touching the manifest.
- Added an explicit `task_id` parameter to `just task-scope-check` for current-slice working-tree validation before commit.
- Updated workflow docs to require explicit working-tree task-scope validation and to document the committed-checkpoint fallback for `just verify-full`.
- Fixed the stale SG2 authority-boundary note in `docs/project/operational_goals.md` so it includes the readiness and counterfactual advisory layers.

## Why It Mattered
- `just verify-full` had started skipping task-scope validation when no task binding could be inferred, which made green validation depend on ambient AK state and commit shape.
- Multi-commit slices could also lose task binding if the manifest was introduced earlier than the last commit in the batch.
- Using the committed session checkpoint as deterministic head-mode binding restores a single repo-local source for post-commit scope validation without reopening a hidden authority path.

## Patterns
- Governance checks should fail closed on missing identity rather than silently downgrade to advisory mode.
- If a validation gate needs repo-local context after commit, bind it to a committed handoff artifact instead of ambient shell state.
- When a new workflow mechanism becomes authoritative, update both the code path and the human workflow docs in the same slice.

## Validation
- `python scripts/check_task_scope.py --task-id 474 --mode working-tree` ✅
- `uv run -m pytest -q tests/test_task_scope.py` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 474 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Return to `AK-473`.
- Materialize the read-only candidate-prior counterfactual advisory on live `module-gen` metadata and persisted receipts without changing V7 ranking or promotion behavior.
