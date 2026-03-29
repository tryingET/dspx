---
summary: "Complete AK-487 by hardening the SG2 counterfactual advisory to fail closed under surface drift."
read_when:
  - "You need the implementation record for AK-487."
  - "You are investigating SG2 counterfactual advisory integrity hardening."
---

# 2026-03-28 — Fail Closed Counterfactual Advisory Invariants

## What I Did
- Claimed `AK-487` as an operator-directed SG2 guardrail hardening slice after the `TG19` implementation landed.
- Hardened `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py` so the counterfactual advisory now fails closed on unsupported readiness/divergence/audit statuses, selected-candidate identity drift across SG2 surfaces, and malformed/divergent divergence comparison sets.
- Fixed selected-candidate `ranking_score` handling so an explicit `0.0` score is preserved instead of being replaced by a fallback divergence value.
- Added regression coverage in `tests/test_module_synthesis_evidence.py` for zero-valued scores, unknown readiness status drift, selected-candidate identity drift, and malformed divergence comparison payloads.
- Updated source-of-truth operational/session artifacts while keeping the next ready queue pinned to `AK-317`.

## Why It Mattered
- SG2 is building receipt-backed evidence for later governance work, so descriptive layers still need strict trust-boundary enforcement.
- The original counterfactual implementation could present plausible advisory output under malformed SG2 inputs, which would have allowed corrupted receipts to masquerade as trustworthy evidence.
- Preserving zero-valued scores matters because governance artifacts must distinguish real `0.0` from missing data.

## Patterns
- Treat persisted SG2 advisory surfaces as typed contracts, not just structured blobs.
- Preserve numeric zero values explicitly; never use truthiness fallbacks on ranking/evidence fields.
- When a consumer derives from multiple advisory layers, validate identity and comparison-set agreement before deriving a new status.

## Validation
- `uv run -m pytest -q tests/test_module_synthesis_evidence.py` ✅
- `uv run -m pytest -q tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py` ✅
- `uv run -q python scripts/check_task_scope.py --task-id 487 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 487 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Keep `AK-317` as the repo-scoped next ready slice unless the operator explicitly redirects the repo back to a new SG2 contract or hardening task.
- If SG2 continues, prefer a centralized invariant validator before layering additional receipt-backed advisory consumers.
