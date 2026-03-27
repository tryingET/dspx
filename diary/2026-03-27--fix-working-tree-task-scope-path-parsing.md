---
summary: "Complete AK-359 by fixing working-tree task-scope path parsing so changed files are reported accurately."
read_when:
  - "You are resuming workflow-guardrail cleanup after AK-359."
  - "You need the rationale behind the working-tree task-scope parsing fix."
---

# 2026-03-27 — Fix Working-Tree Task-Scope Path Parsing

## What I Did
- Claimed `AK-359` and fixed `packages/dspx-core/src/dspx/task_scope.py`.
- Changed `_git_output()` to preserve leading status-column whitespace from `git status --short` output instead of stripping it away.
- Added a regression test in `tests/test_task_scope.py` that exercises `changed_files_for_working_tree()` against a real repo and proves the returned path keeps its first character.

## Why It Mattered
- Working-tree task-scope validation was reporting paths like `ackages/...` and `ests/...`, which turned legitimate in-scope edits into false out-of-scope failures.
- The bug only appeared in working-tree mode because `git status --short` relies on leading status columns; stripping those columns corrupted every parsed path.
- Workflow guardrails should be trustworthy when operators inspect uncommitted scope before commit.

## Patterns
- Do not use blanket `.strip()` on CLI output when column position is part of the protocol.
- For git porcelain parsing, preserve leading columns and trim only trailing newline/whitespace.
- Add regression tests around the exact command surface that produced the operational failure.

## Validation
- `uv run -m pytest -q tests/test_task_scope.py` ✅
- `python scripts/check_task_scope.py --task-id 359 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ⚠️ expected to remain blocked by pre-existing repo-wide `just typecheck` failures outside the AK-359 slice

## Next
- Return to the repo-scoped ready queue; `AK-356` remains the planned SG2 contract-definition slice unless the operator redirects scope again.
