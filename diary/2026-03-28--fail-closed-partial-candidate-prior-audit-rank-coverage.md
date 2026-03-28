---
summary: "Complete AK-431 by omitting candidate-prior audit rank when ranked metadata only partially covers audited candidates."
read_when:
  - "You are resuming after AK-431."
  - "You need the rationale behind the partial-rank coverage guardrail fix."
---

# 2026-03-28 — Fail Closed Partial Candidate-Prior Audit Rank Coverage

## What I Did
- Claimed `AK-431` and hardened `build_module_synthesis_candidate_prior_audit()` in `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py` so partial ranked-candidate coverage no longer leaks partial rank context into the audit.
- Treated rank context as unusable when the ranked metadata does not cover every audited candidate-prior entry, clearing rank output instead of mixing real ranks with `None` values.
- Added regression coverage in `tests/test_module_synthesis_evidence.py` for the partial-coverage divergent case, ensuring the audit emits the correct status while omitting rank context and emitting an explicit note.

## Why It Mattered
- Partial rank context is still misleading evidence: it can make the selected candidate appear confidently ranked while hiding that the positive-prior alternative lacks trustworthy ordering.
- The post-selection audit exists to support later SG2 contract decisions, so incomplete ranking truth must fail closed rather than persist as a plausible-looking receipt.
- This closes the remaining drift gap after `AK-388`, extending the same truth-preserving guardrail from missing rank to incomplete rank coverage.

## Patterns
- For governance-facing diagnostics, treat partial explanatory order as unavailable unless coverage is complete across the audited comparison set.
- If a fallback hardens one missing-data path, inspect the adjacent partial-data path immediately; those often survive the first fix.
- Emit an explicit explanatory note when dropping context intentionally so future readers know the omission is protective, not accidental.

## Validation
- `uv run pytest tests/test_module_synthesis_evidence.py -q` ✅
- `uv run pytest tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py -q` ✅
- `python scripts/check_task_scope.py --task-id 431 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅

## Next
- Return to `AK-386`.
- Freeze the next dated SG2 contract after the completed post-selection candidate-prior audit, now with both missing-rank and partial-rank drift guarded by fail-closed audit semantics.
