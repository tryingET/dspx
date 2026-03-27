---
summary: "Complete AK-377 by emitting read-only candidate winner priors for module-gen deterministic variants."
read_when:
  - "You are resuming after AK-377."
  - "You need the implementation notes behind TG11 completion."
---

# 2026-03-27 — Emit Read-Only Candidate Winner Priors

## What I Did
- Claimed `AK-377` and implemented the ADR-backed candidate winner-prior payload in `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`.
- Added candidate-identity extraction for current `module-gen` candidates and historical exact-match winners using stable `variant_id` + `variant_origin` lineage.
- Emitted `candidate_winner_priors` on `synthesis_diagnostics` for both live module metadata and persisted `module-gen` receipts via `packages/dspx-core/src/dspx/services/module_service.py`.
- Kept the payload advisory-only: it reports winner-history matches, degraded history, unsupported candidate identity, or lack of positive winner history without changing ranking, tie-breaking, pruning, or promotion behavior.
- Added regression coverage in `tests/test_module_synthesis_evidence.py`, `tests/test_module_service.py`, and `tests/test_run_receipts.py` for direct builder semantics, live metadata wiring, and persisted receipt surfaces.

## Why It Mattered
- `TG11` needed proof that SG2 evidence could support a per-candidate prior surface before any predictive ranking experiment consumed it.
- Replay-healthy exact-match prior winners are the strongest authority the repo currently has for candidate-level history, so the payload had to stay asymmetric instead of inventing loser-based penalties.
- Attaching the payload to the existing diagnostics surfaces keeps later V8 work auditable and receipt-backed.

## Patterns
- Reuse the existing SG2 evidence bundle and add new advisory payloads on top instead of creating a second discovery path.
- Match candidate priors on stable pre-evaluation lineage (`variant_id` + `variant_origin`), not on post-selection artifact hashes.
- When historical authority is asymmetric, emit explicit degraded/no-positive states before granting ranking authority.

## Validation
- `uv run pytest tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py -q` ✅
- `python scripts/check_task_scope.py --task-id 377 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅

## Next
- Inspect the repo-scoped AK ready queue.
- If no SG2 slice is ready, define the next tactical/AK contract for how DSPx may evaluate or consume the read-only candidate-prior payload without silently widening authority.
