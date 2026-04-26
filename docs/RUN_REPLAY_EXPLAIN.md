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

## Replay command (implemented MVP)

`dspx run replay --from <receipt> --check-only` now performs local checks:
- receipt parse + schema validation (`receipt_version: v1`, required fields,
  required `replay_inputs` keys)
- output artifact existence + output hash verification
- for `program-gen`, module-surface, execution-episode, inline behavior,
  dataset split, and Oracle-readability evidence artifact verification for declared
  standalone artifacts such as `module_surfaces.json`, `execution_episode.json`,
  `behavior_results.json`, `oracle_evidence.json`, `dataset_manifest.json`,
  `splits/{train,validation,test}.jsonl`, `eval_{train,validation,test}.py`,
  and `behavior_results.{train,validation,test}.json`; replay compares
  declarations from manifest artifact fields, candidate surfaces, receipt-bundle
  evidence, surface hashes, and receipt run summary before hashing local artifacts
- cache linkage verification (`cache_key`, `cache_file`, run-kind cache folder)
- cache provenance verification (recomputed `cache_key`, cached `code` hash)
- stable machine-readable diagnostics in JSON mode:
  - `error_codes`: ordered unique replay issue codes
  - `error_details`: per-issue objects (`code`, `message`, optional `check`)

Stable replay issue codes (current v1 taxonomy):
- receipt validation: `receipt_not_found`, `receipt_invalid_json_object`,
  `receipt_missing_required_field`, `receipt_unsupported_version`,
  `receipt_unsupported_run_kind`, `receipt_invalid_output_path`,
  `receipt_invalid_hash`, `receipt_invalid_cache_key`,
  `receipt_invalid_cache_file`, `receipt_invalid_cache_enabled`,
  `receipt_invalid_replay_inputs`, `receipt_replay_inputs_missing_keys`
- output drift: `output_missing`, `output_hash_mismatch`
- cache linkage/provenance drift: `cache_linkage_basename_mismatch`,
  `cache_linkage_kind_mismatch`, `cache_key_recompute_unsupported`,
  `cache_key_mismatch`, `cache_file_missing`,
  `cache_file_invalid_json_object`, `cache_code_missing`,
  `cache_code_hash_mismatch`
- program-gen evidence drift: `program_manifest_invalid_json_object`,
  `program_evidence_artifact_missing`, `program_evidence_hash_mismatch`,
  `program_evidence_declaration_mismatch`; current declared artifact kinds include
  `module_surfaces`, `execution_episode`, `behavior_results`, `oracle_evidence`,
  `dataset_manifest`, `dataset_split_<split>`, `dataset_split_harness_<split>`, and
  `dataset_split_behavior_results_<split>` when present

Operational guarantees:
- replay command forces local/offline posture (`MLFLOW_ENABLE=0`)
- no provider/network/MLflow dependency for baseline replay verification

Exit codes:
- `0`: verification passed
- `1`: parsed receipt but drift detected
- `2`: invalid receipt/arguments

CI guard (current deterministic path):
- `uv run -q python scripts/check_replay_provenance.py`
- generates a stub-backed receipt in a temp dir,
- verifies `dspx run replay --check-only --json` passes in the clean case,
- mutates the cache payload deliberately,
- requires replay to fail clearly with `cache_code_hash_mismatch`.

## Explain command (implemented MVP)

`dspx run explain --from <receipt>` now provides local-first explanation:
- parses receipt and reports local facts (`run_kind`, provider, output/cache)
- includes replay check results as deterministic baseline facts
- carries replay status/diagnostics explicitly:
  - `replay_status` (`ok`/`failed`/`invalid`)
  - `replay_error_codes`, `replay_error_details`
- separates optional MLflow context into `mlflow_context`

Optional enrichment mode:
- `--with-mlflow` enables best-effort MLflow linkage enrichment
- local sqlite/file-store linkage is inferred from artifact names (with sqlite artifact-root fallback via MLflow experiment metadata)
- remote tracking URIs default to safe/no-network mode unless `--mlflow-remote-lookup` is set
- `--mlflow-remote-lookup` enables bounded remote candidate search (default cap/time-budget fields are reported in `mlflow_context`)
- remote lookup applies bounded MLflow HTTP request behavior (timeout budget applied, retries forced to `0`) to avoid long hangs on unreachable remotes
- deterministic diagnostics are emitted in `mlflow_context` (`degrade_reason_codes`, `reason_code_version`, `lookup_mode`)
- enrichment failures never block baseline explanation output

Exit codes:
- `0`: explanation generated (`ok` or `degraded`)
- `2`: invalid receipt/arguments
