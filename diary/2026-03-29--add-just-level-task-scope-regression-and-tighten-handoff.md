---
summary: "Added an executable just-level regression for the documented task-scope command and tightened the next-session handoff back to its max-3 assumption contract."
read_when:
  - "You need the implementation record for AK-509."
  - "You are checking how DSPx now verifies the documented just-level task-scope flow end to end."
---

# 2026-03-29 — Add Just-Level task-scope Regression and Tighten Handoff

## What I Did
- Created, claimed, and completed `AK-509`.
- Added a regression test in `tests/test_task_scope.py` that runs the real `Justfile` recipe with the documented assignment-style invocation (`just task-scope-check task_id=<AK-ID> mode=working-tree`) against a temporary git repo.
- Disabled `.pyc` emission inside that regression so the working-tree scope check stays focused on the intended manifest/script paths.
- Tightened `next_session_prompt.md` back to the stated `Assumptions (max 3)` contract while refreshing the checkpoint to the new workflow-guardrail slice.

## Why It Mattered
- `AK-505` fixed the CLI boundary, but the repo still lacked an executable regression that exercised the public Just recipe exactly as contributors are told to run it.
- Without that test, the command contract could drift again while workflow-contract checks still passed on text alone.
- The handoff also contained a small but visible contract smell (`max 3` with more than three assumptions), so tightening it removes one more source of prompt drift from the active operator surface.

## Validation
- `uv run -m pytest -q tests/test_task_scope.py` ✅
- `just task-scope-check task_id=509 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 509 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- If the task-scope command surface changes again, update both the CLI-level test and the Just-level regression in the same slice.
- Keep `next_session_prompt.md` contract wording numerically honest so workflow prompts do not accumulate low-grade drift.
