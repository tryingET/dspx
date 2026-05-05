---
summary: "Draft RFC for a shared, governed Oracle coordinate backend for DSPx behavioral evidence."
read_when:
  - "You are designing or implementing a shared Oracle backend beyond local SQLite CoordinateIndex."
  - "You need the authority boundary between DSPx Oracle evidence, DS1621 infrastructure, MLflow, AK, and governance."
  - "You are reconciling session-captured Oracle/Postgres architecture discussion with checked-in DSPx workflow."
type: "rfc"
---

# RFC: Shared Oracle Coordinate Backend

## 0) Metadata

- RFC ID: `RFC-DSPX-ORACLE-20260505-shared-coordinate-backend`
- Status: `draft`
- Owner: `DSPx core`
- Reviewers: `DSPx core reviewers`, `softwareco/infra DS1621 operator`, `AK/governance liaison`
- Created: `2026-05-05`
- Target milestone: `generated-program production-readiness follow-up`
- Related docs:
  - `docs/ARCHITECTURE.md`
  - `docs/ORACLE_TIME_TRAVEL.md`
  - `docs/adr/20260322-synthesis-architecture-v7-v9.md`
  - `docs/adr/20260323-synthesis-evidence-retrieval-v1.md`
  - `docs/rfc/RFC-DSPX-OBS-20260504-mlflow-local-sqlite-backend.md`
  - `docs/MLFLOW_OBSERVABILITY_PLAN.md`
  - `~/ai-society/holdingco/governance-kernel/docs/core/definitions/generated-dspy-program-promotion-governance.md`
  - `~/ai-society/holdingco/governance-kernel/docs/core/definitions/transition-passports/generated-cognition-program-production-activation.md`
  - `~/ai-society/softwareco/infra/ds1621-admin/README.md`
  - `~/ai-society/softwareco/infra/ds1621-admin/diary/2026-05-05--ops-ds1621-mlflow-postgres-minio-cutover.md`

## 1) Problem statement

DSPx Oracle currently has useful local behavior-intelligence surfaces:

- `program-gen` emits `oracle_evidence.json` when example-backed behavior evidence exists.
- `dspx oracle index --from-program-evidence` ingests those artifacts into a local SQLite `CoordinateIndex`.
- `dspx oracle program-evidence report` summarizes indexed program behavior evidence.
- receipt-backed Oracle time-travel commands inspect branch/diff/bisect history from local run metadata.

This is correct for alpha/local replayability, but it does not satisfy the production architecture discussed in session: a shared, inspectable, durable Oracle evidence substrate for generated DSPy/cognition programs.

The current gap is not MLflow. DS1621 MLflow now has Postgres + MinIO for tracking metadata/artifacts, but that is not an Oracle coordinate store. Oracle needs its own shared backend contract if it is to support team workflows, longitudinal behavior history, cross-program similarity, drift/territory analysis, and generated-program activation evidence packets.

## 2) Source of this RFC

This RFC promotes session-captured architecture into a checked-in workflow artifact.

Observed session source, inspected with the `pi-session-jsonl` skill and `jq` only:

- session JSONL: `~/.pi/agent/sessions/--home-tryinget-ai-society-softwareco-owned-dspx--/2026-05-04T02-01-00-544Z_3a398eb6-68f8-4571-86f8-ffdee6307e3b.jsonl`
- relevant assistant message timestamp: `2026-05-05T17:37:00.456Z`
- session question: `What would a production-grade Oracle setup look like for generated DSPy programs, without corrupting the current DSPx authority boundary?`
- distilled conclusion from that session: production Oracle should be a **shared, governed behavioral evidence service**, not an MLflow replacement and not a promotion engine.

Pi session JSONL is historical capture, not canonical repo authority. This RFC is the deliberate propagation step.

## 3) Scope / non-goals

### In scope

