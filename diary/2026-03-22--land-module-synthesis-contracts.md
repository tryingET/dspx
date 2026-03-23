---
summary: "Land AK-249 by adding the initial dspx.synthesis contract package and wiring module generation to emit the bundle."
read_when:
  - "You are continuing the V9-compatible module synthesis wave from AK-250 or AK-251."
  - "You want the rationale behind the first dspx.synthesis contract landing."
---

# 2026-03-22 — Land Module Synthesis Contracts

## What I Did
- Added `packages/dspx-core/src/dspx/synthesis/` as the first synthesis package skeleton.
- Defined V9-compatible contracts for the current module-generation wave: `SynthesisRequest`, structured `ModuleSpecIR`, `CandidateRecord`, `EvaluationRecord`, `SelectionPolicy`, `PromotionDecision`, and a `SynthesisBundle` helper.
- Wired `packages/dspx-core/src/dspx/services/module_service.py` to emit the synthesis bundle into `ModuleArtifact.metadata["synthesis"]` on both fresh renders and cache hits, so the current `module-gen` surface stays stable while the runtime seam becomes explicit.
- Added tests covering the new contracts plus the enriched module-service metadata surface.

## What Surprised Me
- Cache hits were part of the seam too: without rebuilding the synthesis bundle when reading older cached module artifacts, the new contracts would have existed only on cold renders.
- The cleanest first landing was metadata-first rather than runtime-first; it preserves the existing CLI while still making request/candidate/evaluation/policy/promotion objects explicit.

## Patterns
- Contract-first synthesis work lands well when it attaches to the existing artifact boundary before introducing workspaces, promotion paths, or receipts.
- Stable IDs derived from canonical request/candidate payloads are enough for the first lineage layer; workspace-specific identifiers can arrive later without changing the top-level contract shapes.
- If a new runtime seam should apply equally to cache hits and fresh execution, make the seam a post-render enrichment step instead of burying it only in the cold path.

## Validation
- `uv run pytest tests/test_module_service.py tests/test_synthesis_contracts.py tests/test_service_caching.py tests/test_cli_dspx.py -q`
- `uv run ruff check packages/dspx-core/src/dspx/services/module_service.py packages/dspx-core/src/dspx/synthesis/__init__.py packages/dspx-core/src/dspx/synthesis/contracts.py tests/test_module_service.py tests/test_synthesis_contracts.py`
- `./scripts/ci/smoke.sh`
- `just verify-full`

## Next
- `AK-250` should build on this contract bundle to add the candidate workspace boundary, strategy metadata persistence, and an explicit promotion shell.
