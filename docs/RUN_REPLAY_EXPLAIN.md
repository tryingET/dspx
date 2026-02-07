---
summary: "Versioned run-receipt contract for replay/explain and its guardrails."
read_when:
  - "You are implementing replay or explain commands."
  - "You are changing .meta.json or manifest emission in CLI/services."
  - "You need to keep replay deterministic with MLFLOW_ENABLE=0."
---

# Run Replay / Explain Contract

## First principles

1. Replay must be local and deterministic.
   - Source of truth: generated artifact + receipt/manifest + cache metadata.
   - Replay cannot require MLflow or provider availability.

2. Explainability is additive.
   - MLflow may enrich traces/metrics/artifacts.
   - Missing MLflow must never block replay checks.

3. Contracts beat conventions.
   - Receipt format must be versioned.
   - Writers should be centralized to avoid per-command drift.

4. Backward compatibility matters.
   - Existing keys (`hash`, `cache_key`, `cache_file`, `cache_enabled`) remain
     top-level for older tooling.

## Multi-order effects (why this discipline exists)

- No schema versioning -> future replay migration becomes guesswork.
- Per-command bespoke metadata -> fragmented replay behavior and hidden bugs.
- Provider-coupled replay design -> offline/dev/CI reproducibility degrades.
- Overly broad receipts -> accidental secret leakage in local artifacts.
- Tight coupling to MLflow IDs -> replay breaks when tracking backends move.

## Receipt schema (v1)

Path: `<output>.meta.json`

Required fields:
- `receipt_version`: `"v1"`
- `created_at`: UTC ISO timestamp
- `run_kind`: e.g. `signature-gen`, `signature-refine`, `module-gen`, `codegen`
- `provider`: provider name used for run context
- `output_path`: artifact path
- `hash`: output content hash
- `template_version`: template/profile used for generation
- `cache_key`, `cache_file`, `cache_enabled`
- `replay_inputs`: canonical inputs needed for deterministic replay/check
- `run_summary`: optional run-quality summary payload

Optional fields:
- command-specific compatibility fields (e.g. `class_name`, `inputs`,
  `outputs`, `spec_len`, `mode`, `rounds`)

## Implementation boundary

Central module:
- `packages/dspx-core/src/dspx/run_receipts.py`

Use helpers:
- `build_run_receipt(...)`
- `write_run_receipt(output_path, receipt)`
- `load_run_receipt(meta_path)`

Current writers using this contract:
- `dspx signature gen`
- `dspx signature refine` (service emits receipt)
- `dspx module-gen`
- `dspx codegen`
- legacy `dspx.cli.codegen` service path

## Rules for future replay/explain commands

- `dspx run replay` should read receipt first, then verify:
  - output hash
  - cache linkage
  - required replay inputs
- Initial mode should be `--check-only` by default.
- `dspx run explain` should work from receipt/manifest alone and optionally
  merge MLflow context when present.
- Never require network for replay verification.
