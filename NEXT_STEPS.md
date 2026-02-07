# Next Steps (monorepo breaking branch)

This plan is for `feature/full-monorepo-breaking` after the hard split.

## 0) Stabilize the new baseline (now)

- Keep using:
  - `just test`
  - `just monorepo-check`
- Ensure no new core imports of app modules (`dspx_forge.*`).
- Keep diffs reviewable; batch related migration work when it improves momentum.

## 1) Packaging convergence (highest priority)

Goal: workspace-native install/run with no `PYTHONPATH` or `--no-project` workaround.

- Root role chosen: Option A (pure workspace root; no publishable root runtime package).
- Keep per-package build metadata explicit:
  - `packages/dspx-core`: `module-name = "dspx"`
  - `apps/forge`: `module-name = "dspx_forge"`
- Keep app-to-core linkage explicit in Forge packaging (`dspx-core` workspace source).
- Ensure commands work in a clean env with:
  - `uv sync`
  - `just dspx ...`
  - `just forge ...`

Acceptance:
- No errors from stale `src/dspx` expectations.
- Local setup works from clean clone with documented commands.

## 2) CLI contract decisions

Goal: explicit product surfaces after split.

- Keep `dspx` as core-only CLI.
- Keep Forge under separate CLI (`dspx-forge` / `just forge`).
- Decide whether to add optional app dispatch in core CLI later (plugin-based) or keep strict separation.

Acceptance:
- CLI contracts documented and consistent in help/README/docs.

## 3) CI/CD split

Goal: package-aware pipelines.

- Separate checks/jobs:
  - core tests/lint/typecheck
  - forge app tests/lint/typecheck
  - integration smoke (optional)
- Release workflow:
  - independent versioning for `dspx-core` and `dspx-forge` (or explicitly coupled policy).

Acceptance:
- CI green with package-scoped jobs.
- Release steps documented.

## 4) Docs cleanup (branch-wide)

- Update stale references to old layout (`src/dspx/forge`, `dspx forge ...` in core).
- Refresh:
  - `README.md`
  - `docs/ARCHITECTURE.md`
  - `docs/VISION.md`
  - any command examples affected by split
- Keep `PROJECT_STATUS.md` and this file synchronized after each structural change.

Acceptance:
- Docs reflect actual commands/layout on this branch.

## 5) Forge hardening in app boundary

- Continue Forge feature work in `apps/forge/src/dspx_forge` only.
- Expand tests around:
  - GitLab apply idempotency
  - overlap decisions/duplicate close flow
  - policy gate behavior
- Preserve offline/deterministic default behavior in tests.

Acceptance:
- Forge tests stay green without coupling back into core internals.

## 6) Optional later: pluginized app discovery

- If needed, add explicit app/plugin discovery in core (entry points/config driven), not direct imports.

Acceptance:
- Core remains app-agnostic by default.

## Daily checklist

- `pre-commit run --all-files`
- `just test`
- `just monorepo-check`
- Update docs when command/layout behavior changes.
