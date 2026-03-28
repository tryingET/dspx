---
summary: "Complete AK-386 by freezing the next SG2 contract after the post-selection candidate-prior audit."
read_when:
  - "You are resuming SG2 work after AK-386."
  - "You need the rationale behind the post-audit candidate-prior divergence explanation contract."
---

# 2026-03-28 — Freeze Candidate-Prior Divergence Explanation Contract

## What I Did
- Claimed `AK-386` and wrote `docs/adr/20260328-synthesis-evidence-candidate-prior-divergence-explanation-v1.md`.
- Froze the next SG2 contract after the read-only candidate-prior audit as a **post-selection divergence explanation** instead of a pre-selection ranking or pruning change.
- Bound that explanation to the existing `candidate_prior_audit` plus trusted current-run ranked/evaluation metadata, using the `AK-388` and `AK-431` fail-closed rank guardrails as part of the contract boundary.
- Created `AK-441` as the next implementation slice so DSPx can materialize the explanation on live metadata and persisted receipts without changing V7 ranking or promotion behavior.
- Updated tactical/operational/session docs so `TG14` is complete and the next active SG2 wave is the read-only divergence-explanation implementation slice.

## Why It Mattered
- `TG13` proved DSPx can tell when the selected candidate diverges from positive prior support, but the audit alone does not explain whether those prior-supported alternatives failed the current runtime or merely lost under V7 scoring.
- Jumping straight from that audit into predictive ranking would still overstate current evidence authority.
- A bounded divergence explanation gives the repo a receipt-backed way to study prior-vs-selection mismatches before governance decides whether priors deserve any future ranking influence.

## Patterns
- After a read-only audit exposes divergence, add a read-only explanation layer before granting any pre-selection authority.
- If explanation depends on current rank truth, require complete explicit ranked metadata for the full comparison set and fail closed otherwise.
- Use current-run evaluation/ranking metadata only for explanation; do not reopen historical discovery or invent fallback ordering from adjacent fields.

## Validation
- `python scripts/check_task_scope.py --task-id 386 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅

## Next
- Claim `AK-441`.
- Materialize the read-only candidate-prior divergence explanation on live `module-gen` metadata and persisted receipts without changing V7 ranking or promotion behavior.
