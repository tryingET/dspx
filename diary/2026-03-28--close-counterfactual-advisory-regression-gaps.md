---
summary: "Complete AK-493 by closing residual SG2 counterfactual-advisory regression gaps."
read_when:
  - "You need the implementation record for AK-493."
  - "You are checking whether counterfactual advisory hardening also has regression coverage."
---

# 2026-03-28 — Close Counterfactual Advisory Regression Gaps

## What I Did
- Claimed `AK-493` as an operator-directed follow-on slice after `AK-487`.
- Expanded `tests/test_module_synthesis_evidence.py` so the counterfactual advisory now has explicit regressions for unsupported readiness/divergence/audit status values.
- Added a regression proving the advisory fails closed when divergence compared-candidate identities drift away from the audit comparison set.
- Kept the slice bounded to test hardening and source-of-truth updates; runtime behavior did not change.

## Why It Mattered
- `AK-487` hardened the runtime path, but the residual test matrix still left unsupported divergence/audit statuses and compared-candidate identity mismatch under-covered.
- SG2 evidence layers are only trustworthy if the fail-closed contract is enforced by regression coverage, not just by code intent.

## Patterns
- After adding a new invariant family, immediately close the regression matrix around every accepted enum surface and every identity-consistency rule.
- Treat comparison-set identity as a first-class SG2 trust boundary, not just malformed-shape handling.

## Validation
- `uv run -m pytest -q tests/test_module_synthesis_evidence.py` ✅
- `uv run -q python scripts/check_task_scope.py --task-id 493 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 493 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Keep `AK-317` as the repo-scoped next ready slice unless the operator explicitly redirects the repo back into SG2.