- Shared Oracle coordinate backend architecture for DSPx behavioral evidence.
- A storage abstraction that preserves local SQLite as the default while allowing a Postgres + pgvector production backend.
- Explicit ingestion of `program-oracle-evidence-v1` and receipt-derived Oracle records.
- Query/report/search/territory/drift surfaces over a shared backend.
- Operational and authority boundaries for a DS1621 pilot deployment.
- Non-authority contract checks that prevent Oracle from becoming promotion or production-activation authority.

### Out of scope

- Replacing MLflow tracking or artifact storage.
- Migrating historical local SQLite CoordinateIndexes automatically.
- Making `program-gen` auto-index into any shared service.
- Making Oracle select winners, approve promotion, block deployment, mutate AK, mutate governance, or activate production.
- Implementing the DS1621 Docker stack in this RFC.
- Defining the final governance transition judge; that lives in the governance-kernel production-activation passport.

### Invariants (must not break)

- `program-gen` materialization remains local/replayable and does not require Oracle availability.
- Oracle ingestion remains explicit.
- Local SQLite CoordinateIndex remains supported for offline development and tests.
- Shared Oracle records preserve source artifact hashes and non-authority flags.
- Oracle output is evidence/interpretation only; owning domain/governing body decides activation.
- No secrets in git, logs, packets, or RFC examples.

## 4) Current state evidence

### Implemented today

- `dspx.coordinates.storage.CoordinateIndex` is SQLite-backed.
- Default local index path is `generated/oracle/coordinates.db`, or `DSPX_ORACLE_INDEX_PATH` when set.
- `dspx oracle backend-status --json` reports the current backend truth without creating indexes or exposing secret values.
- Generated-program activation packets can include Oracle reports as evidence, while staying blocked until governance/authority requirements are met.

### Operational context

- DS1621 MLflow service exists at `http://ds1621:50000`.
- DS1621 MLflow uses Postgres for MLflow metadata and MinIO for MLflow artifacts.
- That Postgres instance is not currently an Oracle store.

### Session-captured target shape

The production shape discussed in session was:

```text
generated DSPy program
  -> manifest.json / manifest.json.meta.json
  -> behavior_results.json / behavior_episode.json
  -> oracle_evidence.json
  -> explicit ingestion job
  -> shared Oracle CoordinateIndex
  -> report/search/territory/drift APIs
  -> UI / CLI analysis
  -> optional AK/decision handoff, never automatic authority
```

## 5) Option analysis

### Option A: Stay local SQLite only

- Design: keep current SQLite `CoordinateIndex`; only improve local docs/status commands.
- Pros:
  - minimal risk;
  - strongest local replayability;
  - no service operations burden.
- Cons:
  - no shared behavior memory;
  - poor team workflow;
  - weak longitudinal/cross-program analysis;
  - cannot serve as a production evidence substrate.
- Risks:
  - users invent ad-hoc shared indexes or copy SQLite files around.

### Option B: Reuse MLflow Postgres as Oracle storage

- Design: store Oracle coordinates in the DS1621 MLflow Postgres database/schema.
- Pros:
  - fewer containers;
  - shares existing DS1621 database operations.
- Cons:
  - couples Oracle lifecycle to MLflow;
  - muddles ownership and backup/retention semantics;
  - increases blast radius of MLflow upgrades;
  - risks treating MLflow as Oracle authority or vice versa.
- Risks:
  - schema collisions, accidental secret exposure, hard rollback.

### Option C: Dedicated shared Oracle backend with Postgres + pgvector

- Design: add an Oracle store backend separate from MLflow, backed by Postgres + pgvector or equivalent vector storage, with explicit ingestion and read/query APIs.
- Pros:
  - production-grade durability and queryability;
  - clear ownership boundary from MLflow;
  - compatible with local SQLite default;
  - supports semantic neighborhoods, drift, attractors, frontiers, and cross-program retrieval.
- Cons:
  - new service/ops burden;
  - requires storage abstraction and migrations;
  - requires careful authority membrane labels and checks.
- Risks:
  - central Oracle interpretation becomes de facto promotion pressure unless contracts fail closed.

## 6) Decision

