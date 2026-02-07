# Project Status (monorepo breaking branch)

This status reflects the **breaking monorepo branch**:
`feature/full-monorepo-breaking`.

## Snapshot

- Monorepo split is active (no Forge compatibility shims in core).
- Core code lives in:
  - `packages/dspx-core/src/dspx`
- Forge app lives in:
  - `apps/forge/src/dspx_forge`
- Root `pyproject.toml` is now workspace-only:
  - `[tool.uv.workspace] members = ["packages/dspx-core", "apps/forge"]`
- Per-package build metadata is explicit:
  - `packages/dspx-core`: `module-name = "dspx"`
  - `apps/forge`: `module-name = "dspx_forge"`
- Forge package declares explicit bounded dependency on core (`dspx-core>=0.1.0,<0.2.0`) with workspace source override.
- Core CLI remains core-only; Forge CLI remains app-only.
- CI is split into package-aware jobs (`core`, `forge`) plus workspace smoke/hygiene jobs.
- CI includes forge/core compatibility matrix (`latest`, `min`) via wheel-based smoke.
- Package-scoped release workflows exist for core/forge tags.

## Current runtime / packaging behavior

- Workspace install:
  - `uv sync`
- Clean-clone smoke flow:
  - `just clean-clone-smoke`
  - runs: `uv sync`, `just dspx --help`, `just forge --help`, `just test`
- Core CLI:
  - `just dspx ...`
  - runs: `uv run --package dspx-core -q python -m dspx.cli.dspx ...`
- Forge CLI:
  - `just forge ...`
  - runs: `uv run --package dspx-forge -q python -m dspx_forge.cli ...`
- Tests:
  - `just test` runs `uv run -m pytest -q tests`
  - `just test-core` runs `pytest -k "not forge"`
  - `just test-forge` runs `pytest -k "forge"`
- Package-scoped quality recipes:
  - `just lint-core`, `just typecheck-core`
  - `just lint-forge`, `just typecheck-forge`
- Forge/core compatibility smoke:
  - `just forge-core-compat latest`
  - `just forge-core-compat min`
  - `just forge-core-compat-matrix`
- Boundary check:
  - `just monorepo-check` runs `scripts/check_monorepo_boundaries.py`
- Release helpers:
  - `just release-core`, `just tag-core`, `just publish-core`
  - `just release-forge`, `just tag-forge`, `just publish-forge`
- Release workflows:
  - `.github/workflows/release-core.yml` (`dspx-core-v*` tags)
  - `.github/workflows/release-forge.yml` (`dspx-forge-v*` tags)

## Validation snapshot (latest local run)

- `just clean-clone-smoke`: passing.
- `pre-commit run --all-files`: passing.
- `just monorepo-check`: passing.
- `just test`: passing (`151 passed, 4 skipped`).
- `just test-core`: passing (`141 passed, 4 skipped, 10 deselected`).
- `just test-forge`: passing (`10 passed, 1 skipped, 144 deselected`).
- `just forge-core-compat-matrix`: passing (both tracks green; `min` track resolves via `dspx-core-v0.1.0`).

## Boundary status

- Rule: `apps/* -> core`, never reverse.
- Guardrail script: `scripts/check_monorepo_boundaries.py`.
- Core import of `dspx_forge.*` is denied by guardrail.

## What changed from prior architecture

- Previous transition forwarders/shims were removed on this branch.
- This branch remains intentionally **breaking** for legacy paths:
  - old `dspx forge ...` under core CLI
  - old `dspx.forge.*` imports

## Known gaps and immediate risks

- Minimum-supported core tag discipline is required (`dspx-core-v<lower-bound>`) to keep `min` compatibility checks strict over time.
- Some branch docs may still contain stale wording from pre-split architecture.

Recently closed:
- Clean-clone smoke flow is now formalized via `scripts/clean_clone_smoke.sh` / `just clean-clone-smoke` and enforced in CI.
- CI now has package-aware jobs for `core` and `forge` quality/test slices.
- Package-scoped release workflows now validate tag/version and publish only the targeted package.
- Default release policy is now independent package versioning.
- CI now runs forge/core compatibility matrix smoke against latest and minimum-supported core tracks.

## Canonical docs for this branch

- `docs/MONOREPO_TRANSITION.md`
- `apps/forge/README.md`
- `packages/dspx-core/README.md`
- `NEXT_STEPS.md`

## Recommended posture

- Keep boundaries strict and test-enforced.
- Keep independent package versioning as default; use coupled helpers only if needed.
- Avoid reintroducing compatibility shims unless required for unblock.
