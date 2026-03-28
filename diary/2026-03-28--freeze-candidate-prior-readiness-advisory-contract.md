---
summary: "Complete AK-459 by freezing the next SG2 contract after the read-only candidate-prior divergence explanation."
read_when:
  - "You are resuming SG2 work after AK-459."
  - "You need the rationale behind the candidate-prior readiness advisory contract."
---

# 2026-03-28 — Freeze Candidate-Prior Readiness Advisory Contract

## What I Did
- Claimed `AK-459` and wrote `docs/adr/20260328-synthesis-evidence-candidate-prior-readiness-advisory-v1.md`.
- Froze the next SG2 contract after the read-only candidate-prior divergence explanation as a **receipt-backed readiness advisory** instead of predictive ranking, pruning, or policy mutation.
- Limited the advisory to replay-healthy exact-match receipts that already carry persisted `candidate_prior_audit` and `candidate_prior_divergence_explanation` payloads.
- Created `AK-462` as the next implementation slice so DSPx can materialize the readiness advisory on live metadata and persisted receipts without changing V7 ranking or promotion behavior.
- Updated tactical/operational/session docs so `TG16` is complete and the next active SG2 wave is the read-only readiness-advisory implementation slice.

## Why It Mattered
- `TG15` made single-run prior-vs-selection divergence legible, but governance still lacked a bounded way to summarize whether priors look consistently helpful across receipt-backed exact-match history.
- Jumping straight from per-run divergence explanations into predictive ranking would still overstate current evidence authority.
- A read-only readiness advisory gives the repo a disciplined way to judge whether priors are mostly convergent, mostly blocked by runtime failures, mostly outscored under V7, or still too sparse/mixed to trust.

## Patterns
- After a per-run explanation layer, add a retrospective receipt-backed rollup before granting any predictive authority.
- Reuse persisted explanatory surfaces instead of re-scoring historical candidates from raw ranked metadata.
- Treat sparse or malformed historical evidence as a reason to fail closed into readiness unavailability or insufficiency, not as permission to invent posture.

## Validation
- `python scripts/check_task_scope.py --task-id 459 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 459 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Claim `AK-462`.
- Materialize the read-only candidate-prior readiness advisory on live `module-gen` metadata and persisted receipts without changing V7 ranking or promotion behavior.
