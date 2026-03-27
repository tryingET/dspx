---
summary: "Complete AK-357 by hardening advisory evidence resolution semantics, failure-shape stability, and provenance-root coherence."
read_when:
  - "You are resuming SG2 evidence hardening after AK-357."
  - "You need the rationale behind the advisory evidence-resolution fixes."
---

# 2026-03-26 — Harden Advisory Evidence Resolution

## What I Did
- Claimed `AK-357` as an operator-directed follow-up to the `AK-341` advisory rollout.
- Hardened `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py` so advisory status no longer treats malformed/unreadable receipt history as clean `no_history`.
- Added bounded receipt scan errors for unreadable JSON/object failures instead of silently dropping those files during retrieval.
- Updated `packages/dspx-core/src/dspx/services/module_service.py` so unavailable evidence retrieval keeps the same top-level diagnostics shape (`evidence_summary`, `evidence_bundle`, advisory payload) instead of shrinking under failure.
- Aligned the default Oracle index root with `promotion_target.parent` when `module-gen --outfile` writes outside the current working directory, so receipt history and Oracle context stop drifting across roots by default.
- Added regression coverage for malformed structured receipts, invalid JSON receipts, unavailable retrieval shape stability, and out-of-cwd Oracle root alignment.

## Why It Mattered
- `AK-341` proved the advisory surface, but adversarial review showed that bad evidence still masqueraded as missing evidence.
- A read-only signal that says `no_history` when history is damaged will later poison predictive work if TG10 consumes it as a prior.
- Failure paths should not change diagnostics schema; operators need the same surface when evidence is least trustworthy.

## Patterns
- Treat unreadable evidence as degraded state, not absence.
- Keep diagnostics payloads shape-stable across success and failure paths.
- Default provenance roots must align across evidence surfaces unless divergence is explicit in the payload.

## Validation
- `uv run -m pytest -q tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ⚠️ expected to remain blocked by pre-existing repo-wide `just typecheck` failures outside the AK-357 slice

## Next
- `AK-356` remains the next ready SG2 planning slice: freeze the first evidence-backed candidate-prior contract before predictive ranking changes.
