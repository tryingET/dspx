# Workflow examples

This directory contains illustrative generated/example workflow programs.

## Static-analysis policy

These files are intentionally excluded from repo-wide `ruff` and `ty` checks via `pyproject.toml`:

- `examples/workflows/**`

Reason:
- they are demo artifacts, not the primary supported runtime surface
- they can be regenerated and tuned for illustration
- keeping them on the default static-analysis path created disproportionate noise relative to actionable repo code

Expectations:
- examples should remain syntactically valid and runnable as demos when practical
- production/runtime code under `packages/`, `apps/`, `tools/`, `scripts/`, and `tests/` remains on the default lint/type path
- if a workflow example graduates into a supported maintained surface, remove or narrow the exclusion and bring it under full static analysis
