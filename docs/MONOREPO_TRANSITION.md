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
- Re-home CI/release jobs to package-aware workflows.
- Update README/docs command examples to prefer `just dspx ...` and `just forge ...`.
