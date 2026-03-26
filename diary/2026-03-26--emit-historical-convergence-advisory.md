---
summary: "Complete AK-341 by emitting the first SG2 historical convergence advisory on module metadata and receipts."
read_when:
  - "You are resuming SG2 work after AK-341."
  - "You need the rationale behind the historical convergence advisory implementation."
---

# 2026-03-26 — Emit Historical Convergence Advisory

## What I Did
- Claimed `AK-341` and finished the first read-only SG2 evidence consumer for `module-gen`.
- Extended `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py` so exact-match retrieval now:
  - records malformed exact-match receipt eligibility failures as bounded scan errors instead of silently dropping them,
  - distinguishes Oracle lookup states (`missing`, `available`, `unavailable`), and
  - builds the ADR-defined historical convergence advisory from replay-healthy exact-match history.
- Updated `packages/dspx-core/src/dspx/services/module_service.py` so `synthesis_diagnostics` now carries:
  - degraded retrieval status when evidence is partially broken,
  - richer evidence summary fields, and
  - `historical_convergence_advisory` on both live module metadata and persisted receipts.
- Kept artifact-identity comparison anchored on `output_hash`, while carrying `cache_key` and selected candidate identity for explanation only.
- Added regression coverage for advisory posture classification, bounded degraded evidence reporting, and the canonical default Oracle index path when `module-gen --outfile` is used.

## Why It Mattered
- `TG9` required proving that SG2 evidence can support one narrow runtime behavior before DSPx starts predictive ranking or policy mutation.
- Exact-match historical traces are only trustworthy when replay health says the prior artifact/cache linkage still holds; unhealthy receipts should remain diagnostic context, not silent scoring input.
- The advisory needs to survive on both runtime metadata and persisted receipts so later V8/V9 work consumes durable evidence artifacts instead of rediscovering history ad hoc.

## Patterns
- When an evidence surface is advisory-only, fail into explicit degraded/unavailable payloads instead of silently omitting structure.
- Separate eligibility errors from positive evidence: malformed or replay-unhealthy receipts can explain why history is weak without becoming authority.
- Reuse the existing evidence bundle for post-selection explanation so the first evidence consumer does not create a second hidden discovery path.

## Validation
- `uv run -m pytest -q tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ⚠️ blocked by pre-existing repo-wide `just typecheck` failures outside the AK-341 slice (currently `packages/dspx-core/src/dspx/cli/commands/providers.py`, `packages/dspx-core/src/dspx/cli/dspx_mermaid2dspy.py`, and `packages/dspx-core/src/dspx/tools/registry.py`)

## Next
- `TG9` is complete. Inspect the repo-scoped AK ready queue and define or claim the next SG2 execution slice before changing synthesis behavior again.
