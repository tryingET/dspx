---
summary: "Complete AK-378 by freezing the next SG2 contract for consuming candidate winner priors after TG11."
read_when:
  - "You are resuming SG2 work after AK-378."
  - "You need the rationale behind the post-selection candidate-prior audit contract."
---

# 2026-03-27 — Freeze Candidate-Prior Audit Contract

## What I Did
- Claimed `AK-378` and wrote `docs/adr/20260327-synthesis-evidence-candidate-prior-audit-v1.md`.
- Froze the next SG2 contract for consuming `candidate_winner_priors` as a **post-selection candidate-prior audit** instead of a pre-selection ranking or pruning signal.
- Defined a bounded audit posture for how the selected `module-gen` candidate relates to the positive prior support available in the current deterministic fan-out.
- Created `AK-379` as the next implementation slice so DSPx can materialize that audit on live metadata and persisted receipts without changing V7 ranking or promotion behavior.
- Updated tactical/operational/session docs so `TG12` is complete and the next active SG2 wave is the read-only audit implementation slice.

## Why It Mattered
- `TG11` proved that DSPx can emit per-candidate winner-history priors, but that alone did not justify letting priors steer ranking.
- The strongest candidate-level authority still comes from replay-healthy exact-match historical winners, so the next safe question is whether present V7 winners align with that positive support, not whether the runtime should obey it yet.
- A post-selection audit creates a receipt-backed inspection layer that later V8 work can evaluate before governance widens authority.

## Patterns
- When a new prior payload is real but still asymmetric, insert a post-selection audit step before granting pre-selection influence.
- Compare the selected candidate against the subset of candidates with positive prior support; do not treat missing winner history as negative evidence.
- Freeze explanatory status models in a dated ADR before adding new runtime payloads.

## Validation
- `python scripts/check_task_scope.py --task-id 378 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅

## Next
- Claim `AK-379`.
- Materialize the read-only post-selection candidate-prior audit on live `module-gen` metadata and persisted receipts without changing V7 ranking or promotion behavior.
