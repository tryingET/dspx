---
summary: "Boundary map for generated-program evidence surfaces: MLflow, Oracle, runtime traces, receipts, and authority."
read_when:
  - "You compare DSPx MLflow/SQLite capture, Oracle indexing, program runtime traces, receipts, or generated-program activation evidence."
  - "You are changing program-gen evidence artifacts, Oracle ingestion/reporting, MLflow logging/explain correlation, or replay checks."
type: "reference"
---

# Generated-program evidence surface boundaries

## Purpose

Keep DSPx generated-program evidence surfaces distinct and non-authoritative. This is the DRY boundary map for comparing:

- MLflow / SQLite run tracking;
- `program_runtime_traces.json`;
- `oracle_evidence.json` and DSPx Oracle;
- receipts / replay;
- activation or governance authority.

Related canonical context:

- [[program-gen-walkthrough]]
- [[program-synthesis-boundary]]
- [[OBSERVABILITY_ARCH_DRAFTS]]
- [[20260505-shared-oracle-coordinate-backend]]
- [[20260506-oracle-evidence-publication-boundary]]
- [[generated-program-activation-boundary]]

## Boundary summary

| Surface | Owned meaning | Current source artifacts / storage | What it must not become |
|---|---|---|---|
| Run receipts / replay | Local reproducibility and evidence hash checks | `*.meta.json`, `manifest.json`, `run_replay_service.py` | Observability backend, Oracle index, approval authority |
| `program_runtime_traces.json` | Candidate-local semantic trace contract | Generated behavior results plus pipeline trace fragments; replay-validated JSON sidecar | MLflow replacement, Oracle index, tool execution permission, promotion evidence by itself |
| MLflow / SQLite | Observability and artifact run tracking | Explicit `MLFLOW_TRACKING_URI`; tags/params/metrics/artifacts; optional SQLite URI | Replay source of truth, Oracle storage, automatic local fallback, production authority |
| DSPx Oracle | Empirical semantic evidence indexing and reporting | `CoordinateIndex` / `CoordinateStore`, default local SQLite `coordinates.db`; `oracle_evidence.json` ingestion | MLflow backend, raw trace validator, ranking/promoting/activation authority |
| `oracle_evidence.json` | Oracle-readable behavior summary | Derived from behavior/evaluation sources; indexed by `dspx oracle index --from-program-evidence` | Full trace log, authority record, direct MLflow export |
| AK / governance / owning domain | Canonical decisions, evidence bindings, transitions, activation truth | External authority surfaces, not DSPx local sidecars | Convenience mirror of Oracle/MLflow/replay state |

## Current dataflow

```text
behavior_results.json / behavior_results.<split>.json
  -> program_runtime_traces.json
      -> receipt/manifest hash binding and replay semantic checks
  -> oracle_evidence.json
      -> explicit DSPx Oracle indexing/reporting
      -> includes only a trace summary/hash reference, not full traces
  -> optional MLflow artifact logging/correlation when MLflow is configured

manifest.json + manifest.json.meta.json
  -> replay checks
  -> optional explain/MLflow correlation
  -> optional explicit Oracle/program evidence flows
```

## Non-negotiable facts

- DSPx MLflow requires explicit MLflow configuration; no local SQLite fallback should be assumed just because MLflow is installed.
- DSPy/MLflow autolog traces are off by default in the current DSPx baseline.
- Oracle `--from-mlflow` scans local MLflow artifact files; it is not a general MLflow backend/API reader.
- Oracle program-evidence indexing consumes `program-oracle-evidence-v1` / `oracle_evidence.json`, not `program_runtime_traces.json` directly.
- `oracle_evidence.json` may include a hash-bound summary of `program_runtime_traces.json` so Oracle reports can mention trace presence/coverage, but Oracle still does not open or validate runtime traces.
- `program_runtime_traces.json` is replay semantic evidence: module calls, final outputs, linkage, coverage, trace hashes, no-tool posture, and non-authority flags.
- Candidate-local Oracle `coordinates.db` files are scratch/cache indexes. Shared Oracle publication, where allowed, re-indexes curated canonical artifacts rather than copying local DB files.
- None of these DSPx evidence surfaces can rank, select, promote, activate, mutate AK/governance, or mutate external authority by themselves.

## How to extend without blurring surfaces

- To extend Oracle trace reporting, keep using the deliberate trace summary/hash reference in `oracle_evidence.json`; do not make Oracle the replay validator or full trace log.
- To make MLflow useful for trace inspection, log `program_runtime_traces.json` as an artifact; do not make MLflow the replay source of truth.
- To make activation packets cite evidence, cite stable artifacts and reports as evidence only; keep activation blocked on owning-domain/governance authority.
- To add shared Oracle behavior, follow [[20260505-shared-oracle-coordinate-backend]] and [[20260506-oracle-evidence-publication-boundary]]: explicit ingestion, curation, redaction posture, idempotency, and non-authority labels.
