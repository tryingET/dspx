# Project Status (monorepo breaking branch)

This status reflects the **breaking monorepo branch**:
`feature/full-monorepo-breaking`.

## Snapshot

- Monorepo split executed (no Forge compatibility shims).
- Core code moved from `src/dspx` to:
  - `packages/dspx-core/src/dspx`
- Forge app extracted to:
  - `apps/forge/src/dspx_forge`
- Core no longer contains Forge modules (`src/dspx/forge` removed).
- Core CLI no longer mounts `forge` commands.
- Forge now has dedicated app CLI (`dspx_forge.cli`).
- New package manifests added:
  - `packages/dspx-core/pyproject.toml`
  - `apps/forge/pyproject.toml`
- Workspace wiring added in root `pyproject.toml`:
  - `[tool.uv.workspace] members = ["packages/dspx-core", "apps/forge"]`

## Current runtime usage

- Core CLI:
  - `just dspx ...`
  - runs `python -m dspx.cli.dspx` with monorepo PYTHONPATH.
- Forge CLI:
  - `just forge ...`
  - runs `python -m dspx_forge.cli` with monorepo PYTHONPATH.
- Tests:
  - `just test`
  - passes with `PYTHONPATH=packages/dspx-core/src:apps/forge/src` and `uv run --no-project`.

## Validation snapshot

- `pre-commit run --all-files`: passing.
- `just test`: passing (`150 passed, 4 skipped`).
- `just monorepo-check`: passing.

## Boundary status

- Rule: `apps/* -> core`, never reverse.
- Guardrail script updated to current layout:
  - `scripts/check_monorepo_boundaries.py`
- Core import of `dspx_forge` is denied by guardrail.

## What changed from prior architecture

- Previous transition path (shims/forwarders) was removed on this branch.
- This branch is intentionally **breaking** for older paths:
  - old `dspx forge ...` under core CLI
  - old `dspx.forge.*` module imports

## Known gaps

- Root project packaging is still transitional for workspace mode.
- Some root workflows still assume single-package `src/dspx` install semantics.
- README and architecture docs still contain stale pre-split language.
- CI/release jobs not yet fully package-aware (`dspx-core` + `dspx-forge`).

## Documents to treat as canonical for this branch

- `docs/MONOREPO_TRANSITION.md` (branch-specific transition state)
- `apps/forge/README.md` (Forge app boundary)
- `packages/dspx-core/README.md` (core boundary)

## Recommended posture

- Treat this branch as monorepo migration sandbox.
- Avoid adding new compatibility shims unless strictly required for unblock.
- Prioritize package/CI/doc convergence next.
