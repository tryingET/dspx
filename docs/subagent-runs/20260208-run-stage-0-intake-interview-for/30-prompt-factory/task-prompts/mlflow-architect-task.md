# Task prompt — MLflow upstream architecture draft

Draft `40-domain-drafts/mlflow-upstream-architecture.md`.

Inputs:
- `docs/rfc/RFC-MLFLOW-OBS-20260207-dspy-tracing-hardening.md`
- `docs/rfc/RFC-DSPX-OBS-20260207-mlflow-explain-correlation-v11.md`
- `docs/MLFLOW_OBSERVABILITY_PLAN.md`
- run synthesis artifact: `20-synthesis/technical-writer.md`

Task:
1. Produce architecture options for upstream MLflow changes that reduce DSPy tracing fragility.
2. Define issue/PR order with smallest-safe increments.
3. Explicitly map compatibility concerns and rollout gates.
4. Provide validation plan (unit/integration/behavioral signals).

Output sections required:
- Problem framing
- Option matrix + trade-offs
- Recommended issue/PR sequence
- Compatibility + migration notes
- Risks/mitigations
- Open maintainer questions

Use 4 Dimensions structure throughout.