- Chosen option: `C` as the target architecture.
- Current implementation status: `not implemented`; this RFC defines the workflow target.
- Rationale:
  - Oracle is not MLflow: it is a behavioral coordinate/evidence substrate.
  - Local SQLite remains correct for developer/offline replay, but production use needs shared durable coordinates.
  - A dedicated backend gives production usefulness without collapsing observability, evidence, and authority.
- Rejected alternatives:
  - `A` is insufficient for production collaboration and longitudinal behavior analysis.
  - `B` is too entangled with MLflow operational semantics and ownership.

## 7) Target architecture

### 7.1 Component boundaries

| Component | Owns | Must not own |
|---|---|---|
| DSPx | evidence emission, ingestion CLI/API client, CoordinateStore abstraction, reports/search over Oracle records | production deployment authority, AK/governance mutation by default |
| Oracle backend | durable behavioral coordinate records, vector search, metadata filters, report/read APIs | promotion, winner selection, deployment, governance decisions |
| MLflow | run tracking, metrics, artifacts, UI links | Oracle coordinates or semantic authority |
| DS1621 infra | optional pilot service deployment, backups, health, Docker/Compose/runtime ops | DSPx schema semantics or governance decisions |
| AK/current authority | canonical task/evidence/decision binding when explicitly invoked | empirical similarity computation |
| governance-kernel | production-activation transition semantics | local DSPx evidence production |

### 7.2 Storage contract

Introduce a `CoordinateStore` boundary before adding shared storage:

```text
CoordinateStore
  upsert(ExecutionEmbedding) -> StoreWriteResult
  search(query/vector, filters, limit) -> list[SearchResult]
  records(filters, limit/cursor) -> list[CoordinateRecord]
  stats() -> StoreStats
  health() -> StoreHealth
```

Backends:

- `sqlite`: current local `CoordinateIndex`, default.
- `postgres_pgvector`: proposed production backend, explicit opt-in.

Configuration shape, with secret values never logged:

```text
DSPX_ORACLE_STORE=sqlite|postgres_pgvector
DSPX_ORACLE_INDEX_PATH=generated/oracle/coordinates.db        # sqlite only
DSPX_ORACLE_DATABASE_URL=op://... or env-injected secret ref   # postgres only
DSPX_ORACLE_SCHEMA=dspx_oracle
DSPX_ORACLE_REQUIRE_NON_AUTHORITY=true
```

### 7.3 Minimal Postgres + pgvector schema

Logical tables:

- `oracle_records`
  - `run_id text primary key`
  - `run_kind text not null`
  - `provider text not null`
  - `template_version text`
  - `embedding_version integer not null`
  - `dimension integer not null`
  - `vector vector(<dimension>) not null`
  - `input_text text`
  - `output_text text`
  - `config_text text`
  - `source_path text`
  - `source_artifact_hash text`
  - `metadata jsonb not null`
  - `non_authority jsonb not null`
  - `created_at timestamptz`
  - `indexed_at timestamptz not null`

- `oracle_ingest_receipts`
  - `ingest_id text primary key`
  - `source_kind text not null`
  - `source_root text`
  - `record_count integer not null`
  - `error_count integer not null`
  - `input_hash text`
  - `created_at timestamptz not null`
  - `effects jsonb not null`

- `oracle_store_meta`
  - `key text primary key`
  - `value text not null`

Required indexes:

- vector similarity index, tuned after dimension is fixed;
- btree indexes for `run_kind`, `provider`, `template_version`, `created_at`, `indexed_at`;
- jsonb GIN index over selected metadata facets if query pressure justifies it.

### 7.4 Ingestion contract

Ingestion remains explicit:

```bash
just dspx oracle index \
  --from-program-evidence \
  --path generated/programs \
  --store postgres_pgvector \
  --json
```

The CLI shape above is illustrative; implementation may choose environment-only backend selection if that preserves safer secret handling.

The ingestion path must validate:

