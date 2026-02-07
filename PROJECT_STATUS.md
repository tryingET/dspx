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
- Forge/core pytest slicing uses explicit marker-based selection:
  - `just test-core` => `pytest -m "not forge"`
  - `just test-forge` => `pytest -m "forge"`
- Read-only core CLI metadata paths now skip MLflow bootstrap (offline/instant behavior even when `config.toml` has remote tracking URI).

## Completed recently

- Migrated from brittle name-based test slicing (`-k`) to explicit `pytest.mark.forge` slices.
- Added pytest marker registry in `pyproject.toml`.
- Hardened read-only CLI behavior:
  - `dspx providers list`
  - `dspx providers capabilities`
  - `dspx tools openapi ops|describe|env|load`
  no longer bootstrap MLflow.
- Added upstream contribution workflow doc and helper recipes:
  - `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`
  - `just upstream-link-dspy path=...`
  - `just upstream-link-mlflow path=...`
  - `just upstream-reset`

## Current runtime / packaging behavior

- Install/sync workspace:
  - `uv sync`
- Core CLI:
  - `just dspx ...`
  - runs `uv run --package dspx-core -q python -m dspx.cli.dspx ...`
- Forge CLI:
  - `just forge ...`
  - runs `uv run --package dspx-forge -q python -m dspx_forge.cli ...`
- Clean clone smoke:
  - `just clean-clone-smoke`
  - sequence: `uv sync`, `just dspx --help`, `just forge --help`, `just test`
- Quality/test commands:
  - `just test`
  - `just test-core`
  - `just test-forge`
  - `just monorepo-check`
  - `just forge-core-compat-matrix`
- Live optional checks:
  - `DSPX_RUN_LIVE_TESTS=1 just pi-live-smoke`
  - `DSPX_RUN_LIVE_TESTS=1 uv run -m pytest -q tests/test_optimize_gepa_codex_live.py -rs`

## Latest validation snapshot

- `pre-commit run --all-files`: passing
- `just monorepo-check`: passing
- `just test`: passing (`154 passed, 4 skipped`)
- `just test-core`: passing (`144 passed, 4 skipped, 10 deselected`)
- `just test-forge`: passing (`10 passed, 1 skipped, 147 deselected`)
- `just dspx providers list`: passing without forcing `MLFLOW_ENABLE=0`

## Known gaps and immediate risks

- Strict `min` compat track depends on remote tag hygiene:
  - keep `dspx-core-v<lower-bound>` tags present on remote (currently `dspx-core-v0.1.0`).
- Marker discipline must be maintained:
  - new Forge/boundary tests should carry `pytest.mark.forge` to keep slices accurate.
- Some docs still carry legacy wording like “breaking branch”; keep wording aligned with current `main` state.

## Canonical docs

- `docs/MONOREPO_TRANSITION.md`
- `docs/MLFLOW_OBSERVABILITY_PLAN.md`
- `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`
- `apps/forge/README.md`
- `packages/dspx-core/README.md`
- `NEXT_STEPS.md`

## Recommended posture

- Keep boundaries strict and test-enforced.
- Keep default release policy independent per package.
- Prefer upstream fixes via sibling clones + upstream PRs over adding new heavy submodules.
