---
summary: "Complete AK-356 by freezing the first evidence-backed candidate-prior contract and aligning the next implementation slice."
read_when:
  - "You are resuming SG2 planning after AK-356."
  - "You need the rationale behind the candidate-prior trust boundary before predictive ranking."
---

# 2026-03-27 — Freeze Evidence-Backed Candidate-Prior Contract

## What I Did
- Claimed `AK-356` and wrote `docs/adr/20260327-synthesis-evidence-candidate-prior-v1.md`.
- Froze the first SG2 candidate-prior contract for `module-gen` as a **read-only winner-history payload** rather than immediate predictive ranking.
- Anchored candidate-prior identity on the current request tuple plus stable current-candidate fields (`variant_id` and `variant_origin`).
- Limited positive prior authority to replay-healthy exact-match **historical winners** whose selected candidate identity matches a current candidate.
- Explicitly kept historical losers, degraded receipts, and Oracle neighbors out of pruning or negative-prior authority.
- Created `AK-377` as the next implementation slice so DSPx can materialize the payload on live metadata/receipts before any ranking behavior changes.
- Updated tactical/operational/session docs so `TG10` is complete and the next active wave is the read-only candidate-prior implementation slice.

## Why It Mattered
- After `TG9`, the repo had enough evidence visibility to be dangerous: it was easy to jump from diagnostics into hidden candidate scoring.
- Replay health currently proves prior **winners** much better than prior losers, so a safe contract had to stay asymmetric instead of pretending all ranked history has equal authority.
- Freezing the trust boundary first preserves V7 behavior while giving later V8 work a durable payload to inspect and evaluate.

## Patterns
- When only historical winners are replay-verifiable, allow winner-history priors before loser-history penalties.
- Candidate priors need a stable pre-evaluation identity key; for the current runtime that key is variant lineage, not selected artifact hash.
- Freeze a read-only payload before granting it ranking or pruning authority.

## Validation
- `python scripts/check_task_scope.py --task-id 356 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅

## Next
- Claim `AK-377` and materialize the read-only candidate winner-prior payload on live `module-gen` metadata and persisted receipts without changing V7 ranking or promotion behavior.
