---
summary: "Post-ADR implementation plan for the shared Oracle coordinate backend, starting with a no-behavior-change CoordinateStore abstraction."
read_when:
  - "You are implementing ADR 20260505 shared Oracle coordinate backend."
  - "You need the legal first implementation slice after AK decision #29."
---

# Implementation plan — Shared Oracle coordinate backend

- Date: 2026-05-05
- Decision: `#29 Adopt shared Oracle coordinate backend target architecture`
- ADR: `docs/adr/20260505-shared-oracle-coordinate-backend.md`
- RFC: `docs/rfc/RFC-DSPX-ORACLE-20260505-shared-coordinate-backend.md`

## Implementation posture

Proceed in phases. Do not jump directly to DS1621 Postgres/pgvector deployment.

The first implementation slice must preserve behavior and only create the seam needed for future storage backends.

## Phase 1 — CoordinateStore abstraction, no behavior change

Goal: make storage backend pluggable while preserving current SQLite behavior.

Scope:

- introduce a `CoordinateStore` protocol/interface around current `CoordinateIndex` operations;
- adapt SQLite `CoordinateIndex` behind that interface;
- preserve current CLI defaults and JSON outputs;
- keep `program-gen` no-auto-index behavior;
- keep local tests service-free.

Required tests:

- existing Oracle coordinate/index/search/report tests still pass under SQLite;
- new contract tests exercise upsert/search/records/stats/health through the abstraction;
- `backend-status` still reports local SQLite truth when no shared backend exists.

Exit gate:

- no Postgres dependencies are required;
- no network/database connection is attempted by default;
- no generated program artifacts, AK, governance, MLflow, or Oracle indexes are mutated by status/report checks.

## Phase 2 — Postgres + pgvector adapter behind explicit opt-in

Goal: add the shared backend adapter without changing defaults.

Scope:

- add `postgres_pgvector` store adapter;
- add schema/migration management;
- add idempotent upsert semantics;
- add health/status checks;
- add secret redaction in all diagnostics.

Required tests:

- unit tests for config parsing and redaction;
- SQL/schema-generation tests where possible without a live DB;
- optional integration tests gated behind explicit environment/service flags;
- fail-closed tests for missing pgvector, schema mismatch, unreachable DB, and malformed authority-claiming evidence.

Exit gate:

- `DSPX_ORACLE_STORE=postgres_pgvector` or equivalent explicit opt-in is required;
- unset or incomplete config does not silently fall back to a shared backend;
- secret values never appear in JSON/log output.

## Current implementation status

- Phase 1 SQLite `CoordinateStore` boundary: landed.
- Phase 2 Postgres/pgvector adapter: scaffolded behind explicit opt-in.
- Phase 2 optional driver strategy: `dspx-core[oracle-postgres]` installs `psycopg[binary]` for explicit live use.
- Phase 2 live-gated integration smoke: added and skipped by default unless `DSPX_ORACLE_LIVE_POSTGRES=1` plus a database URL are present.
- Phase 3 DS1621 pilot: provisioned on DS1621 with 1Password-backed password, pgvector health passed, DSPx live smoke passed, first disposable restore proof passed, 14-day retention/quota helpers exist, latest dump is exported to operator-confirmed `DspxOracleBackups` Hyper Backup share, and scheduled infra monitoring with ntfy failure-alert path is installed and verified.
- Shared Oracle service: live pilot only; not production-ready until Hyper Backup remote-run evidence, exercised password rotation, and authority-label gates are done.

## Phase 3 — DS1621 pilot service, infra-owned

Goal: run a pilot shared Oracle backend only after infra contract exists.

Scope owned by `softwareco/infra/ds1621-admin`:

- Compose/runbook/service contract — contract-only target now published at `~/ai-society/softwareco/infra/ds1621-admin/docs/project/ds1621-oracle-coordinate-backend-contract.md`;
- health checks;
- backup/restore posture;
- retention/quota policy;
- rollback to local SQLite.

DSPx scope:

- link to infra service contract;
- provide non-secret smoke ingest/report command;
- keep CLI/API client behavior explicit and fail-closed.

Exit gate:

- DS1621 service contract committed in infra repo;
- backend status links the contract without implying a live service;
- non-secret generated-program ingest/report smoke passes;
- service rollback documented.

## Phase 4 — Shared reports/API/UI and activation-packet evidence refs

Goal: make shared Oracle useful to generated cognition-program activation without granting authority.

Scope:

- report/search API or CLI surface;
- optional UI page;
- activation packet may cite shared Oracle report IDs in addition to local report JSON paths.

Required tests:

- report/search contract tests;
- activation packet evidence-reference tests;
- UI/API label checks if UI exists;
- non-authority checks proving Oracle cannot approve, promote, deploy, mutate AK, or mutate governance.

Exit gate:

- activation packets remain blocked unless owning-domain/governing-body decision and canonical binding requirements are satisfied.

## Next task to create

Recommended next AK task depends on owner:

```text
Provision DS1621 Oracle Postgres/pgvector pilot stack from the published contract
```

for `softwareco/infra/ds1621-admin`, or:

```text
Provision DS1621 Oracle Postgres/pgvector pilot stack and run live-gated DSPx smoke
```

across infra plus DSPx once operator-provided secrets are available.

Do not claim production readiness until both the infra service and DSPx live-gated smoke pass with redacted diagnostics.
