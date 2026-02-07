# Next Steps (monorepo breaking branch)

This plan is for `feature/full-monorepo-breaking` after the hard split.

## 0) Keep baseline stable (always)

- Run routinely:
  - `pre-commit run --all-files`
  - `just monorepo-check`
  - `just test`
- Keep boundary strict:
  - allowed: `apps/* -> core`
  - forbidden: `core -> apps/*` (`dspx_forge.*`)

Acceptance:
- Quality gates stay green.
- No new boundary violations.

## 1) Close packaging convergence (highest priority)

Goal: lock in workspace-native behavior from clean clone.

Next actions:
- Add/verify clean-clone smoke path in docs + CI-friendly script:
  - `uv sync`
  - `just dspx --help`
  - `just forge --help`
  - `just test`
- Review remaining Just recipes for explicit package context where helpful
  (`--package dspx-core` / `--package dspx-forge`) to avoid ambiguity as
  the workspace grows.
- Keep root as workspace-only (no root runtime package resurrection).

Acceptance:
- Fresh clone can run the smoke sequence without path hacks.
- No `PYTHONPATH` / `--no-project` workaround reintroduced.

## 2) CI/CD split by package

Goal: package-aware pipeline and release behavior.

Next actions:
- Create separate CI jobs for:
  - core lint/typecheck/test
  - forge lint/typecheck/test
  - optional integration smoke
- Define release policy clearly:
  - independent versions for `dspx-core` and `dspx-forge`, or
  - explicitly coupled versioning (documented rationale)
- Ensure artifacts/publish steps are package-scoped.

Acceptance:
- CI shows package-scoped pass/fail.
- Release process is documented and reproducible.

## 3) Docs convergence for split layout and CLI contracts

Goal: docs match actual branch behavior.

Next actions:
- Sweep docs for stale references to old layout/commands.
- Keep these in sync on each structural change:
  - `README.md`
  - `PROJECT_STATUS.md`
  - `NEXT_STEPS.md`
  - `docs/MONOREPO_TRANSITION.md`
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
