# Project Status

Current working branch: `main`.
Working tree state: dirty (run replay+explain MVP implementation + docs/tests updates not committed yet).

## Snapshot

- Monorepo split is active and enforced.
  - Core package: `packages/dspx-core/src/dspx`
  - Forge app package: `apps/forge/src/dspx_forge`
- Root `pyproject.toml` is workspace-only:
  - `[tool.uv.workspace] members = ["packages/dspx-core", "apps/forge"]`
- Boundary rule is active and tested:
  - allowed: `apps/* -> core`
  - forbidden: `core -> apps/*` (no `dspx_forge.*` imports from core)
- CI is package-aware and split:
  - workspace smoke + hygiene
  - `core` quality/tests + signature provider-corpus gate enforcement
  - `forge` quality/tests
  - forge/core wheel compatibility matrix (`latest`, `min`)
  - signature quality artifact + PR-facing summary (`signature-quality-summary`)
- Package-scoped release workflows are in place:
  - `.github/workflows/release-core.yml` (`dspx-core-v*`)
  - `.github/workflows/release-forge.yml` (`dspx-forge-v*`)
- Default provider fallback is `pi-rpc` (Codex remains optional provider).
- Latest branch commits:
  - `ac331a3` (`docs(replay): sync replay status and roadmap`)
  - `045f03e` (`test(replay): cover replay drift outcomes`)
  - `12c11f5` (`feat(run): add check-only replay verifier`)
  - `f8cfe00` (`docs(replay): document receipt-first replay plan`)
  - `ede761e` (`test(replay): cover receipt schema emission`)

## Completed on this branch

- Signature generation/refine is native DSPx (no runtime `vibe-dspy` dependency).
- Native signature pipeline hardened:
  - spec-first generation (schema -> deterministic render)
  - provider-capability-aware prompting (`json_mode` vs non-JSON)
  - validation/smoke scoring + bounded retries + best-candidate selection
  - structured refinement memory
- Signature telemetry + gates implemented:
  - per-run quality metadata
  - JSONL event log (`generated/cache/signature/quality_runs.jsonl`)
  - `dspx signature quality-summary`
  - run summaries for `signature gen` / `signature refine`
- Provider-shaped coverage extended:
  - parser/renderer corpus tests
  - deterministic provider-corpus gate profile
  - CI gate enforcement + artifact + PR summary
- Supporting additions landed:
  - `packages/dspx-core/src/dspx/services/signature_quality_corpus.py`
  - `scripts/build_signature_provider_quality_log.py`
  - `tests/test_signature_quality_corpus.py`
  - doc updates in architecture/monorepo/signature pipeline/status docs
- Replay/explain UX advanced to first-class `dspx run` commands:
  - replay verifier: `dspx run replay --from <receipt> --check-only`
  - local-first explain: `dspx run explain --from <receipt> [--with-mlflow]`

## Local working-tree delta (not committed yet)

- Added first-class explain service:
  - `packages/dspx-core/src/dspx/services/run_explain_service.py`
- Extended `dspx run` CLI surface in core:
  - `dspx run explain --from <receipt> [--with-mlflow]`
  - implemented in `packages/dspx-core/src/dspx/cli/dspx.py`
- Extended replay/explain behavior coverage:
  - `tests/test_run_receipts.py`
  - includes explain local-first, optional MLflow enrichment, invalid receipt cases
- Synced user/operator docs to current behavior:
  - `README.md`
  - `docs/TUTORIAL_E2E.md`
  - `docs/RUN_REPLAY_EXPLAIN.md`
  - `docs/ARCHITECTURE.md`
  - `docs/VISION.md`
  - `PROJECT_STATUS.md`
  - `NEXT_STEPS.md`

## Current runtime / packaging behavior

- Install/sync workspace:
  - `uv sync`
- Core CLI:
  - `just dspx ...`
  - runs `uv run --package dspx-core -q python -m dspx.cli.dspx ...`
- Forge CLI:
  - `just forge ...`
  - runs `uv run --package dspx-forge -q python -m dspx_forge.cli ...`
