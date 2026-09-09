---
summary: "Historical September 3 implementation and validation notes for jury child result retention and xAI family timeouts."
read_when:
  - "Reviewing the historical child-result envelope, failure retention, or xAI timeout changes."
---

# 2026-09-03 — foundry jury: child result retention and xAI per-family timeout

Follow-up to slice D (`1ce51274`, `diary/2026-09-03--implementation-foundry-jury-fresh-subprocess-and-split.md`)
after the first live xAI run through the child. Nothing committed; no network; no provider
completion calls; no AK mutation. Lineages under `~/.local/state/pi-quests/tmp` were read only.

## Observed

- AK-5353 xAI (`misegraph-foundry-xai-5353.jrIysb`): journal `01-…/events/000004.json` ends
  `outcome_unresolved` / `error_class: transport_timeout` at the 60 s request timeout. Child exit 1,
  empty stdout; parent exit 3; no `comparison-jury-results.json`.
- AK-5350 local vLLM (`misegraph-foundry-local-vllm-5350.DoLQk8`, old in-process path): results
  file present with three `failed` juror records (`AdapterParseError`, then two
  `provider_session_terminal`), status `executed_with_failures`, stop reason
  `local_postprocessing_failed_after_closed_receipt`; the parent then failed the contract with
  "must include at least one judged juror result" (exit 2).

## Root cause, and what it means for the fix

The two lineages are different failure classes. In `run_program_model_jurors`, a
`ProgramModelJuryProviderExecutionError` with `effect_indeterminate=True` is re-raised out of the
juror loop; a closed one becomes a `failed` juror record. `outcome_unresolved` reduces to
`effect_indeterminate` (`soomfon_provider_outcome_receipt_reducer.py:271`), so AK-5353 raised
before any results object existed, in the child exactly as it would have in-process. AK-5350 was
closed, built a results object, and the in-process path wrote it before validating it. The child
printed nothing in both cases, which is what made them indistinguishable.

## What landed

- `program_foundry_gepa_comparison_jury_child.py` (330 -> 475 lines): result schema bumped to
  `dspx-foundry-jury-child-result-v2`; three closed envelope kinds bound to exit statuses:
  `jury_ok` (0, `results`), `jury_failed` (4, `results` + `error`), `jury_error` (5, `error`).
  `respond(payload)` runs the request, applies
  `validate_program_model_jury_results_contract` with the parent's label and error class
  (`classify_child_result`), and classifies. `error_payload` uses the exception's closed `reason`
  when present, else `str(exc)` through `sanitize_diagnostic_text`, capped at 2000 chars.
  Parent-side `_validate_envelope` requires the exact key set per kind, schema v2, matching exit
  status, `results` an object, and a closed `{type, message}` error (identifier type, bounded
  message); anything else is "output kind is unknown" / "output shape drifted" (exit 3).
  `child_timeout_seconds(n, family)` now takes the family.
- `program_foundry_gepa_comparison_jury.py` (414 -> 435 lines): `_run_jury` returns
  `(results, rejection | None)`; `jury_failed` writes the results then raises
  `ProgramFoundryGepaComparisonJuryError(message)`; `jury_error` raises
  `ProgramFoundryGepaComparisonJuryChildError("failed: <type>: <message>")`.
- `program_foundry_gepa_comparison_jury_provider_family.py`: `default_timeout_seconds` field
  (default 60.0); `XAI_FAMILY` 180.0. `_provider.py`: `configure_foundry_jury_provider(timeout_seconds=None)`
  defaults to and enforces the family value. `_provider_metadata.py`: expected metadata uses the
  family value. `_preflight.py`: lease margin uses the family value.
- Tests: `_child.py` (489 -> 933 lines) — drift parametrization rewritten (18 cases incl. the
  retired v1 shape, unknown kind, kind/exit mismatch, non-object results, unbounded/extra-key/
  non-identifier error payloads), `jury_failed` retention direct + CLI (exit 2, results on disk,
  replay blocked, results untouched), `jury_error` indeterminate direct + CLI (exit 3, error text
  surfaced), `respond` classification incl. bounded/redacted message and round-trip through the
  parent validator, `main` exit-status binding; family timeouts in `child_timeout_seconds`.
  `_preflight.py`: xAI lease 210/570/1110 and Copilot 90/210/390. `_xai.py`: literal 180.0,
  metadata and backend request carry 180.0, explicit wrong timeout rejected before owner load
  for xAI and Copilot.
- Doc: "Child result retention and per-family timeouts" appended to
  `docs/project/2026-09-03-foundry-jury-preflight.md`.

## Deviations

1. Added a third envelope kind, `jury_error`, beyond the requested ok/failed pair. Without it the
   AK-5353 class (no results object anywhere) would still surface only as "exited with status 1";
   with it the parent reports the closed error class and reason. It never writes a results file
   and keeps exit 3.
2. Did not synthesize failed juror records for the indeterminate class. That would require
   duplicating the results builder outside the allowed files or reaching into the custodian; the
   provider journals already retain that evidence.
3. `respond`/`classify_child_result`/`error_payload` are public on the child module so the
   classification is unit-testable without a fresh interpreter (`main` stays thin).

## Validation

- `uv run --no-sync pytest -q` over the eight named files (`_child.py` included): 286 passed
  (285 before this pass' new cases minus none removed; one new test needed a fix: the CLI leg
  needed its own lineage because the CLI request carries no `max_jurors`, so a shared lineage
  correctly reported request drift).
- `ruff format --check`/`ruff check` on the six touched src modules and three test files: clean.
  `ty check` on the six touched src modules: clean. `git diff --check`: clean.
- Archived receipts with each lineage's own `DSPX_CACHE_DIR`: AK-5346 Copilot and AK-5352 local
  vLLM validate (`status ok`, `jury_status executed`, `timeout_seconds 60.0`), sha256 of
  `comparison-jury-{attempt,results,receipt}.json` identical before/after, no `dspy_lm_auth*`
  module loaded in the validating process.

## Open items

- The next live xAI run needs an AK lease of at least 570 s for three jurors (was 210 s) and the
  child may run 600 s; the earlier dry-run figure of 210 s in the preflight doc is pre-change.
- Whether 180 s is enough for grok-4.6 on this evidence size is an empirical question; the
  journals will show `transport_timeout` again if not.
