---
summary: "Complete AK-482 by refactoring verify-full into staged gates with a fast pre-push path and parallel heavy checks."
read_when:
  - "You are resuming workflow validation refactoring after AK-482."
  - "You need the rationale behind the staged/parallel verify-full topology."
---

# 2026-03-28 — Refactor Verify-Full Into Staged Parallel Gates

## What I Did
- Claimed `AK-482` and split the old monolithic `just verify-full` path into `verify-fast`, `verify-runtime`, `verify-tests`, `verify-pre-push`, and `verify-full`.
- Added `scripts/ci/verify-full.sh` so the heavy runtime and test branches run in parallel after the fast gate passes.
- Changed the pre-push hook to use the fast guardrail path instead of forcing the full serial suite on every push.
- Updated workflow docs and workflow-contract checks/tests so the new staged validation contract is enforced automatically.

## Why It Mattered
- The old `verify-full` serialized cheap governance checks and the full test suite into one expensive default path.
- That made normal push-time validation far too slow, especially for docs/workflow slices that did not need the entire runtime/test stack.
- Splitting fast vs heavy validation preserves a deterministic full gate while making the default push-time contract much cheaper.

## Validation
- `python scripts/check_task_scope.py --task-id 482 --mode working-tree` ✅
- `uv run -m pytest -q tests/test_workflow_contracts.py` ✅
- `python3 scripts/check_workflow_contracts.py` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 482 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Return to `AK-473`.
- Materialize the read-only candidate-prior counterfactual advisory on live `module-gen` metadata and persisted receipts without changing V7 ranking or promotion behavior.
