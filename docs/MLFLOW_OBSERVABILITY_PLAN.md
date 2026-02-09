---
summary: "MLflow lifecycle policy after dspy-ai 3.1.3 + mlflow 3.9.0: deterministic local backend, explicit run starts, safe DSPy autolog defaults."
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
- DSPx forces deterministic local backend: `sqlite:///mlflow.db`
- expected local artifact root remains `./mlruns`

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
- resolve tracking URI (explicit env or default local sqlite)
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

- unset: `sqlite:///mlflow.db` (DSPx default)
- `file:...` or local path: local file-store
- `sqlite:...`: local sqlite backend
- `http(s)://...`: remote backend (user-managed)

Run explain enrichment (`--with-mlflow`) treats sqlite/file modes as local scan candidates, including sqlite custom artifact roots resolved from MLflow experiment metadata. Remote URIs stay safe by default (no remote lookup) unless `--mlflow-remote-lookup` is explicitly set, in which case bounded remote candidate search is attempted with bounded MLflow HTTP request behavior (timeout budget applied, retries forced to `0`) to avoid long hangs on unreachable remotes.

## Guardrails for contributors

- never `import mlflow` directly outside `dspx.tracing`
- never call `mlflow.log_*` without an active run
- keep read-only CLI commands from bootstrapping tracing
- keep tests offline/deterministic by default

## Validation checklist

- disabled mode: no import + no side effects
- local default mode: uses sqlite + local artifacts
- explicit URI mode: file/sqlite/http behavior covered
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
