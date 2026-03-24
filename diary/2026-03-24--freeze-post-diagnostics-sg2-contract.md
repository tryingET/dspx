---
summary: "Complete AK-337 by freezing the first post-diagnostics SG2 evidence-consuming contract and aligning the next implementation slice."
read_when:
  - "You are resuming SG2 work after AK-337."
  - "You need the rationale behind the historical convergence advisory contract."
---

# 2026-03-24 — Freeze Post-Diagnostics SG2 Contract

## What I Did
- Claimed `AK-337` and wrote `docs/adr/20260324-synthesis-evidence-history-advisory-v1.md`.
- Froze the first post-diagnostics SG2 evidence consumer as a **read-only historical convergence advisory** for the selected `module-gen` artifact.
- Kept the contract explicitly post-selection: it compares the current winner against healthy exact-match history instead of pretending request-level evidence is already a safe pre-evaluation candidate prior.
- Created `AK-341` as the next implementation slice so the repo can materialize the advisory on runtime metadata/receipts before attempting predictive ranking.
- Updated tactical/operational docs so `TG8` is complete and the active follow-on wave is the advisory implementation slice.

## Why It Mattered
- `TG6` and `TG7` made evidence retrievable and visible, but they did not yet prove what the first safe evidence-consuming runtime behavior should be.
- The current evidence bundle is request-scoped, so using it immediately as a candidate-ranking signal would overstate what the contract actually knows.
- A convergence/divergence advisory is the narrowest meaningful next step: it consumes evidence, preserves read-only trust boundaries, and produces a durable signal later V8/V9 work can evaluate.

## Patterns
- When evidence is request-level but candidate ranking is per-candidate, insert a post-selection advisory step before any predictive ranking work.
- Healthy exact-match receipts should be authority for convergence claims; Oracle neighbors stay contextual until a later contract says otherwise.
- Freeze the first evidence consumer in a dated ADR before coding, especially when the tempting next move would blur advisory behavior into policy.

## Validation
- `./scripts/ci/smoke.sh`
- `just verify-full`

## Next
- Claim `AK-341` and emit the historical convergence advisory on live `module-gen` metadata and persisted receipts without changing V7 ranking or promotion behavior.
