---
summary: "DSPx-owned next-step architecture draft for MLflow enrichment and replay/explain correlation."
read_when:
  - "You are designing DSPx-side follow-ups for MLflow explain enrichment."
  - "You need DSPx scope separated from upstream MLflow/DSPy responsibilities."
---

# DSPx Next Architecture Draft

RFC skeleton to fill:
- `docs/RFC_TEMPLATE_DSPX_NEXT.md`

## Scope (DSPx-owned)

Own in DSPx:
- replay/explain local-first behavior
- MLflow enrichment orchestration (`run explain --with-mlflow`)
- DSPx correlation contract (receipt <-> tags <-> artifacts)
- diagnostics + graceful degradation

Do **not** own in DSPx:
- MLflow internal tracing callback reliability bugs
- DSPy callback API contract shape

## Current state

Implemented:
- sqlite-only local MLflow tracking mode for DSPx alpha
- unsupported filesystem-tracking diagnostics for `file:...` and bare local path tracking URIs
- sqlite artifact-root fallback via MLflow experiment metadata
- run metadata fallback via `MlflowClient.get_run(...)` when local artifact-side metadata is missing

Still weak:
- remote backend linkage = best-effort degraded
- correlation schema not yet standardized for remote search precision

## Problem statement

Need higher-confidence explain enrichment without breaking local-first contract.

Goals:
1) stronger linkage precision (low false positives)
2) remote lookup path (optional, never required)
3) stable machine-readable diagnostics for operators

## Proposed target architecture

### A) Correlation contract v1.1 (DSPx tags + receipt hints)

When DSPx starts/logs a run, standardize tags:
- `dspx.run_kind`
- `dspx.template_version`
- `dspx.output_basename`
- `dspx.cache_key`
- `dspx.output_hash_prefix` (e.g. first 12-16 hex)
- keep existing `service`, `provider`, optional `run_group`

Receipt optional hint block (non-breaking):
- `mlflow_hints.tracking_uri_observed`
- `mlflow_hints.output_hash_prefix`
- `mlflow_hints.expected_tags` (subset)

Compatibility: hints optional; replay contract remains local-first.

### B) Explain enrichment pipeline

`run explain --with-mlflow` stages:
1. baseline local replay checks (already source of truth)
2. tracking mode classification: sqlite local, unsupported filesystem tracking, or remote URI
3. sqlite-backed local artifact linkage scan using MLflow metadata and artifact roots
4. local metadata enrich (artifact-side metadata or client fallback)
5. optional remote lookup phase (new)
6. merge + emit deterministic `mlflow_context`

### C) Remote lookup (opt-in, best-effort)

Add explicit flag (candidate):
- `--mlflow-remote-lookup` (default off)

Behavior:
- only when `--with-mlflow` + remote tracking URI
- search runs via tag filters first (`dspx.*` + service)
- artifact listing/check only on narrowed candidates
- never fail explain baseline

### D) Diagnostics contract (stable)

Extend `mlflow_context` with:
- `lookup_mode` (`local-scan`, `remote-search`, `disabled`)
- `lookup_steps` (ordered)
- `degrade_reason_codes` (stable taxonomy)
- `candidate_count`, `matched_count`

## Work packages

### WP1: Correlation contract
- add standardized DSPx tags at run start/log call sites
- add optional receipt `mlflow_hints`
- tests: tag emission on signature/module/codegen paths

### WP2: Remote lookup path
- implement optional remote search phase
- tests with mocked `MlflowClient` pagination/failures

### WP3: Diagnostics hardening
- explicit reason-code taxonomy for degraded enrichment
- docs + JSON examples

## Acceptance criteria

- local replay/explain unchanged as execution truth
- no explain failures caused by MLflow unavailability
- remote lookup opt-in only
- deterministic diagnostics for CI/operator parsing
- no boundary invariant violations

## Risks

- high-cardinality tags: mitigate with hash prefix + bounded keys
- remote listing cost: mitigate with tag-first narrowing + candidate caps
- accidental behavior drift: mitigate with contract tests + fixtures

## Open questions for DSPx domain expert

1. exact tag schema: minimal vs richer set?
2. remote lookup default: always off, or on for remote URI?
3. should `run explain` expose strict mode for enrichment confidence thresholds?
4. should receipt include explicit `mlflow_trace_id` hints when available?
