# Next Steps (monorepo breaking branch)

This plan is for `feature/full-monorepo-breaking` after the hard split.

## 0) Keep baseline stable (always)

- Run routinely:
  - `pre-commit run --all-files`
  - `just monorepo-check`
  - `just test`
- Optional live sanity checks (opt-in):
  - `DSPX_RUN_LIVE_TESTS=1 just pi-live-smoke`
  - `DSPX_RUN_LIVE_TESTS=1 uv run -m pytest -q tests/test_optimize_gepa_codex_live.py -rs`
- Keep boundary strict:
  - allowed: `apps/* -> core`
  - forbidden: `core -> apps/*` (`dspx_forge.*`)

Acceptance:
- Quality gates stay green.
- No new boundary violations.

## 1) Packaging convergence (baseline closed)

Status:
- Clean-clone smoke flow is formalized and wired into CI.

Implemented:
- Script: `scripts/clean_clone_smoke.sh`
- Just wrapper: `just clean-clone-smoke`
- CI smoke sequence:
  - `uv sync`
  - `just dspx --help`
  - `just forge --help`
  - `just test`

Keep-doing:
- Review remaining Just recipes for explicit package context where helpful
  (`--package dspx-core` / `--package dspx-forge`) to avoid ambiguity as
  the workspace grows.
- Keep root as workspace-only (no root runtime package resurrection).

Acceptance:
- Fresh clone runs smoke sequence without path hacks.
- No `PYTHONPATH` / `--no-project` workaround reintroduced.

## 2) Operational hardening for independent versioning (highest priority)

Status:
- CI runs package-aware jobs (`core`, `forge`) plus workspace smoke/hygiene.
- CI includes forge/core compatibility matrix (`latest`, `min`) via wheel installs.
- Forge/core test slices now use explicit `pytest.mark.forge` marker selection.
- Read-only core CLI metadata commands now skip MLflow bootstrap (offline/instant behavior even with remote tracking URI in config).
- Release workflows exist for package tags:
  - `.github/workflows/release-core.yml` (`dspx-core-v*`)
  - `.github/workflows/release-forge.yml` (`dspx-forge-v*`)
- Default release/version policy is independent (`dspx-core` and `dspx-forge`
  ship separately).

Next actions (ordered):
1. Keep `min` compatibility strict in remote CI by maintaining/pushing
   `dspx-core-v<lower-bound>` tags (currently `dspx-core-v0.1.0`).
2. Keep forge/core marker slicing healthy as suite grows (new Forge/boundary tests
   should carry `pytest.mark.forge`; consider path split later if needed).
3. Keep live smoke ergonomics stable (`just pi-live-smoke`, codex readiness via
   `codex login status`) and update docs when CLI auth UX changes.

Acceptance:
- CI shows package-scoped pass/fail. ✅
- Package-scoped publish automation exists. ✅
- `min` compat track is strict and reproducible on remote CI. ⏳

## 3) Docs convergence for split layout and CLI contracts

Goal: docs match actual branch behavior.

Next actions:
- Sweep docs for stale references to old layout/commands.
- Keep these in sync on each structural change:
  - `README.md`
  - `PROJECT_STATUS.md`
  - `NEXT_STEPS.md`
  - `docs/MONOREPO_TRANSITION.md`
  - `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`
- Keep CLI contract explicit:
  - `dspx` = core
  - `dspx-forge` / `just forge` = app

Acceptance:
- No conflicting command or layout guidance across canonical docs.

## 4) Forge hardening within app boundary

Goal: continue Forge work without boundary regressions.

Next actions:
- Expand tests around:
  - GitLab apply idempotency
  - overlap/duplicate resolution flow
  - policy gate behavior
- Keep test defaults offline/deterministic.

Acceptance:
- Forge features advance with green tests and strict core/app separation.

## 5) Optional later: pluginized app discovery

- If app discovery is needed, implement via explicit plugin/entry-point
  mechanisms in core.
- Avoid direct imports from core into app modules.

Acceptance:
- Core remains app-agnostic by default.
