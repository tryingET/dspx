---
summary: "Complete AK-466 by freezing the next SG2 contract after the read-only candidate-prior readiness advisory."
read_when:
  - "You are resuming SG2 work after AK-466."
  - "You need the rationale behind the post-readiness counterfactual advisory contract."
---

# 2026-03-28 — Freeze Candidate-Prior Counterfactual Advisory Contract

## What I Did
- Claimed `AK-466` and wrote `docs/adr/20260328-synthesis-evidence-candidate-prior-counterfactual-advisory-v1.md`.
- Froze the next SG2 contract after the read-only candidate-prior readiness advisory as a **read-only counterfactual advisory** instead of a live ranking or pruning change.
- Bound that advisory to already-emitted SG2 surfaces (`candidate_prior_audit`, `candidate_prior_divergence_explanation`, and `candidate_prior_readiness_advisory`) plus trusted current-run ranked/evaluation metadata.
- Created `AK-473` as the next implementation slice so DSPx can materialize the counterfactual advisory on live metadata and persisted receipts without changing V7 ranking or promotion behavior.
- Updated tactical/operational/session docs so `TG18` is complete and the next active SG2 wave is the read-only counterfactual-advisory implementation slice.

## Why It Mattered
- `TG17` proved DSPx can summarize whether candidate priors look convergent, mostly blocked by runtime failures, mostly outscored under V7 scoring, sparse, or mixed, but that posture alone is still too coarse to justify widening authority.
- Jumping straight from readiness into predictive ranking would skip the repo's established pattern of adding one narrow, auditable, read-only consumer at a time.
- A bounded counterfactual advisory gives the repo a current-run surface for studying viable prior-supported alternatives before governance decides whether any later offline or shadow ranking contract should exist.

## Patterns
- When a governance summary says a later experiment is thinkable, insert one more descriptive current-run layer before granting any ranking authority.
- Reuse only already-frozen SG2 surfaces plus trusted current-run metadata; do not reopen historical discovery or invent synthetic score deltas.
- Keep counterfactual surfaces descriptive enough for governance review, not implicit shadow policies.

## Validation
- `python scripts/check_task_scope.py --task-id 466 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 466 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Claim `AK-473`.
- Materialize the read-only candidate-prior counterfactual advisory on live `module-gen` metadata and persisted receipts without changing V7 ranking or promotion behavior.
