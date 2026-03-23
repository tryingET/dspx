---
summary: "Complete AK-260 by hardening ranked module synthesis with a deterministic regression corpus, quality telemetry, and an explicit verify-full gate."
read_when:
  - "You are continuing SG1/TG4 follow-on work after AK-260."
  - "You need the rationale behind the module-synthesis corpus, selection-integrity checks, or the new verify-full quality gate."
---

# 2026-03-23 — Module-Synthesis Regression Corpus

## What I Did
- Added a deterministic ranked module-synthesis corpus (`tests/golden/module_synthesis_cases.json`) covering baseline no-signature generation, signature-backed generation, and a promoted multi-IO runtime path.
- Added corpus helpers/quality telemetry in `dspx.services.module_synthesis_corpus` and `dspx.services.module_synthesis_quality` so CI can rebuild the corpus, summarize validation/smoke/selection-integrity/receipt-coverage rates, and fail closed if any regression appears.
- Added focused regression tests for the golden corpus, module-synthesis quality summaries, and corpus-derived quality logs.
- Added `scripts/build_module_synthesis_quality_log.py` plus a `just module-synthesis-quality-check` target, then wired that target into `just verify-full` so the ranked runtime path is now explicitly guarded in the main validation gate.

## What Surprised Me
- The direction-to-execution smoke contract assumes the next ready AK slice already exists, so finishing `AK-260` cleanly also required seeding the first SG2-ready task instead of leaving the queue empty.
- The most useful regression signal was not merely "tests pass"; it was confirming selection integrity end-to-end: the selected candidate must remain rank-1, match the returned artifact code, and preserve receipt visibility.

## Patterns
- For synthesis systems, keep a deterministic corpus that exercises both the chosen artifact and the evidence explaining why it won.
- Quality telemetry for synthesis should track more than validation/smoke rates; selection-integrity and receipt-coverage rates are the real guardrails against silent contract drift.
- If `just verify-full` is the canonical pre-merge gate, wire corpus checks there directly rather than relying on developers to remember an auxiliary command.

## Validation
- `uv run -m pytest -q tests/test_module_synthesis_golden_corpus.py tests/test_module_synthesis_quality_summary.py tests/test_module_synthesis_quality_corpus.py tests/test_module_service.py tests/test_synthesis_contracts.py tests/test_run_receipts.py`
- `uv run -q python scripts/build_module_synthesis_quality_log.py`
- `just module-synthesis-quality-check`
- `./scripts/ci/smoke.sh`
- `just verify-full`

## Next
- `AK-263` should define the first SG2 tactical slice and make the receipt/replay/Oracle retrieval contract explicit before any V8-style predictive ranking work starts.
