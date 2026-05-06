---
summary: "Adopt a dedicated shared Oracle coordinate backend target while preserving local SQLite defaults and non-authority boundaries."
read_when:
  - "You are implementing or reviewing a shared Oracle backend beyond local SQLite CoordinateIndex."
  - "You need the accepted boundary between DSPx Oracle, MLflow, DS1621 infra, AK, and governance."
  - "You are changing Oracle ingestion, CoordinateIndex storage, or generated-program activation evidence references."
system4d:
  container:
    boundary: "DSPx Oracle coordinate storage and shared behavioral evidence backend."
    edges:
      - "docs/rfc/RFC-DSPX-ORACLE-20260505-shared-coordinate-backend.md"
      - "docs/project/2026-05-05-review-shared-oracle-coordinate-backend.md"
      - "docs/ARCHITECTURE.md"
      - "docs/ORACLE_TIME_TRAVEL.md"
  compass:
    driver: "Make production Oracle useful as shared behavioral evidence without turning it into MLflow, promotion authority, or governance authority."
    outcome: "A dedicated shared Oracle coordinate backend target with explicit ingestion, local SQLite fallback/default, and hard non-authority membrane."
  engine:
    invariants:
      - "program-gen does not auto-index into Oracle."
      - "Local SQLite CoordinateIndex remains supported for offline development and tests."
      - "Shared Oracle storage is not the MLflow Postgres database/schema."
      - "Oracle reports/search/neighborhoods are evidence only, never promotion or production-activation authority."
      - "Secret values are never printed in JSON/logs/docs/receipts."
  fog:
    risks:
      - "A central Oracle UI or report can become de facto judging authority."
      - "A DS1621 pilot can blur DSPx schema ownership with infra runtime ownership."
      - "Embedding dimension/model drift can make shared vector records incompatible without explicit migration."
---

# ADR 20260505 — Shared Oracle Coordinate Backend

## Status

- accepted
- date: 2026-05-05
- owner: DSPx core
- reviewers: DSPx core reviewers, softwareco/infra DS1621 operator, AK/governance liaison
- AK decision: `#29 Adopt shared Oracle coordinate backend target architecture`
- related_docs:
  - `docs/rfc/RFC-DSPX-ORACLE-20260505-shared-coordinate-backend.md`
  - `docs/project/2026-05-05-review-shared-oracle-coordinate-backend.md`
  - `docs/ARCHITECTURE.md`
  - `docs/ORACLE_TIME_TRAVEL.md`
  - `docs/adr/20260322-synthesis-architecture-v7-v9.md`
  - `docs/adr/20260323-synthesis-evidence-retrieval-v1.md`
  - `~/ai-society/holdingco/governance-kernel/docs/core/definitions/generated-dspy-program-promotion-governance.md`
  - `~/ai-society/holdingco/governance-kernel/docs/core/definitions/transition-passports/generated-cognition-program-production-activation.md`
  - `~/ai-society/softwareco/infra/ds1621-admin/docs/project/ds1621-oracle-coordinate-backend-contract.md`
  - `~/ai-society/softwareco/infra/ds1621-admin/contracts/ds1621-oracle-coordinate-backend.env`

## Executive summary

DSPx will target a dedicated shared Oracle coordinate backend for production behavioral evidence while preserving the current local SQLite `CoordinateIndex` as the default developer/offline store. The shared backend should be a separately owned Oracle substrate, likely Postgres + pgvector or equivalent, not the DS1621 MLflow Postgres database/schema. Oracle remains empirical evidence and interpretation only; it must not become promotion, deployment, AK, or governance authority.

## Context

DSPx Oracle already supports local behavior-intelligence surfaces:

- generated programs can emit `oracle_evidence.json` with `program-oracle-evidence-v1` records;
- explicit `dspx oracle index --from-program-evidence` can ingest those records into a local SQLite `CoordinateIndex`;
- `dspx oracle program-evidence report` can summarize indexed behavior evidence;
- receipt-backed Oracle time-travel commands can inspect local behavioral branch/diff/bisect history.

Separately, DS1621 now hosts the shared MLflow service for DSPx at `http://ds1621:50000`, backed by Postgres for MLflow metadata and MinIO for MLflow artifacts. That service solved MLflow tracking/storage, not Oracle coordinate storage.

A Pi session captured the missing production Oracle architecture: Oracle should become a shared, governed behavioral evidence service with explicit ingestion, shared coordinate search/report APIs, and UI/CLI analysis, while never becoming an approval engine. The RFC promoted that session-only reasoning into repo workflow and the review memo found it ready for ADR.

## Problem statement

Local SQLite Oracle indexes are correct for replayability and alpha development, but they are not enough for production-generated cognition programs. Production workflows need:

- shared durable behavior memory;
- cross-program similarity and failure-mode retrieval;
- longitudinal drift/territory/frontier analysis;
- operator-visible reports and possibly UI;
- evidence references that can feed generated cognition-program activation packets.

At the same time, a central Oracle backend creates authority risk. Semantic neighborhoods and repeated failures are empirical evidence, not permission to promote, deploy, block production, or mutate canonical authority.

## Decision drivers

