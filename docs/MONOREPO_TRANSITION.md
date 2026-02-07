---
summary: "Current monorepo layout and guardrails on main (core + Forge split)."
read_when:
  - "You are changing package boundaries, CLI ownership, or workspace topology."
  - "You are touching forge/core compatibility policy, release tags, or monorepo CI jobs."
---

# Monorepo Layout & Guardrails (`main`)

## Current state (enforced)

- Core package lives at `packages/dspx-core/src/dspx`.
- Forge app package lives at `apps/forge/src/dspx_forge`.
- Root `pyproject.toml` is workspace-only (`[tool.uv.workspace]`).
- Core and Forge are validated in package-aware CI jobs.

## Boundary invariant (non-negotiable)

- Allowed: `apps/* -> core`
- Forbidden: `core -> apps/*`
- Never import `dspx_forge.*` from core.

Automation:
- Guardrail script: `scripts/check_monorepo_boundaries.py`
- Just wrapper: `just monorepo-check`

## CLI ownership

- Core commands: `dspx` (`just dspx ...`)
- Forge app commands: `dspx-forge` (`just forge ...`)
- Forge is **not** a subcommand namespace under `dspx`.

## CI/test/package checks

- CI jobs split by concern:
  - workspace smoke + hygiene
  - `core` quality/tests + signature provider-corpus gate artifact (`signature-quality-summary`)
  - `forge` quality/tests
  - forge/core wheel compatibility (`latest`, `min`)
- Test slices are marker-based:
  - `just test-core` → `pytest -m "not forge"`
  - `just test-forge` → `pytest -m "forge"`

## Forge/core compatibility contract

- Forge dependency bound in `apps/forge/pyproject.toml`:
  - `dspx-core>=0.1.0,<0.2.0` (example current range)
- `min` compat track resolves core from tag:
  - `dspx-core-v<lower-bound>` (example: `dspx-core-v0.1.0`)
- Lower-bound tags must exist on remote for deterministic CI.

## Operator checklist

Run routinely:
- `pre-commit run --all-files`
- `just monorepo-check`
- `just test`
- `just forge-core-compat-matrix`

When bumping Forge lower bound:
1. Update `apps/forge/pyproject.toml` bound.
2. Create/push matching core lower-bound tag (`dspx-core-v<new-lower-bound>`).
3. Re-run `just forge-core-compat-matrix`.
4. Update docs: `README.md`, `PROJECT_STATUS.md`, `NEXT_STEPS.md`.
