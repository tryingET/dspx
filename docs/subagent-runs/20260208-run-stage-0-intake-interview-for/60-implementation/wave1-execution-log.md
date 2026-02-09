# Wave 1 execution log (DSPx foundation)

Date: 2026-02-08
Run: `20260208-run-stage-0-intake-interview-for`

## Implemented in codebase

1. Correlation tags hardening (`dspx.*`)
- `packages/dspx-core/src/dspx/tracing.py`
  - `standard_tags()` now emits normalized:
    - `dspx.run_kind`
    - `dspx.template_version`
    - `dspx.output_basename`
    - `dspx.cache_key`
    - `dspx.output_hash_prefix`
  - legacy tags preserved (`service`, `template_version`, `provider`, `run_group`).
  - `ensure_run_with_standard_tags()` extended with correlation inputs.

2. Receipt-side MLflow hints (additive)
- `packages/dspx-core/src/dspx/run_receipts.py`
  - added `build_mlflow_hints(...)` helper.
- Receipt writers updated:
  - `packages/dspx-core/src/dspx/cli/dspx.py`
  - `packages/dspx-core/src/dspx/services/refine_service.py`
  - `packages/dspx-core/src/dspx/services/codegen_service.py`
- Receipts now include additive `mlflow_hints` block for explain correlation.

3. Explain diagnostics + remote lookup control
- `packages/dspx-core/src/dspx/services/run_explain_service.py`
  - deterministic `mlflow_context` diagnostics fields:
    - `lookup_mode`
    - `degrade_reason_codes`
    - `reason_code_version` (`v1`)
    - `candidate_count`, `matched_count`
    - remote budget/cap telemetry fields
  - bounded remote lookup path implemented behind explicit flag.
- `packages/dspx-core/src/dspx/cli/dspx.py`
  - new option: `--mlflow-remote-lookup` for `dspx run explain`.

## Tests added/updated

- `tests/test_mlflow_tracking_uri_modes.py`
  - added correlation tag contract test.
- `tests/test_run_receipts.py`
  - asserts `mlflow_hints` presence in receipts.
  - asserts new `mlflow_context` fields.
  - added remote default-off and remote-lookup-flag explain tests.

## Docs updated

- `README.md`
- `docs/RUN_REPLAY_EXPLAIN.md`
- `docs/MLFLOW_OBSERVABILITY_PLAN.md`

## Quality gates

Executed successfully:
- `just fmt`
- `just lint`
- `just typecheck`
- `just test`

Result: `196 passed, 4 skipped`