- schema is recognized, e.g. `program-oracle-evidence-v1`;
- record has stable identity: receipt bundle, episode, candidate, assembly where available;
- source artifact hash is computed and recorded;
- non-authority flags are explicitly false for ranking/pruning/promotion/governance/external mutation;
- duplicate upserts are idempotent by `run_id` + source hash;
- no source artifacts, generated programs, AK, governance, MLflow, or production deployments are mutated.

### 7.5 Query/report surfaces

Production Oracle should expose:

- similar program/candidate search by intent, IO facets, failures, and behavior text;
- program-family neighborhoods;
- drift across candidate versions or time windows;
- territory/frontier/attractor reports;
- failure-mode retrieval for generated cognition-program activation packets;
- MLflow run-family links by stored metadata only, never as source of Oracle authority.

### 7.6 UI/operator surface

A future UI may show:

- program family page;
- MLflow run links: `program-gen`, `program-runtime`, `program-eval`;
- Oracle neighborhood;
- behavior status distribution;
- failure signals;
- similar assemblies;
- suggested next questions.

Mandatory labels:

- `Oracle interpretation only`
- `Not ranking authority`
- `Not promotion authority`
- `Not governance authority`
- `Activation requires owning-domain/governing-body decision`

### 7.7 Authority membrane

Oracle may emit:

- reports;
- risk summaries;
- similar-candidate/neighborhood evidence;
- refinement suggestions;
- activation-packet evidence references.

Oracle may not:

- promote;
- select winners;
- mutate AK;
- mutate governance;
- deploy;
- block production by itself;
- mark activation packets approved.

## 8) Rollout plan

### Phase 0 — RFC and workflow alignment

- implementation:
  - land this RFC as `draft`;
  - keep `dspx oracle backend-status` truthful: local SQLite only until implementation lands.
- tests:
  - docs strict;
  - task-scope check.
- exit gate:
  - reviewers agree whether DS1621 is the pilot host.

### Phase 1 — Store abstraction without behavior change

- implementation:
  - introduce `CoordinateStore` interface;
  - adapt current SQLite `CoordinateIndex` behind it;
  - preserve current CLI defaults and JSON output compatibility.
- tests:
  - contract tests shared across stores;
  - existing Oracle tests unchanged under sqlite.
- exit gate:
  - no default Postgres connection attempts;
  - local tests do not require services.

### Phase 2 — Postgres + pgvector backend behind explicit opt-in

- implementation:
  - add Postgres store adapter;
  - add migrations/schema management;
  - add idempotent upsert and health/status checks;
  - keep secret values out of JSON/log output.
- tests:
  - unit tests for SQL generation/config redaction;
  - optional integration test behind explicit env/service flag;
  - fail-closed tests for missing pgvector/migrations.
- exit gate:
  - `DSPX_ORACLE_STORE=postgres_pgvector` is explicit;
  - unset config uses sqlite or reports missing config without side effects.

### Phase 3 — DS1621 pilot service

- implementation:
  - infra-owned DS1621 Compose/runbook, separate from MLflow stack;
  - backups, health endpoint, retention policy;
  - machine-readable service contract in `softwareco/infra/ds1621-admin`.
- tests:
  - health checks from workstation;
  - ingest/report smoke using non-secret generated fixture;
  - rollback check to local sqlite mode.
- exit gate:
  - DS1621 infra diary/runbook committed by infra owner;
  - DSPx docs link the service contract without copying secrets.

### Phase 4 — Shared reports/API/UI and activation-packet integration

- implementation:
  - report/search API;
  - optional UI page;
  - activation packet can cite shared Oracle report IDs in addition to local file paths.
- tests:
  - API contract tests;
  - activation-packet evidence reference tests;
  - non-authority contract tests.
- exit gate:
  - generated cognition-program production-activation remains blocked unless governance/authority fields are satisfied.

## 9) Compatibility and migration

- Existing local SQLite indexes remain valid.
- No automatic migration from SQLite to Postgres in the first implementation.
- If migration is later needed, it must be an explicit export/import command with receipts and source-hash checks.
- Historical local `coordinates.db` files remain developer artifacts, not canonical production state.
- `backend-status` should evolve from `local_sqlite_only` to report configured/available stores without making network connections unless explicitly requested.

