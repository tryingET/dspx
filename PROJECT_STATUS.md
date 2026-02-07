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
- Forge package declares explicit workspace dependency on core (`dspx-core`).
- Core CLI remains core-only; Forge CLI remains app-only.
- CI is split into package-aware jobs (`core`, `forge`) plus workspace smoke/hygiene jobs.

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
- Boundary check:
  - `just monorepo-check` runs `scripts/check_monorepo_boundaries.py`

## Validation snapshot (latest local run)

- `just clean-clone-smoke`: passing.
- `pre-commit run --all-files`: passing.
- `just monorepo-check`: passing.
- `just test`: passing (`150 passed, 4 skipped`).
- `just test-core`: passing (`141 passed, 4 skipped, 9 deselected`).
- `just test-forge`: passing (`9 passed, 1 skipped, 144 deselected`).

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

- Release/versioning policy is still coupled in helper workflow (both package versions bumped together by `just version`).
- Some branch docs may still contain stale wording from pre-split architecture.

Recently closed:
- Clean-clone smoke flow is now formalized via `scripts/clean_clone_smoke.sh` / `just clean-clone-smoke` and enforced in CI.
- CI now has package-aware jobs for `core` and `forge` quality/test slices.

## Canonical docs for this branch

- `docs/MONOREPO_TRANSITION.md`
- `apps/forge/README.md`
- `packages/dspx-core/README.md`
- `NEXT_STEPS.md`

## Recommended posture

- Keep boundaries strict and test-enforced.
- Prioritize package-aware release/version policy next.
- Avoid reintroducing compatibility shims unless required for unblock.
