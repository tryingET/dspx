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
- forge work (`dspx forge ...`): `docs/FORGE.md`
- OpenAPI tools: `docs/OPENAPI_TOOLING.md`
- server/auth/rate-limit/metrics: `docs/SERVER.md`
- tracing/MLflow behavior: `docs/MLFLOW_OBSERVABILITY_PLAN.md`
- tooling defaults: `docs/tech-stack.local.md`
- user-facing CLI/docs examples: `README.md`

## Repo shape
- CLI entrypoints: `src/dspx/cli/`
- service layer: `src/dspx/services/`
- forge pipeline: `src/dspx/forge/`
- providers: `src/dspx/*_lm.py`, `src/dspx/providers*`
- tools/openapi: `src/dspx/tools/`
- server: `src/dspx/server/`
- contracts: `src/dspx/dtos.py`
- policy/redaction: `src/dspx/policy.py`, `src/dspx/redaction.py`

## Standard commands
- install: `just install`
- format: `just fmt`
- lint: `just lint`
- typecheck: `just typecheck`
- test: `just test`
- run root CLI from source: `just dspx ...`

## Delivery checklist (default)
1) implement minimal scoped change
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
