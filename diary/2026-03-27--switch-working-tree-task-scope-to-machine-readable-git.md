---
summary: "Complete AK-362 by replacing brittle working-tree path parsing with machine-readable git output."
read_when:
  - "You are resuming workflow-guardrail cleanup after AK-362."
  - "You need the rationale behind the machine-readable working-tree parser switch."
---

# 2026-03-27 — Switch Working-Tree Task-Scope to Machine-Readable Git

## What I Did
- Claimed `AK-362` and hardened `packages/dspx-core/src/dspx/task_scope.py` again.
- Replaced the ad-hoc `git status --short` text slicing in `changed_files_for_working_tree()` with NUL-delimited machine-readable git output.
- Added a binary-safe `_git_output_nul()` helper and switched working-tree collection to:
  - `git diff --name-only -z HEAD` for tracked changes against `HEAD`
  - `git ls-files --others --exclude-standard -z` for untracked files
- Expanded `tests/test_task_scope.py` to cover tracked paths with spaces, untracked nested files, and filenames containing literal ` -> ` text.

## Why It Mattered
- The previous fix only stopped stripping away the first character; it still depended on human-oriented porcelain formatting.
- Working-tree scope validation remained vulnerable to quoted filenames, collapsed untracked directories, and rename-like text in filenames.
- A workflow guardrail should parse machine-readable git output when its entire job is to produce correct file paths.

## Patterns
- Prefer NUL-delimited git output for file-path parsing.
- Treat human-oriented CLI output as presentation, not protocol.
- When a parser bug survives one fix, expand tests to cover the real filename edge cases that users actually hit.

## Validation
- `uv run -m pytest -q tests/test_task_scope.py` ✅
- `python scripts/check_task_scope.py --task-id 362 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ⚠️ expected to remain blocked by pre-existing repo-wide `just typecheck` failures outside the AK-362 slice

## Next
- Return to the repo-scoped ready queue; `AK-356` remains the planned SG2 contract-definition slice unless the operator redirects scope again.