- Preserve local-first replay and offline development.
- Avoid coupling Oracle lifecycle to MLflow storage.
- Make production Oracle useful for shared evidence retrieval and interpretation.
- Keep ingestion explicit and auditable.
- Keep secrets out of docs, logs, JSON, and receipts.
- Preserve governance-kernel / owning-domain authority over production activation.
- Assign DS1621 service deployment/runbook/backup work to infra, not DSPx core.

## Decision

Adopt Option C from the RFC as the target architecture:

> DSPx Oracle should gain a dedicated shared coordinate backend, separate from MLflow, with local SQLite remaining the default and Postgres + pgvector or equivalent available only through explicit opt-in implementation.

The accepted target includes:

1. a `CoordinateStore` abstraction before adding shared storage;
2. a current/local `sqlite` backend that preserves existing `CoordinateIndex` behavior;
3. a future `postgres_pgvector` or equivalent backend behind explicit configuration;
4. explicit ingestion of declared Oracle evidence records;
5. idempotent writes keyed by stable record/source identity;
6. store health/status diagnostics that do not leak secrets;
7. query/report surfaces for search, neighborhoods, drift, territory/frontiers/attractors, and generated-program activation evidence;
8. hard non-authority checks and labels.

This ADR does **not** approve immediate Postgres implementation or DS1621 deployment. Those require scoped follow-up tasks, validation, and infra-owned runbooks.

## Alternatives considered

### Option A — Stay local SQLite only

Rejected as the long-term production target. It is safe and replayable, but it does not provide shared behavior memory, team visibility, or durable cross-program retrieval.

### Option B — Reuse MLflow Postgres as Oracle storage

Rejected. It would blur MLflow and Oracle ownership, couple service lifecycles, complicate rollback/retention, and make it easier for observability state and behavioral interpretation to collapse into one unclear authority surface.

### Option C — Dedicated shared Oracle backend

Accepted. It creates a clean service/storage boundary for Oracle while preserving local SQLite defaults and non-authority semantics.

## Consequences

Positive:

- DSPx has a clear production Oracle target instead of session-only architecture notes.
- MLflow and Oracle storage responsibilities are separated.
- The current `dspx oracle backend-status` truth remains valid until implementation changes it.
- Future implementation can proceed in phases without breaking local tests or offline workflows.
- Generated cognition-program activation packets can eventually cite shared Oracle reports as evidence without treating Oracle as judge.

Costs / tradeoffs:

- A shared backend adds service, migration, backup, and retention work.
- A `CoordinateStore` abstraction must be introduced before Postgres work.
- DS1621 pilot deployment, if selected, requires infra-owned contracts and rollback docs.
- Embedding model/dimension choices become production schema concerns.
- UI/report wording must be reviewed to avoid implied approval semantics.

Risks:

- Centralized Oracle reports could become de facto promotion authority.
- Direct Postgres access could leak secrets if diagnostics are careless.
- Reusing MLflow infrastructure by convenience could blur owner boundaries.
- Vector index growth could pressure DS1621 storage/resources.
- Schema/version drift could strand old records without migration planning.

## Follow-through obligations

Before any shared backend implementation:

1. scope a Phase 1 task for `CoordinateStore` abstraction with no behavior change;
2. keep SQLite defaults and existing Oracle CLI compatibility;
3. add store contract tests shared by SQLite and future backends;
4. preserve `program-gen` no-auto-index behavior;
5. keep `dspx oracle backend-status --json` truthful.

Before any Postgres/pgvector implementation:

1. prove secret redaction in tests;
2. fail closed on missing/unreachable backend;
3. validate non-authority flags before ingest;
4. decide embedding backend/dimension/version policy;
5. document migration/versioning behavior.

Before any DS1621 pilot:

1. create an infra-owned service contract/runbook in `softwareco/infra/ds1621-admin` — initial contract-only target published at `~/ai-society/softwareco/infra/ds1621-admin/docs/project/ds1621-oracle-coordinate-backend-contract.md`;
2. define health checks, backup/restore, retention, rollback, and operator diagnostics;
3. keep the Oracle service separate from the MLflow database/schema;
4. run a non-secret generated-program ingest/report smoke.

Before activation-packet integration:

1. allow shared Oracle report references only as evidence;
2. keep activation blocked unless owning-domain/governing-body decision and canonical binding requirements are satisfied;
3. ensure UI/CLI labels say Oracle is interpretation only, not authority.

## Validation expectations

For this ADR recording:

- docs strict validation;
- task-scope validation;
- `git diff --check`;
- `just verify-fast`.

For implementation tasks:

- targeted store/CLI tests for touched code;
- existing Oracle program-evidence tests under SQLite;
- docs strict;
- `just verify-fast` at minimum;
- broader validation if `CoordinateIndex`, embeddings, CLI dispatch, or generated-program evidence contracts change.

## Current implementation status

Accepted architecture with the local storage seam and explicit Postgres/pgvector adapter scaffold landed. DS1621 has an infra-owned contract-only pilot target, but no live shared Oracle service is provisioned.

Current truth remains:

```text
DSPx Oracle storage: local SQLite CoordinateStore/CoordinateIndex by default
DSPx Postgres/pgvector adapter: scaffolded behind explicit opt-in
DS1621 MLflow Postgres: MLflow metadata only
DS1621 Oracle pilot contract: published, contract_only_not_deployed
Shared Oracle service: not live / not production-ready
```
