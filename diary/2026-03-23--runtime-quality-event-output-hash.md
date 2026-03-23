---
summary: "Complete AK-271 by binding runtime module-quality events to the selected candidate artifact hash."
read_when:
  - "You are reviewing post-AK-266 synthesis guardrail follow-up work."
  - "You need the rationale behind runtime output-hash checks in module-quality telemetry."
---

# 2026-03-23 — Runtime Quality Event Output Hash

## What I Did
- Tightened `evaluate_module_receipt_invariants()` so runtime module-quality events now verify the returned artifact hash matches the selected candidate artifact hash in the synthesis bundle.
- Added regression coverage for both missing selected-candidate hashes and explicit output-hash drift.

## Why It Mattered
- Before this follow-up, runtime module-quality events could be structurally coherent while still failing to prove that the user-visible artifact matched the selected synthesis candidate.
- That gap would have undermined the evidence substrate work queued under `AK-263`.

## Validation
- `uv run -m pytest -q tests/test_module_synthesis_quality_runtime.py`
- `./scripts/ci/smoke.sh`
- `just verify-full`

## Next
- `AK-263` remains the active next slice.
