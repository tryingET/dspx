---
summary: "Complete AK-250 by adding the module synthesis runtime shell: strategy persistence, candidate workspaces, and explicit promotion boundaries."
read_when:
  - "You are continuing the V9-compatible module synthesis wave from AK-251."
  - "You want the rationale behind the first materialized synthesis runtime shell."
---

# 2026-03-23 — Add Module Synthesis Runtime Shell

## What I Did
- Extended `dspx.synthesis` contracts with explicit runtime-shell structures: `StrategyRecord`, `CandidateWorkspace`, and `PromotionShell`.
- Added `packages/dspx-core/src/dspx/synthesis/runtime.py` to materialize per-candidate scratch workspaces, persist strategy/candidate manifests, and promote only the explicitly selected artifact.
- Wired `packages/dspx-core/src/dspx/services/module_service.py` to emit a materialized synthesis bundle on both fresh renders and cache hits so the current `module-gen` surface stays stable while runtime boundaries become real.
- Added tests covering workspace materialization, strategy persistence, and explicit promotion behavior alongside the enriched module-service metadata surface.

## What Surprised Me
- The most useful first runtime shell is still metadata-led: the service can stay UX-stable while the synthesis seam grows real files, manifests, and promotion paths behind it.
- Promotion becomes much clearer when represented as a separate shell object instead of only a withheld decision; it gives the next slice a concrete place to hang receipt-writing and selection-time execution.
- Cache hits need the same workspace/promotion structure as cold renders, otherwise the runtime seam would only exist for first execution and disappear on replayed paths.

## Patterns
- For V7-first synthesis work, materialize candidate state in scratch space early even if selection is still one-candidate; it keeps later multi-candidate work additive instead of requiring a contract rewrite.
- Persist strategy metadata next to the candidate manifest, not only in top-level artifact metadata, so the runtime shell can be inspected independently from the final artifact boundary.
- Keep promotion a distinct shell that points at both scratch and target paths; this preserves the governance boundary even when the current implementation is still single-candidate.

## Validation
- `uv run pytest tests/test_synthesis_contracts.py tests/test_module_service.py tests/test_service_caching.py tests/test_cli_dspx.py tests/test_run_receipts.py -q`
- `uv run ruff check packages/dspx-core/src/dspx/synthesis/contracts.py packages/dspx-core/src/dspx/synthesis/runtime.py packages/dspx-core/src/dspx/synthesis/__init__.py packages/dspx-core/src/dspx/services/module_service.py tests/test_synthesis_contracts.py tests/test_module_service.py`
- `./scripts/ci/smoke.sh`
- `just verify-full`
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json`
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`

## Next
- `AK-251` should route `module-gen` through this runtime shell so static/smoke validation and run receipts bind to the new candidate/evaluation/promotion objects instead of the legacy direct service path.
