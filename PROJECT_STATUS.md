# Project Status

Current working branch: `main`.
Working tree state: dirty (pending CI signature-quality gate wiring + docs/tests sync).

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
  - `core` quality/tests + provider-corpus signature quality gate enforcement
  - `forge` quality/tests
  - forge/core wheel compatibility matrix (`latest`, `min`)
  - signature quality JSON artifact + PR-facing step summary (`signature-quality-summary`)
- Package-scoped release workflows are in place:
  - `.github/workflows/release-core.yml` (`dspx-core-v*`)
  - `.github/workflows/release-forge.yml` (`dspx-forge-v*`)
- Default provider fallback is `pi-rpc` (Codex remains available as optional provider).
- Recent branch work landed as three commits:
  - `d0a3631` (`feat(signature): add quality telemetry gates`)
  - `c2a0611` (`test(signature): add quality telemetry regressions`)
  - `b24fa13` (`docs(signature): document telemetry gates`)

## Local working-tree delta (not committed yet)

- CI core job now enforces signature provider-corpus quality gates and publishes a PR-facing summary:
  - `.github/workflows/ci.yml`
- Added deterministic provider-corpus quality helpers:
  - `packages/dspx-core/src/dspx/services/signature_quality_corpus.py`
  - `scripts/build_signature_provider_quality_log.py`
- Added regression coverage for corpus gate profile:
  - `tests/test_signature_quality_corpus.py`
- Synced docs for the above behavior:
  - `README.md`, `docs/SIGNATURE_NATIVE_PIPELINE.md`, `docs/MONOREPO_TRANSITION.md`, `docs/ARCHITECTURE.md`

## Completed recently

- Removed all git submodules (`vibe-dspy`, `attachments`, `ovllm`, `dspy`, `codex`); switched to sibling clones under `~/programming/upstream` where needed.
- Signature generation/refine now uses native DSPx implementation only (no runtime `vibe-dspy` dependency).
- Native signature pipeline upgraded:
  - spec-first generation (structured schema → deterministic code rendering)
  - provider-capability-aware prompting (`json_mode` vs non-JSON strategy)
  - validation/smoke scoring + bounded retries + best-candidate selection
  - structured refinement memory (constraints/feedback model)
- Added signature regression coverage:
  - `tests/test_signature_native_pipeline.py`
  - `tests/test_refine_service_memory.py`
  - `tests/test_signature_golden_corpus.py`
  - `tests/test_signature_provider_corpus.py`
  - `tests/test_signature_quality_summary.py`
  - `tests/test_signature_quality_corpus.py`
  - `tests/golden/signature_specs.json`
  - `tests/golden/signature_provider_cases.json`
- Operationalized signature quality telemetry and gates:
  - per-run quality metadata (fallback-used, attempts-used, validation/smoke pass rates)
  - JSONL event log (`generated/cache/signature/quality_runs.jsonl`, overridable)
  - CLI gate/report command: `dspx signature quality-summary`
  - provider-corpus gate profile + CI log builder (`scripts/build_signature_provider_quality_log.py`)
  - CI enforcement in `core` job with artifact + PR summary (`signature-quality-summary`)
  - CI thresholds sourced from `PROVIDER_CORPUS_GATE` to avoid workflow/config drift
  - run-summary emission flags for `signature gen` / `signature refine`
- Added architecture/runbook docs for the pipeline:
  - `docs/SIGNATURE_NATIVE_PIPELINE.md`
  - `README.md` / `docs/ARCHITECTURE.md` updates

## Current runtime / packaging behavior

- Install/sync workspace:
  - `uv sync`
- Core CLI:
  - `just dspx ...`
  - runs `uv run --package dspx-core -q python -m dspx.cli.dspx ...`
- Forge CLI:
  - `just forge ...`
  - runs `uv run --package dspx-forge -q python -m dspx_forge.cli ...`
- Signature generation behavior:
  - `simple-*` templates stay deterministic/no-LM
  - LM-backed native path is spec-first and capability-aware
  - bounded retry knob: `DSPX_SIGNATURE_MAX_ATTEMPTS`
  - quality telemetry knobs:
    - `DSPX_SIGNATURE_QUALITY_ENABLE`
    - `DSPX_SIGNATURE_QUALITY_LOG`
  - promotion gate/report command:
    - `dspx signature quality-summary --json --fail-on-gate`
  - CI/provider-corpus gate profile:
    - `uv run -q python scripts/build_signature_provider_quality_log.py --out generated/ci/signature_provider_quality.jsonl`
    - `dspx signature quality-summary --log-path generated/ci/signature_provider_quality.jsonl --run-kind signature-gen --json --fail-on-gate --max-fallback-rate 0.10 --max-attempts-p95 1.0 --min-validation-pass-rate 1.0 --min-smoke-pass-rate 1.0`
    - CI loads these threshold values from `dspx.services.signature_quality_corpus.PROVIDER_CORPUS_GATE`
  - per-run summary emission:
    - `dspx signature gen --summary --summary-json-out ...`
    - `dspx signature refine --summary --summary-json-out ...`
- Quality/test commands:
  - `just fmt`
  - `just lint`
  - `just typecheck`
  - `just test`
  - `just monorepo-check`
  - `just forge-core-compat-matrix`
- Live optional checks:
  - `DSPX_RUN_LIVE_TESTS=1 just pi-live-smoke`
  - `DSPX_RUN_LIVE_TESTS=1 uv run -m pytest -q tests/test_pi_rpc_provider_live.py -rs`

## Latest validation snapshot

- `pre-commit run --all-files`: passing
- `just monorepo-check`: passing
- `just test`: passing (`172 passed, 4 skipped`)

## Known gaps and immediate risks

- Strict `min` compat track still depends on remote tag hygiene:
  - keep `dspx-core-v<lower-bound>` tags present on remote (currently `dspx-core-v0.1.0`).
- Signature quality telemetry is standardized for signature/refine runs, but still not rolled out uniformly across module/codegen/mermaid services.
- CI signature gates now use deterministic provider-corpus data; runtime telemetry trend gating (rolling provider windows) is still manual/offline.

## Canonical docs

- `docs/MONOREPO_TRANSITION.md`
- `docs/MLFLOW_OBSERVABILITY_PLAN.md`
- `docs/SIGNATURE_NATIVE_PIPELINE.md`
- `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`
- `apps/forge/README.md`
- `packages/dspx-core/README.md`
- `NEXT_STEPS.md`

## Recommended posture

- Keep boundaries strict and test-enforced.
- Keep release policy independent per package.
- Keep signature pipeline hardening measurable (quality metrics + corpus growth + bounded retries).
- Prefer upstream fixes via sibling clones + upstream PRs over adding new heavy submodules.
