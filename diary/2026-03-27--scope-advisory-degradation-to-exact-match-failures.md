---
summary: "Complete AK-366 by scoping advisory degradation to exact-match receipt failures instead of unrelated receipt corruption."
read_when:
  - "You are resuming SG2 evidence hardening after AK-366."
  - "You need the rationale behind exact-match-scoped advisory degradation."
---

# 2026-03-27 — Scope Advisory Degradation to Exact-Match Failures

## What I Did
- Claimed `AK-366` as an operator-directed SG2 hardening follow-up.
- Extended `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py` so the evidence bundle now distinguishes all receipt scan errors from scan errors attributable to exact-match receipts.
- Updated historical-convergence advisory status/notes so `degraded_history_only` is driven only by exact-match receipt failures, while unrelated corrupt receipts remain diagnostic context instead of authority.
- Kept the broader retrieval surface degraded when scan errors exist, but stopped letting unrelated unreadable receipts poison request-local `no_history` classification.
- Added regression coverage proving that malformed exact-match receipts still degrade advisory status while unrelated invalid JSON receipts do not.
- Kept unavailable diagnostics shape stable by mirroring the new exact-match scan-error fields in the unavailable payload path.

## Why It Mattered
- The prior hardening pass fixed silent receipt loss, but it also made unrelated corrupt receipts downgrade advisory posture for every request in the scan root.
- `TG10` cannot safely define future evidence-backed priors if request-local advisory status is still contaminated by unrelated receipt corruption.
- SG2 evidence should degrade based on authority-scoped failures, not ambient filesystem damage elsewhere in the receipts tree.

## Patterns
- Scope diagnostic authority to the same unit of retrieval that drives the decision.
- Keep broad retrieval health and request-local advisory posture separate when they answer different questions.
- When a hardening fix introduces a new error bucket, add tests for unrelated-failure contamination before promoting the semantics.

## Validation
- `uv run -m pytest -q tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ⚠️ expected to remain blocked by pre-existing repo-wide `just typecheck` failures outside the AK-366 slice

## Next
- `AK-356` remains the next ready SG2 planning slice: freeze the first evidence-backed candidate-prior contract before predictive ranking changes.
