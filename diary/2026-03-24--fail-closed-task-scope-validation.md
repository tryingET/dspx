---
summary: "Complete AK-346 by making task-scope validation fail closed and cover full multi-commit task slices."
read_when:
  - "You are resuming workflow-guardrail work after AK-346."
  - "You need the rationale behind fail-closed task-scope validation."
---

# 2026-03-24 — Fail-Closed Task-Scope Validation

## What I Did
- Claimed `AK-346` and hardened `packages/dspx-core/src/dspx/task_scope.py`.
- Changed task-scope resolution so `check_task_scope()` now:
  - prefers an explicit task id when provided,
  - otherwise uses the currently claimed task,
  - otherwise falls back to a task id inferred from a task-scope manifest changed in `HEAD`, and
  - fails closed instead of returning a skip when no task binding can be resolved.
- Replaced the default head-mode range with `auto`, which validates the full attested task slice from the first commit that introduced the task-scope manifest through `HEAD` instead of only `HEAD^..HEAD`.
- Updated `Justfile`, `scripts/check_task_scope.py`, `docs/project/developer_workflow.md`, and `docs/tech-stack.local.md` to describe the new contract.
- Added regression tests covering fail-closed task-id resolution and full multi-commit task-slice validation.
- Fixed `next_session_prompt.md` so the live AK reference uses a real repo-scoped `ak task list -F json | jq ...` command instead of the invalid pseudo-command form.

## Why It Mattered
- The previous workflow could report a green `just verify-full` even when task-scope attestation had silently skipped because no task was currently claimed.
- Head-mode attestation only looked at `HEAD^..HEAD`, which was too narrow for multi-commit task slices and made the check depend on commit timing instead of the actual slice under review.
- Source-of-truth handoff docs should not point operators at unsupported AK CLI syntax.

## Patterns
- Governance checks should fail closed when they cannot bind themselves to the thing they are supposed to govern.
- If a task-scope manifest defines the slice boundary, use that manifest to derive the validation window instead of guessing from the last commit alone.
- Operator handoff files are part of the control plane; pseudo-commands there create real workflow drift.

## Validation
- `uv run -m pytest -q tests/test_task_scope.py tests/test_workflow_contracts.py` ✅
- `uvx ty check packages/dspx-core/src/dspx/task_scope.py scripts/check_task_scope.py` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ⚠️ blocked by pre-existing repo-wide `just typecheck` failures outside the AK-346 slice (for example `packages/dspx-core/src/dspx/cli/commands/providers.py`, `packages/dspx-core/src/dspx/cli/dspx_mermaid2dspy.py`, and `packages/dspx-core/src/dspx/tools/registry.py`)

## Next
- Return to `AK-341` and implement the read-only historical convergence advisory on runtime metadata/receipts now that the workflow guardrail no longer skips silently when task binding disappears.
