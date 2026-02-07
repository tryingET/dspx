# AGENTS.md (repo-local guidance)

Scope: this file is repo-local truth for coding agents in `dspx`.

## TL;DR
- stack: Python 3.13 + `uv` + `just`
- quality gates: `ruff` + `ty` + `pytest`
- default posture: offline/deterministic tests, policy-safe network behavior
- keep docs in sync with behavior

## Read-first map (pick by task)
- product/roadmap: `docs/VISION.md`, `PROJECT_STATUS.md`, `NEXT_STEPS.md`
- architecture seams: `docs/ARCHITECTURE.md`
- forge work (`just forge ...` / `dspx-forge ...`): `docs/FORGE.md`
- OpenAPI tools: `docs/OPENAPI_TOOLING.md`
- server/auth/rate-limit/metrics: `docs/SERVER.md`
- tracing/MLflow behavior: `docs/MLFLOW_OBSERVABILITY_PLAN.md`
- tooling defaults: `docs/tech-stack.local.md`
- user-facing CLI/docs examples: `README.md`

## Repo shape
- core CLI entrypoints: `packages/dspx-core/src/dspx/cli/`
- forge CLI entrypoints: `apps/forge/src/dspx_forge/`
- core service layer: `packages/dspx-core/src/dspx/services/`
- forge pipeline: `apps/forge/src/dspx_forge/`
- core providers: `packages/dspx-core/src/dspx/*_lm.py`, `packages/dspx-core/src/dspx/providers*`
- core tools/openapi: `packages/dspx-core/src/dspx/tools/`
- core server: `packages/dspx-core/src/dspx/server/`
- core contracts: `packages/dspx-core/src/dspx/dtos.py`
- core policy/redaction: `packages/dspx-core/src/dspx/policy.py`, `packages/dspx-core/src/dspx/redaction.py`

## Standard commands
- install: `just install`
- format: `just fmt`
- lint: `just lint`
- typecheck: `just typecheck`
- test: `just test`
- run core CLI from source: `just dspx ...`
- run forge CLI from source: `just forge ...`

## Delivery checklist (default)
1) implement a scoped change with meaningful impact
2) add/adjust tests near changed behavior
3) run: `just fmt && just lint && just typecheck && just test`
4) update docs when behavior/flags/contracts changed

## Safety + policy constraints
- never leak secrets/tokens in code, logs, fixtures, docs
- respect policy gates for providers/tools/network mutation
- prefer dry-run first for mutating tool flows
- keep Forge issue updates bounded to managed blocks; preserve human edits

## Docs sync rules
When behavior changes, update at least:
- `README.md` (user-facing command/flag changes)
- `PROJECT_STATUS.md` (current state/progress)
- `NEXT_STEPS.md` (remaining work)
- domain doc (`docs/FORGE.md`, `docs/OPENAPI_TOOLING.md`, `docs/SERVER.md`, etc.)
