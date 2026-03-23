---
summary: "Complete AK-256 by turning module-gen's synthesis runtime from a single-candidate validator into a ranked multi-candidate selector with receipt-visible evidence."
read_when:
  - "You are continuing the module synthesis wave after AK-256."
  - "You need the rationale behind ranked candidate fan-out, selection bonuses, and receipt extraction for module-gen."
---

# 2026-03-23 — Rank Module-Synthesis Candidates

## What I Did
- Extended `dspx.synthesis.runtime` to materialize/evaluate multiple module candidates, compute deterministic ranking scores, record ranked candidate payloads in the promotion decision/shell metadata, and only promote the winning candidate through the explicit shell.
- Expanded synthesis contracts so requests/policies can represent candidate budgets, ranked selection mode, pre-selection promotion shells, and bundle-level decision metadata for ranked receipts.
- Updated `module_service.run_generate()` to fan out deterministic module variants under the hood, return the selected winner's code to the caller, and persist ranked runtime summaries/synthesis bundles in artifact metadata.
- Exposed ranked selection metadata in module run receipts by extracting the selection policy and ranked candidate list alongside the full synthesis bundle.
- Added regression coverage for multi-candidate evaluation/promotion, service-level ranked generation, and receipt payload enrichment.

## What Surprised Me
- The biggest correctness trap was not ranking logic itself; it was making sure the code returned by `module_service` matched the candidate the runtime actually selected/promoted.
- Cache hits need deliberate handling once winner code can differ from the original seed render; regenerating deterministic seed variants from the spec keeps the ranked runtime stable even when the cache stores the prior winner.
- Pre-selection promotion shells are cleaner when they stay target-oriented first and only bind source/workspace metadata after selection.

## Patterns
- If a runtime can choose among multiple candidates, always return the chosen artifact back through the service boundary; otherwise receipts, promotion, and user-visible output silently diverge.
- Ranked synthesis receipts work best when the governed bundle keeps both the raw ordered candidate list and a compact run summary (`selected_candidate_rank`, `ranked_candidate_ids`, policy ID) for cheap inspection.
- Deterministic fan-out does not require multiple model calls to be useful; small structured render variants are enough to exercise selection/promotion contracts before introducing more expensive V8/V9 behavior.

## Validation
- `uv run pytest tests/test_synthesis_contracts.py tests/test_module_service.py tests/test_run_receipts.py -q`
- `./scripts/ci/smoke.sh`
- `just verify-full`
- `ak evidence record --task 256 --check-type validation:verify-full --result pass --details '{"commands":["./scripts/ci/smoke.sh","just verify-full"]}'`
- `ak task complete 256 --result '{"summary":"Completed ranked multi-candidate module synthesis runtime path with receipt-visible selection metadata.","next_task":260}'`
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json`
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`

## Next
- `AK-260` should harden the ranked runtime with deterministic regression fixtures/corpus coverage and CI assertions so future synthesis changes cannot silently break selection or promotion receipts.
