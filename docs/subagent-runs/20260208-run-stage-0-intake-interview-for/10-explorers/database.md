---
summary: "Archived subagent-run artifact: Database explorer report (SQLite) — rerun after local MLflow materialization."
read_when:
  - "You are auditing the archived subagent-run workflow output."
  - "You need the recorded artifact for Database explorer report (SQLite) — rerun after local MLflow materialization."
type: "reference"
---

# Database explorer report (SQLite) — rerun after local MLflow materialization

## Schema map
- Canonical DB for this run: `mlflow.db`.
- Runtime check: `mlflow.db` is present in working tree.
- File: `./mlflow.db` (~552 KB).

Read-only inspection snapshot:
- table count: `42`
- experiments: `2` (`Default`, `DSPx-Testing`)
- runs: `3`
- sample run names:
  - `signature-Sig_Stage4D`
  - `module-SummarizerStage4D`
  - `mermaid-stage4d`

Observed schema includes expected MLflow tables (examples):
- `experiments`, `runs`, `metrics`, `params`, `tags`
- `latest_metrics`, `trace_info`, `spans`, `trace_metrics`
- `registered_models`, `model_versions`, `logged_models`

## Context note
- Earlier blocker state (missing `mlflow.db`) was cleared by creating local runs via DSPx CLI with:
  - `MLFLOW_ENABLE=1`
  - `MLFLOW_TRACKING_URI=sqlite:///mlflow.db`
- Non-canonical `generated/sixe.db` remains unrelated to MLflow tracking schema.

## Constraints/integrity posture
- Explorer used read-only queries only.
- Canonical-path rule preserved (`mlflow.db`; no substitution to `sixe.db`).

## 4 Dimensions

### Container
- Boundary: read-only schema + minimal content verification.
- Constraint: no exploratory writes during inspection.
- Edge: DB evidence now unblocks downstream consensus/implementation planning.
- Dependency: continued local availability of `./mlflow.db`.
- Anti-Goal: infer broad production behavior from tiny local smoke dataset.

### Compass
- Driver: clear canonical DB blocker with real local MLflow schema.
- Outcome: authoritative DB explorer evidence available for this run.
- Trade-off: small synthetic dataset vs full historical corpus.

### Engine
- Trigger: user request to generate real MLflow sqlite via CLI runs.
- State: missing -> materialized -> inspected.
- Invariant: canonical DB path remains `mlflow.db`.
- Lifecycle: can be rerun anytime as more runs are generated.

### Fog
- Assumption: this local DB is sufficient for workflow-stage evidence.
- Risk: low representativeness of only 3 runs.
- Exception: if DB is deleted/reset, blocker reappears.
- Debt: optional deeper schema/content audit deferred.