## 10) Validation plan

Required before accepting this RFC:

- `node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict`
- `just task-scope-check`
- `just verify-fast`

Required before implementing Phase 2:

- SQLite store contract tests pass unchanged.
- Postgres adapter tests prove secret redaction.
- Postgres missing/unreachable cases degrade without creating local fallback authority.
- Non-authority validation rejects malformed or authority-claiming evidence.

Required before DS1621 pilot:

- Infra runbook validation in `softwareco/infra/ds1621-admin`.
- Health check proof.
- Backup/restore posture documented.
- Rollback to local SQLite documented.

## 11) Operational impact

Expected costs:

- persistent Postgres storage for embeddings and metadata;
- vector index maintenance;
- DS1621 backup/monitoring burden;
- possible dimensionality migration if embedding model changes.

Failure/degraded modes:

- shared store unreachable: local program-gen still succeeds; ingestion fails/degrades with receipt;
- pgvector missing: backend health fails closed;
- schema mismatch: migration required, no silent writes;
- duplicate source: idempotent upsert or conflict report;
- authority-claiming evidence: reject ingestion.

Operator diagnostics:

1. `just dspx oracle backend-status --json`
2. store health endpoint / CLI health command once implemented
3. DS1621 service health/runbook
4. ingest receipt error details
5. non-authority validation results

## 12) Risk register

| Risk | Trigger | Mitigation | Rollback |
|---|---|---|---|
| Oracle becomes de facto judge | UI/report wording says or implies approval | mandatory non-authority labels and activation-packet blockers | remove shared report from activation packet until labels/checks fixed |
| MLflow/Oracle ownership blur | Oracle records stored in MLflow DB/schema | dedicated Oracle DB/schema/service; explicit docs | return to local SQLite; remove shared config |
| Secret leakage | database URL printed in JSON/logs | key-only reporting, redaction tests | disable Postgres backend and rotate secret if needed |
| Service dependency breaks local flows | program-gen or tests require shared Oracle | explicit ingestion only, local SQLite default | unset `DSPX_ORACLE_STORE`, use sqlite |
| Embedding dimension drift | embedding backend changes dimension | store embedding version/dimension, migration policy | new index namespace/schema version |
| DS1621 resource pressure | vector index grows unexpectedly | retention policy, quotas, monitoring | pause ingest, prune/rebuild from source evidence |

## 13) Cross-team dependencies

- DSPx:
  - owns evidence contracts, CLI, local/default behavior, and store abstraction.
- softwareco/infra/ds1621-admin:
  - owns any DS1621 service deployment/runbook/backup contract.
- governance-kernel:
  - owns production-activation transition semantics.
- Agent Kernel:
  - owns canonical task/evidence/decision binding when explicitly invoked by a future adapter.
- Pi/orchestrator:
  - may later orchestrate ingestion/report/activation workflows, but remains conductor, not judge.

## 14) Open questions / decisions needed

1. Should the first shared backend be DS1621-hosted Postgres + pgvector, or should DS1621 remain MLflow-only while Oracle pilots on the workstation?
2. Should DSPx expose direct Postgres access, or only an Oracle HTTP API once the shared backend exists?
3. What embedding backend/dimension should be frozen for production records?
4. What retention policy applies to generated-program Oracle records?
5. Should activation packets cite shared Oracle report IDs, local report JSON paths, or both during the pilot?
6. Which owner reviews non-authority labels in the future UI?

## 15) Execution checklist

- [ ] RFC reviewed by DSPx core.
- [ ] Infra owner confirms or rejects DS1621 as pilot host.
- [ ] Store abstraction task scoped.
- [ ] Postgres + pgvector adapter task scoped.
- [ ] DS1621 service contract task scoped in infra repo if selected.
- [ ] Non-authority tests added before any shared ingest path can land.
- [ ] README/backend-status updated when implementation state changes.
