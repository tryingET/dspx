---
summary: "Complete AK-473 by materializing the read-only candidate-prior counterfactual advisory on live metadata and persisted receipts."
read_when:
  - "You need the implementation record for AK-473."
  - "You are resuming work after the counterfactual-advisory implementation landed."
---

# 2026-03-28 — Emit Candidate-Prior Counterfactual Advisory

## What I Did
- Claimed `AK-473` and implemented `build_module_synthesis_candidate_prior_counterfactual_advisory` plus the matching unavailable payload path in `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`.
- Threaded the new advisory through `packages/dspx-core/src/dspx/services/module_service.py` so it appears on both live `module-gen` metadata and persisted receipts alongside the prior SG2 surfaces.
- Extended historical diagnostics extraction so replayed exact-match receipts now preserve persisted readiness/counterfactual advisory payloads for later SG2 work.
- Added focused regressions in `tests/test_module_synthesis_evidence.py`, `tests/test_module_service.py`, and `tests/test_run_receipts.py` covering positive, sparse, mixed, no-signal, and fail-closed unavailable cases.
- Updated tactical/operational/session source-of-truth docs so `TG19` is recorded as complete and no next SG2 slice is pinned yet.

## Why It Mattered
- `TG18` froze the bounded counterfactual contract, but DSPx still lacked a concrete receipt-backed surface that showed when prior-supported alternatives passed current validation yet still lost under trusted V7 scoring.
- Materializing that advisory gives the repo a descriptive bridge from historical readiness posture to concrete current-run alternatives without creating a hidden second ranking path.
- Persisting the advisory on receipts keeps later SG2 governance work anchored in inspectable artifacts rather than rediscovering the same counterfactual evidence ad hoc.

## Patterns
- Build the next SG2 layer from already-emitted contract surfaces first; only pull new current-run facts when the ADR explicitly authorizes them.
- Fail closed when current comparison metadata does not fully cover the selected candidate and every compared positive-prior candidate.
- Keep observational counterfactual lists descriptive even when they surface viable alternatives; never let them shadow V7 ranking or promotion.

## Validation
- `uv run -m pytest -q tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py` ✅
- `uv run -q python scripts/check_task_scope.py --task-id 473 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 473 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Inspect the repo-scoped ready queue after `TG19` completion.
- If SG2 continues next, freeze the next post-counterfactual evidence-authority contract before widening any live ranking authority.
- Otherwise, only pick up queued non-SG2 work when the operator explicitly redirects the repo away from the SG2 line.
