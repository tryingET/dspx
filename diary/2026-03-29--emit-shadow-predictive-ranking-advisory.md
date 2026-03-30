---
summary: "Complete AK-562 by materializing the read-only shadow predictive-ranking advisory on live metadata and persisted receipts."
read_when:
  - "You need the implementation record for AK-562."
  - "You are resuming work after the shadow predictive-ranking advisory landed."
---

# 2026-03-29 — Emit Shadow Predictive-Ranking Advisory

## What I Did
- Claimed `AK-562` and implemented `build_module_synthesis_shadow_predictive_ranking_advisory` plus the matching unavailable payload path in `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`.
- Threaded the new advisory through `packages/dspx-core/src/dspx/services/module_service.py` so it appears on both live `module-gen` metadata and persisted receipts alongside the prior SG2 surfaces.
- Extended historical diagnostics extraction so replayed exact-match receipts now preserve persisted shadow predictive-ranking advisory payloads for later SG2 work.
- Added focused regressions in `tests/test_module_synthesis_evidence.py`, `tests/test_module_service.py`, and `tests/test_run_receipts.py` covering prefer-alternative, matches-V7, no-signal, mixed, and fail-closed unavailable cases.
- Updated tactical/operational/session source-of-truth docs so `TG21` is recorded as complete and no next SG2 implementation slice is pinned yet.

## Why It Mattered
- `TG20` froze the bounded shadow predictive-ranking contract, but DSPx still lacked the concrete receipt-backed surface that answered whether a bounded prior-aware shadow preference would agree with the trusted V7 winner or surface a different passing positive-prior candidate.
- Materializing that advisory creates the first explicit bridge from descriptive SG2 evidence into a named shadow ranking result without creating a hidden live ranking path.
- Persisting the advisory on receipts keeps later governed policy-evaluation work anchored in inspectable artifacts rather than rediscovering the same shadow comparison ad hoc.

## Patterns
- Reuse already-emitted SG2 surfaces first, then require trusted current comparison metadata to agree before producing a shadow result.
- Fail closed when the current passing comparison set drifts from the audit/divergence/counterfactual surfaces instead of inferring a hidden second ranking path.
- Keep shadow ranking descriptive only; never let it change V7 winner selection, tie-breaking, pruning, or promotion behavior.

## Validation
- `uv run -m pytest -q tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py` ✅
- `just task-scope-check task_id=562 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 562 --result '{...}'` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Re-run the repo-scoped ready queue after `AK-562` completion.
- If it is still empty, do not start a new implementation slice until the next truthful `TG22` contract/materialization step is created.
- Do not widen SG2 authority beyond the new shadow predictive-ranking advisory until a later contract explicitly does so.
