---
summary: "MLflow lifecycle policy after dspy-ai 3.1.3 + mlflow 3.9.0: explicit tracking URI, DS1621 remote target, explicit run starts, safe DSPy autolog defaults."
read_when:
  - "You are changing tracing, MLflow env handling, or run lifecycle behavior."
  - "You are debugging GEPA warnings, MLflow backend selection, or CI hangs."
  - "You are updating replay/explain behavior with optional MLflow enrichment."
---

# MLflow Observability Plan (DSPx)

## Non-negotiable policy

1) `MLFLOW_ENABLE=0` means:
- no `mlflow` import from DSPx tracing helpers
- no run creation
- no tracking/network side effects

2) If `MLFLOW_ENABLE=1` and `MLFLOW_TRACKING_URI` is **unset**:
- DSPx performs no MLflow side effects
- DSPx does not create or imply a local sqlite fallback
- set `MLFLOW_TRACKING_URI=http://ds1621:50000` for the shared DS1621 MLflow service

3) Run creation is explicit:
- bootstrapping tracing does **not** start runs
- runs start only via `ensure_run_from_env()` / `ensure_run_with_standard_tags()`
- no implicit run creation based only on tracking URI presence

4) Replay/explain stay local-first:
- receipts/manifests/cache metadata are execution truth
- MLflow is optional enrichment sink only

## Lifecycle model

### A) Bootstrap (configuration only)
`enable_mlflow_from_env()` does:
- require an explicit tracking URI
- set experiment
- configure DSPy autolog integration (best-effort)

It does **not**:
- start a run

### B) Run start (explicit intent)
Callers that want MLflow logs must call one of:
- `ensure_run_from_env(run_name=..., tags=...)`
- `ensure_run_with_standard_tags(service=..., run_name=..., ...)`

If no run name is available (`run_name`/`MLFLOW_RUN_NAME`), run start is skipped.

### C) Logging
All call sites must gate logging with:
- `mlflow = get_mlflow()`
- `mlflow.active_run() is not None`

## DSPy autolog semantics (mlflow 3.9)

MLflow 3.9 changed `mlflow.dspy.autolog` API (no `create_run`).

DSPx policy defaults:
- autolog enabled in compatibility mode (`DSPX_MLFLOW_DSPY_AUTOLOG=1`)
- trace collection off by default (`DSPX_MLFLOW_DSPY_LOG_TRACES=0`)
- MLflow DSPy integration kept quiet by default (`DSPX_MLFLOW_DSPY_SILENT=1`)

Rationale:
- avoids noisy GEPA warnings (`Failed to start span ... NonRecordingSpan ...`)
- keeps explicit DSPx artifact/metric logging deterministic

Optional opt-in knobs:
- `DSPX_MLFLOW_DSPY_LOG_TRACES=1`
- `DSPX_MLFLOW_DSPY_LOG_TRACES_FROM_COMPILE=1`
- `DSPX_MLFLOW_DSPY_LOG_TRACES_FROM_EVAL=1`
- `DSPX_MLFLOW_DSPY_LOG_COMPILES=1`
- `DSPX_MLFLOW_DSPY_LOG_EVALS=1`

## Tracking URI modes

DSPx is still alpha, so it does not preserve implicit local MLflow fallbacks or MLflow's deprecated filesystem backend.

- unset: unconfigured; no MLflow logging/bootstrap side effects
- `http://ds1621:50000`: normal shared DSPx/NAS MLflow target
- `http(s)://...`: remote backend (user-managed)
- explicit `sqlite:...`: supported only when a developer intentionally chooses a local sqlite tracking URI (not a fallback)
- `file:...` or local path: unsupported filesystem tracking backend; use the DS1621 server or another explicit database-backed tracking URI instead

Run explain enrichment (`--with-mlflow`) requires an explicit tracking URI. Explicit sqlite URIs are local scan candidates, including sqlite custom artifact roots resolved from MLflow experiment metadata. The local scan reads artifact files after sqlite metadata identifies local artifact roots; it does not make filesystem directories a supported MLflow tracking backend. File/local-path tracking URIs degrade MLflow enrichment with deterministic unsupported-backend diagnostics and must not instantiate MLflow's deprecated filesystem tracking backend. Remote URIs stay safe by default (no remote lookup) unless `--mlflow-remote-lookup` is explicitly set, in which case bounded remote candidate search is attempted with bounded MLflow HTTP request behavior (timeout budget applied, retries forced to `0`) to avoid long hangs on unreachable remotes. `http://ds1621:50000` is the current shared DS1621 MLflow server for optional DSPx remote logging/UI; it is backed by Postgres plus MinIO object storage on DS1621.

## Guardrails for contributors

- never `import mlflow` directly outside `dspx.tracing`
- never call `mlflow.log_*` without an active run
- keep read-only CLI commands from bootstrapping tracing
- keep tests offline/deterministic by default

## Validation checklist

- disabled mode: no import + no side effects
- unconfigured mode: no sqlite fallback and no MLflow side effects
- explicit URI mode: http/sqlite supported behavior and unsupported filesystem-tracking diagnostics covered
- nested run behavior: child run does not end parent
- GEPA path with tracing enabled: no noisy span-start warning flood

## Architecture draft handoff

For domain-expert drafting packets:
- `docs/OBSERVABILITY_ARCH_DRAFTS.md`
- `docs/ARCH_DRAFT_DSPX_NEXT.md`
- `docs/ARCH_DRAFT_UPSTREAM_MLFLOW.md`
- `docs/ARCH_DRAFT_UPSTREAM_DSPY.md`
- RFC templates:
  - `docs/RFC_TEMPLATE_DSPX_NEXT.md`
  - `docs/RFC_TEMPLATE_UPSTREAM_MLFLOW.md`
  - `docs/RFC_TEMPLATE_UPSTREAM_DSPY.md`
