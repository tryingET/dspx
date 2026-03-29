---
summary: "Made the documented `just task-scope-check task_id=<AK-ID> mode=working-tree` invocation executable and added a regression test for the assignment-style CLI boundary."
read_when:
  - "You need the implementation record for AK-505."
  - "You are checking why the documented task-scope-check command now works as written."
---

# 2026-03-29 — Make the Documented task-scope-check Invocation Executable

## What I Did
- Created, claimed, and completed `AK-505`.
- Updated `scripts/check_task_scope.py` to normalize assignment-style values such as `task_id=505`, `mode=working-tree`, and `rev_range=auto` before `argparse` validation.
- Added a regression test in `tests/test_task_scope.py` that executes the CLI with the same assignment-style values emitted by the documented `just task-scope-check task_id=<AK-ID> mode=working-tree` flow.
- Refreshed the operational docs and handoff so the repo records that the canonical task-scope-check command now works as written while the repo-scoped ready queue remains empty.

## Why It Mattered
- The canonical workflow docs told contributors to run `just task-scope-check task_id=<AK-ID> mode=working-tree`, but the recipe forwarded those literal values into `argparse`, which failed before any scope validation ran.
- That made the repo's strongest current-slice provenance check look flaky or broken even though the failure was at the command boundary.
- Fixing the CLI boundary is the highest-leverage workflow guardrail because it restores the documented happy path without forcing every workflow doc to switch to an undocumented positional invocation.

## Validation
- `python3 scripts/check_task_scope.py --root . --task-id task_id=505 --mode mode=working-tree --range rev_range=auto` ✅
- `just task-scope-check task_id=505 mode=working-tree` ✅
- `uv run -m pytest -q tests/test_task_scope.py` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 505 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Keep the documented assignment-style task-scope command as the public workflow contract unless and until the repo intentionally rewrites all workflow surfaces and checks together.
- If the task-scope interface changes again, add an executable regression test at the command boundary instead of validating the docs by substring alone.
