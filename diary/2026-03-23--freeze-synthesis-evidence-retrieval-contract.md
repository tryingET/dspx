---
summary: "Complete AK-263 by freezing the first SG2 receipt/replay/Oracle retrieval contract for ranked synthesis."
read_when:
  - "You are resuming SG2 evidence-substrate work after AK-263."
  - "You need the rationale behind the v1 synthesis evidence retrieval bundle."
---

# 2026-03-23 — Freeze Synthesis Evidence Retrieval Contract

## What I Did
- Claimed `AK-263` and wrote `docs/adr/20260323-synthesis-evidence-retrieval-v1.md` to freeze the first SG2 evidence bundle for ranked module synthesis.
- Chose a strict V1 retrieval order: exact-match `module-gen` synthesis receipts first, replay verification facts second, Oracle neighbors third.
- Made replay health an explicit trust boundary: degraded receipts may remain visible for diagnostics, but they are not positive evidence for later ranking/pruning.
- Created the next execution-ready AK slice (`AK-274`) so the repo now moves directly from SG2 planning into a concrete implementation task instead of stopping at architecture prose.
- Advanced project planning docs from `TG5` to `TG6` so the active operating slice now points at the v1 evidence-bundle implementation rather than the contract-definition step.

## Why It Mattered
- `AK-260`, `AK-266`, and `AK-271` hardened the ranked runtime path enough that the next risk was no longer missing guardrails; it was evidence-surface ambiguity.
- Without a frozen retrieval contract, any future V8-facing work could pick different receipt/replay/Oracle subsets and silently drift the meaning of "evidence-backed synthesis."
- Making replay verification a first-class gate protects future ranking work from building on stale or drifted receipts.

## Patterns
- When moving from V7 operational synthesis to V8 evidence-aware synthesis, freeze the retrieval contract before writing ranking logic.
- Use exact request matching as the first trust anchor; semantic neighbors are useful context, but they should not outrank direct receipt lineage in the first iteration.
- If a planning slice is completed successfully, leave behind the next ready AK task immediately so the operating plan stays executable.

## Validation
- `./scripts/ci/smoke.sh`
- `just verify-full`

## Next
- Claim `AK-274` and implement the read-only evidence retrieval bundle under `docs/adr/20260323-synthesis-evidence-retrieval-v1.md`.
