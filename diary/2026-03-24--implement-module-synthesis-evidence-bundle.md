---
summary: "Complete AK-274 by implementing the read-only v1 module-synthesis evidence retrieval bundle."
read_when:
  - "You are resuming SG2 evidence-substrate work after AK-274."
  - "You need the rationale behind the first runtime-facing evidence retrieval helper."
---

# 2026-03-24 — Implement Module-Synthesis Evidence Bundle

## What I Did
- Claimed `AK-274` and implemented `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`.
- Added a read-only retrieval helper that:
  - freezes the request tuple from `ModuleSpec` + `use_signature`,
  - scans prior local `module-gen` receipts for exact matches under the `docs/adr/20260323-synthesis-evidence-retrieval-v1.md` eligibility rules,
  - attaches replay-health facts from `explain_run_receipt()`, and
  - pulls constrained Oracle neighbors from the coordinate index with `run_kind="module-gen"`.
- Added focused regression coverage for exact-match filtering, replay-health gating, Oracle neighbor retrieval, missing-index behavior, and `use_signature` disambiguation.
- Created `AK-278` as the next SG2 slice so the repo can now move from evidence retrieval into runtime-facing diagnostics without jumping prematurely into predictive ranking.

## Why It Mattered
- The SG2 ADR was only a contract until the repo had a concrete helper returning the bundle shape that later runtime logic can consume.
- Exact-match receipts + replay health now exist as one bounded artifact instead of three separate concepts developers would have to reconstruct ad hoc.
- Oracle stays useful but constrained: it supplies nearby context only after direct receipt and replay evidence are already in hand.

## Patterns
- When introducing evidence-aware behavior, land a read-only retrieval seam before any ranking changes.
- Replay verification should travel with receipt evidence, not as a separate optional afterthought.
- If a new evidence helper narrows future implementation choices, encode those constraints in tests immediately so later V8 work cannot silently widen the contract.

## Validation
- `uv run -m pytest -q tests/test_module_synthesis_evidence.py`
- `./scripts/ci/smoke.sh`
- `just verify-full`

## Next
- Claim `AK-278` and thread the evidence bundle into runtime diagnostics/receipts without changing ranked selection behavior.
