---
summary: "Complete AK-477 by enforcing the deterministic task-binding workflow in contract checks and tests."
read_when:
  - "You are resuming workflow-contract hardening after AK-477."
  - "You need the rationale for locking task-binding semantics into automated contract checks."
---

# 2026-03-28 — Lock Deterministic Task Binding Into Contract Checks

## What I Did
- Claimed `AK-477` and tightened `scripts/check_workflow_contracts.py` so the repo now requires the explicit working-tree task-scope command and the fail-closed/next-session-checkpoint wording on the documented workflow surfaces.
- Updated `tests/test_workflow_contracts.py` so the contract checker regression fixtures match the new deterministic task-binding contract.
- Bound the follow-up into a task-scope manifest and updated the session checkpoint for deterministic head-mode validation.

## Why It Mattered
- `AK-474` fixed the runtime and docs, but the repo's contract checker still would not fail if those new semantics drifted back out of the workflow docs or `Justfile`.
- Without this follow-up, the guardrail itself could quietly regress even though the implementation was correct today.

## Patterns
- When a workflow mechanism becomes authoritative, update the contract checker and the contract-check tests in the same wave.
- Guardrails should protect not just runtime behavior, but also the docs and recipe surfaces operators actually follow.

## Validation
- `python scripts/check_task_scope.py --task-id 477 --mode working-tree` ✅
- `uv run -m pytest -q tests/test_workflow_contracts.py` ✅
- `python3 scripts/check_workflow_contracts.py` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 477 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Return to `AK-473`.
- Materialize the read-only candidate-prior counterfactual advisory on live `module-gen` metadata and persisted receipts without changing V7 ranking or promotion behavior.
