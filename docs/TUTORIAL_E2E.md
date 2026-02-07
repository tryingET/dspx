---
summary: "Practical walkthrough: Mermaid generation + OpenAPI tooling + CSV adapter usage."
read_when:
  - "You want a runnable end-to-end path through core DSPx workflows."
  - "You are validating onboarding flow after CLI/tooling changes."
---

End-to-End Tutorial: Mermaid + OpenAPI + CSV
===========================================

Goal: generate DSPy programs from a Mermaid flow, call an OpenAPI endpoint, and preview a local CSV using the new adapters.

Prereqs
- Python 3.13 with `uv` and project deps installed (`just install`).
- Optional: `.env` for provider keys / Just recipes: `cp .env.example .env` (git-ignored).
- Optional: MLflow server:
  - Local file store (no server): set `MLFLOW_TRACKING_URI=file:./mlruns`.
  - Docker compose (Synology/NAS-oriented): `just mlflow-up` then set `MLFLOW_TRACKING_URI=http://127.0.0.1:50000` (see `docker-compose.yml`).

1) Prepare a simple Mermaid workflow
Create `flow.mmd` with a single step and an OpenAPI call:

```
graph TD
  A[Load CSV] --> B[Call API]
```

2) Generate DSPy programs from Mermaid
Run and inspect outputs under `generated/workflows/demo`:

```
just dspx mermaid gen -f flow.mmd -n demo -v predict
ls generated/workflows/demo
```

3) Load an OpenAPI spec and list operations
Assume a local spec `spec.json` (or a URL with `--allow-host`). Filter by tag and by method/path:

```
just dspx tools openapi ops spec.json --tags users --method GET --paths
```

Describe an operation, including request/response schemas (use `--json` for machine-readable output):

```
just dspx tools openapi describe --spec spec.json --op listUsers
just dspx tools openapi describe --spec spec.json --op listUsers --json | jq .
```

4) Register OpenAPI tools (optional for agents/programs)
Persist a mapping to configure environments consistently and print exports:

```
just dspx tools openapi load -p gh --spec ./spec.json
just dspx tools openapi env -p gh
```

5) Use the CSV dataset adapter
Preview a local CSV with schema and head rows via the tools registry, or directly via the adapter API:

```
just data-preview ./data.csv
```

Python snippet (SDK):

```python
from dspx.adapters.datasets import CSVDataset
rows = CSVDataset("./data.csv").load()
print(rows[:2])
```

6) Cache controls and reproducibility
All CLI generators write a `.meta.json` next to outputs with a `cache_key` and `hash`.
Bypass cache or inspect cache info:

```
just dspx signature gen "Extract names" --template-version simple-v1 --outfile sig.py --no-cache
just dspx signature gen "Extract names" --template-version simple-v1 --cache-info > /dev/null
```

7) Observability (optional)
Enable MLflow to record inputs/outputs and attach artifacts/manifests:

```
export MLFLOW_ENABLE=1
export MLFLOW_TRACKING_URI=http://127.0.0.1:50000
just dspx codegen "A CLI that prints hi" -l python --outfile gen.py
```

You should see artifacts (`*.py`, `*.meta.json`, `manifest.json` for Mermaid) in the MLflow run.

8) Grouping runs and naming runs

Set a run group to help filter related executions in MLflow, and provide clearer run names automatically used by the CLIs and services:

```
export MLFLOW_ENABLE=1
export MLFLOW_TRACKING_URI=http://127.0.0.1:50000
export DSPX_RUN_GROUP=my-demo

# Named runs appear as signature-<class>, module-<name>, codegen-<lang>, mermaid-<flow>
just dspx signature gen "Extract names" --template-version simple-v1 --outfile sig.py
just dspx module-gen -n Summarizer -d "Summarize" --template-version simple-v1 --outfile mod.py
just dspx codegen "A CLI that prints hi" -l python --outfile gen.py
```

Check MLflow UI: runs have tag `run_group=my-demo` and a `service.duration_ms` metric for quick timing.

9) Dataset splits with stratification and group balancing

Use the adapters CLI to create deterministic splits from a CSV. Start with a simple dataset containing columns `id`, `label`, and `session_id` (or any group identifier).

Two-way split (80/20) with label stratification and group awareness; balance per-label by groups so each label's groups are evenly distributed regardless of group sizes:

```
just dspx adapters dataset split \
  --csv data.csv \
  --outdir splits_demo \
  --test-size 0.2 \
  --stratify-col label \
  --group-col session_id \
  --group-balance groups
```

Three-way split with ratios and per-instance balancing (default):

```
just dspx adapters dataset split \
  --csv data.csv \
  --outdir splits_demo3 \
  --ratios 0.7,0.2,0.1 \
  --stratify-col label \
  --group-col session_id
```

The command prints a JSON summary with output file paths and counts. You can load and inspect the resulting CSVs in your workflow or pipeline.
