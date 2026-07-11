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

## Receipt schema (v2)

Path: `<output>.meta.json`

Required fields:
- `receipt_version`: `"v2"`
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
- `execution_replay`: emitted on new receipts; binds local execution support to
  input/provider/runtime/output identities and exact permitted effects. Older v2
  receipts remain valid for check-only but fail closed for execution.
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
- `dspx program-run` (`program-runtime`; replay support requires explicit fixture capture)
- legacy `dspx.cli.codegen` service path

## Replay command (implemented MVP)

`dspx run replay --from <receipt> --check-only` now performs local checks:
- receipt parse + schema validation (`receipt_version: v2`, required fields,
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
- execution replay: `execution_replay_unsupported_kind`,
  `execution_replay_unsupported_provider`, `execution_replay_unsupported_inputs`,
  `execution_replay_policy_missing`, `execution_replay_unsupported_effects`,
  `execution_replay_identity_drift`, `execution_replay_process_failed`,
  `execution_replay_unexpected_effect`, `execution_replay_output_invalid`,
  `execution_replay_output_exists`, `execution_replay_output_hash_mismatch`,
  `execution_replay_write_failed`

Operational guarantees:
- replay command forces local/offline posture (`MLFLOW_ENABLE=0`)
- no provider/network/MLflow dependency for baseline replay verification

### Safe local execution replay

`dspx run replay --from <receipt> --no-check-only --to <new-file>` supports
receipt-bound replay for deterministic, stub-backed, `simple-*` `signature-gen`
runs. It does not import or execute generated Python. After the complete check-only
gate passes, it re-runs the real signature generation command in a scrubbed local
subprocess with cache and MLflow disabled, verifies the fresh child receipt and
output identity, then exclusively publishes the result to the explicit
receipt-local `--to` path. Temporary artifacts are removed. The report has
`status: executed` and an `execution-replay-evidence-v1` object with bound
input/provider/runtime/output hashes and hashed subprocess diagnostics.

The v1 strategy is `signature-gen-local-reexecution`. The child uses isolated Python startup (`-I`) and a small allowlisted environment; inherited Python/loader injection variables are removed. The executor requests only the subprocess, temporary filesystem, and explicit replay output write. It does not request network, provider, MLflow, source-write, shared-Oracle, or external-authority effects. This is not an OS network/filesystem sandbox, so the receipt truthfully records that network and external-filesystem isolation are not enforced. Receipt compatibility binds to the versioned executor policy, Python major/minor, and platform rather than source-file bytes or Python patch versions. Execution replay fails closed when:

- the receipt/output/cache check detects any drift;
- the run kind, provider, template, or options have no deterministic executor;
- the receipt lacks the execution policy or its strategy/effects differ at all;
- input, provider, runtime, output, child receipt, or child output identity drifts;
- the sandbox emits any undeclared file;
- `--to` escapes the receipt directory, names a receipt/source/cache file, or
  already exists; publication traverses receipt-local directories with no-follow
  file descriptors and creates the final file exclusively.

Check-only remains the default and does not require execution replay support, so
all existing supported receipt kinds retain their non-mutating verification path.

### Receipt-bound generated-program execution replay

`program-run` now always writes `runtime_episode.json.meta.json`. By default the receipt contains hashes, paths, runtime identity, behavior status, and non-authority posture but is **not execution-replay enabled**, because runtime inputs and provider output can be sensitive.

For an explicitly replayable, local stub-backed episode, the operator must opt in:

```bash
DSPX_PROVIDER=stub \
DSPX_STUB_RESPONSE_JSON='{"reasoning":"...","answer":"..."}' \
  dspx program-run \
  --manifest /path/to/candidate/manifest.json \
  --inputs /path/to/inputs.json \
  --outdir /path/to/runtime \
  --contract-mode pdf_transition_review \
  --skip-oracle-index \
  --capture-replay-fixture

dspx run replay \
  --from /path/to/runtime/runtime_episode.json.meta.json \
  --no-check-only \
  --to replay-evidence.json
```

`--capture-replay-fixture` is an explicit retention decision. It writes `runtime_replay_fixture.json` with mode `0600`, containing the bounded runtime inputs and stub response required for deterministic reproduction. The receipt stores only the fixture path/hash, never those raw payloads. Secret-shaped inputs or stub diagnostics fail closed before fixture creation. Delete the fixture to revoke execution replay; check-only receipt verification remains available but execution replay then fails current-evidence validation.

The `program-runtime-local-reexecution` strategy is limited to provider `stub`, the explicit `none` or `pdf_transition_review` contract modes, `--skip-oracle-index`, no publication preflight, and a current mode-0600 receipt-local replay fixture. Unknown or downgraded contract modes fail closed. It validates the original candidate receipt and runtime bundle, copies and revalidates the candidate in a private sandbox, executes only that snapshot under isolated Python with a scrubbed environment, and exclusively writes a receipt-local `program-execution-replay-evidence-v2` packet. The child requests no network, shared Oracle, MLflow, AK, governance, promotion, activation, or external-authority effects. OS network/external-filesystem isolation is not claimed as enforced.

Execution reproduction, review-contract validity, and declared quality remain separate. Evidence reports the receipt-bound `contract_mode`, underlying `execution_status`, final `behavior_status`, `quality_status`, and canonical quality-evaluation hash. It may truthfully report `status: execution_reproduced` for a quality or review-boundary failure; `behavior_quality_approved` always remains false. Replaying an episode never grants PDF-domain acceptance, promotion, or activation.

Exit codes:
- `0`: verification passed or execution replay completed
- `1`: parsed receipt but drift or an output conflict/write failure was detected
- `2`: invalid receipt/arguments, unsupported kind, or unsupported effects/policy

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
- unset `MLFLOW_TRACKING_URI` is unconfigured: enrichment reports `mlflow_tracking_uri_missing` and DSPx does not create a local sqlite fallback
- explicit sqlite linkage uses MLflow metadata plus local artifact roots (including sqlite artifact-root fallback via MLflow experiment metadata); filesystem artifact scanning does not make filesystem tracking a supported backend
- remote tracking URIs default to safe/no-network mode unless `--mlflow-remote-lookup` is set
- `--mlflow-remote-lookup` enables bounded remote candidate search (default cap/time-budget fields are reported in `mlflow_context`)
- remote lookup applies bounded MLflow HTTP request behavior (timeout budget applied, retries forced to `0`) to avoid long hangs on unreachable remotes
- deterministic diagnostics are emitted in `mlflow_context` (`degrade_reason_codes`, `reason_code_version`, `lookup_mode`)
- enrichment failures never block baseline explanation output

Exit codes:
- `0`: explanation generated (`ok` or `degraded`)
- `2`: invalid receipt/arguments
