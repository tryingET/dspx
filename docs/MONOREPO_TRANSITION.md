---
summary: "Breaking-branch monorepo transition: core extracted, Forge split as optional app."
read_when:
  - "You are working on monorepo structure, package boundaries, or CLI ownership."
  - "You need current boundary rules for core vs app code."
---

# Monorepo Transition (breaking branch)

## Outcome on this branch

- Core source moved to: `packages/dspx-core/src/dspx`
- Forge app source moved to: `apps/forge/src/dspx_forge`
- Core CLI (`dspx`) contains core/tooling commands only.
- Forge commands moved to dedicated app CLI: `dspx_forge.cli` (`just forge ...`).
- Root `pyproject.toml` is workspace-only (no root runtime package).
- No legacy Forge compatibility shims in core runtime.

## Boundary rule

- Allowed: `apps/* -> core`
- Forbidden: `core -> apps/*`

Automated guardrail:
- `scripts/check_monorepo_boundaries.py`
- `just monorepo-check`

## Migration notes

This branch intentionally allows breaking changes to accelerate the transition.
Back-compat import aliases/forwarders were removed in favor of direct package boundaries.

## Next hardening tasks

- Keep workspace-native run/install flow green (`uv sync`, `just dspx ...`, `just forge ...`) without PYTHONPATH shims.
- CI workflows are package-aware (`core`, `forge`) plus smoke/hygiene jobs.
- Forge/core pytest slicing uses explicit `pytest.mark.forge` markers (`just test-core` / `just test-forge`).
- CI now runs forge/core compatibility matrix smoke (`latest`, `min`) via wheel installs.
- Package-scoped release workflows exist (`release-core.yml`, `release-forge.yml`); default policy is independent package versioning.
- Update README/docs command examples to prefer `just dspx ...` and `just forge ...`.

## Clean-clone smoke flow (formalized)

- Script: `scripts/clean_clone_smoke.sh`
- Just wrapper: `just clean-clone-smoke`
- Sequence:
  - `uv sync`
  - `just dspx --help`
  - `just forge --help`
  - `just test`
- CI now runs this smoke flow in `.github/workflows/ci.yml`.

## Package-scoped release automation

- Core release workflow: `.github/workflows/release-core.yml`
  - Trigger: `dspx-core-v*`
  - Validates tag version matches `packages/dspx-core/pyproject.toml`
  - Runs core quality gates, builds core artifacts, wheel-smokes `dspx`
  - Publishes only `dspx_core-*` artifacts
- Forge release workflow: `.github/workflows/release-forge.yml`
  - Trigger: `dspx-forge-v*`
  - Validates tag version matches `apps/forge/pyproject.toml`
  - Runs forge quality gates, builds forge artifacts, wheel-smokes `dspx-forge`
  - Publishes only `dspx_forge-*` artifacts
- Forge package dependency policy:
  - `apps/forge/pyproject.toml` pins bounded core range (`dspx-core>=0.1.0,<0.2.0`)
  - CI compat matrix exercises `latest` and `min` core tracks.
  - `min` track resolves via tag `dspx-core-v<lower-bound>` (e.g. `dspx-core-v0.1.0`).