- Signature behavior:
  - `simple-*` templates: deterministic/no-LM
  - native LM-backed path: spec-first, validation-gated, bounded retries
  - quality telemetry knobs:
    - `DSPX_SIGNATURE_QUALITY_ENABLE`
    - `DSPX_SIGNATURE_QUALITY_LOG`
  - gate/report command:
    - `just dspx signature quality-summary --json --fail-on-gate`
  - CI provider-corpus profile:
    - build log: `uv run -q python scripts/build_signature_provider_quality_log.py --out generated/ci/signature_provider_quality.jsonl`
    - evaluate: `just dspx signature quality-summary --log-path generated/ci/signature_provider_quality.jsonl --run-kind signature-gen --json --fail-on-gate --max-fallback-rate 0.10 --max-attempts-p95 1.0 --min-validation-pass-rate 1.0 --min-smoke-pass-rate 1.0`
- Module + optimization flows available via core CLI:
  - `just dspx module-gen ...`
  - `just dspx optimize gepa ...`
- Replay/explain posture (current local state):
  - replay source-of-truth: local artifacts + manifests + cache metadata +
    versioned run receipts (`*.meta.json`, `receipt_version: v1`)
  - receipt writer/loader centralized in `dspx.run_receipts`
  - commands emitting v1 receipts: signature gen/refine, module-gen, codegen
  - first-class replay verifier: `dspx run replay --from <receipt> --check-only`
  - replay verifier checks: receipt schema + output hash + cache linkage/provenance
  - replay verifier exit codes: `0` pass, `1` drift, `2` invalid receipt/args
  - first-class explain command: `dspx run explain --from <receipt>`
  - explain output is local-first (`local_facts`, `replay_checks`) with optional
    `--with-mlflow` enrichment in separate `mlflow_context`
  - MLflow enrichment mode is best-effort; local file-store linkage supported,
    remote URI enrichment degrades gracefully
  - explain exit codes: `0` (`ok`/`degraded`), `2` invalid receipt/args
  - MLflow remains optional explainability sink, never execution gate

## Latest validation snapshot

- `pre-commit run --all-files`: passing (rerun on current tree)
- `just monorepo-check`: passing (rerun on current tree)
- `just test`: passing (`181 passed, 4 skipped`, rerun on current tree)
- `just typecheck`: passing (rerun on current tree)

## Known gaps and immediate risks

- Replay checker and explain MVP are shipped, but execution/strictness remains:
  - `dspx run replay --check-only` exists
  - `dspx run replay --no-check-only` intentionally not implemented yet
  - replay drift taxonomy and strict mode still need hardening
- Replay cache-key/provenance logic should be audited for LM/legacy signature
  paths to avoid false drift in mixed historical artifacts.
- Explain MLflow enrichment is best-effort and local-file-store-oriented;
  remote run linkage/enrichment is not yet implemented.
- Receipt contract is standardized for key generators, but remaining producers
  (e.g. other manifest/metadata paths) still need explicit coverage audit.
- Signature telemetry is standardized for signature/refine, but equivalent
  quality contracts are not yet rolled out across module/codegen/mermaid.
- Runtime telemetry thresholds still need longer live/provider trend windows
  (pi-rpc/openrouter/codex/claude/gemini) before tightening defaults.
- Strict `min` compat track still depends on remote lower-bound tag hygiene
  (keep `dspx-core-v<lower-bound>` tags present on remote).

## Canonical docs

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/SIGNATURE_NATIVE_PIPELINE.md`
- `docs/MONOREPO_TRANSITION.md`
- `docs/MLFLOW_OBSERVABILITY_PLAN.md`
- `docs/RUN_REPLAY_EXPLAIN.md`
- `PROJECT_STATUS.md`
- `NEXT_STEPS.md`

## Recommended posture

- Keep boundary guardrail strict and continuously tested.
- Keep local-native signature/module/GEPA loop as product center.
- Keep replay artifact-first and explainability optional.
- Keep docs synchronized with real CLI behavior after each scoped change.
