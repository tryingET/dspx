# Next Steps

This document tracks actionable next steps aligned with the phased plan
in `docs/VISION.md`. Phases 1–6 are complete; below focuses on upcoming
work and refinements.

## Phase 7 — Adapter Registry (datasets/eval/stores)

Goal: connectors for datasets (CSV/Parquet/MLflow), stores (MLflow/SQL/object),
eval adapters, and simple metrics.

- Deliverables
  - `dspx/adapters/{datasets,stores,eval}.py` with lightweight interfaces.
  - CSV/Parquet loader, MLflow dataset reference, simple metrics (accuracy/F1).
  - Unit tests with small fixtures, no network.

- Acceptance
  - Adapters usable by services and optimizers; tests deterministic.

## Phase 8 — Server API (optional)

Goal: expose HTTP endpoints for `signature`, `module`, `mermaid` workflows.

- Deliverables
  - `dspx-server` (FastAPI) for `/signature`, `/module`, `/mermaid`.
  - Basic auth/token, request/response DTOs, MLflow tags.

- Acceptance
  - Smoke tests; local run <2s; documented usage.

## Phase 9 — Policy, Safety, Sandboxing

Goal: strengthen policy for tool/provider gating and isolation.

- Deliverables
  - Policy engine for tool/provider allow/deny with budgets/timeouts.
  - Optional isolated worktrees for code-exec; explicit destructive prompts.
  - CLI flags and config propagation.

- Acceptance
  - Policies enforced in tools and providers; tests for deny/allow flows.

## Phase 10 — Plugins & Extension Points

Goal: enable third-party providers/tools/generators via entry points.

- Deliverables
  - Plugin registry + discovery; example plugin + docs.

- Acceptance
  - Plugins loadable and testable; documentation covers lifecycle.

## Refinements (Near-term 80/20)

- OpenAPI: enhance validation (arrays/enums/nested objects), `ops --method` and
  `--paths` added; `describe --json` for programmatic use; next add `--tags`
  and response schemas.
- MLflow: attach manifests and generated code as artifacts; standardize tags
  (`service`, `template_version`, `provider`).
- Templates: expand module/codegen templates (multi-output, additional languages).
- Caching: expose CLI flags to bypass/inspect cache; include cache key in meta files.
- Docs: end-to-end tutorial using Mermaid + OpenAPI node with env/mapping, and
  adapter usage once Phase 7 is in place.

## Day-to-Day Checklist

- Run `just test` before and after changes; target <5s locally.
- Keep docs in sync (VISION/ARCHITECTURE/NEXT_STEPS) with major changes.
- Prefer small, scoped PRs per phase/sub-phase; include acceptance notes.
