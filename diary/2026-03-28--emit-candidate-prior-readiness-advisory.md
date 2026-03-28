---
summary: "Complete AK-462 by emitting the read-only candidate-prior readiness advisory for module-gen outcomes."
read_when:
  - "You are resuming SG2 after AK-462."
  - "You need the implementation notes behind the readiness-advisory payload and historical diagnostics hardening."
---

# 2026-03-28 — Emit Candidate-Prior Readiness Advisory

## What I Did
- Claimed `AK-462` and implemented `candidate_prior_readiness_advisory` in `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`.
- Added a bounded historical-diagnostics capsule to exact-match receipt evidence so replay-healthy historical receipts now expose persisted `candidate_prior_audit` and `candidate_prior_divergence_explanation` payloads through retrieval.
- Tightened TG15 fail-closed behavior so malformed `non_selected_positive_prior_candidates` entries no longer get silently dropped during divergence explanation.
- Materialized the readiness advisory on live `module-gen` metadata and persisted receipts via `packages/dspx-core/src/dspx/services/module_service.py`.
- Added deterministic readiness thresholds (minimum usable history, minimum positive-prior signal, dominant divergence thresholds) and documented them in the readiness ADR.
- Added regression coverage for historical diagnostics extraction, malformed comparison sets, readiness status rollups, module-service metadata, and persisted receipts.

## Why It Mattered
- `TG16` defined a governance-facing readiness advisory, but the historical retrieval layer still lacked a bounded way to expose the persisted audit/divergence payloads that the advisory needed.
- Without that substrate hardening, `AK-462` would have had to reopen raw receipts ad hoc or silently skip malformed historical state.
- The readiness advisory now stays observational while giving SG2 a receipt-backed signal about whether candidate priors are convergent, mostly blocked by runtime failures, mostly outscored under V7, still sparse, or unavailable due to malformed historical truth.

## Patterns
- Before adding a higher-order SG2 rollup, expose the required persisted diagnostics through the historical retrieval bundle explicitly.
- Treat malformed members inside evidence collections as a fail-closed condition, not as items to silently filter away.
- When an ADR uses qualitative words like `too few` or `mostly`, crystallize them into deterministic thresholds before implementation ships.

## Validation
- `uv run ruff check packages/dspx-core/src/dspx/services/module_synthesis_evidence.py packages/dspx-core/src/dspx/services/module_service.py tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py` ✅
- `uv run pytest -q tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py` ✅
- `python scripts/check_task_scope.py --task-id 462 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 462 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Claim `AK-466`.
- Freeze the next SG2 contract after the read-only readiness advisory before any later evidence-authority widening.
