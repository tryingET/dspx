---
summary: "Complete AK-349 by removing residual task-scope CLI wording drift and making the helper script directly runnable."
read_when:
  - "You are resuming workflow-guardrail polish after AK-349."
  - "You need the rationale behind the task-scope CLI contract cleanup."
---

# 2026-03-25 — Polish Task-Scope CLI Contract

## What I Did
- Claimed `AK-349` and polished `scripts/check_task_scope.py`.
- Removed residual stale CLI wording so the script now describes the current contract: an attested task slice, not merely the latest committed slice.
- Added local `sys.path` bootstrap from `packages/dspx-core/src` so `python scripts/check_task_scope.py --help` works directly from the repo root instead of requiring `uv run` just to inspect the CLI.
- Added regression coverage in `tests/test_task_scope.py` that executes the real script entrypoint and asserts the help output matches the current contract.

## Why It Mattered
- After `AK-346`, the task-scope engine had the correct fail-closed/full-slice behavior, but the CLI help text still described the superseded semantics.
- A workflow guardrail script should be inspectable through its real entrypoint without import-path trivia becoming the dominant failure mode.
- The help surface is part of the operational contract; stale wording there recreates prompt/runtime mismatch at the operator layer.

## Patterns
- Treat CLI help text as runtime surface, not comment text.
- When a repo-local script is part of a control-plane workflow, make the direct entrypoint self-sufficient enough for inspection/help flows.
- Add a regression test on the real script surface when the bug was wording/runtime coupling rather than pure library logic.

## Validation
- `uv run -m pytest -q tests/test_task_scope.py` ✅
- `python scripts/check_task_scope.py --help` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ⚠️ expected to remain blocked by pre-existing repo-wide `just typecheck` failures outside the AK-349 slice

## Next
- Return to `AK-341` and implement the read-only historical convergence advisory on runtime metadata/receipts.
