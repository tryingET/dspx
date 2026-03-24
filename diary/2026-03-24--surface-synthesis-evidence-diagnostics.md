---
summary: "Complete AK-278 by surfacing the v1 module-synthesis evidence bundle in runtime diagnostics and module-gen receipts."
read_when:
  - "You are resuming SG2 work after AK-278."
  - "You need the rationale behind synthesis_diagnostics on module artifacts or module-gen receipts."
---

# 2026-03-24 — Surface Synthesis Evidence Diagnostics

## What I Did
- Claimed `AK-278` and threaded the v1 evidence bundle into `packages/dspx-core/src/dspx/services/module_service.py` as bounded `synthesis_diagnostics` metadata.
- Kept ranking behavior unchanged: the synthesis runtime still selects candidates exactly as before; diagnostics retrieval runs read-only alongside the existing path.
- Extended `packages/dspx-core/src/dspx/cli/commands/module.py` so `module-gen` receipts persist the new diagnostics payload next to the existing synthesis receipt fields.
- Added regression coverage proving:
  - runtime metadata exposes the evidence request/bundle shape,
  - the first receipt records empty diagnostics when no prior matching receipt exists, and
  - a follow-up run surfaces the earlier matching receipt as diagnostic evidence without counting the current run yet.

## Why It Mattered
- `AK-274` made evidence retrievable, but later V8/V9 work still needed a stable runtime seam so callers do not have to rediscover receipts/replay/Oracle history ad hoc.
- Putting the bundle into both artifact metadata and persisted receipts makes the evidence substrate observable from the live runtime path and replayable after the fact.
- Because diagnostics stay read-only, this closes the SG2 consumption gap without prematurely introducing predictive ranking or policy mutation.

## Patterns
- When an evidence helper graduates from substrate to runtime use, expose it through a named diagnostics surface before letting it influence selection.
- Receipt plumbing should carry the same diagnostics contract the runtime saw so later consumers can reuse evidence artifacts instead of re-running discovery logic by default.
- Keep the first runtime-facing evidence seam bounded and summary-friendly (`evidence_summary` + `evidence_bundle`) so later slices can extend consumers without changing selection semantics.

## Validation
- `uv run -m pytest -q tests/test_module_service.py tests/test_run_receipts.py -k 'module_service_simple or cli_meta_receipts_are_versioned'`
- `./scripts/ci/smoke.sh`
- `just verify-full`

## Next
- Define the next SG2 tactical/AK slice before coding again; do not jump straight into predictive ranking without an explicit contract for the next evidence-consuming behavior.
