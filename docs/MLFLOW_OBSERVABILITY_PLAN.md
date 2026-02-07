---
summary: "Plan: make MLflow observability reliable, fast, and CI-friendly (and truly off when disabled)."
read_when:
  - "You want to use DSPx inside CI/CD and need deterministic tracing behavior."
  - "MLflow runs are missing, slow, or trying to reach a tracking server unexpectedly."
  - "You are changing run naming/tags/artifact logging for services/tools."
---

# MLflow Observability Plan (DSPx)

## Goal (what “good” looks like)

- Observability is **boring and reliable**: every CLI/service run either logs cleanly (when enabled) or does nothing (when disabled).
- CI-friendly defaults: **no accidental network** and no long retries unless explicitly configured.
- Trace model: a single, queryable story per run:
  - consistent tags (`service`, `provider`, `template_version`, `run_group`, …)
  - reproducibility artifacts (inputs/options + manifests + generated code)
  - budgets/latency metrics (duration + exceeded)

## Non‑negotiable invariants

1) `MLFLOW_ENABLE=0` means:
   - no `mlflow` import
   - no `mlflow.*` calls
   - no tracking-server HTTP attempts

2) `MLFLOW_ENABLE=1` means:
   - MLflow logging is best‑effort, but **never blocks core output**
   - no implicit run creation unless we explicitly decide to start a run

3) Absence of `MLFLOW_TRACKING_URI` should be safe:
   - use MLflow’s local file store behavior (no HTTP) unless user opts into HTTP by setting a URI

4) Replay must remain MLflow-independent:
   - manifests/receipts/meta files are canonical for replay
   - MLflow is a diagnostic/observability sink, not execution truth

## Current failure mode (why tests/CI can stall)

- Some CLI paths called `mlflow.log_*` even when `MLFLOW_ENABLE=0`.
- MLflow “fluent” APIs can implicitly create a run; if `MLFLOW_TRACKING_URI` points to an HTTP server, that triggers network retries (slow/stall).

## Design (how tracing should work in DSPx)

### A) Central gate

- One helper in `packages/dspx-core/src/dspx/tracing.py` owns the rule:
  - `mlflow_enabled()` → env-only boolean
  - `get_mlflow()` → returns `mlflow` module only when enabled+importable
- Every call site must use `get_mlflow()` (or a wrapper that uses it).

### B) Run lifecycle

- Default: **do not** create implicit runs.
- CLI/services that want a run must:
  - call `ensure_run_with_standard_tags(service, run_name=...)`
  - then log only if `mlflow.active_run() is not None`

### C) Tag contract (minimum viable)

- Required tags:
  - `service`: `signature|module|codegen|mermaid|tools|openapi|...`
  - `provider`: from `DSPX_PROVIDER` when present
- Optional but strongly recommended:
  - `template_version`
  - `run_group` (propagate via `DSPX_RUN_GROUP`)
  - `program_name` (Mermaid)
  - `service.budget_ms` (tag)

### D) Artifact contract (minimum viable)

- Always safe to log:
  - generated `.py` outputs
  - `*.meta.json` (cache key + hashes)
  - manifests (`manifest.json`, `program_graph.json`, `artifact.json`)
- Never log secrets:
  - rely on `dspx.redaction` for previews/log text
  - treat headers/cookies/tokens as sensitive by default

## Implementation checklist (concrete)

1) Gate all call sites
   - replace direct `import mlflow` blocks with `mlflow = get_mlflow()`
   - skip logging when `mlflow is None`
   - never call `mlflow.log_*` unless `mlflow.active_run() is not None`

2) Fix defaults
   - in `enable_mlflow_from_env()`: only set tracking URI when `MLFLOW_TRACKING_URI` is set
   - for DSPy autolog: prefer `mlflow.dspy.autolog(create_run=False)` when supported

3) Add regression tests
   - test that `MLFLOW_ENABLE=0` prevents importing `mlflow` (guard `__import__`)
   - test “enabled but no tracking uri” stays local (no HTTP) by ensuring it runs without a server

4) CI/CD wiring (GitLab)
   - decide per pipeline whether MLflow is:
     - disabled (fastest; default for unit tests), or
     - enabled to local store (artifact upload), or
     - enabled to remote tracking server (org-level observability)
   - recommended envs for remote MLflow:
     - `MLFLOW_ENABLE=1`
     - `MLFLOW_TRACKING_URI=https://mlflow.<domain>`
     - `MLFLOW_EXPERIMENT=ai-society/<project>`
     - `DSPX_RUN_GROUP=$CI_PIPELINE_ID` (or `$CI_COMMIT_SHA`)
     - `MLFLOW_RUN_NAME=$CI_JOB_NAME` (optional; DSPx also sets stable per-command run names)

5) Documentation update (publish readiness)
   - document the invariants above in README (short)
   - document CI recipes + run_group conventions

## Validation (how we know we’re done)

- `just test` has no MLflow HTTP retries when `MLFLOW_ENABLE=0`.
- With `MLFLOW_ENABLE=1` and no tracking URI, runs are created locally (no server required).
- With an HTTP tracking URI, runs show:
  - consistent tags
  - artifacts attached
  - budget metrics present when budgets are used

## Self‑critique (risks / what I might be missing)

- Risk: MLflow APIs change; `create_run=False` may not exist in older versions (we need graceful fallback).
- Risk: “active run required” could drop artifacts silently if a caller forgets to start a run; mitigated by always calling `ensure_run_with_standard_tags(...)` in CLI/service entrypoints.
- Risk: local file store in CI can bloat artifacts; need retention policy (GitLab artifact TTL) or remote MLflow with pruning.
- Risk: people will expect OpenTelemetry-style traces; MLflow is “good enough” for artifacts/metrics but not a full tracing system.
