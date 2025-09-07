# Next Steps

This document tracks actionable next steps aligned with the phased plan
in `docs/VISION.md`. Phases 1–6 are complete; below focuses on upcoming
work and refinements.

## Phase 7 — Adapter Registry (datasets/eval/stores)

Status: DONE (MVP+)

- Implemented
  - `dspx/adapters/{datasets,stores,eval}.py` with lightweight interfaces.
  - CSV/Parquet loader, MLflow dataset reference, simple metrics (accuracy/F1).
  - Local object store for examples/tests.
  - Adapters CLI: `dspx adapters list`, `dspx adapters dataset describe`.
  - Unit tests with small fixtures, no network.

- Acceptance
  - Adapters usable by services and optimizers; tests deterministic.

- Next
  - DONE: dataset split helpers + CLI (`adapters dataset split`).
  - DONE: eval metrics (confusion matrix, ROUGE‑1 F1, BLEU‑1) and eval CLI
    (`adapters eval run`, `adapters eval run2`).
  - DONE: stratified splits by label and optional group‑aware splitting (CLI flags, tests).
  - DONE: macro/micro averaging for ROUGE/BLEU (CLI `--average`).
  - DONE: ROC‑AUC and per‑class precision/recall (CLI `--metric` selections, tests).
  - Next: add stratified multi‑class group balancing options; optional min‑count
    constraints; PR curve utilities and calibration metrics.

## Phase 8 — Server API (optional)

Status: DONE (MVP+)

- Implemented
  - `dspx-server` (FastAPI) for `/signature`, `/module`, `/mermaid` served via Granian.
  - Request/response DTOs; ASGI tests using TestClient.
  - Bearer auth (env tokens or file; optional); standardized JSON 401 errors.
  - Rate limiting (per‑identity and global; per‑path overrides); 429 JSON errors.
  - Trusted proxies (CIDR) for X‑Forwarded‑For handling.
  - Structured request logging; lightweight counters; docs at `docs/SERVER.md`.

- Next
  - Distributed rate limiting backend (optional) for multi‑worker deployments.
  - Expose a small `/metrics` for counters (guarded by env) or integrate Prometheus.
  - DTO polish and request metadata tagging for MLflow when enabled.
  - Harden logging config guidance; example JSON formatter setup.

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

- OpenAPI: now includes `ops --tags` and `describe --json` with response schema summaries;
  added validation for enums/arrays/shallow nested objects. Next: widen coverage for complex
  nested schemas and arrays of objects with deeper constraints.
- MLflow: standardized tags (`service`, `template_version`, `provider`) and artifacts/manifests attached;
  added run naming (`signature-*`, `module-*`, `codegen-*`, `mermaid-*`), grouping via `DSPX_RUN_GROUP`,
  and `service.duration_ms` metric. Next: simple budget/time caps and aggregate metrics per service.
- Templates: expand module/codegen templates (multi‑output, additional languages).
- Caching: `--no-cache`, `--cache-info` shipped; meta includes cache key/file. Added
  `dspx cache` subcommands (info/list/show/clear). Next: size summaries by kind and
  selective pruning by age/size.
- Docs: added end‑to‑end tutorial (`docs/TUTORIAL_E2E.md`) showing Mermaid + OpenAPI + CSV adapters.
  Next: extend with runnable OpenAPI node example and adapters split/eval examples.
  Added: server docs (`docs/SERVER.md`) and quickstart in README.

## Day-to-Day Checklist

 - Run `just test` before and after changes; target ~<9s locally.
- Keep docs in sync (VISION/ARCHITECTURE/NEXT_STEPS) with major changes.
- Prefer small, scoped PRs per phase/sub-phase; include acceptance notes.
