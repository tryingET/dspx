---
summary: "Complete AK-441 by emitting the read-only candidate-prior divergence explanation for module-gen outcomes."
read_when:
  - "You are resuming SG2 after AK-441."
  - "You need the implementation notes behind the divergence-explanation payload."
---

# 2026-03-28 — Emit Candidate-Prior Divergence Explanation

## What I Did
- Claimed `AK-441` and implemented `candidate_prior_divergence_explanation` in `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`.
- Reused the existing `candidate_prior_audit` plus trusted current ranked/evaluation metadata from the current synthesis run.
- Failed closed when the selected candidate or any compared positive-prior candidate lacked explicit rank, pass, evaluation status, or ranking score truth.
- Threaded the new explanation payload onto live `module-gen` metadata and persisted receipt diagnostics via `packages/dspx-core/src/dspx/services/module_service.py`.
- Added regression coverage for extraction, status classification, fail-closed comparison truth, module-service metadata, and persisted receipts.

## Why It Mattered
- `candidate_prior_audit` could already say that prior-supported alternatives existed, but it could not explain whether those alternatives failed current runtime checks or simply lost under current V7 scoring.
- This new read-only layer keeps evidence authority bounded while making the divergence legible enough for later SG2 governance work.
- The fail-closed comparison rules preserve the trust boundary established by `AK-388` and `AK-431` instead of fabricating partial rank/score context.

## Patterns
- When explanatory logic depends on current ranking truth, require complete explicit comparison metadata for the selected candidate and every compared alternative.
- Use audit output to choose the comparison set, then use current-run ranked/evaluation metadata only to classify outcomes.
- Keep post-selection evidence surfaces observational until a later contract explicitly widens authority.

## Validation
- `uv run ruff check packages/dspx-core/src/dspx/services/module_service.py packages/dspx-core/src/dspx/services/module_synthesis_evidence.py tests/test_module_service.py tests/test_module_synthesis_evidence.py tests/test_run_receipts.py` ✅
- `uv run pytest -q tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py` ✅
- `python scripts/check_task_scope.py --task-id 441 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Claim `AK-459`.
- Freeze the next SG2 post-divergence contract before any later evidence-authority widening.
