---
summary: "Complete AK-379 by emitting the read-only post-selection candidate-prior audit on live metadata and persisted receipts."
read_when:
  - "You are resuming after AK-379."
  - "You need the implementation notes behind TG13 completion."
---

# 2026-03-27 — Emit Post-Selection Candidate-Prior Audit

## What I Did
- Claimed `AK-379` and implemented the ADR-backed `candidate_prior_audit` payload in `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`.
- Derived the audit from the existing selected candidate identity, ranked-candidate ordering, and `candidate_winner_priors` payload instead of opening a second receipt-discovery path.
- Attached the new audit to `synthesis_diagnostics` for both live `module-gen` artifact metadata and persisted receipts via `packages/dspx-core/src/dspx/services/module_service.py`.
- Added regression coverage in `tests/test_module_synthesis_evidence.py`, `tests/test_module_service.py`, and `tests/test_run_receipts.py` for no-history, degraded, selected-match, non-selected-positive, unsupported, and unavailable audit postures.

## Why It Mattered
- `TG13` needed a bounded first consumer of `candidate_winner_priors` before any future work could argue for predictive ranking authority.
- The audit lets DSPx inspect whether V7 winners align with replay-healthy exact-match prior support without pretending divergence is already a policy failure.
- Keeping the audit read-only preserves the ADR trust boundary while making later SG2 decisions receipt-backed and reviewable.

## Patterns
- Build new SG2 surfaces from already-emitted evidence payloads before widening authority or discovery paths.
- Compare selected outcomes against the subset of current candidates with positive prior support; do not treat missing support as negative evidence.
- When a payload is explanatory-only, make unavailable/degraded states explicit and preserve them on both live metadata and persisted receipts.

## Validation
- `uv run pytest tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py -q` ✅
- `python scripts/check_task_scope.py --task-id 379 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅

## Next
- Inspect the repo-scoped AK ready queue.
- If no SG2 slice is ready, freeze the next dated contract for what comes after the completed read-only candidate-prior audit before implementing more evidence authority.
