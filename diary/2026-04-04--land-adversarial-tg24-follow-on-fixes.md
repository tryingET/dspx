---
summary: "Implement AK-729 by landing the highest-leverage adversarial TG24 follow-on fixes across receipts, MLflow explain, multi-provider sync isolation, OpenAPI numerics, and AK wrapper fallback."
read_when:
  - "You are resuming after AK-729 implementation."
  - "You need the rationale and validation story for the post-review TG24 follow-on slice."
---

# 2026-04-04 — Land Adversarial TG24 Follow-On Fixes

## What I Did
- Materialized and claimed `AK-729` as an operator-directed adversarial follow-on after the deep TG24 review surfaced concrete hidden failure modes.
- Hardened exact-match SG2 receipt validation so wrong-type governed-policy and run-summary fields fail closed instead of surviving through string/int coercion.
- Relaxed local MLflow explain tag matching to accept compatible partial historical tag sets while still rejecting contradictory tags, and fixed required-artifact matching so nested local artifact paths no longer create false negatives.
- Removed the sync-provider `cwd` race in `parallel_first` by moving sync-worker `cwd` overrides/restores inside the worker thread instead of restoring provider state in the main thread before the slow worker finishes.
- Centralized OpenAPI numeric contract enforcement into a shared numeric-schema validator so query/path parameters, array items, and JSON bodies now all enforce `multipleOf` consistently in addition to bounds.
- Fixed the repo-local AK wrapper default path so it now prefers a working PATH `ak` before the broken workspace-core cargo launcher when no override or vendored CLI exists, which restores truthful default `smoke` / `verify-full` behavior on this machine.
- Exported `governance/task-scopes/AK-729.snapshot.json` and refreshed the checked-in work-items projection.

## Why It Mattered
- The deep review found that TG24 was green on its canonical fixtures but still vulnerable to wrong-type evidence fields, historical MLflow layout drift, sync-thread isolation races, and a broken default validation path.
- Those gaps directly undercut the trust model for SG2 receipts/replay/explain even though the earlier TG24 slices had already landed.
- Fixing them in one bounded follow-on slice is the closest practical implementation of the review's NEXUS intervention without prematurely expanding into a broader TG25 contract wave.

## Risk Boundaries
- No live policy widening: the slice only tightens/repairs existing boundary behavior.
- No tactical-goal churn: `TG25` stays active, and this operator-directed follow-on only closes adversarial regressions discovered after `TG24` landed.
- No silent validation folklore: the default repo-local AK wrapper path now self-heals toward the installed CLI instead of requiring an `AK_BIN=ak` operator workaround on this machine.

## Validation
- `uv run --no-sync -m pytest -q tests/test_module_synthesis_evidence.py tests/test_run_receipts.py tests/test_multi_provider_parallel_semantics.py tests/test_openapi_numeric_bounds.py` ✅
- `uvx ruff check packages/dspx-core/src/dspx/services/module_synthesis_evidence.py packages/dspx-core/src/dspx/services/run_explain_service.py packages/dspx-core/src/dspx/multi_provider_lm.py packages/dspx-core/src/dspx/tools/openapi/caller.py tests/test_module_synthesis_evidence.py tests/test_run_receipts.py tests/test_multi_provider_parallel_semantics.py tests/test_openapi_numeric_bounds.py` ✅
- `uvx ty check packages/dspx-core/src/dspx/services/module_synthesis_evidence.py packages/dspx-core/src/dspx/services/run_explain_service.py packages/dspx-core/src/dspx/multi_provider_lm.py packages/dspx-core/src/dspx/tools/openapi/caller.py` ✅
- `just task-scope-check 729 working-tree auto` ✅ (repo-default snapshot skip)
- `./scripts/ci/smoke.sh` ✅ (now passes without `AK_BIN=ak` workaround)
- `just verify-full` ✅
- One-off repro harnesses for wrong-type receipts, partial/nested MLflow histories, sync-provider `cwd` isolation, and query `multipleOf` enforcement ✅
- `./scripts/ak.sh task complete 729 --result '{...}'` ✅
- `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Keep `TG25` as the active tactical wave, but do not guess its first repo-local slice until AK truthfully names it or the operator directs it.
- Preserve the new adversarial regressions as the minimum bar for future receipt/replay/explain and isolation changes.
