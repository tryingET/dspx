# Documentation explorer report

## Documentation baseline
- `qmd` collection exists (`dspx-docs`) with 15 markdown docs (architecture/vision/forge/mlflow/server/openapi, etc.).
- Subagent workflow docs are present in repo but not represented in `qmd` collection:
  - `docs/SUBAGENT_WORKFLOW.md`
  - `docs/subagent-runs/README.md`
  - `docs/subagent-runs/schema/README.md`
- Relevant domain packets for stated focus (MLflow + DSPy issue/PR domain takes) exist:
  - `docs/rfc/RFC-DSPX-OBS-20260207-mlflow-explain-correlation-v11.md`
  - `docs/rfc/RFC-MLFLOW-OBS-20260207-dspy-tracing-hardening.md`
  - `docs/rfc/RFC-DSPY-CALLBACK-20260207-lifecycle-contract-v1.md`
  - `.pi/prompts/rfc-experts/*.md`

## Policy/guardrails
- Repo guardrails emphasize:
  - schema contract canonicalization (`docs/subagent-runs/schema/system4d-attrs.schema.json`)
  - interview-first Stage-0 and gate-before-kickoff
  - no destructive ops; docs sync with behavior.
- Forge docs reinforce policy-safe mutating behavior + dry-run-first posture.

## Decision history + unresolved
- Decision history indicates active observability stream with DSPx-local + upstream MLflow/DSPy RFC packets.
- Resolved in this run:
  - canonical DB semantics: `db_path_or_none` is Stage-1 explorer input, not answer storage.
  - canonical run-id semantics: explicit command RUN_ID is authoritative; additional run IDs are related context.
- Unresolved from this run context:
  - exact prioritized issue/PR subset for explorers.
  - local availability/path for canonical `mlflow.db`.

## 4 Dimensions
### Container
- Boundary:
  - docs support for Stage-0 through prompt-factory flow.
- Constraint:
  - canonical schema + gate checklist must remain aligned with prompt/extension contracts.
- Edge:
  - docs (`docs/*`) ↔ prompts (`.pi/prompts/*`) ↔ extension behavior.
- Dependency:
  - qmd index completeness strongly affects docs-first retrieval quality.
- Anti-Goal:
  - avoid treating qmd-no-result as docs absence.

### Compass
- Driver:
  - reduce workflow ambiguity and preserve interview-first governance.
- Outcome:
  - traceable documentation baseline for explorers/synthesis.
- Trade-off:
  - qmd-first retrieval speed vs direct-file completeness.

### Engine
- Trigger:
  - Stage-1 docs exploration after intake gate pass.
- State:
  - qmd status/list -> query/search -> fallback direct doc read when collection misses files.
- Invariant:
  - schema/gate docs remain source of operational truth.
- Lifecycle:
  - document drift -> update collection/index scope -> rerun query flows.

### Fog
- Assumption:
  - qmd collection reflects current critical docs set.
- Risk:
  - missing subagent docs in qmd can mislead auto-retrieval.
- Exception:
  - qmd query can return no results even when docs exist (collection scope gap).
- Debt:
  - index scope debt: add subagent workflow docs to searchable collection.

## Docs/impl drift notes
- Drift 1: `qmd` collection does not include key subagent workflow docs despite active usage.
- Drift 2: canonical DB/run-id semantics were clarified in prompts/schema docs; collection/index still lags those updates.

## Open questions
- Should `qmd` collection include `docs/subagent-runs/**` and `.pi/prompts/**` by default for this workflow?
- Should `qmd` collection include `docs/rfc/**` by default for observability packet workflows?
