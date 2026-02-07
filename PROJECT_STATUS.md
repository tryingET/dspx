# Project Status

Current working branch: `main`.

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
  - `core` quality/tests
  - `forge` quality/tests
  - forge/core wheel compatibility matrix (`latest`, `min`)
- Package-scoped release workflows are in place:
  - `.github/workflows/release-core.yml` (`dspx-core-v*`)
  - `.github/workflows/release-forge.yml` (`dspx-forge-v*`)
- Default provider fallback is `pi-rpc` (Codex remains available as optional provider).

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
  - `tests/golden/signature_specs.json`
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
- `just test`: passing (`163 passed, 4 skipped`)

## Known gaps and immediate risks

- Strict `min` compat track still depends on remote tag hygiene:
  - keep `dspx-core-v<lower-bound>` tags present on remote (currently `dspx-core-v0.1.0`).
- Signature quality telemetry is not yet standardized across services:
  - fallback-rate / attempts-used trend reporting should be promoted to first-class CI visibility.
- Signature hardening is currently deepest in signature/refine paths; equivalent quality contracts are not yet rolled out uniformly to module/codegen/mermaid outputs.

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
