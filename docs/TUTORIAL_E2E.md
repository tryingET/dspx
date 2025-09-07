End-to-End Tutorial: Mermaid + OpenAPI + CSV
===========================================

Goal: generate DSPy programs from a Mermaid flow, call an OpenAPI endpoint, and preview a local CSV using the new adapters.

Prereqs
- Python 3.13 with `uv` and project installed (`just dev-install`).
- Optional: MLflow server (Docker compose: `just mlflow-up`).

1) Prepare a simple Mermaid workflow
Create `flow.mmd` with a single step and an OpenAPI call:

```
graph TD
  A[Load CSV] --> B[Call API]
```

2) Generate DSPy programs from Mermaid
Run and inspect outputs under `generated/workflows/demo`:

```
uvx dspx mermaid gen -f flow.mmd -n demo -v predict
ls generated/workflows/demo
```

3) Load an OpenAPI spec and list operations
Assume a local spec `spec.json` (or a URL with `--allow-host`). Filter by tag and by method/path:

```
uvx dspx tools openapi ops spec.json --tags users --method GET --paths
```

Describe an operation, including request/response schemas (use `--json` for machine-readable output):

```
uvx dspx tools openapi describe --spec spec.json --op listUsers
uvx dspx tools openapi describe --spec spec.json --op listUsers --json | jq .
```

4) Register OpenAPI tools (optional for agents/programs)
Persist a mapping to configure environments consistently and print exports:

```
uvx dspx tools openapi load -p gh --spec ./spec.json
uvx dspx tools openapi env -p gh
```

5) Use the CSV dataset adapter
Preview a local CSV with schema and head rows via the tools registry, or directly via the adapter API:

```
uvx dspx-tools preview ./data.csv
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
uvx dspx signature gen "Extract names" --template-version simple-v1 --outfile sig.py --no-cache
uvx dspx signature gen "Extract names" --template-version simple-v1 --cache-info > /dev/null
```

7) Observability (optional)
Enable MLflow to record inputs/outputs and attach artifacts/manifests:

```
export MLFLOW_ENABLE=1
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
uvx dspx codegen "A CLI that prints hi" -l python --outfile gen.py
```

You should see artifacts (`*.py`, `*.meta.json`, `manifest.json` for Mermaid) in the MLflow run.

8) Grouping runs and naming runs

Set a run group to help filter related executions in MLflow, and provide clearer run names automatically used by the CLIs and services:

```
export MLFLOW_ENABLE=1
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export DSPX_RUN_GROUP=my-demo

# Named runs appear as signature-<class>, module-<name>, codegen-<lang>, mermaid-<flow>
uvx dspx signature gen "Extract names" --template-version simple-v1 --outfile sig.py
uvx dspx module-gen -n Summarizer -d "Summarize" --template-version simple-v1 --outfile mod.py
uvx dspx codegen "A CLI that prints hi" -l python --outfile gen.py
```

Check MLflow UI: runs have tag `run_group=my-demo` and a `service.duration_ms` metric for quick timing.
