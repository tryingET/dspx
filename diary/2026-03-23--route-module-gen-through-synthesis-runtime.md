---
summary: "Complete AK-251 by routing module-gen through the runtime seam, validating the single candidate, and binding receipts to synthesis evidence."
read_when:
  - "You are continuing the module synthesis wave after AK-251."
  - "You need the rationale behind runtime validation/promotion receipt wiring for module-gen."
---

# 2026-03-23 — Route Module-Gen Through the Synthesis Runtime

## What I Did
- Added an executable runtime path in `dspx.synthesis.runtime` that materializes the module candidate workspace, runs static + smoke validation, marks the candidate selected/rejected, and optionally promotes it through the explicit promotion shell.
- Updated `module_service.run_generate()` so both cold renders and cache hits go through the runtime path, emit synthesis run summaries, and fail fast if the runtime validation surface ever breaks.
- Threaded `module-gen --outfile` through the runtime promotion target so the promoted artifact path is reflected in the synthesis bundle rather than only in legacy direct file writes.
- Updated module run receipts to carry the synthesis bundle plus request/candidate/evaluation/promotion IDs and run-summary fields so replay/explain has direct access to runtime evidence.
- Added regression coverage for runtime execution/promotion, module-service runtime metadata, and receipt payload enrichment.

## What Surprised Me
- The biggest workflow wrinkle was not code generation itself; it was the repo coherence check expecting a real next ready AK task in both `next_session_prompt.md` and `docs/project/operational_goals.md`.
- Passing the `outfile` into the service-level runtime seam is the cleanest way to keep the CLI stable while making the promotion boundary real for receipts.
- Revalidating cache hits through the runtime was effectively free because the deterministic module path already rebuilds a fresh synthesis bundle around cached code.

## Patterns
- If a CLI is supposed to preserve its user-facing surface while architecture changes underneath, push the new execution seam into the service layer and let the CLI only forward boundary-specific context like `outfile`.
- For synthesis work, put the human-facing summary (`run_summary`) and the raw governed evidence (`synthesis`) side by side in metadata/receipts; the summary is convenient, but the IDs and bundle are what keep replay/explain durable.
- Direction-to-execution checks are strict in DSPx: when you finish the current slice, create/export the next ready AK slice before running smoke/verify so docs and AK stay aligned.

## Validation
- `uv run pytest tests/test_synthesis_contracts.py tests/test_module_service.py tests/test_cli_dspx.py tests/test_run_receipts.py -q`
- `uv run ruff check packages/dspx-core/src/dspx/synthesis/contracts.py packages/dspx-core/src/dspx/synthesis/runtime.py packages/dspx-core/src/dspx/synthesis/__init__.py packages/dspx-core/src/dspx/services/module_service.py packages/dspx-core/src/dspx/cli/commands/module.py packages/dspx-core/src/dspx/cli/dspx.py tests/test_synthesis_contracts.py tests/test_module_service.py tests/test_run_receipts.py`
- `./scripts/ci/smoke.sh`
- `just verify-full`
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json`
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`

## Next
- `AK-256` should extend the runtime from one passing candidate to true V7 fan-out + ranking: multiple candidate manifests, ranked selection receipts, and winner handoff into the existing promotion shell.
