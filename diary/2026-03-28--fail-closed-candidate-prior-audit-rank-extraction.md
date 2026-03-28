---
summary: "Complete AK-388 by making candidate-prior audit rank reporting fail closed under metadata drift."
read_when:
  - "You are resuming after AK-388."
  - "You need the rationale behind the post-audit rank-truth guardrail fix."
---

# 2026-03-28 — Fail Closed Candidate-Prior Audit Rank Extraction

## What I Did
- Claimed `AK-388` and tightened `extract_module_synthesis_ranked_candidate_inputs()` in `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py` so the audit only consumes explicit ranked-candidate metadata.
- Stopped deriving audit rank from candidate ordinal when rank metadata is missing or invalid.
- Allowed `promotion_shell.metadata.ranked_candidates` to act as a fallback when `promotion_decision.metadata.ranked_candidates` is empty or unusable.
- Added regression coverage in `tests/test_module_synthesis_evidence.py` for empty/invalid decision-ranked payloads and for rank-omission when no trustworthy ranked metadata is available.

## Why It Mattered
- The candidate-prior audit is meant to be descriptive evidence for later SG2 decisions, so fabricated rank context is worse than missing rank context.
- Metadata drift could previously produce receipts that looked authoritative while silently substituting ordinal for true rank.
- Failing closed preserves the trust boundary between V7 selection truth and explanatory SG2 overlays.

## Patterns
- When multiple metadata surfaces can provide the same explanation field, treat empty primary data as non-authoritative and fall through to a valid fallback.
- For governance-facing diagnostics, preserve nullability instead of synthesizing plausible values from neighboring fields.
- Regression tests for evidence surfaces should include drifted, partial, and empty metadata states, not just happy-path payloads.

## Validation
- `uv run pytest tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py -q` ✅
- `python scripts/check_task_scope.py --task-id 388 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅

## Next
- Return to `AK-386`.
- Freeze the next dated SG2 contract after the completed post-selection candidate-prior audit, using the new fail-closed rank guardrail as part of the trust boundary.
